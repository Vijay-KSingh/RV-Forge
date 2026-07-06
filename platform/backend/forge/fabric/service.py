"""Fabric service: owns the engines, seeds them once, and answers questions
by routing to the right source and executing the chosen query."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from forge.fabric import seed as seeds
from forge.fabric.engines import DocEngine, SqlEngine
from forge.fabric.router import DOMAINS, classify, pick_intent

log = logging.getLogger("forge.fabric")

# Repo-root/.forge_fabric holds the embedded DB files (gitignored).
_FABRIC_DIR = Path(__file__).resolve().parents[3] / ".forge_fabric"

# Realistic connection strings so the "which DB did it connect to" story reads
# true — swap these (and the engine classes) for real servers with no other change.
_CONNECTIONS = {
    "retail": "mysql://forge@localhost:3306/retail",
    "finance": "postgresql://forge@localhost:5432/finance",
    "banking": "postgresql://forge@localhost:5432/banking",
    "healthcare": "mongodb://forge@localhost:27017/healthcare",
}


class Fabric:
    def __init__(self, root: Path = _FABRIC_DIR) -> None:
        self._dir = Path(root)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seeded = False
        self.sources = {
            "retail": SqlEngine("retail", "mysql", self._dir / "retail.db"),
            "finance": SqlEngine("finance", "postgresql", self._dir / "finance.db"),
            "banking": SqlEngine("banking", "postgresql", self._dir / "banking.db"),
            "healthcare": DocEngine("healthcare", self._dir / "healthcare.json"),
        }

    # ── seeding ──────────────────────────────────────────────────────
    def ensure_seeded(self) -> None:
        if self._seeded:
            return
        with self._lock:
            if self._seeded:
                return
            if self.sources["retail"].is_empty():
                self.sources["retail"].executescript(seeds.retail_script())
            if self.sources["finance"].is_empty():
                self.sources["finance"].executescript(seeds.finance_script())
            if self.sources["banking"].is_empty():
                self.sources["banking"].executescript(seeds.banking_script())
            if self.sources["healthcare"].is_empty():
                self.sources["healthcare"].seed(seeds.healthcare_docs())
            self._seeded = True
            log.info("Fabric seeded: %s", {k: v.count_all() for k, v in self.sources.items()})

    # ── introspection ────────────────────────────────────────────────
    def list_sources(self) -> list[dict]:
        self.ensure_seeded()
        out = []
        for name, engine in self.sources.items():
            out.append({
                "name": name,
                "domain": DOMAINS[name]["label"],
                "engine": engine.dialect,
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
            query = intent["sql"]
        else:
            columns, rows, query = intent["fn"](engine.collection("patients"))

        truncated = len(rows) > limit
        if decision["fallback"]:
            explanation = (f"No strong domain signal — defaulted to the {spec['label']} "
                           f"source and ran the '{intent_key}' query.")
        else:
            explanation = (f"Detected a {spec['label']} question ({decision['confidence']}% "
                           f"confidence) → connected to {engine.dialect} "
                           f"({_CONNECTIONS[spec['source']]}) and ran the '{intent_key}' query.")

        return {
            "question": question,
            "domain": spec["label"],
            "source": spec["source"],
            "engine": engine.dialect,
            "connection": _CONNECTIONS[spec["source"]],
            "intent": intent_key,
            "query": query,
            "columns": columns,
            "rows": rows[:limit],
            "row_count": len(rows),
            "truncated": truncated,
            "confidence": decision["confidence"],
            "fallback": decision["fallback"],
            "candidates": decision["candidates"],
            "explanation": explanation,
        }


fabric = Fabric()
