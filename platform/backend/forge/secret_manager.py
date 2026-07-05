"""Secret manager for connection strings and API keys.

Design principles (the architect's red lines):
1. Secrets are NEVER persisted in the manifest, in logs, in error messages,
   or in API responses.
2. The manifest holds a `secret_ref` (e.g. "secret://forge/customer123/db_revenue").
3. This module is the only thing that resolves a ref to a value.
4. At rest, secrets are encrypted with Fernet (AES-128-CBC + HMAC).
5. The KEK (key-encryption-key) is loaded from FORGE_MASTER_KEY env var
   in production. For the demo we use an ephemeral key written to disk
   and gitignored.
6. We expose only `store_secret`, `get_secret`, `delete_secret`,
   `list_refs`. We do NOT expose iteration over secret values.
7. Audit log entry written for every read.

For real deployments swap the backend to AWS Secrets Manager / HashiCorp
Vault / Azure Key Vault — the SecretManager interface is stable.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def _utc_iso() -> str:
    """Timezone-aware UTC timestamp in the legacy '...Z' wire format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


_REF_PATTERN = re.compile(r"^secret://[a-z0-9_\-]+(/[a-z0-9_\-]+)+$", re.IGNORECASE)


def _ref_is_valid(ref: str) -> bool:
    return bool(_REF_PATTERN.match(ref))


@dataclass
class SecretRecord:
    ref: str
    created_at: str
    last_accessed: Optional[str] = None
    access_count: int = 0
    description: str = ""


class SecretManager:
    """Filesystem-backed encrypted secret store. Suitable for the localhost
    demo. In production: replace _read/_write with the cloud secret service
    of choice."""

    def __init__(self, root: Optional[Path] = None, master_key: Optional[bytes] = None):
        self.root = Path(root or os.environ.get("FORGE_SECRET_ROOT", "./.forge_secrets"))
        self.root.mkdir(parents=True, exist_ok=True)
        self._keypath = self.root / ".key"
        self._fernet = Fernet(self._resolve_master_key(master_key))
        self._index_path = self.root / "index.json"
        self._audit_path = self.root / "audit.log"
        self._index_lock = threading.Lock()

    def _resolve_master_key(self, override: Optional[bytes]) -> bytes:
        if override:
            return override
        env = os.environ.get("FORGE_MASTER_KEY", "").strip()
        if env:
            # Accept either the raw base64 key (Fernet.generate_key().decode())
            # or an accidental repr form like b'...'. Validate before use so a
            # malformed key fails loudly instead of silently corrupting secrets.
            if env.startswith("b'") and env.endswith("'"):
                env = env[2:-1]
            key = env.encode("ascii")
            try:
                if len(base64.urlsafe_b64decode(key)) != 32:
                    raise ValueError
            except Exception as exc:  # noqa: BLE001 — surface a clear config error
                raise ValueError(
                    "FORGE_MASTER_KEY must be a urlsafe-base64 32-byte Fernet key "
                    "(output of Fernet.generate_key().decode())."
                ) from exc
            return key
        # demo path: persist a key once, reuse forever
        if self._keypath.exists():
            return self._keypath.read_bytes()
        key = Fernet.generate_key()
        self._keypath.write_bytes(key)
        try:
            os.chmod(self._keypath, 0o600)
        except OSError:
            pass
        return key

    # ── Public API ─────────────────────────────────────────────────────

    def store_secret(self, ref: str, value: str, description: str = "") -> SecretRecord:
        if not _ref_is_valid(ref):
            raise ValueError(f"Invalid secret ref format: {ref}")
        if not value:
            raise ValueError("Refusing to store empty secret")
        path = self._path_for(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        ciphertext = self._fernet.encrypt(value.encode("utf-8"))
        path.write_bytes(ciphertext)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        record = SecretRecord(
            ref=ref,
            created_at=_utc_iso(),
            description=description,
        )
        self._update_index(record)
        self._audit("STORE", ref)
        # NB: never log `value`. Only log ref.
        logger.info("Stored secret ref=%s", ref)
        return record

    def get_secret(self, ref: str, accessor: str = "system") -> str:
        """Returns the plaintext secret. Caller is responsible for not leaking it.
        We deliberately do NOT log or echo the value."""
        if not _ref_is_valid(ref):
            raise ValueError(f"Invalid secret ref format: {ref}")
        path = self._path_for(ref)
        if not path.exists():
            self._audit("MISS", ref, accessor=accessor)
            raise KeyError(f"No secret found for {ref}")
        try:
            plaintext = self._fernet.decrypt(path.read_bytes()).decode("utf-8")
        except InvalidToken:
            self._audit("DECRYPT_FAILURE", ref, accessor=accessor)
            raise RuntimeError("Master key mismatch — cannot decrypt secret. "
                               "Either FORGE_MASTER_KEY changed or the file was tampered with.")
        self._audit("READ", ref, accessor=accessor)
        self._increment_access(ref)
        return plaintext

    def delete_secret(self, ref: str) -> bool:
        path = self._path_for(ref)
        if not path.exists():
            return False
        path.unlink()
        self._remove_from_index(ref)
        self._audit("DELETE", ref)
        return True

    def list_refs(self) -> list[SecretRecord]:
        idx = self._load_index()
        return [SecretRecord(**v) for v in idx.values()]

    # ── Helpers ────────────────────────────────────────────────────────

    def _path_for(self, ref: str) -> Path:
        # ref format: secret://ns/sub/.../key  → <root>/ns/sub/.../key.enc
        rel = ref.replace("secret://", "").replace("/", "_") + ".enc"
        return self.root / rel

    def _load_index(self) -> dict:
        if not self._index_path.exists():
            return {}
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_index(self, idx: dict):
        # Write to a temp file then atomically replace, so a crash mid-write
        # never leaves a truncated/corrupt index.
        tmp = self._index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(idx, indent=2), encoding="utf-8")
        os.replace(tmp, self._index_path)
        try:
            os.chmod(self._index_path, 0o600)
        except OSError:
            pass

    def _update_index(self, record: SecretRecord):
        with self._index_lock:
            idx = self._load_index()
            idx[record.ref] = record.__dict__
            self._save_index(idx)

    def _remove_from_index(self, ref: str):
        with self._index_lock:
            idx = self._load_index()
            idx.pop(ref, None)
            self._save_index(idx)

    def _increment_access(self, ref: str):
        with self._index_lock:
            idx = self._load_index()
            if ref in idx:
                idx[ref]["last_accessed"] = _utc_iso()
                idx[ref]["access_count"] = idx[ref].get("access_count", 0) + 1
                self._save_index(idx)

    def _audit(self, action: str, ref: str, accessor: str = "system"):
        try:
            line = json.dumps({
                "ts": _utc_iso(),
                "action": action,
                "ref": ref,
                "accessor": accessor,
            })
            with self._audit_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            logger.warning("Failed to write audit log: %s", e)


# Singleton accessor (lazily initialized, thread-safe double-checked locking)
_default: Optional[SecretManager] = None
_default_lock = threading.Lock()


def default_manager() -> SecretManager:
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = SecretManager()
    return _default
