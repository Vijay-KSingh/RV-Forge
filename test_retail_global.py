"""Live test suite for the global clothing-retail scenario (10M rows).

Exercises the application against the large warehouse and reports PASS/FAIL with
timings so you can see how it performs at scale. Run from platform/backend:

    cd platform/backend && PYTHONPATH=. python ../../test_retail_global.py
"""
from __future__ import annotations

import sqlite3
import time

from forge import retail_analytics as ra

RESULTS: list[tuple] = []


def check(name: str, fn):
    t0 = time.time()
    try:
        detail = fn()
        ok = True
    except AssertionError as e:
        detail, ok = f"FAILED: {e}", False
    except Exception as e:  # noqa: BLE001
        detail, ok = f"ERROR: {type(e).__name__}: {e}", False
    ms = (time.time() - t0) * 1000
    RESULTS.append((name, ok, detail, ms))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name:38} {ms:8.0f} ms   {detail}")


def _ro():
    return sqlite3.connect(f"file:{ra.DB_PATH}?mode=ro", uri=True)


# ── Volume & integrity ───────────────────────────────────────────────
def t_row_count():
    n = _ro().execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    assert n >= 10_000_000, f"expected >=10M rows, got {n:,}"
    return f"{n:,} sales rows"


def t_dimensions():
    con = _ro()
    stores = con.execute("SELECT COUNT(*) FROM stores").fetchone()[0]
    skus = con.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    assert stores == 500, f"stores={stores}"
    assert skus == 1000, f"skus={skus}"
    return f"{stores} stores · {skus} SKUs"


def t_integrity():
    con = _ro()
    bad = con.execute(
        "SELECT COUNT(*) FROM sales "
        "WHERE units < 1 OR net_revenue < 0 "
        "OR ABS(net_revenue - (gross_revenue - discount_amt)) > 0.02"
    ).fetchone()[0]
    assert bad == 0, f"{bad:,} rows violate units/revenue invariants"
    return "net = gross - discount holds on all rows; units >= 1"


def t_date_range():
    lo, hi = _ro().execute("SELECT MIN(sale_date), MAX(sale_date) FROM sales").fetchone()
    assert lo.startswith("2024-01") and hi.startswith("2025-12"), f"{lo}..{hi}"
    return f"{lo} .. {hi} (2 years)"


# ── Query performance at scale ───────────────────────────────────────
def t_revenue_by_region():
    con = _ro()
    rows = con.execute(
        "SELECT s.region, SUM(f.net_revenue) FROM sales f "
        "JOIN stores s ON s.store_id=f.store_id GROUP BY s.region"
    ).fetchall()
    assert len(rows) == 4, f"expected 4 regions, got {len(rows)}"
    return f"4 regions aggregated over 10M rows"


def t_revenue_by_category():
    con = _ro()
    rows = con.execute(
        "SELECT p.category, SUM(f.net_revenue) FROM sales f "
        "JOIN products p ON p.sku=f.sku GROUP BY p.category"
    ).fetchall()
    assert len(rows) == 7, f"expected 7 categories, got {len(rows)}"
    return f"{len(rows)} categories aggregated over 10M rows"


def t_correctness_totals():
    con = _ro()
    total = con.execute("SELECT SUM(net_revenue) FROM sales").fetchone()[0]
    by_region = con.execute(
        "SELECT SUM(f.net_revenue) FROM sales f JOIN stores s ON s.store_id=f.store_id"
    ).fetchone()[0]
    assert abs(total - by_region) < 1.0, f"join changed the total: {total} vs {by_region}"
    return f"grand total ${total:,.0f} consistent across joins"


def t_seasonality():
    con = _ro()
    holiday = con.execute(
        "SELECT AVG(v) FROM (SELECT SUM(net_revenue) v FROM sales "
        "WHERE substr(sale_date,6,2) IN ('11','12') GROUP BY substr(sale_date,1,7))"
    ).fetchone()[0]
    jan_feb = con.execute(
        "SELECT AVG(v) FROM (SELECT SUM(net_revenue) v FROM sales "
        "WHERE substr(sale_date,6,2) IN ('01','02') GROUP BY substr(sale_date,1,7))"
    ).fetchone()[0]
    assert holiday > jan_feb * 1.3, f"holiday {holiday:.0f} not > post-holiday {jan_feb:.0f}"
    return f"holiday months {holiday/jan_feb:.2f}x post-holiday (seasonality present)"


