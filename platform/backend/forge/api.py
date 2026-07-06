"""Forge Platform API.

This is the BACKEND OF THE PLATFORM ITSELF (not the generated app).
Endpoints:
  GET  /api/catalog/kpis            — KPI catalog for the wizard's KPI step
  GET  /api/catalog/audiences       — Audience templates
  POST /api/manifests               — create/save a manifest
  GET  /api/manifests/{id}          — fetch a manifest
  POST /api/manifests/{id}/secrets  — store a secret (returns secret_ref)
  POST /api/builds                  — start a build for a manifest_id
  GET  /api/builds/{id}             — get build status (snapshot)
  WS   /ws/builds/{id}              — stream build progress
  POST /api/insights/preview        — preview proactive insights for given series
  POST /api/insights/simulate       — preview a what-if scenario
  POST /api/explain                 — "Explain this" for a number+provenance
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue, Empty
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from forge.config import (
    settings, configure_logging, utc_iso,
    is_safe_id, is_safe_manifest_id, is_safe_build_id, resolve_within,
)
from forge.manifest import Manifest
from forge.generator import Generator, BuildEvent
from forge.app_runner import runner as app_runner
from forge import app_probe
from forge.fabric import fabric
from forge.secret_manager import default_manager
from forge.intelligence.insights import (
    TimeSeriesPoint, Anomaly, detect_anomalies, compose_digest,
    SimulationScenario, simulate, NumberProvenance,
)


configure_logging()
log = logging.getLogger("forge.api")
MAX_SERIES = settings.max_series_points

ROOT = Path(__file__).resolve().parent.parent.parent  # platform/
CATALOGS = ROOT / "catalogs"
TEMPLATES = ROOT / "generator" / "templates"
GENERATED = ROOT.parent / "generated_apps"
GENERATED.mkdir(exist_ok=True)
MANIFEST_STORE = ROOT.parent / ".forge_manifests"
MANIFEST_STORE.mkdir(exist_ok=True)


app = FastAPI(title="Forge Platform API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    """When FORGE_API_KEY is configured, require it on every /api/* request.

    Leaves the wizard UI ('/'), static assets, '/health' and websockets open so
    health checks and the SPA shell still load. When no key is set the API is
    open (local-demo default)."""
    if settings.api_key and request.url.path.startswith("/api/"):
        provided = request.headers.get("x-api-key", "")
        if not provided:
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                provided = auth[7:].strip()
        if provided != settings.api_key:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


# ── Build registry: in-memory for the demo, would be Redis in prod ───
class BuildRegistry:
    def __init__(self):
        self._builds: dict[str, dict] = {}
        self._streams: dict[str, list[Queue]] = {}
        self._lock = threading.Lock()

    def create(self, manifest_id: str) -> str:
        bid = f"bld_{uuid4().hex[:10]}"
        with self._lock:
            self._evict_locked()
            self._builds[bid] = {
                "id": bid,
                "manifest_id": manifest_id,
                "status": "pending",
                "events": [],
                "started_at": utc_iso(),
                "finished_at": None,
                "output_path": None,
            }
            self._streams[bid] = []
        return bid

    def _evict_locked(self) -> None:
        """Drop oldest terminal builds once we exceed the retention cap.

        Bounds memory for a long-running process. Builds with active listeners
        or non-terminal status are never evicted. Caller must hold self._lock.
        """
        cap = settings.max_builds_in_memory
        if len(self._builds) < cap:
            return
        for bid, b in list(self._builds.items()):
            if len(self._builds) < cap:
                break
            if b["status"] in ("done", "error") and not self._streams.get(bid):
                self._builds.pop(bid, None)
                self._streams.pop(bid, None)

    def add_listener(self, bid: str) -> Queue:
        q = Queue()
        with self._lock:
            self._streams.setdefault(bid, []).append(q)
        return q

    def remove_listener(self, bid: str, q: Queue):
        with self._lock:
            if bid in self._streams and q in self._streams[bid]:
                self._streams[bid].remove(q)

    def emit(self, bid: str, event: BuildEvent):
        payload = {
            "step": event.step,
            "status": event.status,
            "message": event.message,
            "progress_pct": event.progress_pct,
            "ts": utc_iso(),
        }
        with self._lock:
            if bid in self._builds:
                self._builds[bid]["events"].append(payload)
                if event.step == "done":
                    self._builds[bid]["status"] = "done"
                    self._builds[bid]["finished_at"] = payload["ts"]
                elif event.status == "error":
                    self._builds[bid]["status"] = "error"
                    self._builds[bid]["finished_at"] = payload["ts"]
                else:
                    self._builds[bid]["status"] = "running"
            for q in self._streams.get(bid, []):
                q.put(payload)

    def set_output(self, bid: str, path: str):
        with self._lock:
            if bid in self._builds:
                self._builds[bid]["output_path"] = path

    def get(self, bid: str) -> dict | None:
        with self._lock:
            b = self._builds.get(bid)
            return dict(b) if b else None


registry = BuildRegistry()


# ── Catalog endpoints ────────────────────────────────────────────────

@app.get("/api/catalog/kpis")
def catalog_kpis():
    return json.loads((CATALOGS / "kpi_catalog.json").read_text(encoding="utf-8"))


@app.get("/api/catalog/audiences")
def catalog_audiences():
    return json.loads((CATALOGS / "audience_templates.json").read_text(encoding="utf-8"))


@app.get("/api/catalog/data_source_kinds")
def catalog_data_source_kinds():
    return [
        {"kind": "postgres",     "label": "PostgreSQL",   "auth": ["password", "iam_role"]},
        {"kind": "snowflake",    "label": "Snowflake",    "auth": ["password", "oauth2", "service_account"]},
        {"kind": "databricks",   "label": "Databricks",   "auth": ["api_key", "oauth2"]},
        {"kind": "bigquery",     "label": "BigQuery",     "auth": ["service_account"]},
        {"kind": "redshift",     "label": "Redshift",     "auth": ["password", "iam_role"]},
        {"kind": "mysql",        "label": "MySQL",        "auth": ["password"]},
        {"kind": "salesforce",   "label": "Salesforce",   "auth": ["oauth2"]},
        {"kind": "workday",      "label": "Workday",      "auth": ["oauth2"]},
        {"kind": "sap",          "label": "SAP",          "auth": ["password", "service_account"]},
        {"kind": "rest_api",     "label": "REST API",     "auth": ["api_key", "oauth2", "none"]},
        {"kind": "s3_bucket",    "label": "AWS S3",       "auth": ["iam_role", "api_key"]},
        {"kind": "kafka",        "label": "Kafka",        "auth": ["password", "service_account"]},
        {"kind": "xlsx_upload",  "label": "Excel Upload", "auth": ["none"]},
        {"kind": "csv_upload",   "label": "CSV Upload",   "auth": ["none"]},
    ]


# ── Manifest CRUD ────────────────────────────────────────────────────

class ManifestRequest(BaseModel):
    manifest: dict[str, Any]


def _manifest_path(mid: str) -> Path:
    """Validate a manifest id and resolve its file path inside the store.

    Rejects anything that isn't a well-formed manifest id, closing the
    path-traversal vector on the user-supplied {mid}."""
    if not is_safe_manifest_id(mid):
        raise HTTPException(400, "Invalid manifest id")
    return resolve_within(MANIFEST_STORE, f"{mid}.json")


@app.post("/api/manifests")
def save_manifest(body: ManifestRequest):
    m = Manifest(**body.manifest)
    if not is_safe_manifest_id(m.manifest_id):
        raise HTTPException(400, "Invalid manifest id")
    path = resolve_within(MANIFEST_STORE, f"{m.manifest_id}.json")
    path.write_text(m.model_dump_json(indent=2), encoding="utf-8")
    return {"manifest_id": m.manifest_id, "summary": m.summary()}


@app.get("/api/manifests/{mid}")
def get_manifest(mid: str):
    path = _manifest_path(mid)
    if not path.exists():
        raise HTTPException(404, "Manifest not found")
    return json.loads(path.read_text(encoding="utf-8"))


# ── Secrets (per-manifest namespace) ─────────────────────────────────

class StoreSecretRequest(BaseModel):
    name: str  # like "db_revenue", will become secret_ref secret://forge/<mid>/<name>
    value: str
    description: str = ""


@app.post("/api/manifests/{mid}/secrets")
def store_secret(mid: str, body: StoreSecretRequest):
    if not _manifest_path(mid).exists():
        raise HTTPException(404, "Manifest not found")
    if not is_safe_id(body.name):
        raise HTTPException(400, "Invalid secret name")
    ref = f"secret://forge/{mid}/{body.name}"
    rec = default_manager().store_secret(ref, body.value, body.description)
    return {"secret_ref": rec.ref, "created_at": rec.created_at}


@app.get("/api/manifests/{mid}/secrets")
def list_secrets(mid: str):
    if not is_safe_manifest_id(mid):
        raise HTTPException(400, "Invalid manifest id")
    prefix = f"secret://forge/{mid}/"
    return [
        {"ref": r.ref, "created_at": r.created_at, "last_accessed": r.last_accessed,
         "access_count": r.access_count, "description": r.description}
        for r in default_manager().list_refs() if r.ref.startswith(prefix)
    ]


# ── Build orchestration ──────────────────────────────────────────────

class StartBuildRequest(BaseModel):
    manifest_id: str


def _run_build(bid: str, manifest: Manifest):
    """Runs in a background thread."""
    def callback(ev: BuildEvent):
        registry.emit(bid, ev)
        log.info("[%s] %s - %s - %s%%", bid, ev.step, ev.status, ev.progress_pct)
    try:
        gen = Generator(manifest, GENERATED, TEMPLATES, on_progress=callback)
        out = gen.generate()
        registry.set_output(bid, str(out))
    except Exception:
        # Full detail goes to the server log; the client gets a generic message
        # so we don't leak internal paths/exception internals over the socket.
        log.exception("Build %s failed", bid)
        registry.emit(bid, BuildEvent(step="failed", status="error",
                                       message=f"Build failed - see server logs (build {bid}).",
                                       progress_pct=100))


@app.post("/api/builds")
def start_build(req: StartBuildRequest):
    path = _manifest_path(req.manifest_id)
    if not path.exists():
        raise HTTPException(404, "Manifest not found")
    manifest = Manifest(**json.loads(path.read_text(encoding="utf-8")))
    bid = registry.create(req.manifest_id)
    t = threading.Thread(target=_run_build, args=(bid, manifest), daemon=True)
    t.start()
    return {"build_id": bid, "status": "started"}


@app.get("/api/builds/{bid}")
def get_build(bid: str):
    b = registry.get(bid)
    if not b:
        raise HTTPException(404, "Build not found")
    return b


@app.websocket("/ws/builds/{bid}")
async def ws_build(websocket: WebSocket, bid: str):
    await websocket.accept()
    snapshot = registry.get(bid)
    if not snapshot:
        await websocket.send_json({"error": "build not found"})
        await websocket.close()
        return
    # Replay any events that already happened
    for ev in snapshot["events"]:
        await websocket.send_json(ev)
    if snapshot["status"] in ("done", "error"):
        await websocket.send_json({"final": True, "status": snapshot["status"],
                                    "output_path": snapshot.get("output_path")})
        await websocket.close()
        return

    q = registry.add_listener(bid)
    try:
        while True:
            try:
                ev = q.get(timeout=0.5)
                await websocket.send_json(ev)
                if ev.get("step") == "done" or ev.get("status") == "error":
                    final = registry.get(bid) or {}
                    await websocket.send_json({"final": True, "status": final.get("status"),
                                                "output_path": final.get("output_path")})
                    break
            except Empty:
                # heartbeat to keep the socket alive in some proxies
                await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    finally:
        registry.remove_listener(bid, q)
        try:
            await websocket.close()
        except Exception:
            pass


# ── Run a generated app natively (no Docker) ─────────────────────────
# Generated apps ship a docker-compose.yml, but many dev machines have no
# Docker daemon. Each app is a self-contained FastAPI backend + static
# frontend, so we launch them directly and hand back live URLs.

def _resolve_app_dir(app_id: str) -> Path:
    if not is_safe_id(app_id):
        raise HTTPException(400, "invalid app id")
    try:
        app_dir = resolve_within(GENERATED, app_id)
    except ValueError:
        raise HTTPException(400, "invalid app id")
    if not app_dir.is_dir():
        raise HTTPException(404, "generated app not found")
    return app_dir


@app.post("/api/apps/{app_id}/run")
def run_app(app_id: str):
    app_dir = _resolve_app_dir(app_id)
    try:
        return app_runner.run(app_id, app_dir)
    except (FileNotFoundError, RuntimeError) as e:
        log.warning("Run app %s failed: %s", app_id, e)
        raise HTTPException(422, str(e))


@app.post("/api/apps/{app_id}/stop")
def stop_app(app_id: str):
    if not is_safe_id(app_id):
        raise HTTPException(400, "invalid app id")
    return app_runner.stop(app_id)


@app.get("/api/apps/{app_id}/status")
def app_status(app_id: str):
    if not is_safe_id(app_id):
        raise HTTPException(400, "invalid app id")
    return app_runner.status(app_id)


@app.get("/api/apps/{app_id}/topology")
def app_topology(app_id: str):
    if not is_safe_id(app_id):
        raise HTTPException(400, "invalid app id")
    meta = app_runner.get_meta(app_id)
    if not meta:
        raise HTTPException(409, "app is not running")
    return app_probe.probe_topology(meta)


@app.post("/api/apps/{app_id}/verify")
def app_verify(app_id: str):
    if not is_safe_id(app_id):
        raise HTTPException(400, "invalid app id")
    meta = app_runner.get_meta(app_id)
    if not meta:
        raise HTTPException(409, "app is not running")
    return app_probe.run_verification(meta)


@app.on_event("startup")
def _reap_orphan_apps():
    # Clean up generated-app servers a previously force-killed Forge left behind.
    app_runner.reap_orphans()


# ── Multi-source data fabric (agentic DB router) ─────────────────────

class FabricAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@app.get("/api/fabric/sources")
def fabric_sources():
    return {"sources": fabric.list_sources()}


@app.post("/api/fabric/ask")
def fabric_ask(body: FabricAskRequest):
    return fabric.ask(body.question)


@app.on_event("shutdown")
def _stop_running_apps():
    app_runner.stop_all()


# ── Insights preview (used by wizard's preview step) ─────────────────

class SeriesPoint(BaseModel):
    timestamp: datetime
    value: float


class DigestPreviewRequest(BaseModel):
    kpi_name: str = "Revenue"
    higher_is_better: bool = True
    series: list[SeriesPoint] = Field(min_length=1, max_length=MAX_SERIES)
    audience: str = "CFO"


@app.post("/api/insights/preview")
def insights_preview(body: DigestPreviewRequest):
    pts = [TimeSeriesPoint(timestamp=p.timestamp, value=p.value) for p in body.series]
    anomalies = detect_anomalies(pts, kpi_id="preview", kpi_name=body.kpi_name,
                                  higher_is_better=body.higher_is_better)
    digest = compose_digest(audience=body.audience,
                             period_end=pts[-1].timestamp,
                             period_days=30, anomalies=anomalies)
    return {
        "anomalies": [a.__dict__ | {"timestamp": a.timestamp.isoformat(), "kind": a.kind.value}
                      for a in anomalies],
        "digest_markdown": digest.to_markdown(),
        "n_alerts": sum(1 for a in anomalies if a.is_alert_worthy),
    }


class SimulateRequest(BaseModel):
    series: list[SeriesPoint] = Field(min_length=1, max_length=MAX_SERIES)
    scenario_name: str
    description: str = ""
    parameter_changes: dict[str, float]


@app.post("/api/insights/simulate")
def insights_simulate(body: SimulateRequest):
    pts = [TimeSeriesPoint(timestamp=p.timestamp, value=p.value) for p in body.series]
    sc = SimulationScenario(name=body.scenario_name, description=body.description,
                             parameter_changes=body.parameter_changes)
    res = simulate(pts, sc)
    return {
        "scenario": sc.__dict__,
        "baseline": res.baseline_value,
        "projected": res.projected_value,
        "delta_abs": res.delta_abs,
        "delta_pct": res.delta_pct,
        "ci_low": res.confidence_band_low,
        "ci_high": res.confidence_band_high,
        "horizon": res.horizon,
        "explanation": res.explanation,
    }


class ExplainRequest(BaseModel):
    value: float
    kpi_id: str
    kpi_name: str
    formula: str
    filters: dict[str, str] = {}
    source_tables: list[str] = []
    rows_used: int = 0
    period: str | None = None


@app.post("/api/explain")
def explain(req: ExplainRequest):
    prov = NumberProvenance(**req.model_dump())
    return {"explanation": prov.explain()}


# ── ML endpoints (anomaly + forecast + drift) ────────────────────────
#
# These wrap forge_ml so the wizard, the customer apps, and any external
# caller can drive the ML pipeline through HTTP.

class _MLSeriesPoint(BaseModel):
    timestamp: str
    value: float


def _check_safe_id(v: str) -> str:
    if not is_safe_id(v):
        raise ValueError("must match [A-Za-z0-9_-] and be 1-64 chars")
    return v


def _check_artifact_dir(v: str) -> str:
    # Block traversal via the directory itself; filename components are
    # validated separately as safe ids, so the full path can't escape.
    if ".." in Path(v).parts:
        raise ValueError("artifact_dir must not contain '..'")
    return v


class TrainAnomalyRequest(BaseModel):
    customer_id: str
    kpi_id: str
    history: list[_MLSeriesPoint] = Field(min_length=10, max_length=MAX_SERIES)
    labels: list[int] | None = None  # optional anomaly labels (1=anom, 0=normal)
    artifact_dir: str = "/data/models"

    @field_validator("customer_id", "kpi_id")
    @classmethod
    def _validate_ids(cls, v: str) -> str:
        return _check_safe_id(v)

    @field_validator("artifact_dir")
    @classmethod
    def _validate_dir(cls, v: str) -> str:
        return _check_artifact_dir(v)


class TrainForecastRequest(BaseModel):
    customer_id: str
    kpi_id: str
    history: list[_MLSeriesPoint] = Field(min_length=10, max_length=MAX_SERIES)
    horizon: int = Field(default=30, ge=1, le=3650)
    n_folds: int = Field(default=3, ge=1, le=20)
    test_size: int = Field(default=14, ge=1, le=1000)
    candidate_models: list[str] | None = None
    artifact_dir: str = "/data/models"

    @field_validator("customer_id", "kpi_id")
    @classmethod
    def _validate_ids(cls, v: str) -> str:
        return _check_safe_id(v)

    @field_validator("artifact_dir")
    @classmethod
    def _validate_dir(cls, v: str) -> str:
        return _check_artifact_dir(v)


class ForecastNowRequest(BaseModel):
    history: list[_MLSeriesPoint] = Field(min_length=10, max_length=MAX_SERIES)
    horizon: int = Field(default=30, ge=1, le=3650)
    n_folds: int = Field(default=3, ge=1, le=20)
    test_size: int = Field(default=14, ge=1, le=1000)
    candidate_models: list[str] | None = None


class AnomalyScoreRequest(BaseModel):
    history: list[_MLSeriesPoint] = Field(min_length=1, max_length=MAX_SERIES)
    customer_id: str
    kpi_id: str
    artifact_dir: str = "/data/models"

    @field_validator("customer_id", "kpi_id")
    @classmethod
    def _validate_ids(cls, v: str) -> str:
        return _check_safe_id(v)

    @field_validator("artifact_dir")
    @classmethod
    def _validate_dir(cls, v: str) -> str:
        return _check_artifact_dir(v)


class DriftCheckRequest(BaseModel):
    reference: list[_MLSeriesPoint] = Field(min_length=2, max_length=MAX_SERIES)
    new: list[_MLSeriesPoint] = Field(min_length=2, max_length=MAX_SERIES)
    psi_minor: float = 0.1
    psi_major: float = 0.2


def _to_history_df(points):
    import pandas as pd
    return pd.DataFrame([{"timestamp": p.timestamp, "value": p.value} for p in points])


@app.post("/api/ml/train/anomaly")
def ml_train_anomaly(req: TrainAnomalyRequest):
    """Train + register an anomaly ensemble for one (customer, KPI)."""
    from forge_ml.orchestration.trainer import train_anomaly_detector
    import pandas as pd
    df = _to_history_df(req.history)
    labels = pd.Series(req.labels) if req.labels else None
    return train_anomaly_detector(req.customer_id, req.kpi_id, df,
                                    labels=labels, artifact_dir=req.artifact_dir)


@app.post("/api/ml/train/forecast")
def ml_train_forecast(req: TrainForecastRequest):
    """Train + register the winning forecast model for one (customer, KPI)."""
    from forge_ml.orchestration.trainer import train_forecaster
    df = _to_history_df(req.history)
    return train_forecaster(req.customer_id, req.kpi_id, df, horizon=req.horizon,
                              n_folds=req.n_folds, test_size=req.test_size,
                              candidate_models=req.candidate_models,
                              artifact_dir=req.artifact_dir)


@app.post("/api/ml/forecast")
def ml_forecast(req: ForecastNowRequest):
    """One-shot forecast — auto-select the best model and return predictions
    + 95% intervals + the backtest scoreboard. No training-side persistence.
    """
    from forge_ml.models.forecasting.ensemble import autoselect_and_forecast
    from dataclasses import asdict
    df = _to_history_df(req.history)
    result = autoselect_and_forecast(df, horizon=req.horizon,
                                       n_folds=req.n_folds, test_size=req.test_size,
                                       models=req.candidate_models)
    return {
        "winning_model": result.winning_model,
        "runner_up": result.runner_up_model,
        "selection_reason": result.selection_reason,
        "scoreboard": [asdict(s) for s in result.scoreboard],
        "forecast": [
            {"timestamp": str(t), "yhat": p, "lower95": lo, "upper95": hi}
            for t, p, lo, hi in zip(result.timestamps, result.point,
                                       result.lower95, result.upper95)
        ],
        "trained_on": result.trained_on,
        "horizon": result.horizon,
    }


@app.post("/api/ml/anomaly/score")
def ml_anomaly_score(req: AnomalyScoreRequest):
    """Load the registered anomaly bundle for (customer, KPI) and score
    the supplied history."""
    import joblib
    import pandas as pd
    from pathlib import Path
    from forge_ml.features.pipeline import FeaturePipeline

    bundle_path = Path(req.artifact_dir) / f"{req.customer_id}_{req.kpi_id}_anomaly.joblib"
    if not bundle_path.exists():
        raise HTTPException(404, f"No anomaly bundle for {req.customer_id}/{req.kpi_id}. "
                                  f"Train it first via /api/ml/train/anomaly.")
    bundle = joblib.load(bundle_path)
    ens = bundle["ensemble"]
    pipe = FeaturePipeline.from_dict(bundle["pipeline"])
    feats = pipe.transform(_to_history_df(req.history))
    detections = ens.predict(feats, value_column="value")
    return {
        "n_total": len(detections),
        "n_anomalies": sum(1 for d in detections if d.is_anomaly),
        "detections": [
            {"timestamp": str(d.timestamp), "value": d.value,
             "fused_score": d.fused_score, "is_anomaly": d.is_anomaly,
             "severity": d.severity, "detectors_flagging": d.detectors_flagging,
             "explanation": d.explanation}
            for d in detections if d.is_anomaly
        ],
    }


@app.post("/api/ml/drift/check")
def ml_drift_check(req: DriftCheckRequest):
    """Compare two windows and report PSI/KS-corroborated drift."""
    from forge_ml.drift.detector import compare, DriftConfig
    from forge_ml.features.pipeline import FeaturePipeline
    pipe = FeaturePipeline()
    ref_feats = pipe.fit_transform(_to_history_df(req.reference)).dropna()
    new_feats = pipe.transform(_to_history_df(req.new)).dropna()
    cfg = DriftConfig(psi_minor_threshold=req.psi_minor, psi_major_threshold=req.psi_major)
    report = compare(ref_feats, new_feats, config=cfg)
    return {
        "n_features_checked": report.n_features_checked,
        "should_retrain": report.should_retrain,
        "overall_severity": report.overall_severity.value,
        "summary": report.summary,
        "drifted_features": [
            {"feature": d.feature, "psi": d.psi, "ks_statistic": d.ks_statistic,
             "ks_pvalue": d.ks_pvalue, "severity": d.severity.value,
             "ref_mean": d.ref_summary["mean"], "new_mean": d.new_summary["mean"]}
            for d in report.drifted_features
        ],
    }


# ── Health ───────────────────────────────────────────────────────────

@app.get("/health")
def health():
    body = {
        "status": "ok",
        "service": "forge-platform",
        "now": utc_iso(),
    }
    # Internal absolute paths are an info-leak; only expose when explicitly opted in.
    if settings.health_verbose:
        body["templates_root"] = str(TEMPLATES)
        body["generated_root"] = str(GENERATED)
    return body


# ── Static frontend (the wizard UI) — mounted last so API wins ──────

WIZARD_DIR = ROOT / "frontend"
if WIZARD_DIR.exists() and (WIZARD_DIR / "index.html").exists():
    @app.get("/")
    def root():
        return FileResponse(WIZARD_DIR / "index.html")

    @app.get("/fabric")
    def fabric_page():
        return FileResponse(WIZARD_DIR / "fabric.html")

    app.mount("/static", StaticFiles(directory=str(WIZARD_DIR)), name="static")
