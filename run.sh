#!/usr/bin/env bash
# Start the API and UI at http://localhost:8000
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip -q install -r backend/requirements.txt
[ -f .env ] || { cp .env.example .env; echo "Created .env. Add ANTHROPIC_API_KEY, then re-run."; }
exec uvicorn backend.app:app --port "${PORT:-8000}"
