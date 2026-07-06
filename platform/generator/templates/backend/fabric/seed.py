"""Deterministic seed data for the four fabric domains.

Uses a fixed RNG seed so every boot produces the same rows — stable for demos
and tests. SQL domains return a full CREATE+INSERT script; the healthcare
domain returns document collections for the doc engine.
"""
from __future__ import annotations

import random


def _rng() -> random.Random:
    return random.Random(42)


def _sql_str(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def _insert(table: str, columns: list[str], rows: list[tuple]) -> str:
    if not rows:
        return ""
    cols = ", ".join(columns)
    values = ",\n".join(
        "(" + ", ".join(_sql_str(v) for v in row) + ")" for row in rows)
    return f"INSERT INTO {table} ({cols}) VALUES\n{values};\n"


# ── Retail (MySQL) ───────────────────────────────────────────────────
def retail_script() -> str:
    rng = _rng()
    categories = ["Electronics", "Apparel", "Home", "Grocery", "Beauty"]
    product_names = {
        "Electronics": ["Wireless Earbuds", "4K Monitor", "USB-C Hub", "Smart Watch"],
        "Apparel": ["Denim Jacket", "Running Shoes", "Wool Scarf"],
        "Home": ["Ceramic Mug Set", "LED Desk Lamp", "Cotton Towels"],
        "Grocery": ["Organic Coffee", "Olive Oil"],
        "Beauty": ["Vitamin C Serum", "Bamboo Toothbrush"],
    }
    products = []
    pid = 1
    for cat, names in product_names.items():
        for n in names:
            products.append((pid, n, cat, round(rng.uniform(6, 480), 2), rng.randint(0, 120)))
            pid += 1

    cities = ["Austin", "Seattle", "Denver", "Boston", "Miami", "Chicago"]
    segments = ["Consumer", "SMB", "Enterprise"]
    customers = [(i, f"Customer {i:02d}", rng.choice(cities), rng.choice(segments))
                 for i in range(1, 16)]

    statuses = ["shipped", "shipped", "shipped", "pending", "delivered", "cancelled"]
    orders = []
    for oid in range(1, 241):
        prod = rng.choice(products)
        qty = rng.randint(1, 6)
        amount = round(prod[3] * qty, 2)
        status = rng.choice(statuses)
        month = rng.randint(1, 12)
        orders.append((oid, rng.randint(1, 15), prod[0], qty, amount, status,
                       f"2026-{month:02d}-{rng.randint(1,28):02d}"))

    return (
        "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL, stock INTEGER);\n"
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT, segment TEXT);\n"
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, product_id INTEGER, "
        "quantity INTEGER, amount REAL, status TEXT, order_date TEXT);\n"
        + _insert("products", ["id", "name", "category", "price", "stock"], products)
        + _insert("customers", ["id", "name", "city", "segment"], customers)
        + _insert("orders", ["id", "customer_id", "product_id", "quantity", "amount", "status", "order_date"], orders)
    )


# ── Finance (PostgreSQL) ─────────────────────────────────────────────
def finance_script() -> str:
    rng = _rng()
    regions = ["North America", "EMEA", "APAC", "LATAM"]
    exp_categories = ["Salaries", "Cloud", "Marketing", "Office", "Travel", "R&D"]
    months = [f"2026-{m:02d}" for m in range(1, 13)]

    revenue = []
    rid = 1
    for m in months:
        for r in regions:
            revenue.append((rid, m, r, round(rng.uniform(40_000, 260_000), 2)))
            rid += 1
    expenses = []
    eid = 1
    for m in months:
        for c in exp_categories:
            expenses.append((eid, m, c, round(rng.uniform(10_000, 190_000), 2)))
            eid += 1

    return (
        "CREATE TABLE revenue (id INTEGER PRIMARY KEY, month TEXT, region TEXT, amount REAL);\n"
        "CREATE TABLE expenses (id INTEGER PRIMARY KEY, month TEXT, category TEXT, amount REAL);\n"
        + _insert("revenue", ["id", "month", "region", "amount"], revenue)
        + _insert("expenses", ["id", "month", "category", "amount"], expenses)
    )


# ── Banking (PostgreSQL) ─────────────────────────────────────────────
def banking_script() -> str:
    rng = _rng()
    acct_types = ["checking", "savings", "credit", "money_market"]
    kyc = ["verified", "verified", "verified", "pending", "review"]
    accounts = [(i, f"Holder {i:02d}", rng.choice(acct_types),
                 round(rng.uniform(500, 250_000), 2), rng.choice(kyc))
                for i in range(1, 21)]

    transfers = []
    for tid in range(1, 161):
        amount = round(rng.uniform(20, 90_000), 2)
        flagged = 1 if amount > 60_000 and rng.random() < 0.6 else 0
        month = rng.randint(1, 12)
        transfers.append((tid, rng.randint(1, 20), rng.randint(1, 20), amount,
                          f"2026-{month:02d}-{rng.randint(1,28):02d}", flagged))

    loan_status = ["active", "active", "paid_off", "delinquent"]
    loans = [(i, f"Holder {rng.randint(1,20):02d}", round(rng.uniform(5_000, 400_000), 2),
              round(rng.uniform(3.5, 12.5), 2), rng.choice(loan_status))
             for i in range(1, 13)]

    return (
        "CREATE TABLE accounts (id INTEGER PRIMARY KEY, customer_name TEXT, type TEXT, "
        "balance REAL, kyc_status TEXT);\n"
        "CREATE TABLE transfers (id INTEGER PRIMARY KEY, from_account INTEGER, to_account INTEGER, "
        "amount REAL, txn_date TEXT, flagged INTEGER);\n"
        "CREATE TABLE loans (id INTEGER PRIMARY KEY, customer_name TEXT, principal REAL, "
        "rate REAL, status TEXT);\n"
        + _insert("accounts", ["id", "customer_name", "type", "balance", "kyc_status"], accounts)
        + _insert("transfers", ["id", "from_account", "to_account", "amount", "txn_date", "flagged"], transfers)
        + _insert("loans", ["id", "customer_name", "principal", "rate", "status"], loans)
    )


# ── Healthcare (MongoDB / documents) ─────────────────────────────────
def healthcare_docs() -> dict:
    rng = _rng()
    departments = ["Cardiology", "Oncology", "Pediatrics", "Neurology",
                   "Orthopedics", "Emergency"]
    diagnoses = {
        "Cardiology": ["Arrhythmia", "Hypertension", "Heart Failure"],
        "Oncology": ["Breast Cancer", "Lymphoma", "Leukemia"],
        "Pediatrics": ["Asthma", "Ear Infection", "Influenza"],
        "Neurology": ["Migraine", "Epilepsy", "Stroke"],
        "Orthopedics": ["Fracture", "Arthritis", "ACL Tear"],
        "Emergency": ["Trauma", "Sepsis", "Appendicitis"],
    }
    patients = []
    for i in range(1, 91):
        dept = rng.choice(departments)
        patients.append({
            "id": i,
            "name": f"Patient {i:03d}",
            "age": rng.randint(1, 92),
            "gender": rng.choice(["F", "M"]),
            "department": dept,
            "diagnosis": rng.choice(diagnoses[dept]),
            "status": rng.choice(["admitted", "admitted", "discharged"]),
            "cost": round(rng.uniform(400, 48_000), 2),
            "admitted_on": f"2026-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}",
        })
    return {"patients": patients}
