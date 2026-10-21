#!/bin/sh
# Run from any directory. SQLite/originals stay under this project.
set -eu
study_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$study_root"
if [ ! -x .venv/bin/python ]; then
    printf '%s\n' 'Create the project environment first: python3 -m venv .venv' 'Then: .venv/bin/python -m pip install -r backend/requirements-lock.txt' >&2
    exit 1
fi
export PYTHONPATH="$study_root/backend"
exec .venv/bin/python -m uvicorn study_backend.app:create_app --factory --host 127.0.0.1 --port 8770 --no-access-log
