from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Dict, List, Tuple

import requests
import xml.etree.ElementTree as ET

# Prefer shared time formatter from scoresource if available
try:
    from scoresource.common.timefmt import format_start_time as _shared_format_start_time
except Exception:  # pragma: no cover - fallback for standalone runs
    _shared_format_start_time = None

NBA_API_AVAILABLE = True
NBA_API_ERROR = ""

try:
    from nba_api.live.nba.endpoints import boxscore, scoreboard, playbyplay
except Exception as exc:  # ModuleNotFoundError or runtime import issues
    NBA_API_AVAILABLE = False
    NBA_API_ERROR = str(exc)
    boxscore = scoreboard = playbyplay = None


def _env_float(name: str, default: float, *, min_value: float | None = None) -> float:
    raw = os.environ.get(name)
    if raw is None:
        value = default
    else:
        try:
            value = float(raw)
        except Exception:
            value = default
    if min_value is None:
        return value
    return value if value >= min_value else min_value


def _cache_root_from_env() -> Path:
    raw = os.environ.get("SCORESOURCE_CACHE_DIR")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".cache" / "scoresource"

# ------------------ TEAM COLORS (unchanged) ------------------
TEAM_PRIMARY_COLORS: Dict[str, str] = {
    "ATL": "#E03A3E", "BOS": "#007A33", "BKN": "#000000", "CHA": "#1D1160",
    "CHI": "#CE1141", "CLE": "#860038", "DAL": "#00538C", "DEN": "#0E2240",
    "DET": "#C8102E", "GSW": "#1D428A", "HOU": "#CE1141", "IND": "#002D62",
    "LAC": "#C8102E", "LAL": "#552583", "MEM": "#5D76A9", "MIA": "#98002E",
    "MIL": "#00471B", "MIN": "#0C2340", "NOP": "#0C2340", "NYK": "#006BB6",
    "OKC": "#007AC1", "ORL": "#0077C0", "PHI": "#FFFFFF", "PHX": "#1D1160",
    "POR": "#E03A3E", "SAC": "#5A2D81", "SAS": "#C4CED4", "TOR": "#CE1141",
    "UTA": "#002B5C", "WAS": "#002B5C",
}

TEAM_SECONDARY_COLORS: Dict[str, str] = {
    "ATL": "#C8102E", "BOS": "#BA9653", "BKN": "#FFFFFF", "CHA": "#00788C",
    "CHI": "#000000", "CLE": "#041E42", "DAL": "#B8C4CA", "DEN": "#FEC524",
    "DET": "#FFFFFF", "GSW": "#FFC72C", "HOU": "#FFFFFF", "IND": "#FDBB30",
    "LAC": "#FFFFFF", "LAL": "#FDB927", "MEM": "#12173F", "MIA": "#F9A01B",
    "MIL": "#EEE1C6", "MIN": "#9EA2A2", "NOP": "#9EA2A2", "NYK": "#F58426",
    "OKC": "#EF3B24", "ORL": "#C4CED4", "PHI": "#006BB6", "PHX": "#F9A01B",
    "POR": "#B6BABD", "SAC": "#8A8D8F", "SAS": "#000000", "TOR": "#000000",
    "UTA": "#00471B", "WAS": "#E31837",
}

TEAM_ACCENT_COLORS: Dict[str, str] = {
    "ATL": "#C4CED4", "BOS": "#C4CED4", "BKN": "#C4CED4", "CHA": "#C4CED4",
    "CHI": "#000000", "CLE": "#041E42", "DAL": "#B8C4CA", "DEN": "#FEC524",
    "DET": "#FFFFFF", "GSW": "#FFC72C", "HOU": "#FFFFFF", "IND": "#FDBB30",
    "LAC": "#FFFFFF", "LAL": "#FDB927", "MEM": "#12173F", "MIA": "#F9A01B",
    "MIL": "#EEE1C6", "MIN": "#9EA2A2", "NOP": "#9EA2A2", "NYK": "#F58426",
    "OKC": "#EF3B24", "ORL": "#C4CED4", "PHI": "#006BB6", "PHX": "#F9A01B",
    "POR": "#B6BABD", "SAC": "#8A8D8F", "SAS": "#000000", "TOR": "#000000",
    "UTA": "#00471B", "WAS": "#C4CED4",
}

TEAM_COLORS = TEAM_PRIMARY_COLORS
TEAM_ALT_COLORS = TEAM_ACCENT_COLORS

DEMO_MODE = (os.environ.get("SCORESOURCE_DEMO") == "1") or (not NBA_API_AVAILABLE)

_scoreboard_cache: Dict[str, Any] = {"ts": 0.0, "data": None}
_boxscore_cache: Dict[str, Tuple[float, Any]] = {}
_shotclock_cache: Dict[str, Tuple[float, Any]] = {}
_live_clock_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_shotclock_history: Dict[str, Tuple[float, Any]] = {}
_pbp_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_espn_logo_cache: Dict[str, Tuple[float, Dict[str, str]]] = {}
_espn_team_logo_cache: Dict[str, Tuple[float, Dict[str, str]]] = {}
_logo_override_cache: Tuple[float, Dict[str, Any]] = (0.0, {})

