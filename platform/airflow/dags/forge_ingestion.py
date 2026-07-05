"""DAG: forge_ingestion

Reads ingestion specs from /opt/airflow/config/ingestion_specs.json and pulls
each source on its configured schedule into the DuckDB feature store.

Each spec looks like:
  {
    "id": "fleet_revenue",
    "kind": "csv",                     // or "postgres", "snowflake"
    "path": "fleet/revenue.csv",       // for csv
    "query": "SELECT ts, value FROM …", // for postgres/snowflake
    "target_table": "fleet_revenue",
    "primary_key": ["timestamp"],
    "schedule": "@daily"
  }

The DAG is parameterized — one TaskGroup per spec — so adding a new source
is config-only, not code.
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

DEFAULT_ARGS = {
    "owner": "forge",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "depends_on_past": False,
}

CONFIG_PATH = Path(os.environ.get("FORGE_INGESTION_CONFIG",
                                    "/opt/airflow/config/ingestion_specs.json"))


def _load_specs():
    if not CONFIG_PATH.exists():
        log.warning("No ingestion config at %s — DAG will run with no tasks", CONFIG_PATH)
        return []
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception as e:
        log.error("Failed to parse ingestion config: %s", e)
        return []


with DAG(
    dag_id="forge_ingestion",
    description="Pull configured data sources into the feature store",
    default_args=DEFAULT_ARGS,
    schedule="@hourly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["forge", "ingest"],
) as dag:

    @task
    def list_specs() -> list:
        return _load_specs()

    @task
    def ingest_one(spec: dict) -> dict:
        """Pull one source. Imports inside the task because Airflow workers
        load DAG files at parse time and we don't want heavyweight imports
        on the scheduler."""
        import sys, time
        sys.path.insert(0, "/opt/airflow/forge_backend")
        from forge_ml.ingestion.adapters import build_adapter

        kind = spec["kind"]
        target_kind = spec.get("target_kind", "duckdb")
        target_kwargs = spec.get("target_kwargs", {"db_path": "/data/forge.duckdb"})
        target_table = spec["target_table"]
        pk = spec.get("primary_key", ["timestamp"])

        # Source
        src_kwargs = spec.get("source_kwargs", {})
        if kind == "csv":
            src = build_adapter("csv", base_dir=src_kwargs.get("base_dir", "/data/raw"))
            df = src.extract(spec["path"], **src_kwargs.get("read_kwargs", {}))
        elif kind == "postgres":
            src = build_adapter("postgres", connection_url=src_kwargs["connection_url"])
            df = src.extract(spec["query"])
        elif kind == "snowflake":
            src = build_adapter("snowflake", **src_kwargs)
            df = src.extract(spec["query"])
        else:
            raise ValueError(f"Unsupported source kind: {kind}")

        # Sink
        sink = build_adapter(target_kind, **target_kwargs)
        t0 = time.time()
        n = sink.bulk_load(target_table, df, pk)
        return {
            "spec_id": spec["id"],
            "rows_extracted": len(df),
            "rows_loaded": n,
            "duration_seconds": time.time() - t0,
            "target_table": target_table,
        }

    @task
    def summarize(results: list) -> str:
        total = sum(r["rows_loaded"] for r in results)
        return f"Ingested {total} rows across {len(results)} sources"

    specs = list_specs()
    results = ingest_one.expand(spec=specs)
    summarize(results)
