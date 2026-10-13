#!/usr/bin/env bash
set -euo pipefail
python3 /app/start.py &
owned_pid=$!
trap 'kill "$owned_pid" 2>/dev/null || true; wait "$owned_pid" 2>/dev/null || true' EXIT INT TERM
python3 /app/gpu_runtime_validation.py container --output-root /evidence --model "$SERVED_MODEL_NAME" --url http://127.0.0.1:8000
wait "$owned_pid"
