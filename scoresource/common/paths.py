from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ScoreSource"
APP_SLUG = "scoresource"


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw).expanduser()


def cache_dir() -> Path:
    override = _env_path("SCORESOURCE_CACHE_DIR")
    if override:
        return override
    if sys.platform == "win32":
        base = _env_path("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return base / APP_NAME / "Cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / APP_NAME
    base = _env_path("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return base / APP_SLUG


def state_dir() -> Path:
    override = _env_path("SCORESOURCE_STATE_DIR")
    if override:
        return override
    if sys.platform == "win32":
        base = _env_path("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return base / APP_NAME / "State"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / "State"
    base = _env_path("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    return base / APP_SLUG


def log_dir() -> Path:
    override = _env_path("SCORESOURCE_LOG_DIR")
    if override:
        return override
    if sys.platform == "win32":
        base = _env_path("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return base / APP_NAME / "Logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / APP_NAME
    return state_dir() / "logs"
