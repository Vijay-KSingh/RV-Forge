"""Config-driven data fabric for the generated app.

Connections are defined in ``app/connections.json`` (editable by hand or via the
Connections UI). Each connection prefers its real database (Postgres / MySQL /
MongoDB via drivers) and, for the bundled demo connections, falls back to an
embedded engine seeded with sample data — so the app works before any real DB
is wired. The agent routes a question to a connection by keyword score, then
runs the best-matching query from its catalog (or generic introspection for
connections you add yourself).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from decimal import Decimal
from pathlib import Path

from .catalog import CATALOGS
from .engines import DocEngine, SqlEngine
from .queryspec import generic_sql_intents, run_doc_intent
from .real_engines import RealDocEngine, RealSqlEngine
from . import seed as seeds

log = logging.getLogger("app.fabric")

APP_DIR = Path(__file__).resolve().parents[1]
CONN_FILE = APP_DIR / "connections.json"
EMB_DIR = APP_DIR / "data" / "_fabric"
# Local demo credential used when a connection has no password_env / password.
DEMO_PWD = os.environ.get("FABRIC_DB_PASSWORD", "forge_fabric_pwd")

SEED_SCRIPTS = {"retail": seeds.retail_script, "finance": seeds.finance_script,
                "banking": seeds.banking_script}
VALID_ENGINES = {"mysql", "postgresql", "postgres", "mongodb"}


def _clean(v):
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float):
        return round(v, 2)
    return v


class Fabric:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._resolved: dict = {}
        self._loaded = False

    # ── config file ──────────────────────────────────────────────────
    def _read_config(self) -> dict:
        try:
            return json.loads(CONN_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"connections": []}

    def _write_config(self, cfg: dict) -> None:
        CONN_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        self._loaded = False  # force re-resolve on next use

    def _password(self, conn: dict) -> str:
        env = conn.get("password_env")
        return (os.environ.get(env) if env else None) or conn.get("password") or DEMO_PWD

    # ── engine construction ──────────────────────────────────────────
    def _real_engine(self, conn: dict):
        engine, pwd = conn["engine"], self._password(conn)
        if engine == "mysql":
            return RealSqlEngine(conn["id"], "mysql", {
                "host": conn["host"], "port": int(conn.get("port", 3306)),
                "user": conn["user"], "password": pwd, "database": conn["database"]})
        if engine in ("postgresql", "postgres"):
            return RealSqlEngine(conn["id"], "postgresql", {
                "host": conn["host"], "port": int(conn.get("port", 5432)),
                "user": conn["user"], "password": pwd, "dbname": conn["database"]})
        if engine == "mongodb":
            uri = (f"mongodb://{conn['user']}:{pwd}@{conn['host']}:"
                   f"{int(conn.get('port', 27017))}/?authSource=admin")
            return RealDocEngine(conn["id"], uri, conn["database"])
        return None

    def _embedded_engine(self, conn: dict):
        cat = conn.get("catalog")
        if not conn.get("demo") or cat not in (set(SEED_SCRIPTS) | {"healthcare"}):
            return None
        EMB_DIR.mkdir(parents=True, exist_ok=True)
        if conn["engine"] == "mongodb":
            e = DocEngine(conn["id"], EMB_DIR / f"{conn['id']}.json")
            if e.is_empty():
                e.seed(seeds.healthcare_docs())
            return e
        e = SqlEngine(conn["id"], conn["engine"], EMB_DIR / f"{conn['id']}.db")
        if e.is_empty():
            e.executescript(SEED_SCRIPTS[cat]())
        return e

    def _resolve(self) -> None:
        resolved = {}
        for conn in self._read_config().get("connections", []):
            if not conn.get("enabled", True):
                continue
            engine, mode = None, "offline"
            real = self._real_engine(conn)
            if real and real.is_reachable():
                try:
                    if conn.get("demo") and conn.get("catalog") and real.is_empty():
                        if conn["engine"] == "mongodb":
                            real.seed(seeds.healthcare_docs())
                        elif conn["catalog"] in SEED_SCRIPTS:
                            real.executescript(SEED_SCRIPTS[conn["catalog"]]())
                    engine, mode = real, "docker"
                except Exception:
                    log.exception("seeding real %s failed", conn["id"])
                    engine = None
            if engine is None:
                emb = self._embedded_engine(conn)
                if emb:
                    engine, mode = emb, "embedded"
            resolved[conn["id"]] = {"conn": conn, "engine": engine, "mode": mode}
        self._resolved = resolved
        self._loaded = True

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if not self._loaded:
                self._resolve()

    def reload(self) -> None:
        with self._lock:
            self._resolve()

    # ── routing + execution ──────────────────────────────────────────
    @staticmethod
    def _pick_intent(intents: dict, default: str, q: str) -> str:
        best, best_score = default, 0
        for key, intent in intents.items():
            score = sum(1 for kw in intent.get("keywords", []) if kw in q)
            if score > best_score:
                best, best_score = key, score
        return best

    def _execute(self, engine, conn: dict, question: str):
        q = question.lower()
        cat = CATALOGS.get(conn.get("catalog"))
        if cat and engine.kind == "sql":
            key = self._pick_intent(cat["intents"], cat["default"], q)
            intent = cat["intents"][key]
            cols, rows = engine.query(intent["sql"])
            return cols, [[_clean(v) for v in r] for r in rows], intent["sql"], key
        if cat and engine.kind == "doc":
            key = self._pick_intent(cat["intents"], cat["default"], q)
            coll = cat.get("collection", "patients")
            cols, rows, qtext = run_doc_intent(engine.collection(coll), cat["intents"][key])
            return cols, rows, qtext.replace("{coll}", coll), key
        # ── generic introspection (customer-added connection, no catalog) ──
        if engine.kind == "sql":
            tables = list(engine.table_info().keys())
            gintents = generic_sql_intents(tables)
            key = self._pick_intent(gintents, "list_tables", q)
            intent = gintents[key]
            if intent.get("sql"):
                cols, rows = engine.query(intent["sql"])
                return cols, [[_clean(v) for v in r] for r in rows], intent["sql"], key
            info = engine.table_info()
            rows = [[t, i["rows"], ", ".join(i["columns"])] for t, i in info.items()]
            return ["table", "rows", "columns"], rows, "-- list tables (no catalog)", "list_tables"
        info = engine.table_info()
        rows = [[t, i["rows"], ", ".join(i["columns"])] for t, i in info.items()]
        return ["collection", "documents", "fields"], rows, "// list collections", "list_collections"

    def ask(self, question: str, limit: int = 50) -> dict:
        self.ensure_loaded()
        if not self._resolved:
            return {"error": "No data connections are configured. Add one under Connections."}
        q = question.lower()
        scores = [(cid, sum(1 for k in r["conn"].get("keywords", []) if k in q))
                  for cid, r in self._resolved.items()]
        scores.sort(key=lambda x: -x[1])
        top_id, top_score = scores[0]
        total = sum(s for _, s in scores)
        r = self._resolved[top_id]
        conn, engine, mode = r["conn"], r["engine"], r["mode"]
        confidence = round(top_score / total * 100) if total else 0
        fallback = top_score == 0

        if engine is None:
            return {"question": question, "domain": conn.get("label", top_id), "source": top_id,
                    "engine": conn["engine"], "mode": "offline", "error": "connection unreachable",
                    "explanation": f"Routed to {conn.get('label', top_id)} but its database is offline.",
                    "candidates": [{"domain": self._resolved[c]["conn"].get("label", c), "score": s}
                                   for c, s in scores], "rows": [], "columns": [], "row_count": 0}

        cols, rows, query, intent_key = self._execute(engine, conn, question)
        where = {"docker": "live", "embedded": "embedded (demo)"}.get(mode, mode)
        return {
            "question": question, "domain": conn.get("label", top_id), "source": top_id,
            "engine": conn["engine"], "mode": mode, "intent": intent_key, "query": query,
            "columns": cols, "rows": rows[:limit], "row_count": len(rows),
            "truncated": len(rows) > limit, "confidence": confidence, "fallback": fallback,
            "candidates": [{"domain": self._resolved[c]["conn"].get("label", c), "score": s}
                           for c, s in scores],
            "explanation": (f"Routed to {conn.get('label', top_id)} ({confidence}% match) → "
                            f"{where} {conn['engine']} and ran the '{intent_key}' query."),
        }

    # ── connections CRUD (for the customer to configure DBs) ──────────
    def _public(self, conn: dict) -> dict:
        r = self._resolved.get(conn["id"], {})
        eng = r.get("engine")
        return {
            "id": conn["id"], "label": conn.get("label", conn["id"]),
            "engine": conn["engine"], "host": conn.get("host"), "port": conn.get("port"),
            "database": conn.get("database"), "user": conn.get("user"),
            "password_env": conn.get("password_env"),
            "has_password": bool(conn.get("password")) or bool(conn.get("password_env")),
            "keywords": conn.get("keywords", []), "enabled": conn.get("enabled", True),
            "demo": conn.get("demo", False), "catalog": conn.get("catalog"),
            "mode": r.get("mode", "offline"),
            "tables": eng.table_info() if eng else {},
            "total_rows": eng.count_all() if eng else 0,
        }

    def list_sources(self) -> list[dict]:
        self.ensure_loaded()
        cfg = self._read_config()
        return [self._public(c) for c in cfg.get("connections", []) if c.get("enabled", True)]

    def list_connections(self) -> list[dict]:
        self.ensure_loaded()
        return [self._public(c) for c in self._read_config().get("connections", [])]

    def test_connection(self, payload: dict) -> dict:
        engine = self._real_engine(payload)
        if not engine:
            return {"reachable": False, "error": f"unknown engine '{payload.get('engine')}'"}
        return {"reachable": engine.is_reachable()}

    def upsert_connection(self, payload: dict) -> dict:
        cid = str(payload.get("id", "")).strip()
        if not cid or not cid.replace("_", "").replace("-", "").isalnum():
            raise ValueError("id must be alphanumeric (with _ or -)")
        if payload.get("engine") not in VALID_ENGINES:
            raise ValueError(f"engine must be one of {sorted(VALID_ENGINES)}")
        for field in ("host", "database", "user"):
            if not payload.get(field):
                raise ValueError(f"'{field}' is required")
        cfg = self._read_config()
        conns = cfg.setdefault("connections", [])
        existing = next((c for c in conns if c["id"] == cid), None)
        record = {
            "id": cid, "label": payload.get("label", cid), "engine": payload["engine"],
            "host": payload["host"], "port": payload.get("port"), "database": payload["database"],
            "user": payload["user"], "enabled": payload.get("enabled", True),
            "keywords": payload.get("keywords", []),
        }
        if payload.get("password_env"):
            record["password_env"] = payload["password_env"]
        if payload.get("password"):            # optional plaintext (local only)
            record["password"] = payload["password"]
        if payload.get("catalog"):
            record["catalog"] = payload["catalog"]
        if existing:
            # preserve demo/catalog flags unless overridden
            record.setdefault("catalog", existing.get("catalog"))
            record["demo"] = existing.get("demo", False)
            conns[conns.index(existing)] = record
        else:
            conns.append(record)
        self._write_config(cfg)
        self.reload()
        return self._public(record)

    def delete_connection(self, cid: str) -> dict:
        cfg = self._read_config()
        before = len(cfg.get("connections", []))
        cfg["connections"] = [c for c in cfg.get("connections", []) if c["id"] != cid]
        self._write_config(cfg)
        self.reload()
        return {"deleted": before - len(cfg["connections"])}


fabric = Fabric()
