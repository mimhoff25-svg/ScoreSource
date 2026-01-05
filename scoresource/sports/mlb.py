from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

SPORT = "mlb"
SCOREBOARD_URL = "https://site.web.api.espn.com/apis/v2/sports/baseball/mlb/scoreboard"


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

TEAM_PRIMARY_COLORS: Dict[str, str] = {}
TEAM_SECONDARY_COLORS: Dict[str, str] = {}
TEAM_ACCENT_COLORS: Dict[str, str] = {}
TEAM_COLORS = TEAM_PRIMARY_COLORS
TEAM_ALT_COLORS = TEAM_ACCENT_COLORS

_scoreboard_cache: Dict[str, Any] = {"ts": 0.0, "data": None}
_boxscore_cache: Dict[str, Tuple[float, Any]] = {}

SCOREBOARD_TTL = _env_float("SCORESOURCE_MLB_SCOREBOARD_TTL", 15.0, min_value=0.0)
BOXSCORE_TTL = _env_float("SCORESOURCE_MLB_BOXSCORE_TTL", 12.0, min_value=0.0)
SCOREBOARD_TIMEOUT_SEC = _env_float("SCORESOURCE_MLB_SCOREBOARD_TIMEOUT_SEC", 5.0, min_value=1.0)
LOGO_TIMEOUT_SEC = _env_float("SCORESOURCE_MLB_LOGO_TIMEOUT_SEC", 3.0, min_value=1.0)

CACHE_ROOT = _cache_root_from_env()
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
SCOREBOARD_CACHE_PATH = CACHE_ROOT / f"{SPORT}_scoreboard.json"
BOXSCORE_CACHE_DIR = CACHE_ROOT / f"{SPORT}_boxscores"
BOXSCORE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOGO_VERSION = "2025-05"
LOGO_DIR = CACHE_ROOT / "logos" / SPORT
LOGO_DIR.mkdir(parents=True, exist_ok=True)
_logo_cache: Dict[Tuple[str, str, str], bytes | None] = {}
_logo_session = requests.Session()
_logo_url_map: Dict[str, str] = {}

sport_table_headers = ["#", "Player", "Min", "Pos", "Pts", "Reb", "Ast", "PF"]

STAT_MAP: Dict[str, List[str]] = {
    "points": ["points", "score"],
    "rebounds": ["rebounds"],
    "assists": ["assists"],
}


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


def _extract_start_time_text(g: Dict[str, Any]) -> str:
    status_text = (g.get("gameStatusText") or g.get("statusText") or "").strip()
    if status_text and any(am_pm in status_text.upper() for am_pm in ("AM", "PM")):
        return status_text
    iso_val = g.get("gameTimeUTC") or g.get("startTime") or g.get("date")
    if isinstance(iso_val, str) and iso_val:
        try:
            dt = datetime.fromisoformat(iso_val.replace("Z", "+00:00"))
            dt_local = dt.astimezone()
            return dt_local.strftime("%I:%M %p %Z").lstrip("0")
        except Exception:
            pass
    return status_text or "Scheduled"


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
                resp = _logo_session.get(url, timeout=LOGO_TIMEOUT_SEC)
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


def _map_team(comp: Dict[str, Any], side: str) -> Dict[str, Any]:
    competitors = comp.get("competitors") or []
    raw = next((c for c in competitors if c.get("homeAway") == side), {})
    team = raw.get("team", {}) or {}
    tri = (team.get("abbreviation") or team.get("shortDisplayName") or "TM").upper()
    tid = str(team.get("id") or "")
    logo = team.get("logo") or ((team.get("logos") or [{}])[0]).get("href")
    if logo:
        _logo_url_map[tid or tri] = logo
        _logo_url_map[tri] = logo
    return {
        "teamId": tid,
        "teamName": team.get("displayName") or team.get("name") or "Team",
        "teamTricode": tri,
        "score": int(raw.get("score") or 0),
        "players": [],
    }


def _build_line(g: Dict[str, Any]) -> str:
    home = g.get("homeTeam", {}) or {}
    away = g.get("awayTeam", {}) or {}
    hs = safe_score(home)
    as_ = safe_score(away)
    status = g.get("gameStatusText") or "Scheduled"
    return f"{away.get('teamName','Away')} {as_} @ {home.get('teamName','Home')} {hs} ({status})"


# Compatibility wrappers expected by the test-suite / external callers
def _normalize_game_for_tests(g: Dict[str, Any]) -> Dict[str, Any]:
    home = (g.get("homeTeam") or {}) or {}
    away = (g.get("awayTeam") or {}) or {}
    game_id = str(g.get("gameId") or g.get("id") or "")
    start_time = g.get("gameTimeUTC") or g.get("startTime") or g.get("date")
    period = g.get("period") or {}
    clock = format_clock(g.get("gameClock") or g.get("clock"))
    shot = format_shotclock(g.get("shotClock"))
    try:
        home_score = safe_score(home)
    except Exception:
        home_score = 0
    try:
        away_score = safe_score(away)
    except Exception:
        away_score = 0

    return {
        "gameId": game_id,
        "sport": SPORT,
        "status": g.get("gameStatus"),
        "home": home.get("teamName") or home.get("teamCity") or "Home",
        "away": away.get("teamName") or away.get("teamCity") or "Away",
        "homeTricode": home.get("teamTricode") or home.get("abbreviation") or "",
        "awayTricode": away.get("teamTricode") or away.get("abbreviation") or "",
        "homeScore": home_score,
        "awayScore": away_score,
        "startTime": start_time,
        "period": period,
        "clock": clock,
        "shotClock": shot,
    }