# ── Rollup-accelerated dashboards ────────────────────────────────────
def t_rollups_exist():
    tables = {r[0] for r in _ro().execute("SELECT name FROM sqlite_master WHERE type='table'")}
    need = {"agg_meta", "agg_monthly", "agg_region", "agg_category", "agg_sku"}
    assert need <= tables, f"missing rollups: {need - tables}"
    return "materialized aggregates present"


def t_dashboard_speed():
    s = ra.summary()
    assert s["rows"] >= 10_000_000
    assert s["query_ms"] < 50, f"rollup dashboard too slow: {s['query_ms']}ms"
    return (f"full dashboard in {s['query_ms']}ms (vs ~97s raw scan) · "
            f"${s['total_revenue']:,.0f} total revenue")


# ── Forecasting (the 'solution') ─────────────────────────────────────
def t_forecast_revenue():
    fc = ra.forecast("revenue", periods=6)
    assert len(fc["history"]) == 24, f"expected 24 months history, got {len(fc['history'])}"
    assert len(fc["forecast"]) == 6, "expected 6 forecast points"
    assert all(p["value"] > 0 for p in fc["forecast"]), "forecast has non-positive values"
    nxt = fc["forecast"][0]
    return f"{fc['method']} · next month {nxt['month']}=${nxt['value']:,.0f} · fit {fc['fit_ms']}ms"


def t_forecast_units():
    fc = ra.forecast("units", periods=6)
    assert len(fc["forecast"]) == 6
    assert all(p["value"] > 0 for p in fc["forecast"])
    return f"{fc['method']} · 6-month units forecast produced"


# ── API layer (in-process) ───────────────────────────────────────────
def t_api_summary():
    from fastapi.testclient import TestClient
    from forge.api import app
    r = TestClient(app).get("/api/retail/summary")
    assert r.status_code == 200, r.status_code
    d = r.json()
    assert d["rows"] >= 10_000_000 and d["stores"] == 500
    return f"/api/retail/summary → {d['rows']:,} rows, server query {d['query_ms']}ms"


def t_api_forecast():
    from fastapi.testclient import TestClient
    from forge.api import app
    r = TestClient(app).get("/api/retail/forecast?metric=revenue&periods=6")
    assert r.status_code == 200, r.status_code
    assert len(r.json()["forecast"]) == 6
    return "/api/retail/forecast → 6-month revenue prediction"


def main():
    if not ra.available():
        print("Warehouse not found — run: python data/generate_retail_global.py")
        raise SystemExit(1)
    print(f"\n=== Global retail scenario — live tests ({ra.DB_PATH.name}) ===\n")
    print("Volume & integrity")
    for n, f in [("10M row volume", t_row_count), ("dimensions (stores/skus)", t_dimensions),
                 ("row-level integrity", t_integrity), ("2-year date range", t_date_range)]:
        check(n, f)
    print("\nQuery performance at scale (each over 10M rows)")
    for n, f in [("revenue by region", t_revenue_by_region), ("revenue by category", t_revenue_by_category),
                 ("total consistency across joins", t_correctness_totals), ("seasonality present", t_seasonality)]:
        check(n, f)
    print("\nRollup-accelerated dashboards")
    check("rollup tables present", t_rollups_exist)
    check("full dashboard latency", t_dashboard_speed)
    print("\nForecasting (sales & revenue prediction)")
    check("revenue forecast (6 mo)", t_forecast_revenue)
    check("units forecast (6 mo)", t_forecast_units)
    print("\nAPI layer (in-process)")
    check("GET /api/retail/summary", t_api_summary)
    check("GET /api/retail/forecast", t_api_forecast)

    passed = sum(1 for _, ok, _, _ in RESULTS if ok)
    total = len(RESULTS)
    slowest = max(RESULTS, key=lambda r: r[3])
    print(f"\n=== {passed}/{total} passed · slowest: {slowest[0]} ({slowest[3]:.0f} ms) ===\n")
    raise SystemExit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
