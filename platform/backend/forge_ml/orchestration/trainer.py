"""High-level training orchestrator.

This is what Airflow DAGs call. Wires together:
  - feature pipeline construction
  - anomaly ensemble fit
  - forecast model auto-selection
  - MLflow experiment tracking
  - model registry promotion to Staging

Two top-level entry points:
  - train_anomaly_detector(customer_id, kpi_id, history) -> registry handle
  - train_forecaster(customer_id, kpi_id, history, horizon) -> registry handle

Both are idempotent (running twice produces two MLflow runs and two model
versions; promoting one moves the previous to Archived).
"""
from __future__ import annotations

import json
import logging
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import joblib
import pandas as pd

from forge_ml.features.pipeline import FeaturePipeline, FeatureConfig
from forge_ml.models.anomaly.ensemble import AnomalyEnsemble, AnomalyConfig
from forge_ml.models.forecasting.ensemble import autoselect_and_forecast, walk_forward_backtest
from forge_ml.registry import mlflow_registry as reg

log = logging.getLogger(__name__)


def train_anomaly_detector(
    customer_id: str,
    kpi_id: str,
    history: pd.DataFrame,
    labels: Optional[pd.Series] = None,
    feature_config: Optional[FeatureConfig] = None,
    anomaly_config: Optional[AnomalyConfig] = None,
    artifact_dir: str | Path = "/data/models",
) -> dict:
    """Train the anomaly ensemble, log to MLflow, register the model."""
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    cfg_feat = feature_config or FeatureConfig(timestamp_col="timestamp", target_col="value")
    cfg_anom = anomaly_config or AnomalyConfig()

    # 1) Build features
    pipeline = FeaturePipeline(cfg_feat)
    feats = pipeline.fit_transform(history)
    feats = feats.dropna(subset=pipeline.feature_columns)
    if len(feats) < 50:
        raise ValueError(f"Need ≥50 rows post-feature-build, got {len(feats)}")

    X = feats[pipeline.feature_columns + ["value"]].copy()
    y = labels.reindex(X.index) if labels is not None else None

    # 2) Fit
    t0 = time.time()
    ens = AnomalyEnsemble(cfg_anom).fit(X, y=y, value_column="value")
    fit_seconds = time.time() - t0

    # 3) Score the training set as a quality check
    detections = ens.predict(feats.assign(timestamp=feats["timestamp"]),
                              value_column="value")
    n_anom = sum(1 for d in detections if d.is_anomaly)
    flagged_pct = 100.0 * n_anom / len(detections) if detections else 0.0
    avg_severity = sum(d.severity for d in detections) / max(1, len(detections))

    # 4) Save artifacts (joblib for serving)
    bundle_path = artifact_dir / f"{customer_id}_{kpi_id}_anomaly.joblib"
    joblib.dump({
        "pipeline": pipeline.to_dict(),
        "ensemble": ens,
    }, bundle_path)

    # 5) MLflow logging
    metrics = {
        "n_train_rows": len(X), "fit_seconds": fit_seconds,
        "flagged_pct": flagged_pct, "avg_severity": avg_severity,
        "n_features": len(pipeline.feature_columns),
        "xgb_used": int(ens.xgb is not None),
    }
    params = {**asdict(cfg_feat), **asdict(cfg_anom), "kpi_id": kpi_id}
    model_name = f"forge_{customer_id}_{kpi_id}_anomaly"

    run_id = None
    with reg.start_run(customer_id, "anomaly", run_name=f"{kpi_id}-anomaly") as run:
        if run is not None:
            run_id = run.info.run_id
            reg.log_params(params)
            reg.log_metrics(metrics)
            reg.log_artifact_dict("feature_columns", {"columns": pipeline.feature_columns})
            # Persist the bundle as an artifact
            reg.log_pyfunc_model(bundle_path, name="model")

    registered = reg.register_model(
        run_id=run_id, artifact_subpath="model", model_name=model_name,
        metrics=metrics, promote_to_staging=True,
    ) if run_id else None

    return {
        "customer_id": customer_id, "kpi_id": kpi_id,
        "metrics": metrics, "model_name": model_name,
        "registered_version": registered.version if registered else None,
        "bundle_path": str(bundle_path),
    }


def train_forecaster(
    customer_id: str,
    kpi_id: str,
    history: pd.DataFrame,
    horizon: int = 30,
    n_folds: int = 4,
    test_size: int = 14,
    candidate_models: Optional[list[str]] = None,
    artifact_dir: str | Path = "/data/models",
) -> dict:
    """Run the auto-selection forecast and log everything to MLflow."""
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    result = autoselect_and_forecast(
        history, horizon=horizon, n_folds=n_folds, test_size=test_size,
        models=candidate_models,
    )
    duration = time.time() - t0

    # Forecast points are saved as a CSV artifact
    out_csv = artifact_dir / f"{customer_id}_{kpi_id}_forecast.csv"
    out_df = pd.DataFrame({
        "timestamp": result.timestamps,
        "yhat": result.point,
        "yhat_lower": result.lower95,
        "yhat_upper": result.upper95,
    })
    out_df.to_csv(out_csv, index=False)

    metrics = {
        "winning_mape": next(s.mape for s in result.scoreboard if s.model_name == result.winning_model),
        "winning_rmse": next(s.rmse for s in result.scoreboard if s.model_name == result.winning_model),
        "winning_mae":  next(s.mae  for s in result.scoreboard if s.model_name == result.winning_model),
        "n_train_rows": result.trained_on,
        "horizon": horizon,
        "duration_seconds": duration,
    }
    params = {
        "kpi_id": kpi_id, "winning_model": result.winning_model,
        "runner_up": result.runner_up_model or "", "n_folds": n_folds,
        "test_size": test_size, "candidates": ",".join(s.model_name for s in result.scoreboard),
    }

    model_name = f"forge_{customer_id}_{kpi_id}_forecast"
    run_id = None
    with reg.start_run(customer_id, "forecast",
                          run_name=f"{kpi_id}-forecast",
                          tags={"winning_model": result.winning_model}) as run:
        if run is not None:
            run_id = run.info.run_id
            reg.log_params(params)
            reg.log_metrics(metrics)
            # log per-model backtest scores
            scoreboard = [asdict(s) for s in result.scoreboard]
            reg.log_artifact_dict("scoreboard", {"scores": scoreboard,
                                                    "selection_reason": result.selection_reason})
            reg.log_artifact_dict("forecast", {
                "timestamps": [str(t) for t in result.timestamps],
                "point": result.point,
                "lower95": result.lower95,
                "upper95": result.upper95,
            })

    registered = reg.register_model(
        run_id=run_id, artifact_subpath="model", model_name=model_name,
        metrics=metrics, promote_to_staging=True,
    ) if run_id else None

    return {
        "customer_id": customer_id, "kpi_id": kpi_id,
        "winning_model": result.winning_model,
        "metrics": metrics, "scoreboard": [asdict(s) for s in result.scoreboard],
        "model_name": model_name,
        "registered_version": registered.version if registered else None,
        "forecast_path": str(out_csv),
        "selection_reason": result.selection_reason,
    }
