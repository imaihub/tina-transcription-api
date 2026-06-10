#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/api.pid"
LOG_DIR="$SCRIPT_DIR/logs"

mkdir -p "$LOG_DIR"

bash "$SCRIPT_DIR/api_stop.sh"

echo "Starting API..."
nohup uv --directory "$SCRIPT_DIR/api" run uvicorn app.main:app \
    --host 0.0.0.0 --port 8001 \
    > "$LOG_DIR/api.log" 2>&1 &
echo $! > "$PID_FILE"
echo "API started (PID $(cat "$PID_FILE")). Log: $LOG_DIR/api.log"
