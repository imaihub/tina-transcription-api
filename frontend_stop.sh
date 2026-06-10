#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/frontend.pid"

if [[ -f "$PID_FILE" ]]; then
    pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
        echo "Stopping frontend (PID $pid)..."
        kill "$pid"
    else
        echo "Frontend is not running."
    fi
    rm -f "$PID_FILE"
else
    echo "No PID file for frontend — already stopped?"
fi
