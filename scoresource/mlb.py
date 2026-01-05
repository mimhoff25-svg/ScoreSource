from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Tuple

import requests

from .common.lineups import apply_starting_lineups
from .common.timefmt import format_start_time


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


SCOREBOARD_URL = "https://cdn.espn.com/core/mlb/scoreboard?xhr=1&render=false"
HEADERS = {"User-Agent": "ScoreSource/1.0", "Referer": "https://www.espn.com"}

CACHE_ROOT = _cache_root_from_env()
LOGO_DIR = CACHE_ROOT / "logos" / "mlb"
LOGO_DIR.mkdir(parents=True, exist_ok=True)
_logo_cache: Dict[Tuple[str, str], bytes | None] = {}
_session = requests.Session()

SCOREBOARD_TIMEOUT_SEC = _env_float("SCORESOURCE_MLB_SCOREBOARD_TIMEOUT_SEC", 8.0, min_value=1.0)
LOGO_TIMEOUT_SEC = _env_float("SCORESOURCE_MLB_LOGO_TIMEOUT_SEC", 5.0, min_value=1.0)

TEAM_PRIMARY_COLORS: Dict[str, str] = {
    "ARI": "#A71930",
    "ATL": "#13274F",
    "BAL": "#DF4601",
    "BOS": "#BD3039",
    "CHC": "#0E3386",
    "CWS": "#27251F",
    "CIN": "#C6011F",
    "CLE": "#0C2340",
    "COL": "#33006F",
    "DET": "#0C2340",
    "HOU": "#002D62",
    "KC": "#004687",
    "LAA": "#BA0021",
    "LAD": "#005A9C",
    "MIA": "#00A3E0",
    "MIL": "#12284B",
    "MIN": "#002B5C",
    "NYM": "#002D72",
    "NYY": "#0C2340",
    "OAK": "#003831",
    "PHI": "#E81828",
    "PIT": "#FDB827",
    "SD": "#2F241D",
    "SEA": "#005C5C",
    "SF": "#FD5A1E",
    "STL": "#C41E3A",
    "TB": "#092C5C",
    "TEX": "#003278",
    "TOR": "#134A8E",
    "WSH": "#AB0003",
    "HME": "#4E4E4E",
    "AWY": "#2E2E2E",
}


def _scale(hex_color: str, factor: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    vals = [int(h[i : i + 2], 16) for i in (0, 2, 4)]
    scaled = [min(255, max(0, int(v * factor))) for v in vals]
    return "#%02x%02x%02x" % tuple(scaled)


TEAM_SECONDARY_COLORS: Dict[str, str] = {k: _scale(v, 0.65) for k, v in TEAM_PRIMARY_COLORS.items()}
TEAM_ACCENT_COLORS: Dict[str, str] = {k: _scale(v, 1.35) for k, v in TEAM_PRIMARY_COLORS.items()}
TEAM_ALT_COLORS: Dict[str, str] = dict(TEAM_ACCENT_COLORS)
TEAM_COLORS: Dict[str, str] = TEAM_PRIMARY_COLORS
sport_table_headers = ["#", "Player", "Pos", "AVG", "HR", "RBI", "OBP", "SLG"]
TRICODE_ALIASES: Dict[str, str] = {
    "CHW": "CWS",
    "WSN": "WSH",
    "AZ": "ARI",
    "SDP": "SD",
}


def get_scoreboard() -> Dict[str, Any]:
    try:
        resp = _session.get(SCOREBOARD_URL, headers=HEADERS, timeout=SCOREBOARD_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        events = (data.get("content", {}).get("sbData", {}).get("events", [])) or data.get("events", []) or []
    except Exception:
        return _demo_scoreboard()

    games = []
    for ev in events:
        comp = (ev.get("competitions") or [{}])[0]
        status_block = (ev.get("status") or {}).get("type", {})
        state = status_block.get("state")
        period = status_block.get("period") or 0
        clock = status_block.get("displayClock")
        start = ev.get("date")
        home_raw = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "home"), {})
        away_raw = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "away"), {})
        home = _map_team(home_raw)
        away = _map_team(away_raw)
        status = "final" if state == "post" else ("upcoming" if state == "pre" else "live")
        if status == "upcoming":
            header = format_start_time(start)
        elif status == "final":
            header = "Final"
        else:
            header = status_block.get("shortDetail") or f"{clock or ''}".strip()
        games.append(
            {
                "gameId": str(ev.get("id")),
                "homeTeam": home,
                "awayTeam": away,
                "status": status,
                "startTime": start,
                "header": header,
                "gameStatusText": header,
                "seasonYear": str(ev.get("season", {}).get("year") or "2025"),
            }
        )
    if not games:
        return _demo_scoreboard()
    lines = [_line(g) for g in games]
    return {"games": games, "lines": lines}


def get_boxscore(game_id: str) -> Dict[str, Any]:
    board = get_scoreboard()
    game = next((g for g in board.get("games", []) if g.get("gameId") == game_id), None)
    if not game:
        return _demo_boxscore(game_id)
    header = game.get("header")
    home = {**game.get("homeTeam", {}), "players": []}
    away = {**game.get("awayTeam", {}), "players": []}
    apply_starting_lineups("MLB", home, away)
    return {
        "game": {"gameClock": None, "shotClock": None, "period": {"current": None}, "gameStatusText": header},
        "home": home,
        "away": away,
        "header": header,
        "shotclock": "--",
    }


