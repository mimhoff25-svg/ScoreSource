"""Template backend for ScoreSource sports.

Copy this file to start a new sport backend. Implement `fetch_scores` and
`fetch_boxscore` using your league's feeds, but keep the public API identical
across sports so the UI behaves the same as NBA.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

# --- required identifiers -------------------------------------------------
SPORT = "template"

TEAM_PRIMARY_COLORS: Dict[str, str] = {}
TEAM_SECONDARY_COLORS: Dict[str, str] = {}
TEAM_ACCENT_COLORS: Dict[str, str] = {}
TEAM_COLORS = TEAM_PRIMARY_COLORS
TEAM_ALT_COLORS = TEAM_ACCENT_COLORS

# --- caching ---------------------------------------------------------------
CACHE_ROOT = Path.home() / ".cache" / "scoresource"
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
SCOREBOARD_CACHE_PATH = CACHE_ROOT / f"{SPORT}_scoreboard.json"
BOXSCORE_CACHE_DIR = CACHE_ROOT / f"{SPORT}_boxscores"
BOXSCORE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOGO_VERSION = "2025-05"
LOGO_DIR = CACHE_ROOT / "logos" / SPORT
LOGO_DIR.mkdir(parents=True, exist_ok=True)
_logo_session = requests.Session()
_logo_cache: Dict[Tuple[str, str, str], bytes | None] = {}
_logo_url_map: Dict[str, str] = {}

SCOREBOARD_TTL = 15.0
BOXSCORE_TTL = 12.0

# --- formatting helpers ---------------------------------------------------

def format_clock(clock_raw: Any) -> str:
    if not clock_raw:
        return "--:--"
    if isinstance(clock_raw, (int, float)):
        minutes = int(clock_raw // 60)
        seconds = int(clock_raw % 60)
        return f"{minutes}:{seconds:02d}"
    if not isinstance(clock_raw, str):
        return str(clock_raw)
    match = re.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", clock_raw)
    if match:
        minutes = int(match.group(1) or 0)
        seconds_val = float(match.group(2) or 0)
        seconds = int(seconds_val)
        return f"{minutes}:{seconds:02d}"
    return clock_raw


def format_time_played(value: Any) -> str:
    if value in (None, "", 0):
        return ""
    try:
        if isinstance(value, str) and ":" in value:
            return value
        if isinstance(value, (int, float)):
            minutes = int(value)
            seconds = int(round((value - minutes) * 60))
            return f"{minutes}:{seconds:02d}"
        if isinstance(value, str):
            match = re.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", value)
            if match:
                minutes = int(match.group(1) or 0)
                seconds_val = float(match.group(2) or 0)
                seconds = int(seconds_val)
                return f"{minutes}:{seconds:02d}"
    except Exception:
        return ""
    return str(value)


def format_shotclock(value: Any) -> str:
    if value in (None, "", "--"):
        return "--"
    try:
        num = float(value)
        if num.is_integer():
            return str(int(num))
        return f"{num:.1f}".rstrip("0").rstrip(".")
    except Exception:
        return str(value)


def safe_score(team: Dict[str, Any]) -> int:
    val = team.get("score")
    if val in (None, ""):
        val = team.get("points") or team.get("scoreTotal")
    try:
        return int(val)
    except Exception:
        return int(val or 0)


def extract_start_time_text(game: Dict[str, Any], key: str = "gameTimeUTC") -> str:
    status_text = (game.get("gameStatusText") or game.get("statusText") or "").strip()
    if status_text and any(am_pm in status_text.upper() for am_pm in ("AM", "PM")):
        return status_text
    iso_val = game.get(key) or game.get("startTime") or game.get("date")
    if isinstance(iso_val, str) and iso_val:
        try:
            dt = datetime.fromisoformat(iso_val.replace("Z", "+00:00"))
            dt_local = dt.astimezone()
            return dt_local.strftime("%I:%M %p %Z").lstrip("0")
        except Exception:
            pass
    return status_text or "Scheduled"

# --- disk IO --------------------------------------------------------------

def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _save_json(path: Path, payload: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
    except Exception:
        pass


def _load_disk_scoreboard() -> Dict[str, Any] | None:
    data = _load_json(SCOREBOARD_CACHE_PATH)
    return data if isinstance(data, dict) else None


def _save_disk_scoreboard(payload: Dict[str, Any]) -> None:
    _save_json(SCOREBOARD_CACHE_PATH, payload)


def _load_disk_boxscore(game_id: str) -> Dict[str, Any] | None:
    path = BOXSCORE_CACHE_DIR / f"{game_id}.json"
    data = _load_json(path)
    return data if isinstance(data, dict) else None


def _save_disk_boxscore(game_id: str, payload: Dict[str, Any]) -> None:
    path = BOXSCORE_CACHE_DIR / f"{game_id}.json"
    _save_json(path, payload)


# --- logo loader ----------------------------------------------------------

def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    tc = (tricode or "").upper()
    key = (team_id or "", tc, LOGO_VERSION)
    if key in _logo_cache:
        return _logo_cache[key]

    cache_ext = ".svg"
    cache_name = f"{team_id or tc or 'unknown'}-{LOGO_VERSION}{cache_ext}"
    cache_path = LOGO_DIR / cache_name

    def _try_load_file() -> bytes | None:
        if cache_path.exists():
            try:
                return cache_path.read_bytes()
            except Exception:
                return None
        return None

    def _fetch_urls(urls: List[str]) -> tuple[bytes | None, str]:
        for url in urls:
            try:
                resp = _logo_session.get(url, timeout=3)
                resp.raise_for_status()
                ext = ".svg" if url.lower().endswith(".svg") else ".png"
                return resp.content, ext
            except Exception:
                continue
        return None, cache_ext

    cached = _try_load_file()
    if cached:
        _logo_cache[key] = cached
        return cached

    urls: List[str] = []
    # optional: pre-seed a map of known logo URLs via _logo_url_map
    for code in filter(None, [team_id, tc]):
        url = _logo_url_map.get(str(code))
        if url:
            urls.append(url)

    content, used_ext = _fetch_urls(urls)
    if content:
        try:
            cache_path = cache_path.with_suffix(used_ext)
            cache_path.write_bytes(content)
        except Exception:
            pass
        _logo_cache[key] = content
        return content

    _logo_cache[key] = None
    return None


# --- stubs to override ----------------------------------------------------

def fetch_scores() -> Dict[str, Any]:
    """Override per sport."""
    raise NotImplementedError


def fetch_boxscore(game_id: str) -> Dict[str, Any]:
    """Override per sport."""
    raise NotImplementedError
