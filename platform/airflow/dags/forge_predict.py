"""DAG: forge_predict

Loads the production model from MLflow registry for each (customer, kpi)
and produces fresh forecasts + anomaly scores. Writes to the feature store.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.decorators import task

log = logging.getLogger(__name__)

CONFIG_PATH = Path(os.environ.get("FORGE_TRAINING_CONFIG",
                                    "/opt/airflow/config/training_specs.json"))

DEFAULT_ARGS = {
    "owner": "forge",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def _load_specs():
    if not CONFIG_PATH.exists():
        return []
    return json.loads(CONFIG_PATH.read_text())


with DAG(
    dag_id="forge_predict",
    description="Run production models on schedule",
    default_args=DEFAULT_ARGS,
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["forge", "ml", "predict"],
) as dag:

    @task
    def list_specs() -> list:
        return _load_specs()

    @task
    def predict_one(spec: dict) -> dict:
        import sys, joblib
        sys.path.insert(0, "/opt/airflow/forge_backend")
        from forge_ml.ingestion.adapters import build_adapter
        from forge_ml.models.forecasting.ensemble import autoselect_and_forecast
        from forge_ml.features.pipeline import FeaturePipeline

        ds = build_adapter(spec.get("source_kind", "duckdb"),
                            db_path=spec.get("source_db_path", "/data/forge.duckdb"))
        history = ds.extract(spec["history_query"])

        # For the simple/local demo path, we re-fit on the latest history each run.
        # In a multi-customer production setup, you'd download from MLflow registry
        # and serve that artifact instead.
        result = autoselect_and_forecast(
            history,
            horizon=spec.get("horizon", 30),
            n_folds=spec.get("n_folds", 4),
            test_size=spec.get("test_size", 14),
            candidate_models=spec.get("candidate_models"),
        )

        # Persist forecast back to feature store
        import pandas as pd
        out = pd.DataFrame({
            "timestamp": result.timestamps,
            "yhat": result.point,
            "yhat_lower": result.lower95,
            "yhat_upper": result.upper95,
            "winning_model": result.winning_model,
            "kpi_id": spec["kpi_id"],
            "customer_id": spec["customer_id"],
        })
        target_table = f"forecasts_{spec['kpi_id']}"
        ds.bulk_load(target_table, out, primary_key=["timestamp", "kpi_id", "customer_id"])

        # Run anomaly scoring on the recent window if a bundle exists
        bundle_path = Path(spec.get("artifact_dir", "/data/models")) / \
                       f"{spec['customer_id']}_{spec['kpi_id']}_anomaly.joblib"
        anomaly_summary = None
        if bundle_path.exists():
            try:
                bundle = joblib.load(bundle_path)
                ens = bundle["ensemble"]
                pipe = FeaturePipeline.from_dict(bundle["pipeline"])
                feats = pipe.transform(history.tail(60))
                detections = ens.predict(feats, value_column="value")
                n_anom = sum(1 for d in detections if d.is_anomaly)
                anomaly_summary = {
                    "n_anomalies_recent": n_anom,
                    "n_checked": len(detections),
                    "max_severity": max((d.severity for d in detections), default=0.0),
                }
            except Exception as e:
                log.warning("Anomaly scoring failed: %s", e)

        return {
            "customer_id": spec["customer_id"],
            "kpi_id": spec["kpi_id"],
            "winning_model": result.winning_model,
            "horizon": result.horizon,
            "forecast_rows": len(out),
            "anomaly": anomaly_summary,
        }

    @task
    def summarize(results: list) -> str:
        return f"Produced predictions for {len(results)} KPIs"

    specs = list_specs()
    results = predict_one.expand(spec=specs)
    summarize(results)