SCOREBOARD_TTL = _env_float("SCORESOURCE_NBA_SCOREBOARD_TTL", 15.0, min_value=0.0)
BOXSCORE_TTL = _env_float("SCORESOURCE_NBA_BOXSCORE_TTL", 12.0, min_value=0.0)
SHOTCLOCK_TTL = _env_float("SCORESOURCE_NBA_SHOTCLOCK_TTL", 0.5, min_value=0.0)
LIVE_CLOCK_TTL = _env_float("SCORESOURCE_NBA_LIVE_CLOCK_TTL", 2.0, min_value=0.0)
PBP_TTL = _env_float("SCORESOURCE_NBA_PBP_TTL", 5.0, min_value=0.0)
ESPN_LOGO_TTL = _env_float("SCORESOURCE_NBA_ESPN_LOGO_TTL", 60.0, min_value=0.0)
ESPN_TEAM_LOGO_TTL = _env_float("SCORESOURCE_NBA_ESPN_TEAM_LOGO_TTL", 60.0 * 60.0 * 24.0, min_value=0.0)
LOGO_OVERRIDE_TTL = _env_float("SCORESOURCE_NBA_LOGO_OVERRIDE_TTL", 5.0, min_value=0.0)
NBA_RSS_TTL = _env_float("SCORESOURCE_NBA_RSS_TTL", 60.0 * 5.0, min_value=0.0)

NBA_STATS_TIMEOUT_SEC = _env_float("SCORESOURCE_NBA_STATS_TIMEOUT_SEC", 6.0, min_value=1.0)
NBA_LIVE_TIMEOUT_SEC = _env_float("SCORESOURCE_NBA_LIVE_TIMEOUT_SEC", 3.0, min_value=1.0)
NBA_ESPN_TIMEOUT_SEC = _env_float("SCORESOURCE_NBA_ESPN_TIMEOUT_SEC", 3.0, min_value=1.0)
NBA_RSS_TIMEOUT_SEC = _env_float("SCORESOURCE_NBA_RSS_TIMEOUT_SEC", 4.0, min_value=1.0)
NBA_LOGO_TIMEOUT_SEC = _env_float("SCORESOURCE_NBA_LOGO_TIMEOUT_SEC", 3.0, min_value=1.0)
NBA_PBP_TIMEOUT_SEC = _env_float("SCORESOURCE_NBA_PBP_TIMEOUT_SEC", 3.0, min_value=1.0)

CACHE_ROOT = _cache_root_from_env()
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
SCOREBOARD_CACHE_PATH = CACHE_ROOT / "nba_scoreboard.json"
BOXSCORE_CACHE_DIR = CACHE_ROOT / "nba_boxscores"
BOXSCORE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
PLAYER_POSITION_CACHE_PATH = CACHE_ROOT / "nba_player_positions.json"

LOGO_VERSION = "2025-05"
LOGO_DIR = CACHE_ROOT / "logos"
LOGO_DIR.mkdir(parents=True, exist_ok=True)
_logo_cache: Dict[Tuple[str, str, str], bytes | None] = {}
_logo_session = requests.Session()
LOGO_OVERRIDE_PATH = CACHE_ROOT / "nba_logo_overrides.json"
NBA_RSS_URL = os.environ.get("SCORESOURCE_NBA_RSS", "https://www.espn.com/espn/rss/nba/news")
NBA_RSS_FALLBACKS = [
    "https://www.cbssports.com/rss/headlines/nba/",
]
NBA_RSS_URLS = [NBA_RSS_URL, *NBA_RSS_FALLBACKS]
_rss_cache: Tuple[float, List[str]] = (0.0, [])

PLAYER_POSITION_TTL = _env_float("SCORESOURCE_NBA_PLAYER_POSITION_TTL", 60 * 60 * 24 * 7, min_value=0.0)
_player_position_cache: Dict[str, Tuple[float, str]] = {}
_player_position_cache_dirty = False

NBA_STATS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "Connection": "keep-alive",
}

ESPN_ABBR_MAP = {
    "GS": "GSW",
    "NO": "NOP",
    "NY": "NYK",
    "SA": "SAS",
    "WSH": "WAS",
    "UTAH": "UTA",
}

# ------------------ formatting helpers ------------------
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


def _clock_to_seconds(clock_raw: Any) -> float | None:
    if clock_raw in (None, ""):
        return None
    if isinstance(clock_raw, (int, float)):
        return float(clock_raw)
    if isinstance(clock_raw, str):
        if ":" in clock_raw:
            try:
                mins, secs = clock_raw.split(":")
                return int(mins) * 60 + float(secs)
            except Exception:
                return None
        match = re.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", clock_raw)
        if match:
            minutes = int(match.group(1) or 0)
            seconds_val = float(match.group(2) or 0)
            return minutes * 60 + seconds_val
    return None


def _is_halftime(game: Dict[str, Any]) -> bool:
    status_text = (game.get("gameStatusText") or game.get("statusText") or "").lower().replace("-", " ")
    if "halftime" in status_text or "half time" in status_text:
        return True
    period_field = game.get("period")
    current = period_field.get("current") if isinstance(period_field, dict) else period_field
    if current != 2:
        return False
    status_val = game.get("gameStatus")
    if isinstance(status_val, int) and status_val >= 3:
        return False
    clock_secs = _clock_to_seconds(game.get("gameClock"))
    return clock_secs is not None and clock_secs <= 0.1


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


