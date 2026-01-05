from __future__ import annotations

from typing import Any, Dict, List

from .sports import ncaa_football as backend
from .common.lineups import apply_starting_lineups

sport_name = "NCAA Football"
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


def _normalize_status_text(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return "Scheduled"
    lowered = text.lower()
    if "sched" in lowered:
        return text
    live_tokens = ("q", "final", "ot", "end", "half", "period")
    if any(token in lowered for token in live_tokens):
        return text or "Scheduled"
    if text and not lowered.startswith("starts"):
        return f"Starts {text}"
    return text or "Scheduled"


def _normalize_game(game: Dict[str, Any]) -> Dict[str, Any]:
    game.setdefault("period", {"current": None})
    if isinstance(game.get("period"), int):
        game["period"] = {"current": game["period"]}
    game.setdefault("gameClock", None)
    game["gameStatusText"] = _normalize_status_text(game.get("gameStatusText", ""))
    return game


def fetch_scoreboard() -> Dict[str, Any]:
    data = backend.fetch_scores()
    games = data.get("games", []) or []
    lines: List[str] = []
    for g in games:
        _normalize_game(g)
        away = g.get("awayTeam", {}) or {}
        home = g.get("homeTeam", {}) or {}
        lines.append(
            f"{away.get('teamName','Away')} {safe_score(away)} @ {home.get('teamName','Home')} {safe_score(home)} "
            f"({_normalize_status_text(g.get('gameStatusText',''))})"
        )
    return {"games": games, "lines": lines}


def fetch_boxscore(game_id: str) -> Dict[str, Any]:
    box = backend.fetch_boxscore(game_id) or {}
    game = _normalize_game(box.get("game", {}) or {})
    home = box.get("home") or {"teamName": "HOME", "teamTricode": "HME", "score": 0, "players": []}
    away = box.get("away") or {"teamName": "AWAY", "teamTricode": "AWY", "score": 0, "players": []}
    header = _normalize_status_text(box.get("header") or game.get("gameStatusText", ""))
    apply_starting_lineups("NCAA Football", home, away)
    return {
        "game": game,
        "home": home,
        "away": away,
        "header": header,
        "shotclock": box.get("shotclock"),
    }


def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    return backend.load_logo(team_id, tricode)


def get_scoreboard() -> Dict[str, Any]:
    return fetch_scoreboard()


def get_boxscore(game_id: str) -> Dict[str, Any]:
    return fetch_boxscore(game_id)


def get_team_logo(team_id: str | None, tricode: str | None) -> bytes | None:
    return load_logo(team_id, tricode)


def build_player_rows(team: Dict[str, Any]) -> List[List[str]]:
    tri = (team.get("teamTricode") or team.get("teamName") or "TEAM").upper()
    score = safe_score(team)
    record = team.get("record") or team.get("recordShort") or "--"
    return [
        [tri, "Score", str(score)],
        [tri, "Record", record],
    ]
