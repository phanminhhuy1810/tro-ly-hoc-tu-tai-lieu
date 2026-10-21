#!/bin/sh
# Local inference only. Run in its own terminal; Ctrl+C stops the server.
set -eu
if ! command -v ollama >/dev/null 2>&1; then
    printf '%s\n' 'Ollama is missing. Install with: brew install ollama' >&2
    exit 1
fi
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_NO_CLOUD=1
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_CONTEXT_LENGTH=8192
export OLLAMA_KEEP_ALIVE=5m
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_KV_CACHE_TYPE=q8_0
export OLLAMA_MAX_TRANSFER_STREAMS=64
# Keep verified blobs from an interrupted pull until its manifest is committed.
export OLLAMA_NOPRUNE=1
exec ollama serve
