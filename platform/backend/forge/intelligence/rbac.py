"""RBAC engine: enforces row, column, and capability policies.

Architecture:
- Every query goes through `enforce(query_plan, user)` before execution.
- We rewrite the query: append row WHERE clauses, replace masked columns
  with their masked expressions, deny if the role lacks the capability.
- Column masking strategies:
    allow   — leave the column alone
    deny    — drop the column from SELECT
    mask    — apply a literal pattern (e.g. salary → '***')
    hash    — deterministic SHA-256 (so joins still work, but raw values hidden)
    redact  — return NULL
- Row policies use `${user.field}` substitution so the same policy works for
  any logged-in user (e.g. "country = '${user.country}'" gives each user
  only their country's rows automatically).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any, Optional

from forge.manifest import RBACConfig, Role, ColumnPolicy, RowPolicy


@dataclass
class User:
    id: str
    role_id: str
    attributes: dict[str, Any] = field(default_factory=dict)
    # attributes might include: country, business_unit, region, department


@dataclass
class QueryPlan:
    """A simplified, pre-execution representation. Real engines build this
    by parsing SQL; for the demo we accept a structured form too."""
    table: str
    select_columns: list[str]
    where_clauses: list[str] = field(default_factory=list)
    raw_sql: Optional[str] = None  # original NL-derived SQL


@dataclass
class EnforcementResult:
    allowed: bool
    plan: QueryPlan
    rewritten_sql: Optional[str] = None
    applied_row_filters: list[str] = field(default_factory=list)
    masked_columns: dict[str, str] = field(default_factory=dict)  # col -> strategy
    denied_columns: list[str] = field(default_factory=list)
    deny_reason: Optional[str] = None


class RBACEngine:
    def __init__(self, config: RBACConfig):
        self.config = config
        self._roles: dict[str, Role] = {r.id: r for r in config.roles}

    def get_role(self, role_id: str) -> Optional[Role]:
        return self._roles.get(role_id) or self._roles.get(self.config.default_role_id)

    def enforce(self, plan: QueryPlan, user: User) -> EnforcementResult:
        role = self.get_role(user.role_id)
        if role is None:
            return EnforcementResult(allowed=False, plan=plan,
                                     deny_reason=f"Unknown role: {user.role_id}")

        # 1) Column policies
        kept_cols: list[str] = []
        masked: dict[str, str] = {}
        denied: list[str] = []
        masked_exprs: dict[str, str] = {}

        for col in plan.select_columns:
            policy = self._column_policy_for(role, plan.table, col)
            if policy is None or policy.action == "allow":
                kept_cols.append(col)
                continue
            if policy.action == "deny":
                denied.append(col)
                continue
            if policy.action == "redact":
                kept_cols.append(f"NULL AS {col}")
                masked[col] = "redact"
                masked_exprs[col] = "NULL"
                continue
            if policy.action == "hash":
                kept_cols.append(f"sha256({col}) AS {col}")
                masked[col] = "hash"
                masked_exprs[col] = f"sha256({col})"
                continue
            if policy.action == "mask":
                pattern = policy.mask_pattern or "***"
                # Generic mask: replace any non-NULL with the pattern literal
                expr = f"CASE WHEN {col} IS NULL THEN NULL ELSE '{pattern}' END AS {col}"
                kept_cols.append(expr)
                masked[col] = "mask"
                masked_exprs[col] = expr

        # 2) Row policies
        applied: list[str] = []
        extra_where: list[str] = []
        for row_pol in role.row_policies:
            if not _table_matches(plan.table, row_pol.table_pattern):
                continue
            resolved = _resolve_user_vars(row_pol.where_expression, user)
            extra_where.append(f"({resolved})")
            applied.append(resolved)

        new_where = list(plan.where_clauses) + extra_where
        rewritten_plan = QueryPlan(
            table=plan.table,
            select_columns=kept_cols,
            where_clauses=new_where,
        )
        rewritten_sql = self._render(rewritten_plan)

        return EnforcementResult(
            allowed=True,
            plan=rewritten_plan,
            rewritten_sql=rewritten_sql,
            applied_row_filters=applied,
            masked_columns=masked,
            denied_columns=denied,
        )

    # ── helpers ────────────────────────────────────────────────────────

    def _column_policy_for(self, role: Role, table: str, col: str) -> Optional[ColumnPolicy]:
        """Return the most specific matching policy."""
        best: Optional[ColumnPolicy] = None
        best_specificity = -1
        for pol in role.column_policies:
            patt = pol.column_pattern
            target = f"{table}.{col}"
            if fnmatch(target, patt) or fnmatch(col, patt):
                # specificity: longer pattern, fewer wildcards = more specific
                spec = len(patt) - patt.count("*") * 2
                if spec > best_specificity:
                    best = pol
                    best_specificity = spec
        return best

    @staticmethod
    def _render(plan: QueryPlan) -> str:
        cols = ", ".join(plan.select_columns) if plan.select_columns else "*"
        sql = f"SELECT {cols} FROM {plan.table}"
        if plan.where_clauses:
            sql += " WHERE " + " AND ".join(plan.where_clauses)
        return sql


_VAR = re.compile(r"(?P<quote>['\"]?)\$\{user\.(?P<attr>\w+)\}(?P=quote)")


def _resolve_user_vars(expr: str, user: User) -> str:
    """Replace ${user.country} or '${user.country}' with the user's attribute,
    properly quoted as a SQL literal. We detect whether the placeholder was
    already wrapped in quotes and avoid double-quoting in that case."""
    def replace(m):
        attr = m.group("attr")
        already_quoted = bool(m.group("quote"))
        if attr == "id":
            val = user.id
        else:
            val = user.attributes.get(attr)
        if val is None:
            return "NULL"
        # naive single-quote escape; production would parameterize
        escaped = str(val).replace("'", "''")
        return f"'{escaped}'"  # always emit a single-quoted literal
    return _VAR.sub(replace, expr)


def _table_matches(table: str, pattern: str) -> bool:
    return pattern == "*" or fnmatch(table, pattern)
