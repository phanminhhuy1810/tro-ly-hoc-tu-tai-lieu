#!/bin/sh
# Run existing backend and frontend regression suites from the project root.
set -eu
study_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$study_root"
PYTHONPATH="$study_root/backend" .venv/bin/python -m unittest discover -s backend/tests -v
node --test frontend/tests/*.test.cjs
if [ -d web/node_modules ]; then
    (cd web && npm run typecheck && npm test)
else
    printf '%s\n' 'Skipping web/ tests: run "cd web && npm ci" once to install them.'
fi
