"""Run a Forge-generated app natively — no Docker required.

The generated apps ship a docker-compose.yml, but this machine (and many dev
boxes) has no Docker daemon. Every generated app is, however, a self-contained
FastAPI backend (``app/main.py``, reads local JSON — no database) plus a static
frontend (``frontend/``). Both run with the same interpreter Forge itself uses,
so we can launch them directly and hand back live URLs.

This module owns the lifecycle of those child processes: start, health-check,
status, and stop. It is deliberately dependency-free (stdlib only).
"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from forge.config import utc_iso

log = logging.getLogger("forge.app_runner")

_STATIC_SERVER = Path(__file__).with_name("_static_server.py")
_HEALTH_TIMEOUT_S = 25
_DEFAULT_BACKEND_PORT = 8000
_DEFAULT_FRONTEND_PORT = 3000


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _pick_port(preferred: int) -> int:
    """Prefer the compose-contract port; fall back to an OS-assigned free one."""
    if _port_free(preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _child_env() -> dict:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


class AppRunner:
    """Tracks the native processes for each running generated app."""

    def __init__(self) -> None:
        self._apps: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ── queries ──────────────────────────────────────────────────────
    def _alive(self, rec: dict) -> bool:
        be = rec.get("backend")
        fe = rec.get("frontend")
        return bool(be and be.poll() is None and fe and fe.poll() is None)

    def status(self, app_id: str) -> dict:
        with self._lock:
            rec = self._apps.get(app_id)
            if not rec or not self._alive(rec):
                return {"app_id": app_id, "running": False}
            return {"app_id": app_id, "running": True, **rec["meta"]}

    def get_meta(self, app_id: str) -> dict | None:
        """Return the live process metadata for a running app, or None."""
        with self._lock:
            rec = self._apps.get(app_id)
            if not rec or not self._alive(rec):
                return None
            return dict(rec["meta"])

    # ── lifecycle ────────────────────────────────────────────────────
    def run(self, app_id: str, app_dir: Path) -> dict:
        """Launch backend + frontend for ``app_dir``. Idempotent per app_id."""
        with self._lock:
            existing = self._apps.get(app_id)
            if existing and self._alive(existing):
                return {"app_id": app_id, "running": True, "reused": True, **existing["meta"]}
            # clean up a dead record if present
            if existing:
                self._terminate(existing)
                self._apps.pop(app_id, None)

        backend_dir = app_dir / "app"
        frontend_dir = app_dir / "frontend"
        main_py = backend_dir / "main.py"
        index_html = frontend_dir / "index.html"
        if not main_py.exists():
            raise FileNotFoundError(f"backend entrypoint not found: {main_py}")
        if not index_html.exists():
            raise FileNotFoundError(f"frontend not found: {index_html}")

        backend_port = _pick_port(_DEFAULT_BACKEND_PORT)
        frontend_port = _pick_port(_DEFAULT_FRONTEND_PORT)
        if frontend_port == backend_port:  # extremely unlikely, but be safe
            frontend_port = _pick_port(_DEFAULT_FRONTEND_PORT + 1)

        api_base = f"http://localhost:{backend_port}"
        log_path = app_dir / ".forge_run.log"
        logf = open(log_path, "w", encoding="utf-8")

        env = _child_env()
        env["PORT"] = str(backend_port)

        backend = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app",
             "--host", "127.0.0.1", "--port", str(backend_port)],
            cwd=str(backend_dir), env=env, stdout=logf, stderr=subprocess.STDOUT,
        )
        frontend = subprocess.Popen(
            [sys.executable, str(_STATIC_SERVER), str(frontend_dir),
             str(frontend_port), api_base],
            cwd=str(frontend_dir), env=env, stdout=logf, stderr=subprocess.STDOUT,
        )

        meta = {
            "backend_url": api_base,
            "frontend_url": f"http://localhost:{frontend_port}",
            "health_url": f"{api_base}/health",
            "app_dir": str(app_dir),
            "backend_port": backend_port,
            "frontend_port": frontend_port,
            "backend_pid": backend.pid,
            "frontend_pid": frontend.pid,
            "log_path": str(log_path),
            "started_at": utc_iso(),
        }
        rec = {"backend": backend, "frontend": frontend, "meta": meta, "logf": logf}

        healthy = self._await_health(api_base, backend, frontend)
        if not healthy:
            self._terminate(rec)
            tail = _tail(log_path)
            raise RuntimeError(f"generated app failed to start. Recent log:\n{tail}")

        with self._lock:
            self._apps[app_id] = rec
        log.info("Launched generated app %s (backend %s, frontend %s)",
                 app_id, backend_port, frontend_port)
        return {"app_id": app_id, "running": True, "reused": False, **meta}

    def stop(self, app_id: str) -> dict:
        with self._lock:
            rec = self._apps.pop(app_id, None)
        if not rec:
            return {"app_id": app_id, "running": False, "stopped": False}
        self._terminate(rec)
        log.info("Stopped generated app %s", app_id)
        return {"app_id": app_id, "running": False, "stopped": True}

    def stop_all(self) -> None:
        with self._lock:
            recs = list(self._apps.values())
            self._apps.clear()
        for rec in recs:
            self._terminate(rec)

    # ── internals ────────────────────────────────────────────────────
    def _await_health(self, api_base: str, backend, frontend) -> bool:
        deadline = time.monotonic() + _HEALTH_TIMEOUT_S
        while time.monotonic() < deadline:
            if backend.poll() is not None or frontend.poll() is not None:
                return False  # a child died during startup
            try:
                with urlopen(f"{api_base}/health", timeout=2) as r:
                    if r.status == 200:
                        return True
            except (URLError, OSError):
                pass
            time.sleep(0.4)
        return False

    def _terminate(self, rec: dict) -> None:
        for key in ("backend", "frontend"):
            proc = rec.get(key)
            if not proc:
                continue
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception:  # process may already be gone
                log.debug("terminate %s ignored", key, exc_info=True)
        logf = rec.get("logf")
        if logf:
            try:
                logf.close()
            except Exception:
                pass


def _tail(path: Path, lines: int = 20) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(no log)"
    return "\n".join(text.splitlines()[-lines:])


# Module-level singleton used by the API.
runner = AppRunner()
