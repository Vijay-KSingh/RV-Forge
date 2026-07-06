"""Analytics + forecasting over the large clothing-retail warehouse.

Queries the 10M-row SQLite warehouse produced by data/generate_retail_global.py
and provides headline KPIs, breakdowns, monthly time series, and revenue/units
forecasts (Holt-Winters seasonal, falling back to seasonal-naive).
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / ".forge_fabric" / "retail_global.db"
METRIC_COL = {"revenue": "net_revenue", "units": "units"}


_ROLLUPS = {
    "agg_meta": "SELECT COUNT(*) rows, SUM(net_revenue) revenue, SUM(units) units FROM sales",
    "agg_monthly": ("SELECT substr(sale_date,1,7) ym, SUM(net_revenue) revenue, "
                    "SUM(units) units FROM sales GROUP BY ym"),
    "agg_region": ("SELECT s.region, SUM(f.net_revenue) revenue, SUM(f.units) units "
                   "FROM sales f JOIN stores s ON s.store_id=f.store_id GROUP BY s.region"),
    "agg_category": ("SELECT p.category, SUM(f.net_revenue) revenue, SUM(f.units) units "
                     "FROM sales f JOIN products p ON p.sku=f.sku GROUP BY p.category"),
    "agg_sku": ("SELECT f.sku, p.product_name AS name, SUM(f.net_revenue) revenue, "
                "SUM(f.units) units FROM sales f JOIN products p ON p.sku=f.sku GROUP BY f.sku"),
}


def available() -> bool:
    return DB_PATH.exists()


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _rows(con, sql, params=()):
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return cols, [list(r) for r in cur.fetchall()]


def ensure_rollups(force: bool = False) -> dict:
    """Build materialized aggregate tables (one scan each, one-time) so
    dashboards over the 10M-row fact table stay sub-second. Idempotent."""
    con = sqlite3.connect(DB_PATH)
    built = []
    try:
        existing = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        t0 = time.time()
        for tbl, sql in _ROLLUPS.items():
            if force or tbl not in existing:
                con.execute(f"DROP TABLE IF EXISTS {tbl}")
                con.execute(f"CREATE TABLE {tbl} AS {sql}")
                built.append(tbl)
        if built:
            con.commit()
        return {"built": built, "ms": round((time.time() - t0) * 1000, 1)}
    finally:
        con.close()


def summary() -> dict:
    ensure_rollups()
    con = _conn()
    try:
        t0 = time.time()
        meta = con.execute("SELECT rows, revenue, units FROM agg_meta").fetchone()
        stores = con.execute("SELECT COUNT(*) FROM stores").fetchone()[0]
        skus = con.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        _, by_region = _rows(con, "SELECT region, revenue, units FROM agg_region ORDER BY revenue DESC")
        _, by_category = _rows(con, "SELECT category, revenue, units FROM agg_category ORDER BY revenue DESC")
        _, top_skus = _rows(con, "SELECT sku, name, revenue, units FROM agg_sku ORDER BY revenue DESC LIMIT 10")
        rnd = lambda x: round(x, 2) if isinstance(x, float) else x
        return {
            "rows": meta["rows"], "total_revenue": rnd(meta["revenue"]), "total_units": meta["units"],
            "stores": stores, "skus": skus,
            "by_region": [{"region": r[0], "revenue": rnd(r[1]), "units": r[2]} for r in by_region],
            "by_category": [{"category": r[0], "revenue": rnd(r[1]), "units": r[2]} for r in by_category],
            "top_skus": [{"sku": r[0], "name": r[1], "revenue": rnd(r[2]), "units": r[3]} for r in top_skus],
            "query_ms": round((time.time() - t0) * 1000, 1),
        }
    finally:
        con.close()


def monthly_series(metric: str = "revenue") -> list[dict]:
    ensure_rollups()
    col = "revenue" if metric == "revenue" else "units"
    con = _conn()
    try:
        _, rows = _rows(con, f"SELECT ym, {col} FROM agg_monthly ORDER BY ym")
        return [{"month": r[0], "value": round(r[1], 2) if isinstance(r[1], float) else r[1]} for r in rows]
    finally:
        con.close()


def forecast(metric: str = "revenue", periods: int = 6) -> dict:
    series = monthly_series(metric)
    values = [p["value"] for p in series]
    t0 = time.time()
    method = "holt_winters"
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = ExponentialSmoothing(values, trend="add", seasonal="add",
                                       seasonal_periods=12).fit()
        preds = [round(float(v), 2) for v in fit.forecast(periods)]
    except Exception:
        method = "seasonal_naive"
        preds = [round(values[-12 + (i % 12)], 2) if len(values) >= 12 else round(values[-1], 2)
                 for i in range(periods)]

    # extend the month labels
    last = series[-1]["month"]
    y, m = int(last[:4]), int(last[5:7])
    future = []
    for _ in range(periods):
        m += 1
        if m > 12:
            m, y = 1, y + 1
        future.append(f"{y:04d}-{m:02d}")

    return {
        "metric": metric, "method": method,
        "history": series,
        "forecast": [{"month": mo, "value": v} for mo, v in zip(future, preds)],
        "fit_ms": round((time.time() - t0) * 1000, 1),
    }
