#!/usr/bin/env bash
# Launch ScoreSource from its dedicated folder using its dedicated venv.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Prefer the project-local venv we just set up; fallback to legacy path, then system python.
VENV_PY="$SCRIPT_DIR/.venv/bin/python"
LEGACY_VENV="$HOME/projects/envs/scoresource_env/bin/python"
LOG_DIR="$HOME/.local/share/scoresource"
LOG_FILE="$LOG_DIR/scoreboard.log"
mkdir -p "$LOG_DIR"

cd "$SCRIPT_DIR" || exit 1

{
  echo "===== ScoreSource launch $(date -Is) ====="
  PY_CMD="${VENV_PY}"
  if [ ! -x "$PY_CMD" ] && [ -x "$LEGACY_VENV" ]; then
    PY_CMD="$LEGACY_VENV"
  fi
  if [ ! -x "$PY_CMD" ]; then
    PY_CMD="$(command -v python3)"
  fi

  export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
  exec "$PY_CMD" -m scoresource.main
} >>"$LOG_FILE" 2>&1