# ------------------ disk cache helpers ------------------
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


def _abbrev_position(position: str | None) -> str:
    pos = (position or "").strip()
    if not pos:
        return ""
    if len(pos) <= 3:
        return pos.upper()
    parts = re.split(r"[-/]", pos)
    abbr = "-".join(part.strip()[:1].upper() for part in parts if part.strip())
    return abbr or pos


def _load_player_positions() -> None:
    if _player_position_cache:
        return
    data = _load_json(PLAYER_POSITION_CACHE_PATH) or {}
    if not isinstance(data, dict):
        return
    for pid, entry in data.items():
        if isinstance(entry, dict):
            pos = entry.get("pos")
            ts = entry.get("ts")
        else:
            pos = entry if isinstance(entry, str) else None
            ts = None
        if pos:
            try:
                _player_position_cache[str(pid)] = (float(ts or 0), str(pos))
            except Exception:
                _player_position_cache[str(pid)] = (0.0, str(pos))


def _save_player_positions() -> None:
    global _player_position_cache_dirty
    if not _player_position_cache_dirty:
        return
    payload = {pid: {"pos": pos, "ts": ts} for pid, (ts, pos) in _player_position_cache.items() if pos}
    _save_json(PLAYER_POSITION_CACHE_PATH, payload)
    _player_position_cache_dirty = False


