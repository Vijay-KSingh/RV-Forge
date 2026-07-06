"""Generate a large clothing-retail dataset for the 'global retailer' scenario.

~500 stores worldwide, 1,000 clothing SKUs, and ~10M daily sales-line rows over
two years (2024-2025) with realistic seasonality (holiday + summer peaks).

Written to an indexed SQLite database on G: (the C: drive is full and Docker's
data lives there). SQLite is a real, queryable SQL engine the fabric already
uses; the same rows load into Postgres unchanged when disk allows.

Run:  python data/generate_retail_global.py
"""
from __future__ import annotations

import random
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / ".forge_fabric" / "retail_global.db"
DAYS = 730
STORES = 500
LINES_PER_STORE_DAY = 28          # 730 * 500 * 28 = 10,220,000 rows
START = date(2024, 1, 1)
SEED = 7

REGIONS = {
    "North America": ["USA", "Canada", "Mexico"],
    "EMEA": ["UK", "Germany", "France", "UAE", "South Africa"],
    "APAC": ["Japan", "Australia", "India", "Singapore"],
    "LATAM": ["Brazil", "Argentina", "Chile"],
}
CITIES = ["New York", "London", "Tokyo", "Paris", "Berlin", "Dubai", "Sydney",
          "Mumbai", "Toronto", "São Paulo", "Singapore", "Cape Town"]
CHANNELS = ["Flagship", "Mall", "Outlet", "Online"]
CATEGORIES = {
    "Tops": ["T-Shirt", "Shirt", "Blouse", "Sweater", "Hoodie"],
    "Bottoms": ["Jeans", "Chinos", "Shorts", "Skirt", "Leggings"],
    "Dresses": ["Casual Dress", "Evening Dress", "Maxi Dress"],
    "Outerwear": ["Jacket", "Coat", "Blazer", "Parka"],
    "Footwear": ["Sneakers", "Boots", "Sandals", "Loafers"],
    "Activewear": ["Track Pants", "Sports Bra", "Windbreaker"],
    "Accessories": ["Belt", "Scarf", "Hat", "Bag"],
}
GENDERS = ["Women", "Men", "Kids", "Unisex"]
BRANDS = ["Aurora", "NordFit", "Maison9", "UrbanEdge", "Kite&Co", "Vela", "Loomly"]
COLORS = ["Black", "White", "Navy", "Beige", "Olive", "Burgundy", "Grey", "Teal"]
SIZES = ["XS", "S", "M", "L", "XL", "XXL"]


def season_factor(m: int) -> float:
    if m in (11, 12):      # holiday peak
        return 1.9
    if m in (6, 7):        # summer
        return 1.35
    if m in (1, 2):        # post-holiday dip
        return 0.8
    return 1.0


def build_stores(rng):
    rows = []
    region_list = [(r, c) for r, cs in REGIONS.items() for c in cs]
    for i in range(1, STORES + 1):
        region, country = rng.choice(region_list)
        rows.append((
            i, f"Store {i:03d}", country, region, rng.choice(CITIES),
            rng.choice(CHANNELS), rng.randint(1200, 28000),
            (date(2015, 1, 1) + timedelta(days=rng.randint(0, 3200))).isoformat(),
        ))
    return rows


def build_products(rng):
    rows, price_by_sku = [], {}
    cat_list = [(c, sub) for c, subs in CATEGORIES.items() for sub in subs]
    for n in range(1, 1001):
        sku = f"SKU{n:05d}"
        category, subcategory = rng.choice(cat_list)
        cost = round(rng.uniform(4, 120), 2)
        price = round(cost * rng.uniform(1.8, 3.2), 2)
        price_by_sku[sku] = price
        rows.append((
            sku, f"{rng.choice(BRANDS)} {subcategory}", category, subcategory,
            rng.choice(GENDERS), rng.choice(BRANDS), rng.choice(COLORS),
            rng.choice(SIZES), cost, price,
            (date(2022, 1, 1) + timedelta(days=rng.randint(0, 1400))).isoformat(),
        ))
    return rows, price_by_sku


