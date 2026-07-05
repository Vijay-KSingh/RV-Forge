"""Central configuration, time, identity-validation and logging helpers.

Everything that used to be scattered across module-level constants and ad-hoc
``os.environ`` reads lives here, so the application can be configured per
environment (local / staging / prod) without code changes and validated once
at startup.

Design goals:
  * Safe, permissive defaults so the localhost demo and the test-suite run with
    zero configuration.
  * A single switch (``FORGE_API_KEY``) that locks the API down for production.
  * UTC time helpers that are correct on Python 3.12+ (``datetime.utcnow`` is
    deprecated and returns a naive datetime).
  * Strict identifier validation to close path-traversal vectors on the file
    paths the API builds from user input.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ── Time helpers (timezone-aware UTC; utcnow() is deprecated in 3.12+) ────────

def utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def utc_iso() -> str:
    """ISO-8601 UTC timestamp ending in 'Z' (preserves the legacy wire format)."""
    return utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ── Identifier validation (path-traversal defense) ───────────────────────────

# Generic safe id: letters, digits, underscore, hyphen. No path separators,
# no '..', bounded length. Used for customer_id / kpi_id and similar.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Manifest ids are minted as f"mfst_{uuid4().hex[:12]}".
_MANIFEST_ID_RE = re.compile(r"^mfst_[0-9a-f]{12}$")

# Build ids are minted as f"bld_{uuid4().hex[:10]}".
_BUILD_ID_RE = re.compile(r"^bld_[0-9a-f]{10}$")


def is_safe_id(value: str) -> bool:
    return bool(_SAFE_ID_RE.match(value))


def is_safe_manifest_id(value: str) -> bool:
    return bool(_MANIFEST_ID_RE.match(value))


def is_safe_build_id(value: str) -> bool:
    return bool(_BUILD_ID_RE.match(value))


def safe_id(value: str, field_name: str = "id") -> str:
    """Validate a path-component identifier or raise ValueError."""
    if not is_safe_id(value):
        raise ValueError(
            f"{field_name} must match [A-Za-z0-9_-] and be 1-64 chars; got {value!r}"
        )
    return value


def resolve_within(root: Path, *parts: str) -> Path:
    """Join ``parts`` onto ``root`` and assert the result stays inside ``root``.

    Defends against ``..`` traversal and absolute-path escapes regardless of
    how the individual parts were validated.
    """
    root = root.resolve()
    candidate = root.joinpath(*parts).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Resolved path escapes its permitted root")
    return candidate


# ── Settings ─────────────────────────────────────────────────────────────────

def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Runtime configuration, resolved from the environment at import time."""

    # CORS. Default "*" is convenient for local dev; when it is the wildcard we
    # force allow_credentials=False to stay spec-compliant (browsers reject
    # wildcard-origin + credentials). Set FORGE_ALLOWED_ORIGINS to a real
    # comma-separated allowlist in production.
    allowed_origins: list[str] = field(default_factory=lambda: _env_list("FORGE_ALLOWED_ORIGINS", ["*"]))

    # Optional API key. When set (FORGE_API_KEY), every /api/* request must send
    # it via "X-API-Key: <key>" or "Authorization: Bearer <key>". When empty
    # (the default) the API is open, so the demo and tests need no config.
    api_key: str = field(default_factory=lambda: os.environ.get("FORGE_API_KEY", "").strip())

    # Input bounds (DoS defense). Generous enough for any real series.
    max_series_points: int = field(default_factory=lambda: _env_int("FORGE_MAX_SERIES_POINTS", 200_000))

    # In-memory build registry retention (eviction cap to bound memory).
    max_builds_in_memory: int = field(default_factory=lambda: _env_int("FORGE_MAX_BUILDS_IN_MEMORY", 500))

    # Default root for ML model artifacts written/read by the ML endpoints.
    artifact_root: Path = field(default_factory=lambda: Path(os.environ.get("FORGE_ARTIFACT_ROOT", "/data/models")))

    # Expose absolute internal paths on /health? Off by default (info leak).
    health_verbose: bool = field(default_factory=lambda: _env_bool("FORGE_HEALTH_VERBOSE", False))

    @property
    def cors_allow_credentials(self) -> bool:
        return "*" not in self.allowed_origins


settings = Settings()


# ── Logging ──────────────────────────────────────────────────────────────────

def configure_logging() -> None:
    """Configure root logging with an ASCII format and a UTF-8/■-tolerant stream.

    The previous format embedded a '·' and build messages contain '✓'; on a
    non-UTF-8 console (e.g. Windows cp1252) writing those raised
    UnicodeEncodeError mid-request. We force UTF-8 on the stream when possible
    and fall back to backslash-replacement so a log line can never crash a
    request handler.
    """
    stream = sys.stdout
    try:
        # Python 3.7+: make the stream tolerant of any unicode in messages.
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s - %(message)s"
    ))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
