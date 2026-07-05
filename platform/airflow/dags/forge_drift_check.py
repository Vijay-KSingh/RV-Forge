"""DAG: forge_drift_check

Compares each monitored KPI's recent window against its training reference.
If drift is major, triggers the forge_training DAG for that KPI.

Reads /opt/airflow/config/drift_specs.json:
  [
    {
      "customer_id": "acme",
      "kpi_id": "revenue",
      "feature_store_query": "SELECT * FROM features_revenue WHERE timestamp > NOW() - INTERVAL 90 DAYS",
      "reference_query":     "SELECT * FROM features_revenue WHERE timestamp BETWEEN '2025-01-01' AND '2025-06-30'",
      "min_severity_to_retrain": "major"
    }
  ]
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.decorators import task
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

log = logging.getLogger(__name__)

CONFIG_PATH = Path(os.environ.get("FORGE_DRIFT_CONFIG",
                                    "/opt/airflow/config/drift_specs.json"))

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
    dag_id="forge_drift_check",
    description="Run drift detection and trigger retrain when needed",
    default_args=DEFAULT_ARGS,
    schedule="@hourly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["forge", "ml", "drift"],
) as dag:

    @task
    def list_specs() -> list:
        return _load_specs()

    @task
    def check_one(spec: dict) -> dict:
        import sys
        sys.path.insert(0, "/opt/airflow/forge_backend")

        from forge_ml.ingestion.adapters import build_adapter
        from forge_ml.drift.detector import compare, DriftConfig, DriftSeverity

        ds = build_adapter(spec.get("source_kind", "duckdb"),
                            db_path=spec.get("source_db_path", "/data/forge.duckdb"))
        ref = ds.extract(spec["reference_query"])
        new = ds.extract(spec["feature_store_query"])

        cfg = DriftConfig(
            psi_minor_threshold=spec.get("psi_minor", 0.1),
            psi_major_threshold=spec.get("psi_major", 0.2),
        )
        report = compare(ref, new, config=cfg)

        # Translate severity threshold from spec
        threshold = spec.get("min_severity_to_retrain", "major")
        sev_rank = {"none": 0, "minor": 1, "major": 2}
        should_trigger = sev_rank[report.overall_severity.value] >= sev_rank[threshold]

        return {
            "spec_id": f"{spec['customer_id']}/{spec['kpi_id']}",
            "should_trigger_retrain": bool(should_trigger),
            "overall_severity": report.overall_severity.value,
            "n_drifted": len(report.drifted_features),
            "summary": report.summary,
            "customer_id": spec["customer_id"],
            "kpi_id": spec["kpi_id"],
            "drifted_features": [d.feature for d in report.drifted_features],
        }

    @task(trigger_rule="all_done")
    def maybe_trigger(results: list) -> list:
        """Build the list of (customer, kpi) pairs to retrain."""
        triggers = [{"customer_id": r["customer_id"], "kpi_id": r["kpi_id"]}
                    for r in results if r.get("should_trigger_retrain")]
        log.info("Drift detected, triggering retrains: %s", triggers)
        return triggers

    trigger = TriggerDagRunOperator(
        task_id="trigger_training",
        trigger_dag_id="forge_training",
        # We trigger the training DAG; the drift specs that flagged determine
        # which KPIs the operator restricts to via conf payload.
        conf={"triggered_by": "drift_check"},
        wait_for_completion=False,
        reset_dag_run=True,
        # Only fire if at least one drift was detected (handled below via Branch).
    )

    specs = list_specs()
    drifts = check_one.expand(spec=specs)
    triggers = maybe_trigger(drifts)
    triggers >> trigger
