"""MLflow integration.

Two responsibilities:
  1. Experiment tracking — log every fit/backtest with metrics, params, artifacts.
  2. Model registry — register winning models, manage stage transitions
     (None → Staging → Production), and serve the production version for
     scheduled prediction.

Why we wrap MLflow instead of using it directly everywhere:
  - Callers (training DAG, drift DAG, API) need ONE consistent way to do this.
  - We can swap MLflow for SageMaker Model Registry / Vertex AI later if
    a customer requires it — same interface.
  - Forge's cross-cutting concerns (per-customer namespacing, audit log)
    happen here once.

Trusted OSS: mlflow. Gracefully degrades if MLflow isn't installed.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import warnings
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

try:
    import mlflow
    from mlflow.tracking import MlflowClient
    HAVE_MLFLOW = True
except ImportError:
    HAVE_MLFLOW = False
    log.warning("mlflow not installed — registry calls will be no-ops.")


@dataclass
class RegisteredModel:
    name: str
    version: str
    stage: str
    run_id: str
    metrics: dict[str, float]


def _tracking_uri() -> str:
    return os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")


def _experiment_name(customer_id: str, kind: str) -> str:
    """Customer-namespaced experiments: 'forge.<customer>.<kind>'.
    kind is e.g. 'forecast', 'anomaly', 'drift'."""
    return f"forge.{customer_id}.{kind}"


@contextmanager
def start_run(customer_id: str, kind: str, run_name: str,
                tags: Optional[dict] = None):
    """Context manager that wraps mlflow.start_run with our naming convention.
    If MLflow isn't reachable or no tracking URI is configured, becomes a
    no-op so dev/local runs don't break."""
    if not HAVE_MLFLOW:
        log.debug("MLflow not installed — skipping run %s", run_name)
        yield None
        return
    # Only attempt to track if explicitly configured.
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        log.debug("MLFLOW_TRACKING_URI not set — skipping tracking for run %s", run_name)
        yield None
        return
    try:
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(_experiment_name(customer_id, kind))
        with mlflow.start_run(run_name=run_name, tags=tags or {}) as run:
            yield run
    except Exception as e:
        log.warning("MLflow run failed (continuing without tracking): %s", e)
        yield None


def log_metrics(metrics: dict[str, float]):
    if not HAVE_MLFLOW:
        return
    try:
        for k, v in metrics.items():
            if v is not None and not (isinstance(v, float) and (v != v)):  # skip NaN
                mlflow.log_metric(k, float(v))
    except Exception as e:
        log.warning("log_metrics failed: %s", e)


def log_params(params: dict[str, Any]):
    if not HAVE_MLFLOW:
        return
    try:
        # MLflow params are strings ≤ 500 chars
        flat = {k: str(v)[:500] for k, v in params.items()}
        mlflow.log_params(flat)
    except Exception as e:
        log.warning("log_params failed: %s", e)


def log_artifact_dict(name: str, payload: dict):
    """Serialize a dict as JSON and log it as an artifact."""
    if not HAVE_MLFLOW:
        return
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(payload, f, indent=2, default=str)
            fpath = f.name
        mlflow.log_artifact(fpath, artifact_path=name)
        os.unlink(fpath)
    except Exception as e:
        log.warning("log_artifact_dict failed: %s", e)


def log_sklearn_model(model, name: str = "model"):
    if not HAVE_MLFLOW:
        return
    try:
        mlflow.sklearn.log_model(model, name)
    except Exception as e:
        log.warning("log_sklearn_model failed: %s", e)


def log_pyfunc_model(model_path: Path, name: str = "model"):
    if not HAVE_MLFLOW:
        return
    try:
        mlflow.log_artifact(str(model_path), artifact_path=name)
    except Exception as e:
        log.warning("log_pyfunc_model failed: %s", e)


def register_model(run_id: str, artifact_subpath: str, model_name: str,
                    metrics: dict[str, float],
                    promote_to_staging: bool = True) -> Optional[RegisteredModel]:
    """Register a tracked model, then optionally move to Staging."""
    if not HAVE_MLFLOW:
        return None
    try:
        client = MlflowClient(_tracking_uri())
        model_uri = f"runs:/{run_id}/{artifact_subpath}"
        # Ensure registered model exists
        try:
            client.get_registered_model(model_name)
        except Exception:
            client.create_registered_model(model_name)
        mv = client.create_model_version(model_name, model_uri, run_id=run_id)
        if promote_to_staging:
            client.transition_model_version_stage(model_name, mv.version, "Staging")
        return RegisteredModel(
            name=model_name, version=mv.version, stage="Staging" if promote_to_staging else "None",
            run_id=run_id, metrics=metrics,
        )
    except Exception as e:
        log.warning("register_model failed: %s", e)
        return None


def promote_to_production(model_name: str, version: str) -> bool:
    if not HAVE_MLFLOW:
        return False
    try:
        client = MlflowClient(_tracking_uri())
        # Archive the previous Production version first
        for mv in client.search_model_versions(f"name='{model_name}'"):
            if mv.current_stage == "Production" and mv.version != version:
                client.transition_model_version_stage(model_name, mv.version, "Archived")
        client.transition_model_version_stage(model_name, version, "Production")
        return True
    except Exception as e:
        log.warning("promote_to_production failed: %s", e)
        return False


def get_production_model_uri(model_name: str) -> Optional[str]:
    if not HAVE_MLFLOW:
        return None
    try:
        client = MlflowClient(_tracking_uri())
        for mv in client.search_model_versions(f"name='{model_name}'"):
            if mv.current_stage == "Production":
                return f"models:/{model_name}/{mv.version}"
    except Exception as e:
        log.warning("get_production_model_uri failed: %s", e)
    return None
