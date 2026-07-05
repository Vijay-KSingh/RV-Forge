"""Generator: Manifest → Customer Application Package.

Produces a self-contained directory at output_dir/<app_slug>/ with:
  app/                — FastAPI backend (uses forge.intelligence as a library)
  frontend/           — pre-configured React SPA (rewires to the customer's KPIs)
  infra/              — Terraform + docker-compose
  observability/      — Prometheus, Grafana, Loki configs
  .github/workflows/  — CI pipeline with quality gates
  manifest.yaml       — the input manifest (versioned)
  README.md           — customer-facing run guide
  rbac/policy.yaml    — derived RBAC policy

The generator is a pure function: same manifest → identical bytes (modulo
timestamps in headers). This is what makes generated apps re-generatable
when the manifest changes.

We stream progress through a callback so the UI can show real-time updates.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import yaml

from forge.manifest import Manifest


@dataclass
class BuildEvent:
    step: str
    status: str  # "started" | "ok" | "error" | "info"
    message: str = ""
    progress_pct: int = 0


ProgressCallback = Callable[[BuildEvent], None]


class Generator:
    def __init__(self, manifest: Manifest, output_root: Path,
                 templates_root: Path,
                 on_progress: Optional[ProgressCallback] = None):
        self.manifest = manifest
        self.output_root = Path(output_root)
        self.templates_root = Path(templates_root)
        self.on_progress = on_progress or (lambda ev: None)
        self.app_slug = manifest.app_slug()
        self.target_dir = self.output_root / self.app_slug

    def generate(self) -> Path:
        steps = [
            ("scaffold",    "Scaffolding project tree",        self._scaffold),
            ("manifest",    "Writing manifest + RBAC policy",  self._write_manifest),
            ("backend",     "Generating backend application",  self._gen_backend),
            ("frontend",    "Generating frontend application", self._gen_frontend),
            ("rbac",        "Compiling RBAC policy",            self._gen_rbac),
            ("kpis",        "Wiring KPI catalog",               self._gen_kpis),
            ("data_sources","Configuring data source adapters", self._gen_datasources),
            ("observability","Configuring observability stack", self._gen_observability),
            ("docker",      "Generating Docker assets",         self._gen_docker),
            ("infra",       "Generating Terraform IaC",         self._gen_terraform),
            ("cicd",        "Generating CI/CD pipeline",        self._gen_cicd),
            ("docs",        "Generating customer README",       self._gen_docs),
        ]
        total = len(steps)
        for i, (key, label, fn) in enumerate(steps):
            pct = int(i * 100 / total)
            self.on_progress(BuildEvent(step=key, status="started", message=label, progress_pct=pct))
            try:
                fn()
            except Exception as e:
                self.on_progress(BuildEvent(step=key, status="error",
                                            message=f"{label} failed: {e}", progress_pct=pct))
                raise
            self.on_progress(BuildEvent(step=key, status="ok", message=f"{label} ✓",
                                        progress_pct=int((i + 1) * 100 / total)))
        self.on_progress(BuildEvent(step="done", status="ok",
                                    message=f"Application '{self.app_slug}' ready at {self.target_dir}",
                                    progress_pct=100))
        return self.target_dir

    # ── individual steps ──────────────────────────────────────────────

    def _scaffold(self):
        if self.target_dir.exists():
            shutil.rmtree(self.target_dir)
        for sub in ["app", "app/api", "app/data", "frontend", "frontend/src",
                    "infra", "observability/prometheus", "observability/grafana/dashboards",
                    "observability/loki", ".github/workflows", "rbac", "scripts"]:
            (self.target_dir / sub).mkdir(parents=True, exist_ok=True)

    def _write_manifest(self):
        path = self.target_dir / "manifest.yaml"
        # YAML is friendlier than JSON for humans editing later
        path.write_text(yaml.safe_dump(self.manifest.model_dump(mode="json"),
                                        sort_keys=False, default_flow_style=False),
                        encoding="utf-8")

    def _gen_backend(self):
        backend_template = self.templates_root / "backend"
        target = self.target_dir / "app"
        for src in backend_template.rglob("*"):
            if src.is_file():
                rel = src.relative_to(backend_template)
                dst = target / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                content = src.read_text(encoding="utf-8")
                content = self._render_vars(content)
                dst.write_text(content, encoding="utf-8")

    def _gen_frontend(self):
        frontend_template = self.templates_root / "frontend"
        target = self.target_dir / "frontend"
        for src in frontend_template.rglob("*"):
            if src.is_file():
                rel = src.relative_to(frontend_template)
                dst = target / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                content = src.read_text(encoding="utf-8")
                content = self._render_vars(content)
                dst.write_text(content, encoding="utf-8")

    def _gen_rbac(self):
        path = self.target_dir / "rbac" / "policy.yaml"
        rbac = self.manifest.rbac.model_dump(mode="json")
        path.write_text(yaml.safe_dump(rbac, sort_keys=False), encoding="utf-8")

    def _gen_kpis(self):
        path = self.target_dir / "app" / "data" / "kpis.json"
        path.write_text(json.dumps(
            [k.model_dump(mode="json") for k in self.manifest.kpis], indent=2),
            encoding="utf-8")
        # Audiences too (drive smart query suggestions)
        aud_path = self.target_dir / "app" / "data" / "audiences.json"
        aud_path.write_text(json.dumps(
            [a.model_dump(mode="json") for a in self.manifest.audiences], indent=2),
            encoding="utf-8")

    def _gen_datasources(self):
        path = self.target_dir / "app" / "data" / "datasources.json"
        # Strip secret_ref values for safety; they're still in manifest.yaml
        out = []
        for ds in self.manifest.data_sources:
            entry = ds.model_dump(mode="json")
            entry["connection_template_safe"] = entry.pop("connection_template", "")
            out.append(entry)
        path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    def _gen_observability(self):
        obs_template = self.templates_root / "observability"
        target = self.target_dir / "observability"
        for src in obs_template.rglob("*"):
            if src.is_file():
                rel = src.relative_to(obs_template)
                dst = target / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                content = src.read_text(encoding="utf-8")
                content = self._render_vars(content)
                dst.write_text(content, encoding="utf-8")

    def _gen_docker(self):
        compose_template = self.templates_root / "infra" / "docker-compose.yml"
        if compose_template.exists():
            content = self._render_vars(compose_template.read_text(encoding="utf-8"))
            (self.target_dir / "docker-compose.yml").write_text(content, encoding="utf-8")
        # Dockerfile for backend
        df = self.templates_root / "infra" / "Dockerfile.backend"
        if df.exists():
            (self.target_dir / "Dockerfile.backend").write_text(
                self._render_vars(df.read_text(encoding="utf-8")), encoding="utf-8")
        df_fe = self.templates_root / "infra" / "Dockerfile.frontend"
        if df_fe.exists():
            (self.target_dir / "Dockerfile.frontend").write_text(
                self._render_vars(df_fe.read_text(encoding="utf-8")), encoding="utf-8")

    def _gen_terraform(self):
        tf_template = self.templates_root / "infra" / "terraform"
        if not tf_template.exists():
            return
        target = self.target_dir / "infra" / "terraform"
        target.mkdir(parents=True, exist_ok=True)
        for src in tf_template.rglob("*"):
            if src.is_file():
                rel = src.relative_to(tf_template)
                dst = target / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(self._render_vars(src.read_text(encoding="utf-8")), encoding="utf-8")

    def _gen_cicd(self):
        cicd_template = self.templates_root / "cicd"
        if not cicd_template.exists():
            return
        target = self.target_dir / ".github" / "workflows"
        for src in cicd_template.rglob("*.yml"):
            content = self._render_vars(src.read_text(encoding="utf-8"))
            (target / src.name).write_text(content, encoding="utf-8")

    def _gen_docs(self):
        readme = f"""# {self.manifest.customer.company_name} — Forge Application

