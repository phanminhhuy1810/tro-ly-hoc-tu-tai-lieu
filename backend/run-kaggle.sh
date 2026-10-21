#!/bin/sh
# Private runtime config only. Run run-backend.sh normally to return to local AI.
set -eu
study_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export STUDY_PROVIDER=kaggle
export STUDY_KAGGLE_CONFIG="${STUDY_KAGGLE_CONFIG:-$study_root/backend/runtime/kaggle-private.json}"
exec sh "$study_root/backend/run-backend.sh"
