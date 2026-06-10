#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/frontend.pid"
LOG_DIR="$SCRIPT_DIR/logs"

mkdir -p "$LOG_DIR"

bash "$SCRIPT_DIR/frontend_stop.sh"

echo "Starting frontend..."
nohup uv --directory "$SCRIPT_DIR/api_frontend" run uvicorn main:app \
    --host 0.0.0.0 --port 8080 \
    > "$LOG_DIR/frontend.log" 2>&1 &
echo $! > "$PID_FILE"
echo "Frontend started (PID $(cat "$PID_FILE")). Log: $LOG_DIR/frontend.log"
