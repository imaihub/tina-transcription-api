#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/api.pid"

if [[ -f "$PID_FILE" ]]; then
    pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
        echo "Stopping API (PID $pid)..."
        kill "$pid"
    else
        echo "API is not running."
    fi
    rm -f "$PID_FILE"
else
    echo "No PID file for API — already stopped?"
fi
