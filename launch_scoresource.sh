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
    for preferred in 20 0 1 10; do
        if [[ -S "/tmp/.X11-unix/X$preferred" ]]; then
            export DISPLAY=":$preferred.0"
            break
        fi
    done
    if [[ -z "${DISPLAY:-}" ]]; then
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

PY_CMD="$VENV_PY"
if [[ ! -x "$PY_CMD" && -x "$LEGACY_VENV" ]]; then
    PY_CMD="$LEGACY_VENV"
fi
if [[ ! -x "$PY_CMD" ]]; then
    PY_CMD="$(command -v python3)"
fi

# Keep one live ScoreSource process so users do not end up interacting with
# stale windows from earlier runs.
pkill -f '/home/mike/projects/ScoreScource/.venv/bin/python -m scoresource.main' >/dev/null 2>&1 || true
pkill -f "$LEGACY_VENV -m scoresource.main" >/dev/null 2>&1 || true

{
    echo "===== ScoreSource launch $(date -Is) ====="
    echo "DISPLAY=${DISPLAY:-}"
    echo "Using Python: $PY_CMD"
    exec "$PY_CMD" -m scoresource.main
} >>"$LOG_FILE" 2>&1
