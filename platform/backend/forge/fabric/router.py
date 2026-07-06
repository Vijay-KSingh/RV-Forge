"""The agentic router.

Given a natural-language question it (1) scores each domain's vocabulary to
decide *which* data source to connect to, then (2) picks the best-matching
query intent within that domain. Returns a fully-formed plan the service can
execute, plus the scoring so the UI can explain the decision.
"""
from __future__ import annotations

from collections import Counter


# ── Healthcare document queries (MongoDB-style, run in Python) ────────
def _hc_by_department(docs):
    c = Counter(d["department"] for d in docs)
    rows = [[k, v] for k, v in c.most_common()]
    return (["department", "patients"], rows,
            "db.patients.aggregate([{ $group: { _id: '$department', patients: { $sum: 1 } } }])")


def _hc_avg_cost(docs):
    agg = {}
    for d in docs:
        agg.setdefault(d["department"], []).append(d["cost"])
    rows = [[k, len(v), round(sum(v) / len(v), 2)] for k, v in agg.items()]
    rows.sort(key=lambda r: -r[2])
    return (["department", "patients", "avg_cost"], rows,
            "db.patients.aggregate([{ $group: { _id: '$department', avg_cost: { $avg: '$cost' } } }])")


def _hc_admissions(docs):
    admitted = [d for d in docs if d["status"] == "admitted"]
    c = Counter(d["department"] for d in admitted)
    rows = [[k, v] for k, v in c.most_common()]
    return (["department", "admitted"], rows,
            "db.patients.find({ status: 'admitted' })  // grouped by department")


def _hc_diagnosis(docs):
    c = Counter(d["diagnosis"] for d in docs)
    rows = [[k, v] for k, v in c.most_common()]
    return (["diagnosis", "count"], rows,
            "db.patients.aggregate([{ $group: { _id: '$diagnosis', count: { $sum: 1 } } }])")


def _hc_seniors(docs):
    seniors = sorted([d for d in docs if d["age"] >= 60], key=lambda d: -d["age"])
    rows = [[d["name"], d["age"], d["department"], d["diagnosis"]] for d in seniors[:15]]
    return (["name", "age", "department", "diagnosis"], rows,
            "db.patients.find({ age: { $gte: 60 } }).sort({ age: -1 })")


