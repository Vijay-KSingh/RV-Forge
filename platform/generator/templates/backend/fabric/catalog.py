"""Built-in query intents per data domain.

Each connection in connections.json references a ``catalog`` id here. SQL
sources carry ``sql`` strings; the MongoDB source carries declarative ops that
queryspec.py interprets. Customers can add connections without a catalog — the
service then falls back to generic table/collection introspection.
"""

CATALOGS = {
    "retail": {
        "default": "total_sales",
        "intents": {
            "top_products": {"keywords": ["top product", "best selling", "best-selling", "top selling", "bestseller"],
                "sql": "SELECT p.name, p.category, SUM(o.quantity) AS units, SUM(o.amount) AS revenue "
                       "FROM orders o JOIN products p ON p.id=o.product_id "
                       "WHERE o.status<>'cancelled' GROUP BY p.id, p.name, p.category ORDER BY revenue DESC LIMIT 5"},
            "revenue_by_category": {"keywords": ["category", "categories"],
                "sql": "SELECT p.category, SUM(o.amount) AS revenue, COUNT(*) AS orders "
                       "FROM orders o JOIN products p ON p.id=o.product_id "
                       "WHERE o.status<>'cancelled' GROUP BY p.category ORDER BY revenue DESC"},
            "orders_by_status": {"keywords": ["status", "cancelled", "shipped", "pending", "delivered"],
                "sql": "SELECT status, COUNT(*) AS orders, SUM(amount) AS amount "
                       "FROM orders GROUP BY status ORDER BY orders DESC"},
            "low_stock": {"keywords": ["stock", "inventory", "restock", "low"],
                "sql": "SELECT name, category, stock FROM products WHERE stock < 25 ORDER BY stock ASC"},
            "top_customers": {"keywords": ["top customer", "best customer", "biggest customer", "spend"],
                "sql": "SELECT c.name, c.city, c.segment, SUM(o.amount) AS spend "
                       "FROM orders o JOIN customers c ON c.id=o.customer_id "
                       "WHERE o.status<>'cancelled' GROUP BY c.id, c.name, c.city, c.segment ORDER BY spend DESC LIMIT 5"},
            "total_sales": {"keywords": ["total", "how much", "sales", "revenue"],
                "sql": "SELECT SUM(amount) AS total_sales, COUNT(*) AS orders FROM orders WHERE status<>'cancelled'"},
        },
    },
    "finance": {
        "default": "total_revenue",
        "intents": {
            "revenue_by_region": {"keywords": ["region", "geography", "market"],
                "sql": "SELECT region, SUM(amount) AS revenue FROM revenue GROUP BY region ORDER BY revenue DESC"},
            "revenue_by_month": {"keywords": ["month", "monthly", "trend", "over time", "quarter"],
                "sql": "SELECT month, SUM(amount) AS revenue FROM revenue GROUP BY month ORDER BY month"},
            "top_expenses": {"keywords": ["expense", "expenses", "cost", "spend", "spending"],
                "sql": "SELECT category, SUM(amount) AS spend FROM expenses GROUP BY category ORDER BY spend DESC LIMIT 6"},
            "profit": {"keywords": ["profit", "margin", "net", "bottom line"],
                "sql": "SELECT (SELECT SUM(amount) FROM revenue) AS revenue, "
                       "(SELECT SUM(amount) FROM expenses) AS expenses, "
                       "(SELECT SUM(amount) FROM revenue)-(SELECT SUM(amount) FROM expenses) AS profit"},
            "total_revenue": {"keywords": ["revenue", "total", "income", "how much"],
                "sql": "SELECT SUM(amount) AS total_revenue, COUNT(DISTINCT month) AS months FROM revenue"},
        },
    },
    "banking": {
        "default": "deposits_by_type",
        "intents": {
            "flagged_transfers": {"keywords": ["flag", "flagged", "fraud", "suspicious", "aml", "laundering"],
                "sql": "SELECT id, from_account, to_account, amount, txn_date FROM transfers "
                       "WHERE flagged=1 ORDER BY amount DESC"},
            "high_value_transfers": {"keywords": ["high value", "largest transfer", "biggest transfer", "large transfer"],
                "sql": "SELECT id, from_account, to_account, amount, txn_date FROM transfers ORDER BY amount DESC LIMIT 8"},
            "loans_outstanding": {"keywords": ["loan", "loans", "outstanding", "principal", "delinquent"],
                "sql": "SELECT status, COUNT(*) AS loans, SUM(principal) AS principal FROM loans GROUP BY status ORDER BY principal DESC"},
            "kyc_pending": {"keywords": ["kyc", "verification", "compliance", "onboarding"],
                "sql": "SELECT customer_name, type, kyc_status FROM accounts WHERE kyc_status<>'verified' ORDER BY kyc_status"},
            "deposits_by_type": {"keywords": ["deposit", "balance", "account", "savings", "checking", "total"],
                "sql": "SELECT type, COUNT(*) AS accounts, SUM(balance) AS total_balance FROM accounts GROUP BY type ORDER BY total_balance DESC"},
        },
    },
    "healthcare": {
        "default": "by_department",
        "collection": "patients",
        "intents": {
            "avg_cost": {"keywords": ["cost", "bill", "billing", "charge", "expense", "price"],
                "op": "group_avg", "by": "department", "value": "cost",
                "columns": ["department", "patients", "avg_cost"]},
            "admissions": {"keywords": ["admit", "admission", "admitted", "inpatient"],
                "op": "count_where_group", "where": {"status": "admitted"}, "group": "department",
                "columns": ["department", "admitted"]},
            "diagnosis_distribution": {"keywords": ["diagnosis", "condition", "disease", "illness"],
                "op": "group_count", "by": "diagnosis", "columns": ["diagnosis", "count"]},
            "senior_patients": {"keywords": ["senior", "elderly", "old", "age", "geriatric"],
                "op": "find", "where": {"age__gte": 60}, "sort": "age", "desc": True, "limit": 15,
                "fields": ["name", "age", "department", "diagnosis"]},
            "by_department": {"keywords": ["department", "ward", "unit", "how many", "count"],
                "op": "group_count", "by": "department", "columns": ["department", "patients"]},
        },
    },
}
