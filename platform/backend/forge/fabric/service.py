"""Fabric service: owns the engines, seeds them once, and answers questions
by routing to the right source and executing the chosen query.

Each source prefers a **live Docker database** (Postgres / MySQL / MongoDB from
docker/fabric/compose.yml) and falls back to an embedded engine when the
container isn't reachable — so the demo works with or without Docker.
"""
from __future__ import annotations

import logging
import os
import threading
from decimal import Decimal
from pathlib import Path

from forge.fabric import seed as seeds
from forge.fabric.engines import DocEngine, SqlEngine
from forge.fabric.real_engines import RealDocEngine, RealSqlEngine, ensure_pg_database
from forge.fabric.router import DOMAINS, classify, pick_intent

log = logging.getLogger("forge.fabric")

_FABRIC_DIR = Path(__file__).resolve().parents[3] / ".forge_fabric"
_DB_HOST = os.environ.get("FABRIC_DB_HOST", "localhost")
_DB_PWD = os.environ.get("FABRIC_DB_PASSWORD", "forge_fabric_pwd")

# Display strings — password intentionally omitted so it never leaks to the UI.
_CONNECTIONS = {
    "retail": f"mysql://forge@{_DB_HOST}:3306/retail",
    "finance": f"postgresql://forge@{_DB_HOST}:5432/finance",
    "banking": f"postgresql://forge@{_DB_HOST}:5432/banking",
    "healthcare": f"mongodb://forge@{_DB_HOST}:27017/healthcare",
}


def _clean(v):
    """Coerce DB numeric types for JSON + round floats for display."""
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float):
        return round(v, 2)
    return v


def _real_engines() -> dict:
    pg = lambda db: {"host": _DB_HOST, "port": 5432, "user": "forge",
                     "password": _DB_PWD, "dbname": db}
    return {
        "retail": RealSqlEngine("retail", "mysql", {
            "host": _DB_HOST, "port": 3306, "user": "forge",
            "password": _DB_PWD, "database": "retail"}),
        "finance": RealSqlEngine("finance", "postgresql", pg("finance")),
        "banking": RealSqlEngine("banking", "postgresql", pg("banking")),
        "healthcare": RealDocEngine(
            "healthcare",
            f"mongodb://forge:{_DB_PWD}@{_DB_HOST}:27017/?authSource=admin",
            "healthcare"),
    }


class Fabric:
    def __init__(self, root: Path = _FABRIC_DIR) -> None:
        self._dir = Path(root)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ready = False
        self._embedded = {
            "retail": SqlEngine("retail", "mysql", self._dir / "retail.db"),
            "finance": SqlEngine("finance", "postgresql", self._dir / "finance.db"),
            "banking": SqlEngine("banking", "postgresql", self._dir / "banking.db"),
            "healthcare": DocEngine("healthcare", self._dir / "healthcare.json"),
        }
        self._real = _real_engines()
        self.sources: dict = {}
        self.mode: dict = {}          # name -> "docker" | "embedded"

    # ── resolve real-vs-embedded + seed ──────────────────────────────
    def _seed_scripts(self):
        return {
            "retail": seeds.retail_script,
            "finance": seeds.finance_script,
            "banking": seeds.banking_script,
        }

    def ensure_seeded(self) -> None:
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            # The 'banking' Postgres DB has to exist before we can connect to it.
            try:
                if self._real["finance"].is_reachable():
                    ensure_pg_database(
                        {"host": _DB_HOST, "port": 5432, "user": "forge",
                         "password": _DB_PWD, "dbname": "finance"}, "banking")
            except Exception:
                log.debug("could not ensure banking db", exc_info=True)

            scripts = self._seed_scripts()
            for name in ("retail", "finance", "banking", "healthcare"):
                real = self._real[name]
                engine = real if real.is_reachable() else self._embedded[name]
                self.sources[name] = engine
                self.mode[name] = "docker" if engine is real else "embedded"
                try:
                    if engine.is_empty():
                        if name == "healthcare":
                            engine.seed(seeds.healthcare_docs())
                        else:
                            engine.executescript(scripts[name]())
                except Exception:
                    log.exception("seeding %s failed; falling back to embedded", name)
                    engine = self._embedded[name]
                    self.sources[name] = engine
                    self.mode[name] = "embedded"
                    if engine.is_empty():
                        if name == "healthcare":
                            engine.seed(seeds.healthcare_docs())
                        else:
                            engine.executescript(scripts[name]())
            self._ready = True
            log.info("Fabric ready: %s", self.mode)

    # ── introspection ────────────────────────────────────────────────
    def list_sources(self) -> list[dict]:
        self.ensure_seeded()
        out = []
        for name in ("retail", "finance", "banking", "healthcare"):
            engine = self.sources[name]
            out.append({
                "name": name,
                "domain": DOMAINS[name]["label"],
                "engine": engine.dialect,
                "mode": self.mode[name],
                "connection": _CONNECTIONS[name],
                "tables": engine.table_info(),
                "total_rows": engine.count_all(),
            })
        return out

    # ── the agentic query ────────────────────────────────────────────
    def ask(self, question: str, limit: int = 50) -> dict:
        self.ensure_seeded()
        decision = classify(question)
        domain = decision["domain"]
        spec = DOMAINS[domain]
        engine = self.sources[spec["source"]]
        intent_key = pick_intent(domain, question)
        intent = spec["intents"][intent_key]

        if spec["engine"] == "sql":
            columns, rows = engine.query(intent["sql"])
            rows = [[_clean(v) for v in r] for r in rows]  # round floats, coerce Decimals
            query = intent["sql"]
        else:
            columns, rows, query = intent["fn"](engine.collection("patients"))

        mode = self.mode[spec["source"]]
        where = "live Docker" if mode == "docker" else "embedded"
        if decision["fallback"]:
            explanation = (f"No strong domain signal — defaulted to the {spec['label']} "
                           f"source ({where} {engine.dialect}) and ran the '{intent_key}' query.")
        else:
            explanation = (f"Detected a {spec['label']} question ({decision['confidence']}% "
                           f"confidence) → connected to the {where} {engine.dialect} database "
                           f"({_CONNECTIONS[spec['source']]}) and ran the '{intent_key}' query.")

        return {
            "question": question,
            "domain": spec["label"],
            "source": spec["source"],
            "engine": engine.dialect,
            "mode": mode,
            "connection": _CONNECTIONS[spec["source"]],
            "intent": intent_key,
            "query": query,
            "columns": columns,
            "rows": rows[:limit],
            "row_count": len(rows),
            "truncated": len(rows) > limit,
            "confidence": decision["confidence"],
            "fallback": decision["fallback"],
            "candidates": decision["candidates"],
            "explanation": explanation,
        }


fabric = Fabric()
