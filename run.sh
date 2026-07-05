#!/usr/bin/env bash
# Forge — native (no-Docker) launcher for the platform API + wizard UI.
#
#   ./run.sh            # set up venv if needed, then serve on :8800
#   ./run.sh --core     # install only the core deps (skip the heavy ML stack)
#   PORT=9000 ./run.sh  # override the port
#
# After it boots, open http://localhost:8800 for the Forge wizard.
set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-8800}"
HOST="${HOST:-0.0.0.0}"
VENV=".venv"

# Resolve a python interpreter.
PY="$(command -v python || command -v python3 || true)"
[ -z "$PY" ] && { echo "error: python not found on PATH" >&2; exit 1; }

# venv layout differs across platforms.
if [ -x "$VENV/Scripts/python.exe" ]; then VPY="$VENV/Scripts/python.exe"   # Windows
elif [ -x "$VENV/bin/python" ];    then VPY="$VENV/bin/python"             # POSIX
else VPY=""; fi

if [ -z "$VPY" ]; then
  echo "==> creating virtualenv in $VENV"
  "$PY" -m venv "$VENV"
  if [ -x "$VENV/Scripts/python.exe" ]; then VPY="$VENV/Scripts/python.exe"; else VPY="$VENV/bin/python"; fi
  "$VPY" -m pip install --quiet --upgrade pip

  REQ="requirements.txt"
  if [ "${1:-}" = "--core" ]; then
    echo "==> installing CORE deps only (wizard + generator)"
    "$VPY" -m pip install fastapi "uvicorn[standard]" pydantic cryptography pyyaml python-multipart
  else
    echo "==> installing full stack from $REQ (this includes the ML libraries)"
    "$VPY" -m pip install -r "$REQ"
  fi
fi

# Load .env if present (export each non-comment KEY=VALUE line).
if [ -f .env ]; then
  echo "==> loading .env"
  set -a; . ./.env; set +a
fi

# UTF-8 everywhere so logs/IO never crash on a non-UTF-8 console (e.g. Windows).
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export PYTHONPATH="platform/backend"

echo "==> Forge wizard:  http://localhost:${PORT}"
echo "==> health:        http://localhost:${PORT}/health"
exec "$VPY" -m uvicorn forge.api:app --app-dir platform/backend --host "$HOST" --port "$PORT"
