"""In-process E2E test for the platform (manifest/generator/RBAC/insights).
No external server; uses FastAPI's TestClient."""
import sys, os, time
from datetime import datetime, timedelta

sys.path.insert(0, "/home/claude/forge/platform/backend")

import random
from fastapi.testclient import TestClient
from forge.api import app

client = TestClient(app)


def t(name): print(f"\n{'─'*60}\n {name}\n{'─'*60}")


t("health")
r = client.get("/health"); assert r.status_code == 200
print(f"  {r.json()['service']} ✓")

t("frontend root")
r = client.get("/"); assert r.status_code == 200
assert "<title>Forge" in r.text
print(f"  / ({len(r.text)} bytes) ✓")
r = client.get("/static/wizard.jsx"); assert r.status_code == 200
print(f"  /static/wizard.jsx ({len(r.text)} bytes) ✓")

t("catalogs")
r = client.get("/api/catalog/kpis")
data = r.json()
n_kpis = sum(len(v["kpis"]) for v in data["domains"].values())
print(f"  {len(data['domains'])} KPI domains, {n_kpis} total")
r = client.get("/api/catalog/audiences")
print(f"  {len(r.json()['audiences'])} audiences")
r = client.get("/api/catalog/data_source_kinds")
print(f"  {len(r.json())} source kinds")

t("manifest + secret")
manifest = {
    "schema_version": "1.0.0",
    "customer": {"company_name": "TestCo"},
    "capabilities": ["ai_dashboard", "anomaly_detection", "time_series_forecasting"],
    "deployment": "localhost",
    "data_sources": [{
        "id": "ds_x", "name": "main_db", "kind": "postgres", "auth_method": "password",
        "connection_template": "postgresql://reader:{{PWD}}@host/db",
        "secret_ref": "", "description": "",
    }],
    "audiences": [{"id": "a1", "name": "CFO"}],
    "kpis": [{
        "id": "k1", "name": "Revenue", "domain": "finance",
        "formula": "SUM(x)", "unit": "currency", "higher_is_better": True,
        "chart_type": "line", "refresh_cadence": "daily",
    }],
}
r = client.post("/api/manifests", json={"manifest": manifest})
assert r.status_code == 200
mid = r.json()["manifest_id"]
print(f"  manifest_id={mid}")

r = client.post(f"/api/manifests/{mid}/secrets",
                  json={"name": "db_pwd", "value": "s3cret", "description": "demo"})
assert r.status_code == 200
print(f"  secret_ref={r.json()['secret_ref']}")

t("build")
r = client.post("/api/builds", json={"manifest_id": mid})
assert r.status_code == 200
bid = r.json()["build_id"]
for _ in range(40):
    s = client.get(f"/api/builds/{bid}").json()
    if s["status"] in ("done", "error"): break
    time.sleep(0.2)
assert s["status"] == "done", f"Build failed: {s}"
print(f"  status={s['status']} events={len(s['events'])} → {s['output_path']}")

t("insights preview")
random.seed(42)
base = datetime(2026, 4, 1)
series = []
for i in range(40):
    v = 100 + random.gauss(0, 5)
    if i == 35: v *= 1.4  # spike
    series.append({"timestamp": (base + timedelta(days=i)).isoformat(), "value": v})

r = client.post("/api/insights/preview", json={
    "kpi_name": "X", "higher_is_better": True, "series": series, "audience": "Ops"})
prev = r.json()
print(f"  alerts={prev['n_alerts']} anomalies={len(prev['anomalies'])}")

r = client.post("/api/insights/simulate", json={
    "series": series, "scenario_name": "Boost", "description": "test",
    "parameter_changes": {"lift_pct": 10.0}})
sim = r.json()
print(f"  sim baseline={sim['baseline']:.1f} projected={sim['projected']:.1f} ({sim['delta_pct']:+.1f}%)")

r = client.post("/api/explain", json={
    "value": 1234567.0, "kpi_id": "k1", "kpi_name": "Revenue",
    "formula": "SUM(x)", "filters": {"q": "Q1"}, "source_tables": ["x"],
    "rows_used": 100, "period": "Q1"})
print(f"  explain ok ({len(r.json()['explanation'])} chars)")

print(f"\n{'='*60}\n✅ ALL PLATFORM TESTS PASS\n{'='*60}")
