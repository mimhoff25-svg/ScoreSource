#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$SCRIPT_DIR/.venv/bin/python"
LEGACY_VENV="$HOME/projects/envs/scoresource_env/bin/python"
LOG_DIR="$HOME/.local/share/scoresource"
LOG_FILE="$LOG_DIR/scoreboard.log"

mkdir -p "$LOG_DIR"
cd "$SCRIPT_DIR"

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    for sock in /tmp/.X11-unix/X*; do
        [[ -S "$sock" ]] || continue
        export DISPLAY=":${sock##/tmp/.X11-unix/X}"
        break
    done
fi

PY_CMD="$VENV_PY"
if [[ ! -x "$PY_CMD" && -x "$LEGACY_VENV" ]]; then
    PY_CMD="$LEGACY_VENV"
fi
if [[ ! -x "$PY_CMD" ]]; then
    PY_CMD="$(command -v python3)"
fi

{
    echo "===== ScoreSource launch $(date -Is) ====="
    echo "DISPLAY=${DISPLAY:-}"
    echo "Using Python: $PY_CMD"
    exec "$PY_CMD" -m scoresource.main
} >>"$LOG_FILE" 2>&1
