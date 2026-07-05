"""DAG: forge_training

Reads /opt/airflow/config/training_specs.json — one entry per (customer, kpi).
For each, pulls history from the feature store and runs the trainer.

This DAG is also TRIGGERED by the drift_check DAG when drift is detected.
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
    "retry_delay": timedelta(minutes=10),
}


def _load_specs():
    if not CONFIG_PATH.exists():
        return []
    return json.loads(CONFIG_PATH.read_text())


with DAG(
    dag_id="forge_training",
    description="Train forecast + anomaly models for each KPI",
    default_args=DEFAULT_ARGS,
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["forge", "ml", "train"],
) as dag:

    @task
    def list_specs() -> list:
        return _load_specs()

    @task
    def train_one(spec: dict) -> dict:
        """Train one KPI's model bundle (anomaly + forecast)."""
        import sys
        sys.path.insert(0, "/opt/airflow/forge_backend")

        from forge_ml.ingestion.adapters import build_adapter
        from forge_ml.orchestration.trainer import train_anomaly_detector, train_forecaster

        # 1) Pull history from the feature store
        ds = build_adapter(
            spec.get("source_kind", "duckdb"),
            db_path=spec.get("source_db_path", "/data/forge.duckdb"),
        )
        df = ds.extract(spec["history_query"])
        if "timestamp" not in df.columns or "value" not in df.columns:
            raise ValueError(f"history query must select 'timestamp' and 'value'; got {df.columns.tolist()}")

        # 2) Anomaly model
        anom_result = None
        if spec.get("train_anomaly", True):
            anom_result = train_anomaly_detector(
                customer_id=spec["customer_id"],
                kpi_id=spec["kpi_id"],
                history=df,
                artifact_dir=spec.get("artifact_dir", "/data/models"),
            )

        # 3) Forecast model
        fc_result = None
        if spec.get("train_forecast", True):
            fc_result = train_forecaster(
                customer_id=spec["customer_id"],
                kpi_id=spec["kpi_id"],
                history=df,
                horizon=spec.get("horizon", 30),
                n_folds=spec.get("n_folds", 4),
                test_size=spec.get("test_size", 14),
                candidate_models=spec.get("candidate_models"),
                artifact_dir=spec.get("artifact_dir", "/data/models"),
            )

        return {
            "spec": {k: spec[k] for k in ("customer_id", "kpi_id")},
            "anomaly": anom_result,
            "forecast": fc_result,
        }

    @task
    def summarize(results: list) -> str:
        ok = [r for r in results if r.get("forecast") or r.get("anomaly")]
        names = [f"{r['spec']['customer_id']}/{r['spec']['kpi_id']}" for r in ok]
        return f"Trained {len(ok)} models: {', '.join(names) or '—'}"

    specs = list_specs()
    results = train_one.expand(spec=specs)
    summarize(results)
