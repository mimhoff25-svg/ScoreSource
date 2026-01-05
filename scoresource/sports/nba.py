from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

from ..common.utils import extract_three_point_made, format_player_initial_name

NBA_API_AVAILABLE = True
NBA_API_ERROR = ""

try:
    from nba_api.live.nba.endpoints import boxscore, scoreboard, playbyplay
except Exception as exc:  # ModuleNotFoundError or runtime import issues
    NBA_API_AVAILABLE = False
    NBA_API_ERROR = str(exc)
    boxscore = scoreboard = playbyplay = None

SPORT = "nba"


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
    k: "#%02x%02x%02x" % tuple(int(int(v.lstrip("#")[i:i+2], 16) * 0.65) for i in (0, 2, 4))
    for k, v in TEAM_PRIMARY_COLORS.items()
}

TEAM_ACCENT_COLORS: Dict[str, str] = {
    "ATL": "#FF8A65", "BOS": "#58FF9E", "BKN": "#7DF0FF", "CHA": "#A678FF",
    "CHI": "#FF6A6A", "CLE": "#FF9E6E", "DAL": "#63C9FF", "DEN": "#FFCC66",
    "DET": "#4EC4FF", "GSW": "#FFD166", "HOU": "#FF7B7B", "IND": "#73A7FF",
    "LAC": "#FF7B7B", "LAL": "#FFD54F", "MEM": "#8ED0FF", "MIA": "#FF7F9C",
    "MIL": "#7CFF91", "MIN": "#6FE3FF", "NOP": "#8CD0FF", "NYK": "#FFB347",
    "OKC": "#7FE1FF", "ORL": "#7FDBFF", "PHI": "#6EBBFF", "PHX": "#D28BFF",
    "POR": "#FF6A6A", "SAC": "#C08CFF", "SAS": "#C7D7E5", "TOR": "#FF8080",
    "UTA": "#7BC4FF", "WAS": "#7FC1FF",
}

TEAM_COLORS = TEAM_PRIMARY_COLORS
TEAM_ALT_COLORS = TEAM_ACCENT_COLORS

DEMO_MODE = (os.environ.get("SCORESOURCE_DEMO") == "1") or (not NBA_API_AVAILABLE)

_scoreboard_cache: Dict[str, Any] = {"ts": 0.0, "data": None}
_boxscore_cache: Dict[str, Tuple[float, Any]] = {}
_shotclock_cache: Dict[str, Tuple[float, Any]] = {}
_live_clock_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_shotclock_history: Dict[str, Tuple[float, Any]] = {}

SCOREBOARD_TTL = _env_float("SCORESOURCE_NBA_SCOREBOARD_TTL", 15.0, min_value=0.0)
BOXSCORE_TTL = _env_float("SCORESOURCE_NBA_BOXSCORE_TTL", 12.0, min_value=0.0)
SHOTCLOCK_TTL = _env_float("SCORESOURCE_NBA_SHOTCLOCK_TTL", 0.5, min_value=0.0)
LIVE_CLOCK_TTL = _env_float("SCORESOURCE_NBA_LIVE_CLOCK_TTL", 2.0, min_value=0.0)
LIVE_TIMEOUT_SEC = _env_float("SCORESOURCE_NBA_LIVE_TIMEOUT_SEC", 3.0, min_value=1.0)
LOGO_TIMEOUT_SEC = _env_float("SCORESOURCE_NBA_LOGO_TIMEOUT_SEC", 3.0, min_value=1.0)

CACHE_ROOT = _cache_root_from_env()
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
SCOREBOARD_CACHE_PATH = CACHE_ROOT / "nba_scoreboard.json"
BOXSCORE_CACHE_DIR = CACHE_ROOT / "nba_boxscores"
BOXSCORE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

LOGO_VERSION = "2025-05"
LOGO_DIR = CACHE_ROOT / "logos" / SPORT
LOGO_DIR.mkdir(parents=True, exist_ok=True)
_logo_cache: Dict[Tuple[str, str, str], bytes | None] = {}
_logo_session = requests.Session()


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


# ------------------ small helpers for start time ------------------
def _display_zone() -> ZoneInfo:
    tz_name = os.environ.get("SCORESOURCE_TZ", "America/Chicago")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("America/Chicago")


