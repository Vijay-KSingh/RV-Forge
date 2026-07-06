"""Embedded engines for the data fabric.

``SqlEngine`` — a file-backed SQLite database presented under a SQL dialect
label (``postgresql`` / ``mysql``). ``DocEngine`` — a JSON-backed, in-process
document store with a MongoDB-flavoured surface. Both expose ``table_info`` and
``count_all`` so the fabric can describe a source without querying it.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class SqlEngine:
    def __init__(self, name: str, dialect: str, db_path: Path) -> None:
        self.name = name
        self.dialect = dialect          # "postgresql" | "mysql"
        self.kind = "sql"
        self.db_path = Path(db_path)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def is_empty(self) -> bool:
        with self._conn() as c:
            n = c.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        return n == 0

    def executescript(self, script: str) -> None:
        with self._conn() as c:
            c.executescript(script)

    def query(self, sql: str, params: tuple = ()) -> tuple[list[str], list[list]]:
        with self._conn() as c:
            cur = c.execute(sql, params)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            return cols, [list(r) for r in rows]

    def table_info(self) -> dict:
        with self._conn() as c:
            tables = [r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            out = {}
            for t in tables:
                rows = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
                out[t] = {"rows": rows, "columns": cols}
            return out

    def count_all(self) -> int:
        return sum(t["rows"] for t in self.table_info().values())


class DocEngine:
    def __init__(self, name: str, db_path: Path) -> None:
        self.name = name
        self.dialect = "mongodb"
        self.kind = "doc"
        self.db_path = Path(db_path)
        self._data: dict[str, list[dict]] = {}
        if self.db_path.exists():
            try:
                self._data = json.loads(self.db_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._data = {}

    def is_empty(self) -> bool:
        return not any(self._data.values())

    def seed(self, collections: dict[str, list[dict]]) -> None:
        self._data = collections
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.write_text(json.dumps(collections), encoding="utf-8")

    def collection(self, name: str) -> list[dict]:
        return self._data.get(name, [])

    def table_info(self) -> dict:
        out = {}
        for name, docs in self._data.items():
            cols = sorted({k for d in docs for k in d.keys()})
            out[name] = {"rows": len(docs), "columns": cols}
        return out

    def count_all(self) -> int:
        return sum(len(v) for v in self._data.values())
