#!/bin/sh
# Start the web/backend on 127.0.0.1:8770. Does not start Kaggle or download a model.
set -eu
study_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec sh "$study_root/backend/run-backend.sh"
