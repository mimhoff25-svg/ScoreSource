from __future__ import annotations

"""
NBA backend (wraps existing pyside/nba.py for real data; adapts to unified contract).
"""

import importlib.util
from pathlib import Path
from typing import Any, Dict, List

from .common.lineups import apply_starting_lineups
from .common.timefmt import format_start_time

_backend_path = Path(__file__).resolve().parents[1] / "pyside" / "nba.py"
_nba = None
if _backend_path.exists():
    spec = importlib.util.spec_from_file_location("scoresource_pyside_nba", _backend_path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[arg-type]
        _nba = module
if _nba is None:
    raise ImportError(f"Unable to load NBA backend from {_backend_path}")

TEAM_PRIMARY_COLORS: Dict[str, str] = getattr(_nba, "TEAM_PRIMARY_COLORS", {})
TEAM_SECONDARY_COLORS: Dict[str, str] = getattr(_nba, "TEAM_SECONDARY_COLORS", {})
TEAM_ACCENT_COLORS: Dict[str, str] = getattr(_nba, "TEAM_ACCENT_COLORS", {})
TEAM_ALT_COLORS: Dict[str, str] = getattr(_nba, "TEAM_ALT_COLORS", TEAM_ACCENT_COLORS)
TEAM_COLORS: Dict[str, str] = TEAM_PRIMARY_COLORS


def _status_from_game(g: Dict[str, Any]) -> str:
    gs = g.get("gameStatus")
    if gs == 3:
        return "final"
    if gs in (1, 0, None):
        return "upcoming"
    return "live"


def _is_halftime(g: Dict[str, Any]) -> bool:
    status_text = (g.get("gameStatusText") or g.get("statusText") or "").lower().replace("-", " ")
    if "halftime" in status_text or "half time" in status_text:
        return True
    period = g.get("period", {})
    current = period.get("current") if isinstance(period, dict) else period
    if current != 2:
        return False
    clock = _nba.format_clock(g.get("gameClock"))
    return clock in ("0:00", "00:00")


def _header_from_game(g: Dict[str, Any]) -> str:
    status = _status_from_game(g)
    if status == "upcoming":
        return format_start_time(g.get("gameTimeUTC") or g.get("gameEt") or g.get("startTime"))
    if status == "final":
        return "Final"
    if _is_halftime(g):
        return "HALF TIME"
    period = g.get("period", {})
    current = period.get("current") if isinstance(period, dict) else period
    clock = _nba.format_clock(g.get("gameClock"))
    return f"Q{current} {clock}".strip() if current else (g.get("gameStatusText") or clock or "Live")


def get_scoreboard() -> Dict[str, Any]:
    try:
        raw = _nba.fetch_scores()
    except Exception:
        raw = _nba.demo_scoreboard()
    games_raw = raw.get("games", []) or []
    games = []
    for g in games_raw:
        status = _status_from_game(g)
        header = _header_from_game(g)
        games.append(
            {
                "gameId": g.get("gameId"),
                "homeTeam": g.get("homeTeam", {}),
                "awayTeam": g.get("awayTeam", {}),
                "status": status,
                "startTime": g.get("gameTimeUTC") or g.get("gameEt"),
                "header": header,
                "gameStatusText": header,
                "seasonYear": g.get("seasonYear") or "2025",
            }
        )
    lines = raw.get("lines") or [f"{(g.get('awayTeam') or {}).get('teamName','Away')} @ {(g.get('homeTeam') or {}).get('teamName','Home')}" for g in games]
    if not games:
        games = [
            {
                "gameId": "NBA_DEMO",
                "homeTeam": {"teamId": "0", "teamName": "Home", "teamTricode": "HME", "score": 0},
                "awayTeam": {"teamId": "0", "teamName": "Away", "teamTricode": "AWY", "score": 0},
                "status": "upcoming",
                "startTime": None,
                "header": "Demo",
                "seasonYear": "2025",
            }
        ]
        lines = ["AWY 0 @ HME 0 (Demo)"]
    return {"games": games, "lines": lines}


def get_boxscore(game_id: str) -> Dict[str, Any]:
    try:
        raw = _nba.fetch_boxscore(game_id)
    except Exception:
        raw = _nba.demo_boxscore()
    header = raw.get("header") or _header_from_game(raw.get("game", {}))
    shotclock = raw.get("shotclock") or _nba.format_shotclock(raw.get("game", {}).get("shotClock"))
    home = raw.get("home") or {}
    away = raw.get("away") or {}
    apply_starting_lineups("NBA", home, away)
    return {
        "game": raw.get("game") or {},
        "home": home,
        "away": away,
        "header": header,
        "shotclock": shotclock,
    }


def get_team_colors(tricode: str) -> Dict[str, str]:
    tri = (tricode or "").upper()
    primary = TEAM_PRIMARY_COLORS.get(tri, "#444444")
    secondary = TEAM_SECONDARY_COLORS.get(tri, primary)
    accent = TEAM_ACCENT_COLORS.get(tri, primary)
    alt = TEAM_ALT_COLORS.get(tri, accent)
    return {"primary": primary, "secondary": secondary, "accent": accent, "alt": alt}


def get_team_logo(team_id: str | None, tricode: str | None) -> bytes | None:
    try:
        return _nba.load_logo(team_id, tricode)
    except Exception:
        return None


sport_table_headers = ["#", "Player", "Min", "Pos", "Pts", "Reb", "Ast", "3pt"]

# legacy compat
def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    return get_team_logo(team_id, tricode)


def safe_score(team: Dict[str, Any]) -> int:
    try:
        return _nba.safe_score(team)
    except Exception:
        try:
            return int(team.get("score") or 0)
        except Exception:
            return 0


def format_time_played(value: Any) -> str:
    try:
        return _nba.format_time_played(value)
    except Exception:
        return str(value or "")


def format_shotclock(value: Any) -> str:
    try:
        return _nba.format_shotclock(value)
    except Exception:
        return "--"


def get_rss_headlines(limit: int = 10) -> list[str]:
    try:
        return _nba.fetch_rss_headlines(limit)
    except Exception:
        return []


def fetch_play_by_play(game_id: str, limit: int = 16) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    try:
        if hasattr(_nba, "_fetch_pbp_actions"):
            actions = _nba._fetch_pbp_actions(game_id) or []  # type: ignore[attr-defined]
        else:
            url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
            resp = _nba._logo_session.get(url, timeout=5)  # type: ignore[attr-defined]
            resp.raise_for_status()
            data = resp.json()
            actions = data.get("game", {}).get("actions", []) or []
    except Exception:
        actions = []

    if not actions:
        return []
    cleaned: List[Dict[str, Any]] = []
    for action in actions:
        desc = str(action.get("description") or "").strip()
        if not desc:
            continue
        cleaned.append(
            {
                "id": action.get("actionNumber") or action.get("orderNumber"),
                "period": action.get("period"),
                "clock": _nba.format_clock(action.get("clock")),
                "description": desc,
                "teamTricode": (action.get("teamTricode") or "").upper(),
                "scoreHome": action.get("scoreHome"),
                "scoreAway": action.get("scoreAway"),
            }
        )
    if not cleaned:
        return []
    return cleaned[-max(1, int(limit)) :]


# compatibility aliases for UI expecting legacy names
fetch_scoreboard = get_scoreboard
fetch_boxscore = get_boxscore
fetch_rss_headlines = get_rss_headlines
