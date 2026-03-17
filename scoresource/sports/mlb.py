from __future__ import annotations

from typing import Any, Dict, List

from .. import mlb as backend

SPORT = "mlb"

TEAM_PRIMARY_COLORS: Dict[str, str] = backend.TEAM_PRIMARY_COLORS
TEAM_SECONDARY_COLORS: Dict[str, str] = backend.TEAM_SECONDARY_COLORS
TEAM_ACCENT_COLORS: Dict[str, str] = backend.TEAM_ACCENT_COLORS
TEAM_ALT_COLORS: Dict[str, str] = backend.TEAM_ALT_COLORS
TEAM_COLORS: Dict[str, str] = backend.TEAM_COLORS

sport_table_headers = backend.sport_table_headers


def safe_score(team: Dict[str, Any]) -> int:
    return backend.safe_score(team)


def format_time_played(value: Any) -> str:
    return backend.format_time_played(value)


def format_shotclock(value: Any) -> str:
    return backend.format_shotclock(value)


def fetch_scores() -> Dict[str, Any]:
    return backend.get_scoreboard()


def fetch_boxscore(game_id: str) -> Dict[str, Any]:
    return backend.get_boxscore(game_id)


def fetch_play_by_play(game_id: str, limit: int = 18) -> List[Dict[str, Any]]:
    return backend.fetch_play_by_play(game_id, limit)


def get_team_colors(tricode: str) -> Dict[str, str]:
    return backend.get_team_colors(tricode)


def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    return backend.load_logo(team_id, tricode)


def get_team_logo(team_id: str | None, tricode: str | None) -> bytes | None:
    return backend.get_team_logo(team_id, tricode)


def build_player_rows(team: Dict[str, Any]) -> List[List[str]]:
    return backend.build_player_rows(team)


def _status_value(game: Dict[str, Any]) -> int:
    status = game.get("gameStatus")
    if isinstance(status, int):
        return status
    raw = str(game.get("status") or "").strip().lower()
    if raw in ("final", "post"):
        return 3
    if raw in ("upcoming", "pre", "scheduled"):
        return 1
    return 2


def _normalize_game_for_tests(game: Dict[str, Any]) -> Dict[str, Any]:
    home = (game.get("homeTeam") or {}) or {}
    away = (game.get("awayTeam") or {}) or {}
    period_field = game.get("period")
    if isinstance(period_field, dict):
        period = period_field.get("current")
    elif isinstance(period_field, int):
        period = period_field
    else:
        period = None

    return {
        "gameId": str(game.get("gameId") or game.get("id") or ""),
        "sport": SPORT,
        "status": _status_value(game),
        "home": home.get("teamName") or home.get("teamCity") or "Home",
        "away": away.get("teamName") or away.get("teamCity") or "Away",
        "homeTricode": home.get("teamTricode") or home.get("abbreviation") or "",
        "awayTricode": away.get("teamTricode") or away.get("abbreviation") or "",
        "homeScore": safe_score(home),
        "awayScore": safe_score(away),
        "startTime": game.get("startTime") or game.get("gameTimeUTC") or game.get("date"),
        "period": period,
        "clock": str(game.get("gameClock") or game.get("clock") or "--:--"),
        "shotClock": "--",
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
    return {"games": normalized, "lines": raw.get("lines") or []}


def fetch_schedule() -> Dict[str, Any]:
    return fetch_live()
