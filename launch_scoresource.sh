#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$SCRIPT_DIR/.venv/bin/python"
cd "$SCRIPT_DIR"

PY_CMD="$VENV_PY"
if [[ ! -x "$PY_CMD" ]]; then
    PY_CMD="$(command -v python3 || command -v python)"
fi
[[ -n "${PY_CMD:-}" ]] || { echo "Python was not found." >&2; exit 1; }

if [[ "$(uname -s 2>/dev/null || true)" == "Linux" && -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    for preferred in 20 0 1 10; do
        if [[ -S "/tmp/.X11-unix/X$preferred" ]]; then
            export DISPLAY=":$preferred.0"
            break
        fi
    done
    if [[ -z "${DISPLAY:-}" && -d /tmp/.X11-unix ]]; then
        while IFS= read -r sock; do
            [[ -S "$sock" ]] || continue
            display_num="${sock##/tmp/.X11-unix/X}"
            if [[ "$display_num" =~ ^[0-9]+$ ]] && (( display_num < 100 )); then
                export DISPLAY=":$display_num.0"
                break
            fi
        done < <(find /tmp/.X11-unix -maxdepth 1 -type s -name 'X*' | sort -V)
    fi
fi

LOG_DIR="$("$PY_CMD" -c 'from scoresource.common.paths import log_dir; print(log_dir())')"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/scoreboard.log"

{
    echo "===== ScoreSource launch $(date -Is) ====="
    echo "DISPLAY=${DISPLAY:-}"
    echo "Using Python: $PY_CMD"
    exec "$PY_CMD" -m scoresource.main
} >>"$LOG_FILE" 2>&1
