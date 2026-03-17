from __future__ import annotations

"""NBA facade for the active ScoreSource application.

This module adapts the normalized ``scoresource.sports.nba`` backend to the
UI/logic contract used across the rest of the app.
"""

import html
import os
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

import requests

from .common.lineups import apply_starting_lineups
from .common.timefmt import format_start_time
from .sports_meta import display_name_for_sport
from .sports import nba as backend

sport_name = display_name_for_sport("NBA")
sport_table_headers = backend.sport_table_headers

TEAM_PRIMARY_COLORS: Dict[str, str] = backend.TEAM_PRIMARY_COLORS
TEAM_SECONDARY_COLORS: Dict[str, str] = backend.TEAM_SECONDARY_COLORS
TEAM_ACCENT_COLORS: Dict[str, str] = backend.TEAM_ACCENT_COLORS
TEAM_ALT_COLORS: Dict[str, str] = backend.TEAM_ALT_COLORS
TEAM_COLORS: Dict[str, str] = TEAM_PRIMARY_COLORS

_RSS_TIMEOUT_SEC = float(os.environ.get("SCORESOURCE_NBA_RSS_TIMEOUT_SEC", "4.0"))
_RSS_TTL_SEC = float(os.environ.get("SCORESOURCE_NBA_RSS_TTL", str(60.0 * 5.0)))
_RSS_URLS = [
    os.environ.get("SCORESOURCE_NBA_RSS", "https://www.espn.com/espn/rss/nba/news"),
    "https://www.nba.com/rss/nba_rss.xml",
]
_RSS_CACHE: tuple[float, list[str]] = (0.0, [])
_RSS_SESSION = requests.Session()
_RSS_SESSION.headers.update({"User-Agent": "ScoreSource/1.0", "Accept": "application/rss+xml, application/xml"})
_PBP_SESSION = requests.Session()
_PBP_SESSION.headers.update({"User-Agent": "ScoreSource/1.0", "Accept": "application/json"})


def _status_from_game(game: Dict[str, Any]) -> str:
    game_status = game.get("gameStatus")
    if isinstance(game_status, str):
        normalized = game_status.strip().lower()
        if normalized in {"final", "post"}:
            return "final"
        if normalized in {"pre", "upcoming", "scheduled"}:
            return "upcoming"
        if normalized in {"live", "in", "in progress", "inprogress", "ongoing"}:
            return "live"
    if game_status == 3:
        return "final"
    if game_status in (1, 0, None):
        return "upcoming"
    return "live"


def _is_halftime(game: Dict[str, Any]) -> bool:
    status_text = (game.get("gameStatusText") or game.get("statusText") or "").lower().replace("-", " ")
    if "halftime" in status_text or "half time" in status_text:
        return True
    period = game.get("period", {})
    current = period.get("current") if isinstance(period, dict) else period
    if current != 2:
        return False
    clock = backend.format_clock(game.get("gameClock"))
    return clock in ("0:00", "00:00")


def _header_from_game(game: Dict[str, Any]) -> str:
    status = _status_from_game(game)
    if status == "upcoming":
        return format_start_time(game.get("gameTimeUTC") or game.get("gameEt") or game.get("startTime"))
    if status == "final":
        return "Final"
    if _is_halftime(game):
        return "HALF TIME"
    period = game.get("period", {})
    current = period.get("current") if isinstance(period, dict) else period
    clock = backend.format_clock(game.get("gameClock"))
    return f"Q{current} {clock}".strip() if current else (game.get("gameStatusText") or clock or "Live")


def _normalized_period(period: Any) -> Dict[str, Any]:
    if isinstance(period, dict):
        return period
    if isinstance(period, int) and period > 0:
        return {"current": period}
    return {}


def _normalize_scoreboard_game(game: Dict[str, Any]) -> Dict[str, Any]:
    status = _status_from_game(game)
    header = _header_from_game(game)
    start_time = game.get("gameTimeUTC") or game.get("gameEt") or game.get("startTime")
    status_text = game.get("gameStatusText") or game.get("statusText") or header
    return {
        "gameId": game.get("gameId"),
        "homeTeam": game.get("homeTeam", {}),
        "awayTeam": game.get("awayTeam", {}),
        "status": status,
        "gameStatus": game.get("gameStatus"),
        "startTime": start_time,
        "gameTimeUTC": start_time,
        "header": header,
        "gameStatusText": status_text,
        "statusText": status_text,
        "gameClock": game.get("gameClock"),
        "period": _normalized_period(game.get("period")),
        "shotClock": game.get("shotClock"),
        "seasonYear": game.get("seasonYear") or "2025",
    }


