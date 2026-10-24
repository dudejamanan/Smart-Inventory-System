#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/backend"
if [[ "${1:-}" == "--hardware" ]]; then
  exec .venv/bin/python -m app
else
  exec .venv/bin/python -m app --simulate
fi