def fetch_live() -> Dict[str, Any]:
    raw = fetch_scores()
    games = raw.get("games") or []
    normalized = [_normalize_game_for_tests(g) for g in games]
    if not normalized:
        normalized = [
            {
                "gameId": "0",
                "sport": SPORT,
                "status": 1,
                "home": "Home",
                "away": "Away",
                "homeTricode": "HME",
                "awayTricode": "AWY",
                "homeScore": 0,
                "awayScore": 0,
                "startTime": None,
                "period": 0,
                "clock": "--:--",
                "shotClock": "--",
            }
        ]
    return {"games": normalized, "lines": raw.get("lines")}


def fetch_schedule() -> Dict[str, Any]:
    return fetch_live()


def fetch_scores() -> Dict[str, Any]:
    now = time.monotonic()
    if _scoreboard_cache.get("data") is None:
        disk = _load_disk_scoreboard()
        if disk:
            _scoreboard_cache["data"] = disk
            _scoreboard_cache["ts"] = now
            return disk

    cached = _scoreboard_cache.get("data")
    if cached and now - _scoreboard_cache.get("ts", 0) < SCOREBOARD_TTL:
        return cached

    try:
        resp = _logo_session.get(SCOREBOARD_URL, timeout=SCOREBOARD_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        disk = _load_disk_scoreboard()
        if disk:
            return disk
        return {"games": [], "lines": ["No games today."]}

    events = data.get("events", []) or []
    games: List[Dict[str, Any]] = []
    for ev in events:
        comp = (ev.get("competitions") or [{}])[0]
        status_block = (ev.get("status") or {}).get("type", {})
        state = status_block.get("state")
        period = status_block.get("period") or 0
        clock = status_block.get("displayClock")
        start_time = ev.get("date")
        status_text_raw = status_block.get("shortDetail") or status_block.get("detail")
        home = _map_team(comp, "home")
        away = _map_team(comp, "away")

        if state == "pre":
            game_status = 1
            status_text = _extract_start_time_text({"date": start_time, "gameStatusText": status_text_raw})
        elif state == "post":
            game_status = 3
            status_text = status_text_raw or "Final"
        else:
            game_status = 2
            status_text = status_text_raw or (f"P{period} {clock}" if period else "Live")

        game = {
            "gameId": str(ev.get("id")),
            "homeTeam": home,
            "awayTeam": away,
            "gameStatus": game_status,
            "gameStatusText": status_text,
            "period": {"current": period} if period else {},
            "gameClock": clock,
            "gameTimeUTC": start_time,
        }
        games.append(game)

    lines = [_build_line(g) for g in games] if games else ["No games today."]
    result = {"games": games, "lines": lines}
    _scoreboard_cache["data"] = result
    _scoreboard_cache["ts"] = time.monotonic()
    _save_disk_scoreboard(result)
    return result


def _build_header(game: Dict[str, Any]) -> str:
    status_value = game.get("gameStatus")
    period = game.get("period") or {}
    current = period.get("current") if isinstance(period, dict) else period
    clock = format_clock(game.get("gameClock"))
    status_text = (game.get("gameStatusText") or "").strip()

    if status_value == 3 and status_text:
        return status_text
    if status_value in (None, 0, 1) or not current:
        return _extract_start_time_text(game)
    return f"P{current} {clock}" if current else (status_text or clock or "Live")


def fetch_boxscore(game_id: str) -> Dict[str, Any]:
    now = time.monotonic()
    cached = _boxscore_cache.get(game_id)
    if cached and now - cached[0] < BOXSCORE_TTL:
        return cached[1]

    board = _scoreboard_cache.get("data") or _load_disk_scoreboard() or fetch_scores()
    games = board.get("games", []) if isinstance(board, dict) else []
    game = next((g for g in games if str(g.get("gameId")) == str(game_id)), None)
    if game:
        header = _build_header(game)
        result = {
            "game": game,
            "home": game.get("homeTeam", {}),
            "away": game.get("awayTeam", {}),
            "header": header,
            "shotclock": "--",
        }
        _boxscore_cache[game_id] = (now, result)
        _save_disk_boxscore(game_id, result)
        return result

    disk = _load_disk_boxscore(game_id)
    if disk:
        _boxscore_cache[game_id] = (now, disk)
        return disk

    stub = {
        "game": {"gameStatusText": "Scheduled", "period": {"current": None}},
        "home": {"teamName": "Home", "teamTricode": "HME", "score": 0},
        "away": {"teamName": "Away", "teamTricode": "AWY", "score": 0},
        "header": "No data",
        "shotclock": "--",
    }
    _boxscore_cache[game_id] = (now, stub)
    return stub


def build_player_rows(team: Dict[str, Any]) -> List[List[str]]:
    return []