def get_scoreboard() -> Dict[str, Any]:
    try:
        raw = backend.fetch_scores()
    except Exception:
        raw = backend.demo_scoreboard()
    games_raw = raw.get("games", []) or []
    games = [_normalize_scoreboard_game(game) for game in games_raw if isinstance(game, dict)]
    lines = raw.get("lines") or [
        f"{(game.get('awayTeam') or {}).get('teamName', 'Away')} @ {(game.get('homeTeam') or {}).get('teamName', 'Home')}"
        for game in games
    ]
    if not games:
        games = [
            {
                "gameId": "NBA_DEMO",
                "homeTeam": {"teamId": "0", "teamName": "Home", "teamTricode": "HME", "score": 0},
                "awayTeam": {"teamId": "0", "teamName": "Away", "teamTricode": "AWY", "score": 0},
                "status": "upcoming",
                "gameStatus": 1,
                "startTime": None,
                "gameTimeUTC": None,
                "header": "Demo",
                "gameStatusText": "Demo",
                "statusText": "Demo",
                "gameClock": None,
                "period": {},
                "shotClock": None,
                "seasonYear": "2025",
            }
        ]
        lines = ["AWY 0 @ HME 0 (Demo)"]
    return {"games": games, "lines": lines}


def get_boxscore(game_id: str) -> Dict[str, Any]:
    try:
        raw = backend.fetch_boxscore(game_id)
    except Exception:
        raw = backend.demo_boxscore()
    game = raw.get("game") or {}
    header = raw.get("header") or _header_from_game(game)
    shotclock = raw.get("shotclock") or backend.format_shotclock(game.get("shotClock"))
    home = raw.get("home") or {}
    away = raw.get("away") or {}
    for team in (home, away):
        try:
            backend._apply_player_positions(team)
        except Exception:
            continue
    apply_starting_lineups("NBA", home, away)
    return {
        "game": game,
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
        return backend.load_logo(team_id, tricode)
    except Exception:
        return None


def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    return get_team_logo(team_id, tricode)


def safe_score(team: Dict[str, Any]) -> int:
    try:
        return backend.safe_score(team)
    except Exception:
        try:
            return int(team.get("score") or 0)
        except Exception:
            return 0


def format_time_played(value: Any) -> str:
    try:
        return backend.format_time_played(value)
    except Exception:
        return str(value or "")


def format_shotclock(value: Any) -> str:
    try:
        return backend.format_shotclock(value)
    except Exception:
        return "--"


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


def get_rss_headlines(limit: int = 10) -> list[str]:
    now = time.monotonic()
    cached_ts, cached = _RSS_CACHE
    if cached and now - cached_ts <= _RSS_TTL_SEC:
        return cached[:limit]

    titles: list[str] = []
    for url in _RSS_URLS:
        if not url:
            continue
        try:
            response = _RSS_SESSION.get(url, timeout=_RSS_TIMEOUT_SEC)
            response.raise_for_status()
            titles = _parse_rss_titles(response.text)
        except Exception:
            titles = []
        if titles:
            globals()["_RSS_CACHE"] = (now, titles)
            return titles[:limit]

    if cached:
        return cached[:limit]
    return []


def fetch_play_by_play(game_id: str, limit: int = 16) -> List[Dict[str, Any]]:
    try:
        response = _PBP_SESSION.get(
            f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json",
            timeout=5.0,
        )
        response.raise_for_status()
        actions = (response.json().get("game", {}) or {}).get("actions") or []
    except Exception:
        actions = []

    cleaned: List[Dict[str, Any]] = []
    for action in actions:
        desc = str(action.get("description") or "").strip()
        if not desc:
            continue
        cleaned.append(
            {
                "id": action.get("actionNumber") or action.get("orderNumber"),
                "period": action.get("period"),
                "clock": backend.format_clock(action.get("clock")),
                "description": desc,
                "teamTricode": (action.get("teamTricode") or "").upper(),
                "scoreHome": action.get("scoreHome"),
                "scoreAway": action.get("scoreAway"),
            }
        )
    return cleaned[-max(1, int(limit)) :]


def build_player_rows(team: Dict[str, Any]) -> List[List[str]]:
    return backend.build_player_rows(team)


fetch_scoreboard = get_scoreboard
fetch_boxscore = get_boxscore
fetch_rss_headlines = get_rss_headlines
