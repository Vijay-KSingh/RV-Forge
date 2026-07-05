"""Forge Manifest — the single source of truth for a generated application.

The wizard produces a Manifest. The generator consumes it. Everything else
(IaC, RBAC, KPIs, observability) is derived from this object.

Versioning matters: customers in production must be able to upgrade. We
embed schema_version so future generators can migrate old manifests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


SCHEMA_VERSION = "1.0.0"


# ──────────────────────────────────────────────────────────────────────
# Step 1 — Service capabilities
# ──────────────────────────────────────────────────────────────────────

class ServiceCapability(str, Enum):
    """High-level capabilities the customer wants. Maps to feature toggles
    in the generated app and to which agents/modules get bundled in."""
    AI_DASHBOARD = "ai_dashboard"
    NL_QUERY = "nl_query"
    ANOMALY_DETECTION = "anomaly_detection"
    TIME_SERIES_FORECASTING = "time_series_forecasting"
    FRAUD_DETECTION = "fraud_detection"
    CHURN_PREDICTION = "churn_prediction"
    REVENUE_FORECASTING = "revenue_forecasting"
    DOCUMENT_INTELLIGENCE = "document_intelligence"
    PROACTIVE_INSIGHTS = "proactive_insights"
    WHAT_IF_SIMULATION = "what_if_simulation"
    EXECUTIVE_SUMMARY = "executive_summary"
    AGENTIC_WORKFLOWS = "agentic_workflows"


# ──────────────────────────────────────────────────────────────────────
# Step 2 — Deployment topology
# ──────────────────────────────────────────────────────────────────────

class DeploymentTarget(str, Enum):
    CLOUD_AWS = "cloud_aws"
    CLOUD_AZURE = "cloud_azure"
    CLOUD_GCP = "cloud_gcp"
    ON_PREM = "on_prem"
    HYBRID = "hybrid"
    LOCALHOST = "localhost"  # for the demo path


class InfraOwnership(str, Enum):
    SELF_MANAGED = "self_managed"   # customer manages
    FULLY_MANAGED = "fully_managed"  # we manage (SaaS)
    CO_MANAGED = "co_managed"        # shared


# ──────────────────────────────────────────────────────────────────────
# Step 4 — Data sources (auth handled with care)
# ──────────────────────────────────────────────────────────────────────

class DataSourceKind(str, Enum):
    POSTGRES = "postgres"
    MYSQL = "mysql"
    SNOWFLAKE = "snowflake"
    DATABRICKS = "databricks"
    BIGQUERY = "bigquery"
    REDSHIFT = "redshift"
    SAP = "sap"
    WORKDAY = "workday"
    SALESFORCE = "salesforce"
    REST_API = "rest_api"
    XLSX_UPLOAD = "xlsx_upload"
    CSV_UPLOAD = "csv_upload"
    S3_BUCKET = "s3_bucket"
    KAFKA = "kafka"


class AuthMethod(str, Enum):
    PASSWORD = "password"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    SERVICE_ACCOUNT = "service_account"
    IAM_ROLE = "iam_role"
    KERBEROS = "kerberos"
    NONE = "none"


class DataSource(BaseModel):
    """A single data source. Secrets are NEVER stored in the manifest itself —
    the manifest holds a *reference* to a secret, and the secret lives in
    the generated app's secret manager (env vars, Vault, KMS)."""
    id: str = Field(default_factory=lambda: f"ds_{uuid4().hex[:8]}")
    name: str
    kind: DataSourceKind
    auth_method: AuthMethod
    # "Connection string template" with placeholders — actual secret resolved
    # from the secret_ref at runtime.
    connection_template: str = ""
    # Reference to where the secret is stored (e.g. "env:DB_URL_REVENUE",
    # "vault:secret/data/forge/customer123/db_revenue", "aws-sm:revenue-db")
    secret_ref: str = ""
    schema_hint: Optional[dict[str, Any]] = None
    refresh_schedule: Optional[str] = None  # cron, e.g. "0 */6 * * *"
    description: str = ""

    @field_validator("connection_template")
    @classmethod
    def no_secrets_in_template(cls, v: str) -> str:
        """Defense-in-depth: prevent accidentally embedding a secret in the
        manifest. We reject anything that looks like a real password."""
        if not v:
            return v
        # Form 1: query-string keys (password=, token=, etc.)
        suspicious_kv = ["password=", "pwd=", "secret=", "token=", "api_key=",
                         "apikey=", "access_key=", "access_token="]
        lowered = v.lower()
        for s in suspicious_kv:
            if s in lowered:
                idx = lowered.index(s) + len(s)
                rest = v[idx:].strip()
                if rest and not rest.startswith(("{{", "${", "<", "$")):
                    raise ValueError(
                        f"Connection template appears to contain a literal secret near '{s}'. "
                        f"Use a placeholder like {{{{SECRET}}}} and store the real value via secret_ref."
                    )
        # Form 2: scheme://user:password@host
        import re
        m = re.match(r"^[a-z][a-z0-9+\-.]*://([^/@?\s]+):([^/@?\s]+)@", v, re.IGNORECASE)
        if m:
            password_part = m.group(2)
            if not (password_part.startswith("{{") or password_part.startswith("${")
                    or password_part.startswith("<") or password_part == ""):
                raise ValueError(
                    "Connection template appears to embed a literal password in the userinfo "
                    "(user:password@host form). Use a placeholder like 'user:{{PWD}}@host' "
                    "and store the real password via secret_ref."
                )
        return v