DOMAINS = {
    "retail": {
        "source": "retail", "engine": "sql", "label": "Retail",
        "vocab": [("retail", 3), ("product", 3), ("products", 3), ("order", 2), ("orders", 2),
                  ("sale", 2), ("sales", 2), ("inventory", 3), ("stock", 3), ("category", 2),
                  ("store", 2), ("customer", 1), ("purchase", 2), ("sku", 3), ("best selling", 3)],
        "default": "total_sales",
        "intents": {
            "top_products": {"keywords": ["top product", "best selling", "best-selling", "top selling", "bestseller"],
                "sql": "SELECT p.name, p.category, SUM(o.quantity) AS units, ROUND(SUM(o.amount),2) AS revenue "
                       "FROM orders o JOIN products p ON p.id=o.product_id "
                       "WHERE o.status<>'cancelled' GROUP BY p.id ORDER BY revenue DESC LIMIT 5"},
            "revenue_by_category": {"keywords": ["category", "categories"],
                "sql": "SELECT p.category, ROUND(SUM(o.amount),2) AS revenue, COUNT(*) AS orders "
                       "FROM orders o JOIN products p ON p.id=o.product_id "
                       "WHERE o.status<>'cancelled' GROUP BY p.category ORDER BY revenue DESC"},
            "orders_by_status": {"keywords": ["status", "cancelled", "shipped", "pending", "delivered", "fulfil"],
                "sql": "SELECT status, COUNT(*) AS orders, ROUND(SUM(amount),2) AS amount "
                       "FROM orders GROUP BY status ORDER BY orders DESC"},
            "low_stock": {"keywords": ["stock", "inventory", "restock", "low"],
                "sql": "SELECT name, category, stock FROM products WHERE stock < 25 ORDER BY stock ASC"},
            "top_customers": {"keywords": ["top customer", "best customer", "biggest customer", "spend"],
                "sql": "SELECT c.name, c.city, c.segment, ROUND(SUM(o.amount),2) AS spend "
                       "FROM orders o JOIN customers c ON c.id=o.customer_id "
                       "WHERE o.status<>'cancelled' GROUP BY c.id ORDER BY spend DESC LIMIT 5"},
            "total_sales": {"keywords": ["total", "how much", "sales", "revenue"],
                "sql": "SELECT ROUND(SUM(amount),2) AS total_sales, COUNT(*) AS orders "
                       "FROM orders WHERE status<>'cancelled'"},
        },
    },
    "finance": {
        "source": "finance", "engine": "sql", "label": "Finance",
        "vocab": [("finance", 3), ("financial", 3), ("revenue", 2), ("expense", 3), ("expenses", 3),
                  ("profit", 3), ("margin", 3), ("budget", 3), ("cash", 2), ("burn", 3),
                  ("income", 2), ("spend", 1), ("cost", 1), ("region", 1)],
        "default": "total_revenue",
        "intents": {
            "revenue_by_region": {"keywords": ["region", "geography", "geographic", "market"],
                "sql": "SELECT region, ROUND(SUM(amount),2) AS revenue FROM revenue "
                       "GROUP BY region ORDER BY revenue DESC"},
            "revenue_by_month": {"keywords": ["month", "monthly", "trend", "over time", "quarter"],
                "sql": "SELECT month, ROUND(SUM(amount),2) AS revenue FROM revenue "
                       "GROUP BY month ORDER BY month"},
            "top_expenses": {"keywords": ["expense", "expenses", "cost", "spend", "spending"],
                "sql": "SELECT category, ROUND(SUM(amount),2) AS spend FROM expenses "
                       "GROUP BY category ORDER BY spend DESC LIMIT 6"},
            "profit": {"keywords": ["profit", "margin", "net", "bottom line"],
                "sql": "SELECT ROUND((SELECT SUM(amount) FROM revenue),2) AS revenue, "
                       "ROUND((SELECT SUM(amount) FROM expenses),2) AS expenses, "
                       "ROUND((SELECT SUM(amount) FROM revenue)-(SELECT SUM(amount) FROM expenses),2) AS profit"},
            "total_revenue": {"keywords": ["revenue", "total", "income", "how much"],
                "sql": "SELECT ROUND(SUM(amount),2) AS total_revenue, COUNT(DISTINCT month) AS months "
                       "FROM revenue"},
        },
    },
    "banking": {
        "source": "banking", "engine": "sql", "label": "Banking",
        "vocab": [("bank", 3), ("banking", 3), ("account", 3), ("accounts", 3), ("balance", 3),
                  ("transfer", 3), ("transfers", 3), ("deposit", 3), ("loan", 3), ("loans", 3),
                  ("kyc", 3), ("fraud", 3), ("flagged", 3), ("suspicious", 3), ("aml", 3),
                  ("withdrawal", 2), ("transaction", 1)],
        "default": "deposits_by_type",
        "intents": {
            "flagged_transfers": {"keywords": ["flag", "flagged", "fraud", "suspicious", "aml", "laundering"],
                "sql": "SELECT id, from_account, to_account, amount, txn_date FROM transfers "
                       "WHERE flagged=1 ORDER BY amount DESC"},
            "high_value_transfers": {"keywords": ["high value", "largest transfer", "biggest transfer", "large transfer"],
                "sql": "SELECT id, from_account, to_account, amount, txn_date FROM transfers "
                       "ORDER BY amount DESC LIMIT 8"},
            "loans_outstanding": {"keywords": ["loan", "loans", "outstanding", "principal", "delinquent"],
                "sql": "SELECT status, COUNT(*) AS loans, ROUND(SUM(principal),2) AS principal "
                       "FROM loans GROUP BY status ORDER BY principal DESC"},
            "kyc_pending": {"keywords": ["kyc", "verification", "compliance", "onboarding"],
                "sql": "SELECT customer_name, type, kyc_status FROM accounts "
                       "WHERE kyc_status<>'verified' ORDER BY kyc_status"},
            "deposits_by_type": {"keywords": ["deposit", "balance", "account", "savings", "checking", "total"],
                "sql": "SELECT type, COUNT(*) AS accounts, ROUND(SUM(balance),2) AS total_balance "
                       "FROM accounts GROUP BY type ORDER BY total_balance DESC"},
        },
    },
    "healthcare": {
        "source": "healthcare", "engine": "doc", "label": "Healthcare",
        "vocab": [("health", 3), ("healthcare", 3), ("patient", 3), ("patients", 3), ("diagnosis", 3),
                  ("hospital", 3), ("admission", 3), ("admitted", 3), ("department", 2), ("doctor", 3),
                  ("medical", 3), ("clinical", 3), ("disease", 3), ("ward", 2), ("treatment", 2)],
        "default": "by_department",
        "intents": {
            "avg_cost": {"keywords": ["cost", "bill", "billing", "charge", "expense", "price"], "fn": _hc_avg_cost},
            "admissions": {"keywords": ["admit", "admission", "admitted", "inpatient"], "fn": _hc_admissions},
            "diagnosis_distribution": {"keywords": ["diagnosis", "condition", "disease", "illness"], "fn": _hc_diagnosis},
            "senior_patients": {"keywords": ["senior", "elderly", "old", "age", "geriatric"], "fn": _hc_seniors},
            "by_department": {"keywords": ["department", "ward", "unit", "how many", "count"], "fn": _hc_by_department},
        },
    },
}


def classify(question: str) -> dict:
    """Score every domain; return the winner plus the full ranking."""
    q = question.lower()
    scores = {dom: sum(w for term, w in spec["vocab"] if term in q)
              for dom, spec in DOMAINS.items()}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top_domain, top_score = ranked[0]
    fallback = top_score == 0
    if fallback:
        top_domain = "retail"          # graceful default when nothing matches
    total = sum(scores.values())
    confidence = round((top_score / total) * 100) if total else 0
    return {
        "domain": top_domain,
        "confidence": confidence,
        "fallback": fallback,
        "candidates": [{"domain": d, "score": s} for d, s in ranked],
    }


def pick_intent(domain: str, question: str) -> str:
    """Choose the best query intent within a domain by keyword score."""
    q = question.lower()
    spec = DOMAINS[domain]
    best_key, best_score = spec["default"], 0
    for key, intent in spec["intents"].items():
        score = sum(1 for kw in intent["keywords"] if kw in q)
        if score > best_score:
            best_key, best_score = key, score
    return best_key
