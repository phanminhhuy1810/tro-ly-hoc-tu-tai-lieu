#!/bin/sh
# Start the web/backend on 127.0.0.1:8770. Does not start Kaggle or download a model.
# The new interface (web/) is built once if web/dist is missing; the previous
# interface stays at http://127.0.0.1:8770/legacy/.
set -eu
study_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ ! -f "$study_root/web/dist/index.html" ]; then
    if command -v npm >/dev/null 2>&1; then
        printf '%s\n' 'Building the new interface in web/ (first run only)...'
        (cd "$study_root/web" && { [ -d node_modules ] || npm ci --no-audit --no-fund; } && npm run build)
    else
        printf '%s\n' 'npm not found: serving the previous interface. Install Node.js, then run: cd web && npm ci && npm run build' >&2
    fi
fi
exec sh "$study_root/backend/run-backend.sh"
