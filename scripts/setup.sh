#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
npm ci
.venv/bin/python scripts/prepare_assistant_models.py
.venv/bin/python scripts/prepare_access_runtime.py
npm run build
.venv/bin/python -m pytest
printf '\nArranque: .venv/bin/python scripts/run_preview.py\n'
