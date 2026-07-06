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

import json
import logging
import os
import signal
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
_IS_WINDOWS = os.name == "nt"
# Records of launched child processes, so a fresh Forge can reap orphans left
# behind by a previously force-killed one. Lives inside generated_apps/ (gitignored).
_DEFAULT_STATE_FILE = Path(__file__).resolve().parents[3] / "generated_apps" / ".forge_runs.json"


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _pids_on_port(port: int) -> set:
    """PIDs currently LISTENING on ``port`` (best-effort, per-OS). Used to
    verify a recorded orphan is still the process holding its port before we
    kill it — which makes killing a recycled PID essentially impossible."""
    pids: set = set()
    try:
        if _IS_WINDOWS:
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                                 capture_output=True, text=True, timeout=8).stdout
            needle = f":{port} "
            for line in out.splitlines():
                if needle in line and "LISTENING" in line:
                    parts = line.split()
                    if parts and parts[-1].isdigit():
                        pids.add(int(parts[-1]))
        else:
            out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                                 capture_output=True, text=True, timeout=8).stdout
            pids = {int(t) for t in out.split() if t.isdigit()}
    except Exception:
        log.debug("port scan for %s failed", port, exc_info=True)
    return pids


def _kill_tree(pid: int) -> None:
    """Kill a process *and its children*. On Windows `python -m uvicorn` runs
    the real server as a child of the launcher, so we must take the whole tree
    (/T) — terminating just the launcher leaves the server orphaned."""
    try:
        if _IS_WINDOWS:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=8)
        else:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.4)
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    except Exception:
        log.debug("kill tree %s ignored", pid, exc_info=True)


_OUR_SIGNATURES = ("uvicorn", "_static_server", "main:app")


def _cmdline(pid: int) -> str:
    try:
        if _IS_WINDOWS:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}')"
                 f".CommandLine"],
                capture_output=True, text=True, timeout=8).stdout
            return out or ""
        return Path(f"/proc/{pid}/cmdline").read_text(errors="replace").replace("\0", " ")
    except Exception:
        return ""


def _looks_like_ours(pid: int) -> bool:
    """True if the process holding a port is a generated-app server we launched
    (guards against killing an unrelated process that reused the port)."""
    cl = _cmdline(pid).lower()
    return any(sig in cl for sig in _OUR_SIGNATURES)


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

    def __init__(self, state_file: Path | None = None) -> None:
        self._apps: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._state_file = state_file or _DEFAULT_STATE_FILE

    # ── crash-safe run registry ──────────────────────────────────────
    def _persist(self) -> None:
        """Write the PIDs/ports of live apps so a future Forge can reap them.
        Call while holding the lock."""
        records = {
            app_id: {
                "backend_pid": rec["meta"].get("backend_pid"),
                "frontend_pid": rec["meta"].get("frontend_pid"),
                "backend_port": rec["meta"].get("backend_port"),
                "frontend_port": rec["meta"].get("frontend_port"),
                "started_at": rec["meta"].get("started_at"),
            }
            for app_id, rec in self._apps.items()
        }
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(records, indent=2), encoding="utf-8")
        except OSError:
            log.debug("could not persist run state", exc_info=True)

    def reap_orphans(self) -> None:
        """Kill generated-app servers left over from a force-killed Forge.

        Keyed on the *port* we recorded, not the PID: the real server runs under
        a different PID than the launcher we tracked, and after a crash the tree
        is broken. We kill whoever now holds a recorded port, but only if its
        command line matches one of our servers — so an unrelated process that
        happened to reuse the port is left alone."""
        try:
            records = json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            records = {}
        ports = set()
        for rec in (records or {}).values():
            for port_key in ("backend_port", "frontend_port"):
                if rec.get(port_key):
                    ports.add(int(rec[port_key]))
        reaped = 0
        for port in ports:
            for pid in _pids_on_port(port):
                if _looks_like_ours(pid):
                    _kill_tree(pid)
                    reaped += 1
        if reaped:
            log.info("Reaped %d orphaned generated-app process(es) from a prior run", reaped)
        try:
            self._state_file.unlink()  # this process owns nothing yet
        except OSError:
            pass

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
            self._persist()
        log.info("Launched generated app %s (backend %s, frontend %s)",
                 app_id, backend_port, frontend_port)
        return {"app_id": app_id, "running": True, "reused": False, **meta}

    def stop(self, app_id: str) -> dict:
        with self._lock:
            rec = self._apps.pop(app_id, None)
            self._persist()
        if not rec:
            return {"app_id": app_id, "running": False, "stopped": False}
        self._terminate(rec)
        log.info("Stopped generated app %s", app_id)
        return {"app_id": app_id, "running": False, "stopped": True}

    def stop_all(self) -> None:
        with self._lock:
            recs = list(self._apps.values())
            self._apps.clear()
            self._persist()
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
        meta = rec.get("meta", {})
        for key in ("backend", "frontend"):
            proc = rec.get(key)
            if not proc:
                continue
            _kill_tree(proc.pid)  # tree-kill: the real server is a child of the launcher
            try:
                proc.wait(timeout=5)
            except Exception:  # already gone / not waitable
                log.debug("wait %s ignored", key, exc_info=True)
        # Belt-and-suspenders: if a server child got reparented and survived the
        # tree-kill, clear it by its known port too.
        for port_key in ("backend_port", "frontend_port"):
            port = meta.get(port_key)
            if port:
                for pid in _pids_on_port(int(port)):
                    if _looks_like_ours(pid):
                        _kill_tree(pid)
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
