#!/bin/bash
# QUILL — local web demo launcher.
# Run from the repo root or from inside web/. Either works.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

# Pick up API keys from ~/.bashrc if they were exported there.
if [ -f "$HOME/.bashrc" ]; then
    eval "$(grep -E '^export (GROQ|GEMINI)_API_KEY=' "$HOME/.bashrc" || true)"
fi

# Activate venv if not already active.
if [ -z "${VIRTUAL_ENV:-}" ] && [ -d "venv" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

PORT="${QUILL_PORT:-8000}"
HOST="${QUILL_HOST:-127.0.0.1}"

echo "Starting QUILL web demo on http://${HOST}:${PORT}"
exec uvicorn web.app:app --host "$HOST" --port "$PORT" --log-level info