def _extract_start_time_text(g: Dict[str, Any]) -> str:
    status_text = (g.get("gameStatusText") or "").strip()

    game_time_utc = g.get("gameTimeUTC") or g.get("gameEt") or g.get("startTime")
    if isinstance(game_time_utc, str) and game_time_utc:
        try:
            dt = datetime.fromisoformat(game_time_utc.replace("Z", "+00:00"))
            dt_local = dt.astimezone(_display_zone())
            return dt_local.strftime("%a %I:%M %p CT").replace(" 0", " ")
        except Exception:
            pass

    return status_text or "Scheduled"


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
        resp = _logo_session.get(url, timeout=LIVE_TIMEOUT_SEC)
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
    url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
    try:
        resp = _logo_session.get(url, timeout=LIVE_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        actions = data.get("game", {}).get("actions", []) or []
        for action in reversed(actions):
            sc = action.get("shotClock")
            if sc not in (None, "", "--"):
                return sc
    except Exception:
        return None
    return None


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


def _stub_boxscore_from_scoreboard(game_id: str) -> Dict[str, Any] | None:
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


# ------------------ LIVE / HYBRID LOGIC ------------------
def fetch_scores() -> Dict[str, Any]:
    """
    Return today's NBA games, including pre-game, with start times.
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

        def _format_game_line(g: Dict[str, Any]) -> str:
            home_team = g.get("homeTeam", {}) or {}
            away_team = g.get("awayTeam", {}) or {}
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
                if current:
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
    if DEMO_MODE or not NBA_API_AVAILABLE or boxscore is None:
        disk = _load_disk_boxscore(game_id)
        stub = _stub_boxscore_from_scoreboard(game_id)
        result = stub or disk or demo_boxscore()
        _boxscore_cache[game_id] = (time.monotonic(), result)
        return result

    now = time.monotonic()

    if game_id not in _boxscore_cache:
        disk_box = _load_disk_boxscore(game_id)
        if disk_box:
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
        status_val = game_cached.get("gameStatus")
        if status_val in (None, 0, 1) or not _current_period_from_game(game_cached):
            game_cached["gameStatusText"] = header
        result = {**base, "shotclock": shotclock, "header": header}
        _boxscore_cache[game_id] = (cached[0], result)
        _save_disk_boxscore(game_id, result)
        return result

    try:
        data = boxscore.BoxScore(game_id=game_id).get_dict()
    except Exception:
        disk = _load_disk_boxscore(game_id)
        stub = _stub_boxscore_from_scoreboard(game_id)
        result = stub or disk or demo_boxscore()
        _boxscore_cache[game_id] = (time.monotonic(), result)
        return result

    game = data.get("game") or {}
    home = game.get("homeTeam") or {}
    away = game.get("awayTeam") or {}
    if not home or not away:
        disk = _load_disk_boxscore(game_id)
        stub = _stub_boxscore_from_scoreboard(game_id)
        result = stub or disk or demo_boxscore()
        _boxscore_cache[game_id] = (time.monotonic(), result)
        return result

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
    _boxscore_cache[game_id] = (now, result)
    _save_disk_boxscore(game_id, result)
    return result


def _build_header(game: Dict[str, Any]) -> str:
    status_value = game.get("gameStatus")
    current_period = _current_period_from_game(game)
    clock = format_clock(game.get("gameClock"))
    status_text = (game.get("gameStatusText") or "").strip()

    if status_value == 3 and status_text:
        return status_text

    if status_value in (None, 0, 1) or not current_period:
        return _extract_start_time_text(game)

    if current_period:
        return f"Q{current_period} {clock or '--:--'}"

    return status_text or clock or "Scheduled"


sport_table_headers = ["#", "Player", "Min", "Pos", "Pts", "Reb", "Ast", "3pt"]


def build_player_rows(team: Dict[str, Any]) -> List[List[str]]:
    players = team.get("players", []) or []
    def _order(p: Dict[str, Any]) -> Any:
        return p.get("order", 9999)

    def _truthy_flag(val: Any) -> bool:
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "y")
        return bool(val)

    def _is_on_court(p: Dict[str, Any]) -> bool:
        stats = p.get("statistics", {}) or {}
        for key in ("isOnCourt", "onCourt", "oncourt"):
            if key in stats and stats.get(key) not in (None, ""):
                return _truthy_flag(stats.get(key))
        for key in ("onCourt", "oncourt", "isOnCourt"):
            if key in p and p.get(key) not in (None, ""):
                return _truthy_flag(p.get(key))
        return False

    on_court = [p for p in players if _is_on_court(p)]
    off_court = [p for p in players if not _is_on_court(p)]
    on_court.sort(key=_order)
    off_court.sort(key=_order)
    if on_court:
        players = on_court[:5] + off_court + on_court[5:]
    else:
        players = sorted(players, key=_order)
    rows: List[List[str]] = []
    for p in players:
        stats = p.get("statistics", {}) or {}
        jersey = p.get("jerseyNum") or ""
        first = (p.get("firstName") or "").strip()
        last = (p.get("familyName") or "").strip()
        name = format_player_initial_name(first, last)
        pos = p.get("position") or ""
        minutes = format_time_played(stats.get("minutes") or stats.get("minutesCalculated"))
        pts = str(stats.get("points", 0))
        reb = str(stats.get("reboundsTotal", stats.get("rebounds", 0)))
        ast = str(stats.get("assists", 0))
        pf = str(extract_three_point_made(stats))
        rows.append([jersey, name, minutes, pos, pts, reb, ast, pf])
    return rows


# Compatibility wrappers expected by the test-suite / external callers
def _normalize_game_for_tests(g: Dict[str, Any]) -> Dict[str, Any]:
    home = (g.get("homeTeam") or {}) or {}
    away = (g.get("awayTeam") or {}) or {}
    game_id = str(g.get("gameId") or g.get("gameCode") or "")
    start_time = g.get("gameTimeUTC") or g.get("gameEt") or g.get("gameTime") or g.get("gameTimeUTC")
    period = _current_period_from_game(g) or _current_period_from_game(g.get("period") or {})
    clock = format_clock(g.get("gameClock"))
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
        "home": home.get("teamName") or home.get("nickname") or home.get("teamCity") or "Home",
        "away": away.get("teamName") or away.get("nickname") or away.get("teamCity") or "Away",
        "homeTricode": home.get("teamTricode") or home.get("tricode") or "",
        "awayTricode": away.get("teamTricode") or away.get("tricode") or "",
        "homeScore": home_score,
        "awayScore": away_score,
        "startTime": start_time,
        "period": period,
        "clock": clock,
        "shotClock": shot,
    }


def fetch_live() -> Dict[str, Any]:
    """Return live games in the normalized shape expected by consumers/tests."""
    raw = fetch_scores()
    games = raw.get("games") or []
    normalized = [_normalize_game_for_tests(g) for g in games]
    return {"games": normalized, "lines": raw.get("lines")}


def fetch_schedule() -> Dict[str, Any]:
    """Return schedule (same as live) normalized for compatibility."""
    return fetch_live()
