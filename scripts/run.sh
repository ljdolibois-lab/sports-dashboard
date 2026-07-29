#!/usr/bin/env bash
# Build yesterday's dashboard. This is what the scheduler calls.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

# Use the project venv if present, else whatever python3 is on PATH.
PY="$DIR/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

mkdir -p logs
exec "$PY" -m src.main "$@" >> logs/run.log 2>&1