# ──────────────────────────────────────────────────────────────────────
# Step 5 — KPIs and metrics catalog
# ──────────────────────────────────────────────────────────────────────

class KPIDefinition(BaseModel):
    """A KPI selected from the catalog (or custom). The generator wires
    these into the dashboard, the proactive-insights digest, and the
    NL-query semantic layer."""
    id: str
    name: str
    domain: str  # finance, sales, ops, hr, customer, product
    formula: str  # SQL expression or DSL — generator translates to runtime
    unit: str = "number"  # currency, percent, count, ratio, days, etc.
    higher_is_better: bool = True
    chart_type: Literal["line", "bar", "area", "pie", "kpi", "table", "scatter", "funnel"] = "line"
    target_value: Optional[float] = None
    alert_threshold_pct: Optional[float] = None  # alert if delta > this %
    refresh_cadence: Literal["realtime", "hourly", "daily", "weekly", "monthly"] = "daily"
    audiences: list[str] = Field(default_factory=list)  # role ids that see this


class TargetAudience(BaseModel):
    """An end-user persona. Drives the personalized "smart query suggestions"
    feature and tailors which KPIs surface on which dashboard."""
    id: str
    name: str  # e.g. "CFO", "RevOps Lead"
    description: str = ""
    default_kpi_ids: list[str] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# Step 6 — Observability
# ──────────────────────────────────────────────────────────────────────

class ObservabilityTier(str, Enum):
    BASIC = "basic"        # logs only
    STANDARD = "standard"  # logs + metrics + traces
    ADVANCED = "advanced"  # standard + audit + lineage + cost tracking
    REGULATED = "regulated"  # advanced + immutable audit + approval flows


class ObservabilityConfig(BaseModel):
    tier: ObservabilityTier = ObservabilityTier.STANDARD
    log_retention_days: int = 30
    audit_retention_days: int = 365
    metrics_backend: Literal["prometheus", "datadog", "cloudwatch", "azure_monitor"] = "prometheus"
    traces_backend: Literal["tempo", "jaeger", "datadog", "x-ray", "none"] = "tempo"
    alert_channels: list[str] = Field(default_factory=list)  # slack:#ops, email:ops@x.com
    enable_data_lineage: bool = False
    enable_query_audit: bool = True
    enable_cost_tracking: bool = False


# ──────────────────────────────────────────────────────────────────────
# Step 7 — RBAC down to row/column
# ──────────────────────────────────────────────────────────────────────

class ColumnPolicy(BaseModel):
    """How a column is exposed to a role."""
    column_pattern: str  # regex or glob, e.g. "*.salary" or "workers.salary_usd"
    action: Literal["allow", "deny", "mask", "hash", "redact"] = "allow"
    mask_pattern: Optional[str] = None  # e.g. "***-**-####" for SSN tail


