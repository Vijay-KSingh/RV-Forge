"""Interpret declarative document-query intents over a list of docs, and render
a human-readable query string for the UI. Also builds generic introspection
intents for connections that have no built-in catalog.
"""
from __future__ import annotations

from collections import Counter


def _match(doc: dict, where: dict) -> bool:
    for key, val in (where or {}).items():
        if key.endswith("__gte"):
            if not (doc.get(key[:-5], 0) >= val):
                return False
        elif key.endswith("__lte"):
            if not (doc.get(key[:-5], 0) <= val):
                return False
        else:
            if doc.get(key) != val:
                return False
    return True


def run_doc_intent(docs: list[dict], intent: dict) -> tuple[list[str], list[list], str]:
    op = intent.get("op")
    if op == "group_count":
        by = intent["by"]
        c = Counter(d.get(by) for d in docs)
        rows = [[k, v] for k, v in c.most_common()]
        return (intent.get("columns", [by, "count"]), rows,
                f"db.{{coll}}.aggregate([{{ $group: {{ _id: '${by}', count: {{ $sum: 1 }} }} }}])")
    if op == "group_avg":
        by, value = intent["by"], intent["value"]
        agg: dict = {}
        for d in docs:
            agg.setdefault(d.get(by), []).append(d.get(value, 0) or 0)
        rows = [[k, len(v), round(sum(v) / len(v), 2)] for k, v in agg.items()]
        rows.sort(key=lambda r: -r[2])
        return (intent.get("columns", [by, "count", f"avg_{value}"]), rows,
                f"db.{{coll}}.aggregate([{{ $group: {{ _id: '${by}', avg: {{ $avg: '${value}' }} }} }}])")
    if op == "count_where_group":
        where, group = intent.get("where", {}), intent["group"]
        filtered = [d for d in docs if _match(d, where)]
        c = Counter(d.get(group) for d in filtered)
        rows = [[k, v] for k, v in c.most_common()]
        return (intent.get("columns", [group, "count"]), rows,
                f"db.{{coll}}.find({where}) // grouped by {group}")
    if op == "find":
        where = intent.get("where", {})
        rows_docs = [d for d in docs if _match(d, where)]
        sort = intent.get("sort")
        if sort:
            rows_docs.sort(key=lambda d: d.get(sort, 0), reverse=intent.get("desc", False))
        if intent.get("limit"):
            rows_docs = rows_docs[: intent["limit"]]
        fields = intent.get("fields") or (sorted(rows_docs[0].keys()) if rows_docs else [])
        rows = [[d.get(f) for f in fields] for d in rows_docs]
        return (fields, rows, f"db.{{coll}}.find({where}).sort({{{sort}: -1}})")
    return (["result"], [], "// unsupported op")


def generic_sql_intents(table_names: list[str]) -> dict:
    """When a SQL connection has no catalog, expose list-tables + per-table sample."""
    intents = {
        "list_tables": {"keywords": ["table", "tables", "schema", "what"],
                        "sql": None, "_tables": table_names}}
    for t in table_names:
        intents[f"sample_{t}"] = {"keywords": [t, t.rstrip("s")], "sql": f"SELECT * FROM {t} LIMIT 25"}
    return intents
