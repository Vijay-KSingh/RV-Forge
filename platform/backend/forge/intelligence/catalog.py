"""Generic semantic catalog.

What changed vs ram_intelligence:
- ram_intelligence.schema.canonical_schema is HARDCODED to HP TIO workforce data.
- Here, the catalog is BUILT FROM THE MANIFEST. Each generated app gets its
  own catalog reflecting its own data sources, KPIs, and business rules.

This is what unlocks "spin up an analytics app for any customer" — the
intelligence layer is data-driven, not domain-coded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from forge.manifest import Manifest, KPIDefinition


@dataclass
class CanonicalField:
    name: str
    data_type: str  # "number" | "currency" | "percent" | "date" | "text" | "id"
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    sensitive: bool = False  # if true, defaults to mask for non-privileged roles
    sources: list[str] = field(default_factory=list)


@dataclass
class SemanticTable:
    name: str
    description: str = ""
    fields: list[CanonicalField] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)


@dataclass
class SemanticCatalog:
    """The runtime knowledge map for an app. NL-query, validator, SQL
    synthesizer, and RBAC all read from here."""
    tables: dict[str, SemanticTable] = field(default_factory=dict)
    kpis: dict[str, KPIDefinition] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)  # phrase -> canonical field name

    def find_field(self, term: str) -> Optional[CanonicalField]:
        term_l = term.lower().strip()
        # direct
        for table in self.tables.values():
            for f in table.fields:
                if f.name.lower() == term_l:
                    return f
                if term_l in (a.lower() for a in f.aliases):
                    return f
        # alias index
        canonical = self.aliases.get(term_l)
        if canonical:
            return self.find_field(canonical)
        return None

    def kpi_for_question(self, question: str) -> Optional[KPIDefinition]:
        q = question.lower()
        # exact name match wins
        for kpi in self.kpis.values():
            if kpi.name.lower() in q:
                return kpi
        # fall back to any token match
        for kpi in self.kpis.values():
            if any(tok in q for tok in kpi.name.lower().split()):
                return kpi
        return None


def build_catalog_from_manifest(manifest: Manifest) -> SemanticCatalog:
    """Construct the runtime catalog from the wizard's manifest.

    For each data source we synthesize a SemanticTable from its schema_hint.
    KPIs are indexed by id and by name.
    Aliases are derived from KPI names + audience suggested questions.
    """
    catalog = SemanticCatalog()

    for ds in manifest.data_sources:
        table = SemanticTable(
            name=ds.name,
            description=ds.description or f"Data from {ds.kind.value}",
        )
        hint = ds.schema_hint or {}
        for field_name, field_meta in (hint.get("fields") or {}).items():
            sensitive = bool(field_meta.get("sensitive", False))
            table.fields.append(CanonicalField(
                name=field_name,
                data_type=field_meta.get("type", "text"),
                description=field_meta.get("description", ""),
                aliases=field_meta.get("aliases", []),
                sensitive=sensitive,
                sources=[ds.id],
            ))
        if hint.get("primary_key"):
            table.primary_key = hint["primary_key"]
        catalog.tables[table.name] = table

    for kpi in manifest.kpis:
        catalog.kpis[kpi.id] = kpi
        catalog.aliases[kpi.name.lower()] = kpi.id

    # also allow domain-level aliases — "revenue" → fin_revenue_total etc.
    for kpi in manifest.kpis:
        toks = kpi.name.lower().split()
        if len(toks) >= 2:
            catalog.aliases[" ".join(toks[:2])] = kpi.id

    return catalog