class RowPolicy(BaseModel):
    """A row-level filter applied transparently when this role queries.
    Equivalent to a WHERE clause appended to every query."""
    table_pattern: str  # e.g. "workers" or "*"
    where_expression: str  # e.g. "country = '${user.country}'" — variables resolved at query time


class Role(BaseModel):
    id: str
    name: str
    description: str = ""
    column_policies: list[ColumnPolicy] = Field(default_factory=list)
    row_policies: list[RowPolicy] = Field(default_factory=list)
    capabilities: list[ServiceCapability] = Field(default_factory=list)
    can_export: bool = True
    can_share: bool = False
    requires_approval_for: list[str] = Field(default_factory=list)  # KPI ids needing approval


class RBACConfig(BaseModel):
    sso_provider: Literal["azure_ad", "okta", "google", "saml", "none"] = "none"
    mfa_required: bool = True
    roles: list[Role] = Field(default_factory=list)
    default_role_id: str = "viewer"
    # Sensitive query approval workflow
    approval_chain: list[str] = Field(default_factory=list)  # role ids in order


# ──────────────────────────────────────────────────────────────────────
# Step 8 — Custom requests (free-form, captured for the generator's
# `extra` slot — these become feature-flagged stubs in the generated app)
# ──────────────────────────────────────────────────────────────────────

class CustomRequest(BaseModel):
    title: str
    description: str
    priority: Literal["must_have", "nice_to_have", "future"] = "nice_to_have"


# ──────────────────────────────────────────────────────────────────────
# The full Manifest
# ──────────────────────────────────────────────────────────────────────

class CustomerInfo(BaseModel):
    company_name: str
    industry: str = ""
    contact_email: str = ""
    primary_use_case: str = ""


class Manifest(BaseModel):
    schema_version: str = SCHEMA_VERSION
    manifest_id: str = Field(default_factory=lambda: f"mfst_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    customer: CustomerInfo

    # Step 1
    capabilities: list[ServiceCapability] = Field(default_factory=list)
    # Step 2 + 3
    deployment: DeploymentTarget = DeploymentTarget.LOCALHOST
    infra_ownership: InfraOwnership = InfraOwnership.SELF_MANAGED
    cloud_region: str = "us-east-1"
    # Step 4
    data_sources: list[DataSource] = Field(default_factory=list)
    # Step 5
    audiences: list[TargetAudience] = Field(default_factory=list)
    kpis: list[KPIDefinition] = Field(default_factory=list)
    # Step 6
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    # Step 7
    rbac: RBACConfig = Field(default_factory=RBACConfig)
    # Step 8
    custom_requests: list[CustomRequest] = Field(default_factory=list)

    # Generator hints (set by the wizard's review step)
    branding: dict[str, str] = Field(default_factory=dict)  # logo_url, primary_color, app_name
    feature_flags: dict[str, bool] = Field(default_factory=dict)

    @field_validator("manifest_id", mode="before")
    @classmethod
    def _default_manifest_id(cls, v: Any) -> Any:
        # The wizard seeds manifest_id as null until the first save; an explicit
        # None would otherwise defeat the default_factory and fail validation.
        if v is None or (isinstance(v, str) and not v.strip()):
            return f"mfst_{uuid4().hex[:12]}"
        return v

    @field_validator("created_at", mode="before")
    @classmethod
    def _default_created_at(cls, v: Any) -> Any:
        if v is None or (isinstance(v, str) and not v.strip()):
            return datetime.now(timezone.utc)
        return v

    def app_slug(self) -> str:
        """Filesystem-safe app id derived from customer name."""
        import re
        s = re.sub(r"[^a-zA-Z0-9]+", "-", self.customer.company_name.lower()).strip("-")
        return f"{s}-{self.manifest_id[-6:]}"

    def summary(self) -> dict[str, Any]:
        return {
            "app_slug": self.app_slug(),
            "capabilities": [c.value for c in self.capabilities],
            "deployment": self.deployment.value,
            "n_data_sources": len(self.data_sources),
            "n_kpis": len(self.kpis),
            "n_roles": len(self.rbac.roles),
            "observability_tier": self.observability.tier.value,
        }
