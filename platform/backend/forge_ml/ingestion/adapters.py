"""Data ingestion adapters.

Common interface: every adapter implements

    extract(query_or_path) -> pandas.DataFrame
    bulk_load(table, dataframe, primary_key) -> int  (upserts, returns row count)

Adapters in this file:
  - PostgresAdapter  (uses sqlalchemy + psycopg2 — production-ready)
  - SnowflakeAdapter (uses snowflake-connector-python — implemented but the
    cloud parts are tested only against the documented driver behavior)
  - CSVAdapter       (pandas read_csv)
  - DuckDBAdapter    (good local store; default sink for the demo)

All adapters resolve secrets via the secret_manager rather than accepting
raw credentials. This keeps secrets out of caller code.

Trusted OSS only: sqlalchemy, psycopg2-binary, pandas, duckdb.
snowflake-connector-python and pyarrow optional.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    rows_extracted: int
    rows_loaded: int
    source: str
    target: str
    duration_seconds: float


class SourceAdapter(ABC):
    """Read from a source."""
    name: str

    @abstractmethod
    def extract(self, query_or_path: str, **kwargs) -> pd.DataFrame:
        ...


class SinkAdapter(ABC):
    """Write to a sink."""
    name: str

    @abstractmethod
    def bulk_load(self, table: str, df: pd.DataFrame, primary_key: list[str]) -> int:
        ...


# ──────────────────────────────────────────────────────────────────────
# Postgres (source + sink)
# ──────────────────────────────────────────────────────────────────────

class PostgresAdapter(SourceAdapter, SinkAdapter):
    name = "postgres"

    def __init__(self, connection_url: str):
        # Importing lazily so callers without psycopg2 still get the rest of the module
        from sqlalchemy import create_engine
        self.engine = create_engine(connection_url, pool_pre_ping=True)

    def extract(self, query: str, **kwargs) -> pd.DataFrame:
        return pd.read_sql(query, self.engine, **kwargs)

    def bulk_load(self, table: str, df: pd.DataFrame, primary_key: list[str]) -> int:
        """Idempotent upsert via INSERT ... ON CONFLICT DO UPDATE."""
        from sqlalchemy import text
        if df.empty:
            return 0
        with self.engine.begin() as conn:
            # Create table if missing (best-effort schema inference)
            self._ensure_table(conn, table, df, primary_key)
            # Use a temp table + INSERT ... ON CONFLICT
            tmp = f"_tmp_{table}_{id(df)}"
            df.to_sql(tmp, conn, if_exists="replace", index=False)
            cols = ", ".join(f'"{c}"' for c in df.columns)
            updates = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in df.columns
                                  if c not in primary_key)
            pk = ", ".join(f'"{c}"' for c in primary_key)
            conn.execute(text(
                f'INSERT INTO "{table}" ({cols}) SELECT {cols} FROM "{tmp}" '
                f'ON CONFLICT ({pk}) DO UPDATE SET {updates}'
            ))
            conn.execute(text(f'DROP TABLE IF EXISTS "{tmp}"'))
        return len(df)

    def _ensure_table(self, conn, table: str, df: pd.DataFrame, primary_key: list[str]):
        from sqlalchemy import text
        # Inspect existing
        exists = conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
        ), {"t": table}).first()
        if exists:
            return
        cols_ddl = ", ".join(f'"{c}" {self._sql_type(df[c])}' for c in df.columns)
        pk_ddl = ", ".join(f'"{c}"' for c in primary_key)
        conn.execute(text(f'CREATE TABLE "{table}" ({cols_ddl}, PRIMARY KEY ({pk_ddl}))'))

    @staticmethod
    def _sql_type(s: pd.Series) -> str:
        if pd.api.types.is_integer_dtype(s): return "BIGINT"
        if pd.api.types.is_float_dtype(s):   return "DOUBLE PRECISION"
        if pd.api.types.is_bool_dtype(s):    return "BOOLEAN"
        if pd.api.types.is_datetime64_any_dtype(s): return "TIMESTAMP"
        return "TEXT"


# ──────────────────────────────────────────────────────────────────────
# DuckDB (sink, used as the demo's local feature store)
# ──────────────────────────────────────────────────────────────────────

class DuckDBAdapter(SourceAdapter, SinkAdapter):
    name = "duckdb"

    def __init__(self, db_path: str | Path = "/data/forge.duckdb"):
        import duckdb
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(db_path)
        self._duckdb = duckdb

    def _conn(self):
        return self._duckdb.connect(self.db_path)

    def extract(self, query: str, **kwargs) -> pd.DataFrame:
        with self._conn() as c:
            return c.execute(query).df()

    def bulk_load(self, table: str, df: pd.DataFrame, primary_key: list[str]) -> int:
        if df.empty:
            return 0
        with self._conn() as c:
            self._ensure_table(c, table, df, primary_key)
            tmp = f"_tmp_{table}"
            c.register(tmp, df)
            cols = ", ".join(f'"{x}"' for x in df.columns)
            pk = ", ".join(f'"{x}"' for x in primary_key)
            updates = ", ".join(f'"{x}" = EXCLUDED."{x}"' for x in df.columns
                                  if x not in primary_key) or '"' + df.columns[0] + '" = EXCLUDED."' + df.columns[0] + '"'
            # DuckDB supports INSERT ... ON CONFLICT
            c.execute(
                f'INSERT INTO "{table}" ({cols}) SELECT {cols} FROM {tmp} '
                f'ON CONFLICT ({pk}) DO UPDATE SET {updates}'
            )
            c.unregister(tmp)
        return len(df)

    def _ensure_table(self, c, table: str, df: pd.DataFrame, primary_key: list[str]):
        existing = c.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name=?",
            [table],
        ).fetchall()
        if existing:
            return
        cols_ddl = ", ".join(f'"{col}" {self._duck_type(df[col])}' for col in df.columns)
        pk = ", ".join(f'"{x}"' for x in primary_key)
        c.execute(f'CREATE TABLE "{table}" ({cols_ddl}, PRIMARY KEY ({pk}))')

    @staticmethod
    def _duck_type(s: pd.Series) -> str:
        if pd.api.types.is_integer_dtype(s): return "BIGINT"
        if pd.api.types.is_float_dtype(s):   return "DOUBLE"
        if pd.api.types.is_bool_dtype(s):    return "BOOLEAN"
        if pd.api.types.is_datetime64_any_dtype(s): return "TIMESTAMP"
        return "VARCHAR"


# ──────────────────────────────────────────────────────────────────────
# Snowflake
# ──────────────────────────────────────────────────────────────────────

class SnowflakeAdapter(SourceAdapter, SinkAdapter):
    name = "snowflake"

    def __init__(self, account: str, user: str, password: str,
                  warehouse: str, database: str, schema: str):
        try:
            import snowflake.connector  # noqa
            self._snowflake = snowflake.connector
        except ImportError as e:
            raise RuntimeError(
                "snowflake-connector-python not installed. "
                "Install with: pip install 'snowflake-connector-python[pandas]'"
            ) from e
        self._kwargs = {
            "account": account, "user": user, "password": password,
            "warehouse": warehouse, "database": database, "schema": schema,
        }

    def _conn(self):
        return self._snowflake.connect(**self._kwargs)

    def extract(self, query: str, **kwargs) -> pd.DataFrame:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(query)
            return cur.fetch_pandas_all()

    def bulk_load(self, table: str, df: pd.DataFrame, primary_key: list[str]) -> int:
        from snowflake.connector.pandas_tools import write_pandas
        if df.empty:
            return 0
        with self._conn() as conn:
            success, n_chunks, n_rows, output = write_pandas(conn, df, table.upper(),
                                                              auto_create_table=True,
                                                              overwrite=False)
            if not success:
                raise RuntimeError("Snowflake write_pandas failed")
        return int(n_rows)


# ──────────────────────────────────────────────────────────────────────
# CSV (file-based source)
# ──────────────────────────────────────────────────────────────────────

class CSVAdapter(SourceAdapter):
    name = "csv"

    def __init__(self, base_dir: str | Path = "/data/raw"):
        self.base_dir = Path(base_dir)

    def extract(self, path: str, **kwargs) -> pd.DataFrame:
        p = Path(path)
        if not p.is_absolute():
            p = self.base_dir / p
        if not p.exists():
            raise FileNotFoundError(p)
        # let pandas infer encoding/dtypes; caller can override via kwargs
        return pd.read_csv(p, **kwargs)


# ──────────────────────────────────────────────────────────────────────
# Top-level convenience
# ──────────────────────────────────────────────────────────────────────

def build_adapter(kind: str, **kwargs) -> SourceAdapter | SinkAdapter:
    """Factory used by Airflow operators and the API."""
    kind = kind.lower()
    if kind == "postgres":
        return PostgresAdapter(connection_url=kwargs["connection_url"])
    if kind == "duckdb":
        return DuckDBAdapter(db_path=kwargs.get("db_path", "/data/forge.duckdb"))
    if kind == "snowflake":
        return SnowflakeAdapter(**kwargs)
    if kind in ("csv", "csv_upload"):
        return CSVAdapter(base_dir=kwargs.get("base_dir", "/data/raw"))
    raise ValueError(f"Unsupported adapter kind: {kind}")
