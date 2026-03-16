from __future__ import annotations

from typing import Any, Dict, List

from .sports import mls as backend
from .common.lineups import apply_starting_lineups
from .sports_meta import display_name_for_sport

SPORT_KEY = "MLS"
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
    game = box.get("game", {}) or {}
    home = box.get("home") or {"teamName": "HOME", "teamTricode": "HME", "score": 0, "players": []}
    away = box.get("away") or {"teamName": "AWAY", "teamTricode": "AWY", "score": 0, "players": []}
    header = box.get("header") or game.get("gameStatusText") or "Scheduled"
    apply_starting_lineups(SPORT_KEY, home, away)
    return {
        "game": game,
        "home": home,
        "away": away,
        "header": header,
        "shotclock": box.get("shotclock"),
    }


def get_scoreboard() -> Dict[str, Any]:
    return fetch_scoreboard()


def get_boxscore(game_id: str) -> Dict[str, Any]:
    return fetch_boxscore(game_id)


def get_team_logo(team_id: str | None, tricode: str | None) -> bytes | None:
    return load_logo(team_id, tricode)


def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    return backend.load_logo(team_id, tricode)


def build_player_rows(team: Dict[str, Any]) -> List[List[str]]:
    return backend.build_player_rows(team)