def _fetch_player_position(person_id: str) -> str:
    url = f"https://stats.nba.com/stats/commonplayerinfo?PlayerID={person_id}"
    try:
        resp = _logo_session.get(url, headers=NBA_STATS_HEADERS, timeout=NBA_STATS_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return ""
    result_sets = data.get("resultSets") or data.get("resultSet") or []
    if not result_sets:
        return ""
    info = result_sets[0]
    headers = info.get("headers") or []
    rows = info.get("rowSet") or []
    if not rows or not headers:
        return ""
    try:
        idx = headers.index("POSITION")
    except ValueError:
        return ""
    return _abbrev_position(rows[0][idx] if rows[0] else "")


def _get_player_position(person_id: str | None) -> str:
    pid = str(person_id or "").strip()
    if not pid:
        return ""
    _load_player_positions()
    now = time.time()
    cached = _player_position_cache.get(pid)
    if cached and now - cached[0] <= PLAYER_POSITION_TTL:
        return cached[1]
    pos = _fetch_player_position(pid)
    _player_position_cache[pid] = (now, pos)
    global _player_position_cache_dirty
    _player_position_cache_dirty = True
    return pos


def _apply_player_positions(team: Dict[str, Any]) -> None:
    players = team.get("players") or []
    if not isinstance(players, list):
        return
    updated = False
    for player in players:
        pos = player.get("position")
        if isinstance(pos, dict):
            pos = pos.get("abbreviation") or pos.get("name") or pos.get("displayName")
        if pos:
            player["position"] = _abbrev_position(str(pos))
            continue
        pid = player.get("personId") or player.get("id") or player.get("playerId")
        fetched = _get_player_position(pid)
        if fetched:
            player["position"] = fetched
            updated = True
    if updated:
        _save_player_positions()


def _stub_boxscore_from_scoreboard(game_id: str) -> Dict[str, Any] | None:
    """
    Build a lightweight boxscore using the last known scoreboard entry.
    Useful when the official boxscore endpoint lags for pre-game.
    """
    scores = _scoreboard_cache.get("data") or _load_disk_scoreboard() or {}
    games = scores.get("games") or []
    for g in games:
        if str(g.get("gameId")) != str(game_id):
            continue
        game_block = {
            "gameClock": g.get("gameClock"),
            "shotClock": g.get("shotClock"),
            "period": g.get("period") or {},
            "gameStatusText": g.get("gameStatusText"),
            "gameStatus": g.get("gameStatus"),
            "gameTimeUTC": g.get("gameTimeUTC") or g.get("gameEt"),
        }
        header = _build_header({**g, **game_block})
        return {
            "game": game_block,
            "home": g.get("homeTeam") or {},
            "away": g.get("awayTeam") or {},
            "header": header,
            "shotclock": format_shotclock(g.get("shotClock")),
        }
    return None


# ------------------ small helpers for start time ------------------
def _display_zone() -> ZoneInfo:
    tz_name = os.environ.get("SCORESOURCE_TZ", "America/Chicago")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("America/Chicago")


def _extract_start_time_text(g: Dict[str, Any]) -> str:
    """
    Try to get a human-readable tipoff time when the game has not started yet.

    Prefer converting gameTimeUTC into local time (SCORESOURCE_TZ). Fall back to status text.
    """
    status_text = (g.get("gameStatusText") or "").strip()

    start_raw = g.get("gameTimeUTC") or g.get("gameEt") or g.get("startTime")
    if _shared_format_start_time:
        formatted = _shared_format_start_time(start_raw)
    else:
        # Fallback: approximate with local zone if shared helper unavailable
        try:
            dt = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
            dt_local = dt.astimezone(_display_zone())
            formatted = dt_local.strftime("%-m/%-d %-I:%M %p %Z").replace(" 0", " ")
        except Exception:
            formatted = "Starts TBA"
    return formatted if formatted != "Starts TBA" else (status_text or "Scheduled")


def _current_period_from_game(game: Dict[str, Any]) -> int | None:
    period_field = game.get("period")
    if isinstance(period_field, dict):
        return period_field.get("current")
    if isinstance(period_field, int):
        return period_field
    return None


def _fetch_live_clock(game_id: str) -> Dict[str, Any] | None:
    now = time.monotonic()
    cached = _live_clock_cache.get(game_id)
    if cached and now - cached[0] <= LIVE_CLOCK_TTL:
        return cached[1]
    url = f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
    try:
        resp = _logo_session.get(url, timeout=NBA_LIVE_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json().get("game", {}) or {}
        result = {
            "gameClock": data.get("gameClock"),
            "shotClock": data.get("shotClock"),
            "statusText": data.get("gameStatusText"),
            "status": data.get("gameStatus"),
            "period": data.get("period"),
        }
        _live_clock_cache[game_id] = (now, result)
        return result
    except Exception:
        return None


def _fetch_live_boxscore(game_id: str) -> Dict[str, Any] | None:
    url = f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
    try:
        resp = _logo_session.get(url, timeout=NBA_LIVE_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    game = data.get("game")
    if not isinstance(game, dict):
        return None
    return data


def _has_players(team: Dict[str, Any]) -> bool:
    players = team.get("players") or []
    return isinstance(players, list) and bool(players)


def _select_espn_logo(logos: List[Dict[str, Any]]) -> str | None:
    if not logos:
        return None
    prefer_sets = [
        ("scoreboard",),
        ("scoreboard", "dark"),
        ("default",),
        ("dark",),
    ]
    for prefs in prefer_sets:
        for logo in logos:
            rels = set((logo.get("rel") or []))
            if all(p in rels for p in prefs):
                href = logo.get("href")
                if isinstance(href, str) and href.startswith("http"):
                    return href
    for logo in logos:
        href = logo.get("href")
        if isinstance(href, str) and href.startswith("http"):
            return href
    return None


def _fetch_espn_team_logo_map() -> Dict[str, str]:
    now = time.monotonic()
    cached = _espn_team_logo_cache.get("data")
    if cached and now - cached[0] <= ESPN_TEAM_LOGO_TTL:
        return cached[1]

    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
    try:
        resp = _logo_session.get(url, timeout=NBA_ESPN_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return cached[1] if cached else {}

    logos: Dict[str, str] = {}
    for sport in data.get("sports", []) or []:
        for league in sport.get("leagues", []) or []:
            for entry in league.get("teams", []) or []:
                team = entry.get("team") or {}
                abbr = (team.get("abbreviation") or "").upper()
                tri = ESPN_ABBR_MAP.get(abbr, abbr)
                logo = _select_espn_logo(team.get("logos") or [])
                if tri and logo:
                    logos[tri] = logo

    _espn_team_logo_cache["data"] = (now, logos)
    return logos


def _fetch_espn_logo_map(date_key: str | None = None) -> Dict[str, str]:
    now = time.monotonic()
    cache_key = date_key or "today"
    cached = _espn_logo_cache.get(cache_key)
    if cached and now - cached[0] <= ESPN_LOGO_TTL:
        return cached[1]

    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    if date_key:
        url = f"{url}?dates={date_key}"
    try:
        resp = _logo_session.get(url, timeout=NBA_ESPN_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return cached[1] if cached else {}

    logos: Dict[str, str] = {}
    for event in data.get("events", []) or []:
        comp = (event.get("competitions") or [{}])[0] or {}
        for entry in comp.get("competitors", []) or []:
            team = entry.get("team") or {}
            abbr = (team.get("abbreviation") or "").upper()
            tri = ESPN_ABBR_MAP.get(abbr, abbr)
            logos_list = team.get("logos") or []
            logo = _select_espn_logo(logos_list) or team.get("logo")
            if tri and logo:
                logos[tri] = logo

    _espn_logo_cache[cache_key] = (now, logos)
    return logos


def _apply_logo_url(team: Dict[str, Any], logo_map: Dict[str, str], *, force: bool = False) -> None:
    if not force and (team.get("logoUrl") or team.get("logo")):
        return
    tri = (team.get("teamTricode") or team.get("tricode") or team.get("abbreviation") or "").upper()
    if not tri:
        return
    logo = logo_map.get(tri)
    if logo:
        team["logoUrl"] = logo


def _game_date_key(game: Dict[str, Any]) -> str | None:
    tz = _display_zone()
    for key in ("gameTimeLocal", "gameEt", "gameTimeUTC"):
        val = game.get(key)
        if isinstance(val, str) and val:
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            except Exception:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            else:
                dt = dt.astimezone(tz)
            return dt.strftime("%Y%m%d")
    return None


def _load_logo_overrides() -> Dict[str, Any]:
    now = time.monotonic()
    cached_ts, cached = _logo_override_cache
    if cached and now - cached_ts <= LOGO_OVERRIDE_TTL:
        return cached
    data: Dict[str, Any] = {}
    if LOGO_OVERRIDE_PATH.exists():
        try:
            data = json.loads(LOGO_OVERRIDE_PATH.read_text())
        except Exception:
            data = {}
    globals()["_logo_override_cache"] = (now, data)
    return data


def _logo_override_for_team(
    overrides: Dict[str, Any], game_id: str | None, date_key: str | None, tricode: str
) -> str | None:
    tri = (tricode or "").upper()
    if not tri:
        return None
    if game_id:
        block = (overrides.get("games") or {}).get(str(game_id))
        if isinstance(block, dict):
            val = block.get(tri)
            if isinstance(val, str) and val:
                return val
    if date_key:
        block = (overrides.get("dates") or {}).get(str(date_key))
        if isinstance(block, dict):
            val = block.get(tri)
            if isinstance(val, str) and val:
                return val
    val = (overrides.get("teams") or {}).get(tri)
    if isinstance(val, str) and val:
        return val
    return None


def _apply_logo_map_to_result(result: Dict[str, Any]) -> None:
    game = result.get("game") or {}
    date_key = _game_date_key(game)
    base_map = _fetch_espn_team_logo_map()
    game_map = _fetch_espn_logo_map(date_key)
    logo_map: Dict[str, str] = {}
    if base_map:
        logo_map.update(base_map)
    if game_map:
        logo_map.update(game_map)
    _apply_logo_url(result.get("home") or {}, logo_map, force=True)
    _apply_logo_url(result.get("away") or {}, logo_map, force=True)
    overrides = _load_logo_overrides()
    if not overrides:
        return
    game_id = game.get("gameId") or result.get("gameId")
    for team in (result.get("home") or {}, result.get("away") or {}):
        tri = (team.get("teamTricode") or team.get("tricode") or team.get("abbreviation") or "").upper()
        override = _logo_override_for_team(overrides, str(game_id) if game_id else None, date_key, tri)
        if override:
            team["logoUrl"] = override


def _parse_rss_titles(payload: str) -> List[str]:
    titles: List[str] = []
    try:
        root = ET.fromstring(payload)
    except Exception:
        return titles
    for item in root.findall(".//item"):
        title = item.findtext("title")
        if not title:
            continue
        cleaned = html.unescape(title).strip()
        if cleaned and cleaned not in titles:
            titles.append(cleaned)
    return titles


def fetch_rss_headlines(limit: int = 10) -> List[str]:
    now = time.monotonic()
    cached_ts, cached = _rss_cache
    if cached and now - cached_ts <= NBA_RSS_TTL:
        return cached[:limit]
    for url in NBA_RSS_URLS:
        if not url:
            continue
        try:
            resp = _logo_session.get(
                url,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml, application/xml"},
                timeout=NBA_RSS_TIMEOUT_SEC,
            )
            resp.raise_for_status()
            titles = _parse_rss_titles(resp.text)
            if titles:
                globals()["_rss_cache"] = (now, titles)
                return titles[:limit]
        except Exception:
            continue
    if cached:
        return cached[:limit]
    return []


def _load_logo_from_url(team_id: str | None, url: str) -> bytes | None:
    key = (team_id or "", url, LOGO_VERSION)
    if key in _logo_cache:
        return _logo_cache[key]

    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix not in (".svg", ".png", ".jpg", ".jpeg"):
        suffix = ".png"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    cache_name = f"url-{digest}-{LOGO_VERSION}{suffix}"
    cache_path = LOGO_DIR / cache_name

    if cache_path.exists():
        try:
            content = cache_path.read_bytes()
            _logo_cache[key] = content
            return content
        except Exception:
            pass

    try:
        resp = _logo_session.get(url, timeout=NBA_LOGO_TIMEOUT_SEC)
        resp.raise_for_status()
        content = resp.content
    except Exception:
        _logo_cache[key] = None
        return None

    try:
        cache_path.write_bytes(content)
    except Exception:
        pass
    _logo_cache[key] = content
    return content


def _looks_like_path(token: str) -> bool:
    if "/" in token or "\\" in token:
        return True
    lower = token.lower()
    return lower.endswith((".png", ".svg", ".jpg", ".jpeg"))


def _load_logo_from_path(team_id: str | None, path_str: str) -> bytes | None:
    key = (team_id or "", path_str, LOGO_VERSION)
    if key in _logo_cache:
        return _logo_cache[key]
    path = Path(path_str)
    if not path.exists():
        _logo_cache[key] = None
        return None
    try:
        content = path.read_bytes()
    except Exception:
        _logo_cache[key] = None
        return None
    _logo_cache[key] = content
    return content


def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    """
    Returns raw logo bytes (PNG) for a team, cached on disk. None on failure.
    """
    tc_raw = tricode or ""
    if tc_raw.lower().startswith("http"):
        return _load_logo_from_url(team_id, tc_raw)
    if tc_raw and _looks_like_path(tc_raw):
        return _load_logo_from_path(team_id, tc_raw)
    tc = tc_raw.upper()
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
                resp = _logo_session.get(url, timeout=NBA_LOGO_TIMEOUT_SEC)
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
    alt_codes = [tc]
    if tc == "NOP":
        alt_codes.append("NO")
    if team_id:
        base = f"https://cdn.nba.com/logos/nba/{team_id}"
        urls.extend(
            [
                f"{base}/primary/L/logo.svg",
                f"{base}/global/L/logo.svg",
                f"{base}/primary/L/logo.png",
                f"{base}/global/L/logo.png",
            ]
        )
    for code in alt_codes:
        base_code = f"https://cdn.nba.com/logos/nba/{code}"
        urls.extend(
            [
                f"{base_code}/primary/L/logo.svg",
                f"{base_code}/global/L/logo.svg",
                f"{base_code}/primary/L/logo.png",
                f"{base_code}/global/L/logo.png",
            ]
        )

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


def _fetch_live_shotclock(game_id: str) -> Any:
    actions = _fetch_pbp_actions(game_id)
    for action in reversed(actions):
        sc = action.get("shotClock")
        if sc not in (None, "", "--"):
            return sc
    return None


def _fetch_pbp_actions(game_id: str) -> List[Dict[str, Any]]:
    now = time.monotonic()
    cached = _pbp_cache.get(game_id)
    if cached and now - cached[0] <= PBP_TTL:
        return cached[1]

    data = None
    if NBA_API_AVAILABLE and playbyplay is not None:
        try:
            data = playbyplay.PlayByPlay(game_id=game_id).get_dict()
        except Exception:
            data = None
    if data is None:
        url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
        try:
            resp = _logo_session.get(url, timeout=NBA_PBP_TIMEOUT_SEC)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            data = None

    actions = (data or {}).get("game", {}).get("actions", []) or []
    _pbp_cache[game_id] = (now, actions)
    return actions


def _compute_team_fouls_by_period(actions: List[Dict[str, Any]]) -> Dict[str, Dict[int, int]]:
    fouls: Dict[str, Dict[int, int]] = {}
    for action in actions:
        action_type = str(action.get("actionType") or "").lower()
        if action_type != "foul" and not action.get("isFoul"):
            continue
        sub_type = str(action.get("subType") or "").lower()
        if "technical" in sub_type:
            continue
        tri = (action.get("teamTricode") or "").upper()
        period = action.get("period")
        if not tri or not isinstance(period, int):
            continue
        per = fouls.setdefault(tri, {})
        per[period] = per.get(period, 0) + 1
    return fouls


def _apply_period_fouls(game_id: str, game: Dict[str, Any], home: Dict[str, Any], away: Dict[str, Any]) -> None:
    current_period = _current_period_from_game(game)
    if not isinstance(current_period, int):
        return
    actions = _fetch_pbp_actions(game_id)
    fouls = _compute_team_fouls_by_period(actions)
    for team in (home, away):
        tri = (team.get("teamTricode") or team.get("tricode") or "").upper()
        if not tri:
            continue
        team["foulsPeriod"] = fouls.get(tri, {}).get(current_period, 0)
        team["foulsPeriodNum"] = current_period


def _derive_shotclock_from_pbp(game_id: str) -> Any:
    if not NBA_API_AVAILABLE or playbyplay is None:
        return _fetch_live_shotclock(game_id)
    now = time.monotonic()
    cached = _shotclock_cache.get(game_id)
    if cached and now - cached[0] <= SHOTCLOCK_TTL:
        return cached[1]
    try:
        data = playbyplay.PlayByPlay(game_id=game_id).get_dict()
        actions = data.get("game", {}).get("actions", []) or []
        for action in reversed(actions):
            sc = action.get("shotClock")
            if sc not in (None, ""):
                _shotclock_cache[game_id] = (now, sc)
                return sc
    except Exception:
        pass
    live = _fetch_live_shotclock(game_id)
    if live not in (None, "", "--"):
        _shotclock_cache[game_id] = (now, live)
        return live
    return None


def _resolve_shotclock(game_id: str, game: Dict[str, Any], current_period: int | None) -> str:
    if not (isinstance(current_period, int) and current_period > 0):
        return format_shotclock(game.get("shotClock"))

    pbp_val = _derive_shotclock_from_pbp(game_id)
    if pbp_val not in (None, "", "--"):
        return format_shotclock(pbp_val)
    return format_shotclock(game.get("shotClock"))


# ------------------ DEMO HELPERS ------------------
def demo_scoreboard() -> Dict[str, Any]:
    games: List[Dict[str, Any]] = []
    lines = ["No NBA games today."]
    return {"games": games, "lines": lines}


def demo_boxscore() -> Dict[str, Any]:
    game = {
        "gameClock": None,
        "shotClock": None,
        "period": {"current": 0},
        "gameStatusText": "No games",
    }
    home = {
        "teamId": "0",
        "teamName": "Home",
        "teamTricode": "HOM",
        "score": 0,
        "players": [],
    }
    away = {
        "teamId": "0",
        "teamName": "Away",
        "teamTricode": "AWY",
        "score": 0,
        "players": [],
    }
    return {"game": game, "home": home, "away": away, "header": "No games", "shotclock": "--"}


# ------------------ LIVE / HYBRID LOGIC ------------------
def fetch_scores() -> Dict[str, Any]:
    """
    Return today's NBA games, including pre-game, with start times.

    Result:
        {
            "games": [raw-game-dict, ...],
            "lines": [
                "Lakers 87 @ Warriors 92 (Q3 4:09)",
                "Spurs 0 @ Rockets 0 (7:30 PM CT)",
                ...
            ],
        }
    """
    if DEMO_MODE or not NBA_API_AVAILABLE or scoreboard is None:
        disk = _load_disk_scoreboard()
        return disk or demo_scoreboard()

    now = time.monotonic()

    if _scoreboard_cache.get("data") is None:
        disk_seed = _load_disk_scoreboard()
        if disk_seed:
            _scoreboard_cache["data"] = disk_seed
            _scoreboard_cache["ts"] = now
            return disk_seed

    cached = _scoreboard_cache.get("data")
    if cached and now - _scoreboard_cache["ts"] < SCOREBOARD_TTL:
        return cached

    try:
        data = scoreboard.ScoreBoard().get_dict()
        games = data.get("scoreboard", {}).get("games", []) or []
        base_map = _fetch_espn_team_logo_map() if games else {}
        game_map = _fetch_espn_logo_map() if games else {}
        logo_map: Dict[str, str] = {}
        if base_map:
            logo_map.update(base_map)
        if game_map:
            logo_map.update(game_map)

        def _format_game_line(g: Dict[str, Any]) -> str:
            home_team = g.get("homeTeam", {}) or {}
            away_team = g.get("awayTeam", {}) or {}
            if logo_map:
                _apply_logo_url(home_team, logo_map, force=True)
                _apply_logo_url(away_team, logo_map, force=True)
            home = home_team.get("teamName", "Home")
            away = away_team.get("teamName", "Away")
            hs = safe_score(home_team)
            as_ = safe_score(away_team)

            status_value = g.get("gameStatus")
            period = g.get("period", {})
            current = period.get("current") if isinstance(period, dict) else period
            clock = format_clock(g.get("gameClock"))

            if status_value == 3 and g.get("gameStatusText"):
                status = g.get("gameStatusText")
            elif status_value in (None, 0, 1) or not current:
                status = _extract_start_time_text(g)
            else:
                if _is_halftime(g):
                    status = "HALF TIME"
                elif current:
                    status = f"Q{current} {clock}"
                else:
                    status = g.get("gameStatusText", clock or "In Progress")

            g["gameStatusText"] = status
            return f"{away} {as_} @ {home} {hs} ({status})"

        lines = [_format_game_line(g) for g in games]

        if not games:
            result = demo_scoreboard()
        else:
            result = {"games": games, "lines": lines}

        _scoreboard_cache["data"] = result
        _scoreboard_cache["ts"] = now
        _save_disk_scoreboard(result)
        return result
    except Exception:
        if _scoreboard_cache.get("data"):
            return _scoreboard_cache["data"]
        disk = _load_disk_scoreboard()
        if disk:
            return disk
        return demo_scoreboard()


def fetch_boxscore(game_id: str) -> Dict[str, Any]:
    """
    Return a hybrid live boxscore:
    - Works for pre-game: header shows "7:30 PM ET" (tipoff time).
    - Works for in-progress: header shows "Qx mm:ss".
    """
    if DEMO_MODE or not NBA_API_AVAILABLE or boxscore is None:
        disk = _load_disk_boxscore(game_id)
        stub = _stub_boxscore_from_scoreboard(game_id)
        result = stub or disk or demo_boxscore()
        _apply_player_positions(result.get("home") or {})
        _apply_player_positions(result.get("away") or {})
        _apply_logo_map_to_result(result)
        _apply_period_fouls(game_id, result.get("game") or {}, result.get("home") or {}, result.get("away") or {})
        _boxscore_cache[game_id] = (time.monotonic(), result)
        _save_disk_boxscore(game_id, result)
        return result

    now = time.monotonic()

    if game_id not in _boxscore_cache:
        disk_box = _load_disk_boxscore(game_id)
        if disk_box:
            _apply_player_positions(disk_box.get("home") or {})
            _apply_player_positions(disk_box.get("away") or {})
            _apply_logo_map_to_result(disk_box)
            _apply_period_fouls(game_id, disk_box.get("game") or {}, disk_box.get("home") or {}, disk_box.get("away") or {})
            _boxscore_cache[game_id] = (now, disk_box)
            return disk_box

    cached = _boxscore_cache.get(game_id)
    if cached and now - cached[0] < BOXSCORE_TTL:
        base = cached[1] or {}
        game_cached = base.get("game") or {}
        current_period = _current_period_from_game(game_cached)

        live_clock = _fetch_live_clock(game_id) or {}
        if live_clock.get("gameClock") not in (None, ""):
            game_cached["gameClock"] = live_clock.get("gameClock")
        if live_clock.get("shotClock") not in (None, ""):
            game_cached["shotClock"] = live_clock.get("shotClock")
        if live_clock.get("statusText"):
            game_cached["gameStatusText"] = live_clock.get("statusText")
        if live_clock.get("period") not in (None, ""):
            lp = live_clock.get("period")
            game_cached["period"] = {"current": lp} if not isinstance(lp, dict) else lp
            current_period = _current_period_from_game(game_cached)

        shotclock = _resolve_shotclock(game_id, game_cached, current_period)
        header = _build_header(game_cached)
        if header == "HALF TIME":
            game_cached["gameStatusText"] = header
        status_val = game_cached.get("gameStatus")
        if status_val in (None, 0, 1) or not _current_period_from_game(game_cached):
            game_cached["gameStatusText"] = header
        result = {**base, "shotclock": shotclock, "header": header}
        _apply_player_positions(result.get("home") or {})
        _apply_player_positions(result.get("away") or {})
        _apply_logo_map_to_result(result)
        _apply_period_fouls(game_id, result.get("game") or {}, result.get("home") or {}, result.get("away") or {})
        _boxscore_cache[game_id] = (cached[0], result)
        _save_disk_boxscore(game_id, result)
        return result

    try:
        data = boxscore.BoxScore(game_id=game_id).get_dict()
    except Exception:
        data = None
    if data is None:
        data = _fetch_live_boxscore(game_id)
    if data is None:
        disk = _load_disk_boxscore(game_id)
        stub = _stub_boxscore_from_scoreboard(game_id)
        result = stub or disk or demo_boxscore()
        _apply_player_positions(result.get("home") or {})
        _apply_player_positions(result.get("away") or {})
        _apply_logo_map_to_result(result)
        _apply_period_fouls(game_id, result.get("game") or {}, result.get("home") or {}, result.get("away") or {})
        _boxscore_cache[game_id] = (time.monotonic(), result)
        _save_disk_boxscore(game_id, result)
        return result

    game = data.get("game") or {}
    home = game.get("homeTeam") or {}
    away = game.get("awayTeam") or {}
    if not home or not away:
        live = _fetch_live_boxscore(game_id)
        if live:
            game = live.get("game") or {}
            home = game.get("homeTeam") or {}
            away = game.get("awayTeam") or {}
    if not home or not away:
        disk = _load_disk_boxscore(game_id)
        stub = _stub_boxscore_from_scoreboard(game_id)
        result = stub or disk or demo_boxscore()
        _apply_player_positions(result.get("home") or {})
        _apply_player_positions(result.get("away") or {})
        _apply_logo_map_to_result(result)
        _apply_period_fouls(game_id, result.get("game") or {}, result.get("home") or {}, result.get("away") or {})
        _boxscore_cache[game_id] = (time.monotonic(), result)
        _save_disk_boxscore(game_id, result)
        return result
    if not _has_players(home) and not _has_players(away):
        live = _fetch_live_boxscore(game_id)
        if live:
            game = live.get("game") or {}
            home = game.get("homeTeam") or {}
            away = game.get("awayTeam") or {}

    live_clock = _fetch_live_clock(game_id) or {}
    if live_clock:
        if live_clock.get("gameClock") not in (None, ""):
            game["gameClock"] = live_clock.get("gameClock")
        if live_clock.get("shotClock") not in (None, ""):
            game["shotClock"] = live_clock.get("shotClock")
        lp = live_clock.get("period")
        if lp not in (None, ""):
            game["period"] = {"current": lp} if not isinstance(lp, dict) else lp
        if live_clock.get("statusText"):
            game["gameStatusText"] = live_clock.get("statusText")

    current_period = _current_period_from_game(game)
    shotclock = _resolve_shotclock(game_id, game, current_period)
    if shotclock not in (None, "", "--"):
        _shotclock_history[game_id] = (now, shotclock)
    else:
        hist = _shotclock_history.get(game_id)
        if hist:
            shotclock = hist[1]

    header = _build_header(game)
    if header == "HALF TIME":
        game["gameStatusText"] = header
    status_val = game.get("gameStatus")
    if status_val in (None, 0, 1) or not _current_period_from_game(game):
        game["gameStatusText"] = header

    result = {
        "game": game,
        "home": home,
        "away": away,
        "header": header,
        "shotclock": shotclock,
    }
    _apply_player_positions(home)
    _apply_player_positions(away)
    _apply_logo_map_to_result(result)
    _apply_period_fouls(game_id, game, home, away)
    _boxscore_cache[game_id] = (now, result)
    _save_disk_boxscore(game_id, result)
    return result


def _build_header(game: Dict[str, Any]) -> str:
    """
    Build the header string used by the UI.

    - If gameStatus == 1 (pre-game), show tipoff time ("7:30 PM ET").
    - If in progress, prefer "Qx mm:ss".
    - If final or unknown, fall back to gameStatusText.
    """
    status_value = game.get("gameStatus")
    current_period = _current_period_from_game(game)
    clock = format_clock(game.get("gameClock"))
    status_text = (game.get("gameStatusText") or "").strip()

    if status_value == 3 and status_text:
        return status_text

    if status_value in (None, 0, 1) or not current_period:
        return _extract_start_time_text(game)

    if _is_halftime(game):
        return "HALF TIME"

    if current_period:
        return f"Q{current_period} {clock or '--:--'}"

    return status_text or clock or "Scheduled"
