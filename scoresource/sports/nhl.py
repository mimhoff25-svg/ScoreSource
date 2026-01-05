from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests
import logging

SPORT = "nhl"
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"

TEAM_PRIMARY_COLORS: Dict[str, str] = {
    "ANA": "#F47A38",
    "ARI": "#8C2633",
    "BOS": "#FFB81C",
    "BUF": "#002654",
    "CGY": "#C8102E",
    "CAR": "#CC0000",
    "CHI": "#CF0A2C",
    "COL": "#6F263D",
    "CBJ": "#002654",
    "DAL": "#006847",
    "DET": "#CE1126",
    "EDM": "#041E42",
    "FLA": "#041E42",
    "LAK": "#111111",
    "MIN": "#154734",
    "MTL": "#AF1E2D",
    "NSH": "#FFB81C",
    "NJD": "#C8102E",
    "NYI": "#00529B",
    "NYR": "#0038A8",
    "OTT": "#C52032",
    "PHI": "#F74902",
    "PIT": "#FCB514",
    "SEA": "#99D9D9",
    "SJS": "#006D75",
    "STL": "#002F87",
    "TBL": "#002868",
    "TOR": "#00205B",
    "VAN": "#00205B",
    "VGK": "#B4975A",
    "WSH": "#041E42",
    "WPG": "#041E42",
}

TRICODE_ALIASES: Dict[str, str] = {
    "LA": "LAK",
    "NJ": "NJD",
    "SJ": "SJS",
    "TB": "TBL",
    "WAS": "WSH",
}


def _scale(hex_color: str, factor: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    vals = [int(h[i : i + 2], 16) for i in (0, 2, 4)]
    scaled = [min(255, max(0, int(v * factor))) for v in vals]
    return "#%02x%02x%02x" % tuple(scaled)


TEAM_SECONDARY_COLORS: Dict[str, str] = {k: _scale(v, 0.65) for k, v in TEAM_PRIMARY_COLORS.items()}
TEAM_ACCENT_COLORS: Dict[str, str] = {k: _scale(v, 1.3) for k, v in TEAM_PRIMARY_COLORS.items()}
TEAM_COLORS = TEAM_PRIMARY_COLORS
TEAM_ALT_COLORS = TEAM_ACCENT_COLORS

logger = logging.getLogger(__name__)

_scoreboard_cache: Dict[str, Any] = {"ts": 0.0, "data": None}
_boxscore_cache: Dict[str, Tuple[float, Any]] = {}

SCOREBOARD_TTL = 15.0
BOXSCORE_TTL = 12.0

CACHE_ROOT = Path.home() / ".cache" / "scoresource"
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

sport_table_headers = ["#", "Player", "Pos", "G", "A", "PTS", "SOG", "PIM", "SV", "SV%"]

STAT_MAP: Dict[str, List[str]] = {
    "goals": ["goals", "g"],
    "assists": ["assists", "a"],
    "points": ["points", "pts"],
    "shots": ["shots", "sog", "shotsOnGoal"],
    "pim": ["pim", "penaltyMinutes"],
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
    match = re.match(r"^(\d+):(\d{2})$", clock_raw)
    if match:
        return f"{int(match.group(1))}:{int(match.group(2)):02d}"
    return text


def _period_label(period: int | None, status_text: str | None = None) -> str:
    text = (status_text or "").upper()
    if "SHOOTOUT" in text or "SO" in text:
        return "SO"
    if period in (1, 2, 3):
        return f"P{period}"
    if period and period > 3:
        return "OT" if period == 4 else f"OT{period - 3}"
    return ""


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
        except Exception as exc:
            logger.exception("_extract_start_time_text failed for %r", iso_val)
            pass
    return status_text or "Scheduled"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        logger.exception("Failed to load JSON from %s: %s", path, exc)
        return None


def _save_json(path: Path, payload: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
    except Exception as exc:
        logger.exception("Failed to save JSON to %s: %s", path, exc)


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
            except Exception as exc:
                logger.exception("Failed to read logo cache file %s: %s", cache_path, exc)
                return None
        return None

    def _fetch_urls(urls: List[str]) -> tuple[bytes | None, str]:
        for url in urls:
            try:
                resp = _logo_session.get(url, timeout=3)
                resp.raise_for_status()
                ext = ".svg" if url.lower().endswith(".svg") else ".png"
                return resp.content, ext
            except Exception as exc:
                logger.debug("Logo fetch failed for %s: %s", url, exc)
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
        except Exception as exc:
            logger.exception("Failed to write logo cache %s: %s", cache_path, exc)
        _logo_cache[key] = content
        return content

    _logo_cache[key] = None
    return None


def _map_team(comp: Dict[str, Any], side: str) -> Dict[str, Any]:
    competitors = comp.get("competitors") or []
    raw = next((c for c in competitors if c.get("homeAway") == side), {})
    team = raw.get("team", {}) or {}
    tri_raw = team.get("abbreviation") or team.get("shortDisplayName") or "TM"
    tri = _normalize_tricode(tri_raw)
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
        resp = _logo_session.get(SCOREBOARD_URL, timeout=5)
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
        status = ev.get("status") or {}
        status_type = status.get("type") or {}
        state = status_type.get("state")
        period = status.get("period") or 0
        clock = status.get("displayClock") or status.get("clock")
        start_time = ev.get("date")
        status_text_raw = status_type.get("shortDetail") or status_type.get("detail")
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
            label = _period_label(period, status_text_raw)
            if status_text_raw and "intermission" in status_text_raw.lower():
                status_text = "Intermission"
            else:
                status_text = status_text_raw or (f"{label} {clock}".strip() if (label or clock) else "Live")

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
    if status_text:
        return status_text
    label = _period_label(current, status_text)
    return f"{label} {clock}".strip() if (label or clock) else "Live"


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


# Compatibility wrappers expected by the test-suite / external callers
def _normalize_game_for_tests(g: Dict[str, Any]) -> Dict[str, Any]:
    home = (g.get("homeTeam") or {}) or {}
    away = (g.get("awayTeam") or {}) or {}
    game_id = str(g.get("gameId") or g.get("id") or "")
    start_time = g.get("gameTimeUTC") or g.get("gameEt") or g.get("date")
    period_field = g.get("period")
    if isinstance(period_field, dict):
        period = period_field.get("current")
    elif isinstance(period_field, int):
        period = period_field
    else:
        period = None
    clock = format_clock(g.get("gameClock") or g.get("clock"))
    shot = format_shotclock(g.get("shotClock")) if "format_shotclock" in globals() else "--"
    status = _status_from_game(g)
    period_display = _period_label(period, g.get("gameStatusText")) if status == "live" else ""
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
        "status": status,
        "home": home.get("teamName") or home.get("nickname") or "Home",
        "away": away.get("teamName") or away.get("nickname") or "Away",
        "homeTricode": _normalize_tricode(home.get("teamTricode") or home.get("abbreviation")),
        "awayTricode": _normalize_tricode(away.get("teamTricode") or away.get("abbreviation")),
        "homeScore": home_score,
        "awayScore": away_score,
        "startTime": start_time,
        "period": period_display,
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
                "status": "upcoming",
                "home": "Home",
                "away": "Away",
                "homeTricode": "HME",
                "awayTricode": "AWY",
                "homeScore": 0,
                "awayScore": 0,
                "startTime": None,
                "period": "",
                "clock": "--:--",
                "shotClock": "--",
            }
        ]
    return {"games": normalized, "lines": raw.get("lines")}


def fetch_schedule() -> Dict[str, Any]:
    return fetch_live()