def main():
    rng = random.Random(SEED)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=MEMORY;
        CREATE TABLE stores(store_id INTEGER PRIMARY KEY, store_name TEXT, country TEXT,
            region TEXT, city TEXT, channel TEXT, size_sqft INTEGER, opened_date TEXT);
        CREATE TABLE products(sku TEXT PRIMARY KEY, product_name TEXT, category TEXT,
            subcategory TEXT, gender TEXT, brand TEXT, color TEXT, size TEXT,
            unit_cost REAL, unit_price REAL, launch_date TEXT);
        CREATE TABLE sales(sale_date TEXT, store_id INTEGER, sku TEXT, units INTEGER,
            gross_revenue REAL, discount_amt REAL, net_revenue REAL);
    """)
    con.executemany("INSERT INTO stores VALUES (?,?,?,?,?,?,?,?)", build_stores(rng))
    products, price_by_sku = build_products(rng)
    con.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?)", products)
    con.commit()
    print(f"stores=500 products=1000 -> generating {DAYS*STORES*LINES_PER_STORE_DAY:,} sales rows")

    skus = [f"SKU{n:05d}" for n in range(1, 1001)]
    prices = [price_by_sku[s] for s in skus]
    dates = [(START + timedelta(days=d)) for d in range(DAYS)]
    date_strs = [d.isoformat() for d in dates]
    factors = [season_factor(d.month) for d in dates]

    t0 = time.time()
    total = 0
    ri = rng.randint
    rr = rng.random
    insert = "INSERT INTO sales VALUES (?,?,?,?,?,?,?)"
    # Insert one store-day-batch at a time (store x all days) to keep memory flat.
    for store in range(1, STORES + 1):
        batch = []
        for di in range(DAYS):
            ds = date_strs[di]
            f = factors[di]
            for _ in range(LINES_PER_STORE_DAY):
                ski = ri(0, 999)
                price = prices[ski]
                units = max(1, int(round((2 + rr() * 8) * f)))
                disc = round(rr() * 0.35, 2)
                gross = round(units * price, 2)
                d_amt = round(gross * disc, 2)
                batch.append((ds, store, skus[ski], units, gross, d_amt, round(gross - d_amt, 2)))
        con.executemany(insert, batch)
        con.commit()
        total += len(batch)
        if store % 50 == 0:
            print(f"  {store}/500 stores · {total:,} rows · {time.time()-t0:.1f}s")

    print("creating indexes…")
    con.executescript("""
        CREATE INDEX ix_sales_date ON sales(sale_date);
        CREATE INDEX ix_sales_store ON sales(store_id);
        CREATE INDEX ix_sales_sku ON sales(sku);
    """)
    con.commit()

    print("building rollup tables (sub-second dashboards over 10M rows)…")
    con.executescript("""
        CREATE TABLE agg_meta AS SELECT COUNT(*) rows, SUM(net_revenue) revenue, SUM(units) units FROM sales;
        CREATE TABLE agg_monthly AS SELECT substr(sale_date,1,7) ym, SUM(net_revenue) revenue, SUM(units) units FROM sales GROUP BY ym;
        CREATE TABLE agg_region AS SELECT s.region, SUM(f.net_revenue) revenue, SUM(f.units) units FROM sales f JOIN stores s ON s.store_id=f.store_id GROUP BY s.region;
        CREATE TABLE agg_category AS SELECT p.category, SUM(f.net_revenue) revenue, SUM(f.units) units FROM sales f JOIN products p ON p.sku=f.sku GROUP BY p.category;
        CREATE TABLE agg_sku AS SELECT f.sku, p.product_name name, SUM(f.net_revenue) revenue, SUM(f.units) units FROM sales f JOIN products p ON p.sku=f.sku GROUP BY f.sku;
    """)
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    con.close()
    size_mb = DB_PATH.stat().st_size / 1e6
    print(f"DONE: {n:,} sales rows · {size_mb:.0f} MB · {time.time()-t0:.1f}s · {DB_PATH}")


if __name__ == "__main__":
    main()