**Slug:** `{self.app_slug}`
**Generated:** {self.manifest.created_at.isoformat()}
**Manifest version:** {self.manifest.schema_version}

## What this is

This is a customer-tailored application generated from a Forge manifest. It includes:
- A FastAPI backend with the Forge intelligence engine (NL-query, anomaly detection, what-if).
- A React SPA pre-configured with your selected KPIs and personas.
- An RBAC policy enforced down to row & column.
- An observability stack (Prometheus + Grafana + Loki) bundled in docker-compose.
- A Terraform IaC skeleton for {self.manifest.deployment.value}.
- A GitHub Actions CI/CD pipeline with quality gates.

## Capabilities enabled

{chr(10).join(f"- {c.value}" for c in self.manifest.capabilities)}

## KPIs configured ({len(self.manifest.kpis)})

{chr(10).join(f"- **{k.name}** ({k.domain}) — {k.formula}" for k in self.manifest.kpis[:15])}
{("- … and " + str(len(self.manifest.kpis) - 15) + " more") if len(self.manifest.kpis) > 15 else ""}

## How to run (localhost)

```bash
docker-compose up --build
```

- Backend:    http://localhost:8000
- Frontend:   http://localhost:3000  (admin / change-me-on-first-login)
- Grafana:    http://localhost:3001
- Prometheus: http://localhost:9090

## Where the secrets live

Connection strings and API keys are NOT in this repo. They are referenced via
`secret_ref:` in `manifest.yaml`. On localhost they resolve from `.env`. In
production, they resolve from your cloud's secret manager (configured in
`infra/terraform/`).
"""
        (self.target_dir / "README.md").write_text(readme, encoding="utf-8")

    # ── utilities ─────────────────────────────────────────────────────

    def _render_vars(self, content: str) -> str:
        """Tiny placeholder substitution. We deliberately avoid Jinja to keep
        the dep tree minimal — the templates only need a handful of vars."""
        b = self.manifest.branding
        replacements = {
            "{{APP_SLUG}}":     self.app_slug,
            "{{APP_NAME}}":     b.get("app_name", self.manifest.customer.company_name + " Insights"),
            "{{COMPANY}}":      self.manifest.customer.company_name,
            "{{PRIMARY_COLOR}}": b.get("primary_color", "#0F62FE"),
            "{{ACCENT_COLOR}}": b.get("accent_color", "#6929C4"),
            "{{INDUSTRY}}":     self.manifest.customer.industry or "general",
            "{{REGION}}":       self.manifest.cloud_region,
            "{{DEPLOYMENT}}":   self.manifest.deployment.value,
            "{{OBS_TIER}}":     self.manifest.observability.tier.value,
        }
        for k, v in replacements.items():
            content = content.replace(k, str(v))
        return content
