"""Real database connectors for the fabric — Postgres, MySQL, MongoDB.

These talk to the containers started by docker/fabric/compose.yml. They mirror
the embedded engines' interface (query / executescript / seed / table_info /
count_all / is_empty) plus ``is_reachable`` so the fabric can prefer a live
server and fall back to the embedded engine when a container is down.
"""
from __future__ import annotations

import logging

log = logging.getLogger("forge.fabric.real")


def _split_statements(script: str) -> list[str]:
    # Seed scripts have no semicolons inside string values, so a plain split is
    # safe and avoids driver multi-statement quirks.
    return [s.strip() for s in script.split(";") if s.strip()]


class RealSqlEngine:
    def __init__(self, name: str, dialect: str, dsn: dict) -> None:
        self.name = name
        self.dialect = dialect        # "postgresql" | "mysql"
        self.kind = "sql"
        self._dsn = dsn

    # ── connection ───────────────────────────────────────────────────
    def _connect(self):
        if self.dialect == "postgresql":
            import psycopg2
            return psycopg2.connect(connect_timeout=3, **self._dsn)
        import pymysql
        return pymysql.connect(connect_timeout=3, read_timeout=8, write_timeout=8, **self._dsn)

    def is_reachable(self) -> bool:
        try:
            conn = self._connect()
            conn.close()
            return True
        except Exception:
            return False

    # ── schema / data ────────────────────────────────────────────────
    def is_empty(self) -> bool:
        try:
            return len(self.table_info()) == 0
        except Exception:
            return True

    def executescript(self, script: str) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            for stmt in _split_statements(script):
                cur.execute(stmt)
            conn.commit()
        finally:
            conn.close()

    def query(self, sql: str, params: tuple = ()) -> tuple[list[str], list[list]]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(sql, params or None)
            rows = cur.fetchall() if cur.description else []
            cols = [d[0] for d in cur.description] if cur.description else []
            return cols, [list(r) for r in rows]
        finally:
            conn.close()

    def table_info(self) -> dict:
        if self.dialect == "postgresql":
            tsql = ("SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' ORDER BY table_name")
        else:
            tsql = ("SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema=DATABASE() ORDER BY table_name")
        _, trows = self.query(tsql)
        out = {}
        for (t,) in [(r[0],) for r in trows]:
            _, cnt = self.query(f"SELECT COUNT(*) FROM {t}")
            _, crows = self.query(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name=%s ORDER BY ordinal_position", (t,))
            out[t] = {"rows": cnt[0][0], "columns": [c[0] for c in crows]}
        return out

    def count_all(self) -> int:
        return sum(t["rows"] for t in self.table_info().values())


class RealDocEngine:
    def __init__(self, name: str, uri: str, dbname: str) -> None:
        self.name = name
        self.dialect = "mongodb"
        self.kind = "doc"
        self._uri = uri
        self._dbname = dbname

    def _client(self):
        import pymongo
        return pymongo.MongoClient(self._uri, serverSelectionTimeoutMS=2000)

    def is_reachable(self) -> bool:
        try:
            client = self._client()
            client.admin.command("ping")
            client.close()
            return True
        except Exception:
            return False

    def is_empty(self) -> bool:
        try:
            client = self._client()
            n = client[self._dbname]["patients"].estimated_document_count()
            client.close()
            return n == 0
        except Exception:
            return True

    def seed(self, collections: dict) -> None:
        client = self._client()
        db = client[self._dbname]
        for name, docs in collections.items():
            db[name].delete_many({})
            if docs:
                db[name].insert_many([dict(d) for d in docs])
        client.close()

    def collection(self, name: str) -> list[dict]:
        client = self._client()
        docs = list(client[self._dbname][name].find({}, {"_id": 0}))
        client.close()
        return docs

    def aggregate(self, name: str, pipeline: list) -> list[dict]:
        client = self._client()
        docs = list(client[self._dbname][name].aggregate(pipeline))
        client.close()
        for d in docs:  # stringify a non-scalar group key so it renders in a table
            if "_id" in d and not isinstance(d["_id"], (str, int, float, bool)):
                d["_id"] = str(d["_id"])
        return docs

    def find_docs(self, name: str, flt: dict, sort=None, limit=None, projection=None) -> list[dict]:
        client = self._client()
        cur = client[self._dbname][name].find(flt or {}, projection or {"_id": 0})
        if sort:
            cur = cur.sort(list(sort.items()) if isinstance(sort, dict) else sort)
        if limit:
            cur = cur.limit(int(limit))
        docs = list(cur)
        client.close()
        return docs

    def table_info(self) -> dict:
        client = self._client()
        db = client[self._dbname]
        out = {}
        for name in db.list_collection_names():
            docs = list(db[name].find({}, {"_id": 0}).limit(50))
            cols = sorted({k for d in docs for k in d.keys()})
            out[name] = {"rows": db[name].estimated_document_count(), "columns": cols}
        client.close()
        return out

    def count_all(self) -> int:
        return sum(t["rows"] for t in self.table_info().values())


def ensure_pg_database(admin_dsn: dict, dbname: str) -> None:
    """CREATE DATABASE <dbname> on the Postgres server if it doesn't exist."""
    import psycopg2
    conn = psycopg2.connect(connect_timeout=3, **admin_dsn)
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (dbname,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{dbname}"')
            log.info("Created Postgres database %s", dbname)
    finally:
        conn.close()