def get_team_colors(tricode: str) -> Dict[str, str]:
    tri = (tricode or "").upper()
    return {
        "primary": TEAM_PRIMARY_COLORS.get(tri, "#444444"),
        "secondary": TEAM_SECONDARY_COLORS.get(tri, "#2b2b2b"),
        "accent": TEAM_ACCENT_COLORS.get(tri, "#777777"),
    }


def get_team_logo(team_id: str | None, tricode: str | None) -> bytes | None:
    tri = (tricode or "").upper()
    key = (team_id or "", tri)
    if key in _logo_cache:
        return _logo_cache[key]
    cache_path = LOGO_DIR / f"{team_id or tri or 'unknown'}.png"
    if cache_path.exists():
        try:
            data = cache_path.read_bytes()
            _logo_cache[key] = data
            return data
        except Exception:
            pass
    urls = []
    if tri:
        urls.append(f"https://www.mlbstatic.com/team-logos/{tri}.svg")
        urls.append(f"https://a.espncdn.com/i/teamlogos/mlb/500/{tri}.png")
    for url in urls:
        try:
            resp = _session.get(url, headers=HEADERS, timeout=LOGO_TIMEOUT_SEC)
            resp.raise_for_status()
            data = resp.content
            cache_path.write_bytes(data)
            _logo_cache[key] = data
            return data
        except Exception:
            continue
    _logo_cache[key] = None
    return None


def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    return get_team_logo(team_id, tricode)


def safe_score(team: Dict[str, Any]) -> int:
    try:
        return int(team.get("score") or 0)
    except Exception:
        return 0


def format_time_played(value: Any) -> str:
    if value in (None, "", 0):
        return ""
    return str(value)


def format_shotclock(value: Any) -> str:
    return "--"


def _record_summary(raw: Dict[str, Any]) -> str | None:
    records = raw.get("records") or raw.get("record") or []
    if isinstance(records, dict):
        records = [records]
    summary = None
    for rec in records:
        if not isinstance(rec, dict):
            continue
        value = rec.get("summary") or rec.get("displayValue") or rec.get("shortDisplayName")
        if not value:
            continue
        rec_type = str(rec.get("type") or rec.get("name") or "").lower()
        if rec_type in ("total", "overall", "ytd", "game"):
            summary = value
            break
        if summary is None:
            summary = value
    return str(summary) if summary else None


def _wins_losses_from_summary(summary: str | None) -> tuple[int, int] | None:
    if not summary:
        return None
    nums = re.findall(r"\d+", str(summary))
    if len(nums) < 2:
        return None
    try:
        return int(nums[0]), int(nums[1])
    except Exception:
        return None


def _map_team(raw: Dict[str, Any]) -> Dict[str, Any]:
    team = raw.get("team", {}) or {}
    tri_raw = (team.get("abbreviation") or team.get("shortDisplayName") or "TM").upper()
    tri = TRICODE_ALIASES.get(tri_raw, tri_raw)
    mapped = {
        "teamId": str(team.get("id") or ""),
        "teamName": team.get("displayName") or team.get("name") or "Team",
        "teamTricode": tri,
        "score": int(raw.get("score") or 0),
    }
    summary = _record_summary(raw)
    wins_losses = _wins_losses_from_summary(summary)
    if summary:
        mapped["record"] = summary
    if wins_losses:
        mapped["wins"], mapped["losses"] = wins_losses
    return mapped


def _line(g: Dict[str, Any]) -> str:
    away = g.get("awayTeam", {}) or {}
    home = g.get("homeTeam", {}) or {}
    return f"{away.get('teamTricode','AWY')} {away.get('score',0)} @ {home.get('teamTricode','HME')} {home.get('score',0)} ({g.get('header','')})"


def _demo_scoreboard() -> Dict[str, Any]:
    now = time.time()
    games = [
        {
            "gameId": "MLB_DEMO",
            "homeTeam": {"teamId": "SF", "teamName": "Giants", "teamTricode": "SF", "score": 0},
            "awayTeam": {"teamId": "LAD", "teamName": "Dodgers", "teamTricode": "LAD", "score": 0},
            "status": "upcoming",
            "startTime": now + 3600,
            "header": format_start_time(now + 3600),
            "seasonYear": "2025",
        }
    ]
    return {"games": games, "lines": [_line(games[0])]}


def _demo_boxscore(game_id: str) -> Dict[str, Any]:
    board = _demo_scoreboard()
    g = board["games"][0]
    return {
        "game": {"gameClock": None, "shotClock": None, "period": {"current": 0}, "gameStatusText": g["header"]},
        "home": {**g["homeTeam"], "players": []},
        "away": {**g["awayTeam"], "players": []},
        "header": g["header"],
        "shotclock": "--",
    }


# compatibility aliases
fetch_scoreboard = get_scoreboard
fetch_boxscore = get_boxscore
