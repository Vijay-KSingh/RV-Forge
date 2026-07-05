"""Probe a running generated app: live topology + golden-dataset verification.

Two jobs, both performed against the *live* app over HTTP (stdlib only):

* ``probe_topology`` — hit each component's real endpoint and report which
  nodes are live and which links are actively carrying data. Drives the
  animated architecture view in the wizard.

* ``run_verification`` — a golden-dataset check. The app's own manifest data
  (``app/data/*.json``) is the golden reference; we assert the live API returns
  exactly what the manifest promised, proves NL query returns the expected
  answer, and confirms secrets never leak. This shows the app didn't just
  *start* — it behaves *correctly*.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ── low-level HTTP helpers ───────────────────────────────────────────
def _get(url: str, timeout: float = 4.0):
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8")


def _get_json(url: str, timeout: float = 4.0):
    status, body = _get(url, timeout)
    return status, json.loads(body)


def _post_json(url: str, payload: dict, timeout: float = 6.0):
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method="POST",
                  headers={"Content-Type": "application/json", "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _reachable(url: str, timeout: float = 3.0) -> bool:
    try:
        with urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except (URLError, HTTPError, OSError):
        return False


def _load_golden(app_dir: str, name: str):
    path = Path(app_dir) / "app" / "data" / name
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


# ── topology ─────────────────────────────────────────────────────────
def probe_topology(meta: dict) -> dict:
    """Return components + links with their live status, probed in real time."""
    be = meta["backend_url"]
    fe = meta["frontend_url"]

    frontend_ok = _reachable(fe + "/")
    backend_ok = _reachable(be + "/health")

    data_ok = False
    try:
        status, body = _get_json(be + "/api/kpis")
        data_ok = status == 200 and isinstance(body, list) and len(body) > 0
    except Exception:
        pass

    intel_ok = False
    try:
        status, body = _post_json(be + "/api/ask", {"question": "revenue"})
        intel_ok = status == 200 and isinstance(body, dict) and "answer" in body
    except Exception:
        pass

    def node(nid, label, icon, ok):
        return {"id": nid, "label": label, "icon": icon,
                "status": "live" if ok else "starting"}

    components = [
        node("frontend", "Web UI", "🖥️", frontend_ok),
        node("backend", "API service", "⚙️", backend_ok),
        node("data", "Data & catalogs", "🗄️", data_ok),
        node("intelligence", "Insights engine", "✨", intel_ok),
    ]
    links = [
        {"source": "frontend", "target": "backend", "label": "HTTP", "active": frontend_ok and backend_ok},
        {"source": "backend", "target": "data", "label": "reads", "active": backend_ok and data_ok},
        {"source": "backend", "target": "intelligence", "label": "invokes", "active": backend_ok and intel_ok},
    ]
    all_live = all(c["status"] == "live" for c in components)
    return {"components": components, "links": links, "all_live": all_live}


# ── golden-dataset verification ──────────────────────────────────────
def _check(name: str, passed: bool, expected, actual, detail: str = "") -> dict:
    return {"name": name, "passed": bool(passed),
            "expected": expected, "actual": actual, "detail": detail}


def run_verification(meta: dict) -> dict:
    """Run the golden-dataset checks against the live app."""
    be = meta["backend_url"]
    app_dir = meta["app_dir"]
    golden_kpis = _load_golden(app_dir, "kpis.json")
    golden_ds = _load_golden(app_dir, "datasources.json")
    checks: list[dict] = []

    # 1. Backend is healthy and identifies itself correctly.
    try:
        status, health = _get_json(be + "/health")
        ok = status == 200 and health.get("status") == "ok"
        checks.append(_check("Backend healthy", ok, "status=ok", health,
                             "GET /health returns a healthy service"))
    except Exception as e:
        checks.append(_check("Backend healthy", False, "status=ok", str(e)))

    # 2. KPI catalog matches the manifest exactly (golden reference).
    try:
        status, kpis = _get_json(be + "/api/kpis")
        want_ids = sorted(k.get("id") for k in golden_kpis)
        got_ids = sorted(k.get("id") for k in kpis) if isinstance(kpis, list) else []
        ok = status == 200 and want_ids == got_ids
        checks.append(_check("KPI catalog matches manifest", ok,
                             f"{len(want_ids)} KPIs: {want_ids}",
                             f"{len(got_ids)} KPIs: {got_ids}",
                             "Live /api/kpis equals the golden manifest KPIs"))
    except Exception as e:
        checks.append(_check("KPI catalog matches manifest", False, "match", str(e)))

    # 3. Data sources count matches the manifest.
    try:
        status, ds = _get_json(be + "/api/datasources")
        got = len(ds) if isinstance(ds, list) else -1
        ok = status == 200 and got == len(golden_ds)
        checks.append(_check("Data sources exposed", ok,
                             f"{len(golden_ds)} sources", f"{got} sources",
                             "Live /api/datasources count equals the manifest"))
    except Exception as e:
        checks.append(_check("Data sources exposed", False, "match", str(e)))

    # 4. SECURITY: secrets must never leak through the API.
    try:
        status, ds = _get_json(be + "/api/datasources")
        leaked = [d for d in (ds if isinstance(ds, list) else []) if "secret_ref" in d]
        ok = status == 200 and not leaked
        checks.append(_check("Secrets never leak", ok,
                             "no secret_ref in any datasource",
                             f"{len(leaked)} leaked" if leaked else "none leaked",
                             "The API must strip secret references"))
    except Exception as e:
        checks.append(_check("Secrets never leak", False, "no leaks", str(e)))

    # 5. FUNCTIONAL: NL query returns the expected KPI for a golden question.
    if golden_kpis:
        target = golden_kpis[0]
        question = f"How is our {target.get('name', '')} doing?"
        try:
            status, ans = _post_json(be + "/api/ask", {"question": question})
            ok = status == 200 and ans.get("kpi_id") == target.get("id")
            checks.append(_check("NL query returns correct KPI", ok,
                                 f"kpi_id={target.get('id')}",
                                 f"kpi_id={ans.get('kpi_id')}",
                                 f'Asked: "{question}"'))
        except Exception as e:
            checks.append(_check("NL query returns correct KPI", False,
                                 target.get("id"), str(e)))
    else:
        checks.append(_check("NL query returns correct KPI", False,
                             "a KPI to test", "no KPIs in manifest"))

    # 6. Proactive digest reflects the real manifest counts.
    try:
        status, digest = _get_json(be + "/api/insights/digest")
        blob = json.dumps(digest)
        ok = status == 200 and str(len(golden_kpis)) in blob
        checks.append(_check("Digest reflects manifest", ok,
                             f"mentions {len(golden_kpis)} KPIs",
                             "headline generated" if ok else "count mismatch",
                             "The digest is derived from the configured KPIs"))
    except Exception as e:
        checks.append(_check("Digest reflects manifest", False, "match", str(e)))

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    return {"passed": passed, "total": total, "ok": passed == total, "checks": checks}
