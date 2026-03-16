from __future__ import annotations

from typing import Any, Dict, List

from .common.lineups import apply_starting_lineups
from .common.utils import extract_three_point_made, format_player_initial_name
from .sports_meta import display_name_for_sport
from .sports import ncaa_basketball as backend

SPORT_KEY = "NCAA BASKETBALL"
sport_name = display_name_for_sport(SPORT_KEY)
sport_table_headers = backend.sport_table_headers

TEAM_PRIMARY_COLORS: Dict[str, str] = backend.TEAM_PRIMARY_COLORS
TEAM_COLORS = TEAM_PRIMARY_COLORS
TEAM_SECONDARY_COLORS: Dict[str, str] = backend.TEAM_SECONDARY_COLORS
TEAM_ACCENT_COLORS: Dict[str, str] = backend.TEAM_ACCENT_COLORS
TEAM_ALT_COLORS: Dict[str, str] = backend.TEAM_ALT_COLORS


def safe_score(team: Dict[str, Any]) -> int:
    return backend.safe_score(team)


def format_time_played(value: Any) -> str:
    return backend.format_time_played(value)


def format_shotclock(value: Any) -> str:
    return backend.format_shotclock(value)


def fetch_scoreboard() -> Dict[str, Any]:
    return backend.fetch_scores()


def fetch_boxscore(game_id: str) -> Dict[str, Any]:
    box = backend.fetch_boxscore(game_id) or {}
    game = box.get("game") or {}
    home = box.get("home") or {"teamName": "HOME", "teamTricode": "HOME", "score": 0, "players": []}
    away = box.get("away") or {"teamName": "AWAY", "teamTricode": "AWAY", "score": 0, "players": []}
    header = box.get("header") or game.get("gameStatusText") or "Scheduled"
    apply_starting_lineups(SPORT_KEY, home, away)
    return {
        "game": game,
        "home": home,
        "away": away,
        "header": header,
        "shotclock": box.get("shotclock") or "--",
    }


def get_scoreboard() -> Dict[str, Any]:
    return fetch_scoreboard()


def get_boxscore(game_id: str) -> Dict[str, Any]:
    return fetch_boxscore(game_id)


def get_team_logo(team_id: str | None, tricode: str | None) -> bytes | None:
    return load_logo(team_id, tricode)


def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    return backend.load_logo(team_id, tricode)


def _player_sort_key(player: Dict[str, Any]) -> tuple[int, int, int, str]:
    stats = player.get("statistics") or {}
    starter = bool(player.get("starter"))
    try:
        minutes = int(float(stats.get("minutes") or 0))
    except Exception:
        minutes = 0
    try:
        points = int(float(stats.get("points") or 0))
    except Exception:
        points = 0
    name = str(player.get("displayName") or player.get("fullName") or "")
    return (0 if starter else 1, -minutes, -points, name)


def build_player_rows(team: Dict[str, Any]) -> List[List[str]]:
    players = team.get("players") or []
    if not isinstance(players, list) or not players:
        return []

    rows: List[List[str]] = []
    for player in sorted((entry for entry in players if isinstance(entry, dict)), key=_player_sort_key):
        stats = player.get("statistics") or {}
        name = format_player_initial_name(player.get("firstName"), player.get("familyName"))
        if not name.strip():
            name = str(player.get("displayName") or player.get("fullName") or "")
        three_pt = extract_three_point_made(stats)
        rows.append(
            [
                str(player.get("jerseyNum") or ""),
                str(name or ""),
                backend.format_time_played(stats.get("minutes")),
                str(player.get("position") or ""),
                str(stats.get("points") or 0),
                str(stats.get("reboundsTotal") or stats.get("rebounds") or 0),
                str(stats.get("assists") or 0),
                str(three_pt),
            ]
        )
    return rows
