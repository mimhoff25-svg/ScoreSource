"""
Sport-agnostic orchestrator for ScoreSource.

- Unified API for all sports
- Backends live in scoresource/<sport>.py modules
- Provides caching, logo loading, and start time formatting
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict
import logging

from .common.utils import iso_to_local
from .common.timefmt import format_start_time
from . import nba, nfl, mlb, nhl, ncaa_football, mls
from .sports import mlb as sports_mlb, nba as sports_nba, nfl as sports_nfl, nhl as sports_nhl, mls as sports_mls
from .sports import ncaa_football as sports_ncaa_football

BACKENDS: Dict[str, Any] = {
    "NBA": nba,
    "NFL": nfl,
    "MLB": mlb,
    "NHL": nhl,
    "NCAA FOOTBALL": ncaa_football,
    "MLS": mls,
}

NORMALIZED_FETCHERS: Dict[str, Callable[[], Dict[str, Any]]] = {
    "NBA": sports_nba.fetch_live,
    "NFL": sports_nfl.fetch_live,
    "MLB": sports_mlb.fetch_live,
    "NHL": sports_nhl.fetch_live,
    "NCAA FOOTBALL": sports_ncaa_football.fetch_live,
    "MLS": sports_mls.fetch_live,
}

LOGO_CACHE_ROOT = Path.home() / ".cache" / "scoresource" / "logos"
LOGO_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

_REALTIME_DISABLED_VALUES = {"0", "false", "no", "off"}


def _is_realtime_enabled() -> bool:
    value = os.environ.get("SCORESOURCE_REALTIME_ENABLED", "1")
    return value.strip().lower() not in _REALTIME_DISABLED_VALUES



class TaskManager:
    """
    Simple tracker for background tasks; allows cancel tokens if expanded later.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: set[threading.Thread] = set()

    def run(self, fn: Callable[[], Any]) -> None:
        def _wrapper():
            try:
                fn()
            finally:
                with self._lock:
                    self._tasks.discard(thread)

        thread = threading.Thread(target=_wrapper, daemon=True)
        with self._lock:
            self._tasks.add(thread)
        thread.start()

    def cancel_all(self) -> None:
        # Threads are daemons; they will exit when process exits.
        with self._lock:
            self._tasks.clear()


class ScoreSourceLogic:
    """
    Unified facade used by the UI.
    """

    def __init__(self, sport: str = "NBA", *, default_sport: str | None = None) -> None:
        # accept default_sport for legacy callers
        active = default_sport or sport or "NBA"
        self.task_manager = TaskManager()
        self.current_sport = active.upper()
        self._realtime_client = None

    # compatibility
    def get_scoreboard(self) -> Dict[str, Any]:
        return self.fetch_scores(self.current_sport)

    def get_boxscore(self, game_id: str) -> Dict[str, Any]:
        return self.fetch_boxscore(self.current_sport, game_id)

    def set_sport(self, sport: str) -> None:
        self.current_sport = sport.upper()

    def fetch_scores(self, sport: str | None = None) -> Dict[str, Any]:
        sp = (sport or self.current_sport).upper()
        backend = BACKENDS.get(sp)
        if not backend:
            return _demo_scoreboard(sp)
        try:
            return backend.get_scoreboard()
        except Exception as exc:
            logger.exception("fetch_scores failed for sport=%s backend=%s", sp, getattr(backend, "__name__", repr(backend)))
            return _demo_scoreboard(sp)

    def fetch_boxscore(self, sport: str | None, game_id: str) -> Dict[str, Any]:
        sp = (sport or self.current_sport).upper()
        backend = BACKENDS.get(sp)
        if not backend:
            return _demo_boxscore(sp, game_id)
        try:
            return backend.get_boxscore(game_id)
        except Exception as exc:
            logger.exception("fetch_boxscore failed for sport=%s backend=%s game_id=%s", sp, getattr(backend, "__name__", repr(backend)), game_id)
            return _demo_boxscore(sp, game_id)

    def fetch_scores_for_sport(self, sport: str | None = None) -> Dict[str, Any]:
        sp = (sport or self.current_sport).upper()
        fetcher = NORMALIZED_FETCHERS.get(sp)
        if fetcher:
            try:
                data = fetcher()
            except Exception:
                data = _normalize_scoreboard_for_ui(self.fetch_scores(sp), sp)
        else:
            data = _normalize_scoreboard_for_ui(self.fetch_scores(sp), sp)

        games = data.get("games") or []
        for game in games:
            game.setdefault("startTimeLocal", iso_to_local(game.get("startTime")))
        return {"games": games, "lines": data.get("lines") or []}

    def load_logo(self, sport: str, team_id: str | None, tricode: str | None) -> bytes | None:
        sp = (sport or self.current_sport).upper()
        backend = BACKENDS.get(sp)
        if backend and hasattr(backend, "get_team_logo"):
            try:
                return backend.get_team_logo(team_id, tricode)
            except Exception:
                pass
        return None

    # -------- realtime hooks (stub for non-NBA) --------
    def start_realtime(self, game_id: str, on_update: Callable[[Any], None]) -> None:
        self.stop_realtime()
        if not _is_realtime_enabled():
            return
        try:
            from .realtime import start_client
        except Exception:
            return
        try:
            self._realtime_client = start_client(game_id, on_update, sport=self.current_sport)
        except Exception:
            self._realtime_client = None

    def stop_realtime(self) -> None:
        if self._realtime_client is not None:
            try:
                self._realtime_client.stop()
            except Exception:
                pass
            self._realtime_client = None


# ---------------- demo helpers ----------------
def _demo_scoreboard(sport: str) -> Dict[str, Any]:
    sport = sport.upper()
    now = time.time()
    return {
        "games": [
            {
                "gameId": f"{sport}_DEMO_1",
                "homeTeam": {"teamId": "H1", "teamName": "Home", "teamTricode": "HME", "score": 0},
                "awayTeam": {"teamId": "A1", "teamName": "Away", "teamTricode": "AWY", "score": 0},
                "status": "upcoming",
                "startTime": now + 3600,
                "header": format_start_time(now + 3600),
                "seasonYear": "2025",
            }
        ],
        "lines": ["AWY 0 @ HME 0 (Demo)"],
    }


def _demo_boxscore(sport: str, game_id: str) -> Dict[str, Any]:
    return {
        "game": {"gameClock": None, "shotClock": None, "period": {"current": 0}, "gameStatusText": "Scheduled"},
        "home": {"teamId": "H1", "teamName": "Home", "teamTricode": "HME", "score": 0, "players": []},
        "away": {"teamId": "A1", "teamName": "Away", "teamTricode": "AWY", "score": 0, "players": []},
        "header": "Scheduled",
        "shotclock": "--",
    }


def _normalize_scoreboard_for_ui(raw: Dict[str, Any], sport: str) -> Dict[str, Any]:
    games = []
    for game in (raw or {}).get("games") or []:
        games.append(_normalize_game_for_ui(game, sport))
    return {"games": games, "lines": (raw or {}).get("lines") or []}


def _normalize_game_for_ui(raw_game: Dict[str, Any], sport: str) -> Dict[str, Any]:
    home_team = _as_team_dict(raw_game.get("homeTeam") or raw_game.get("home") or {}, "Home")
    away_team = _as_team_dict(raw_game.get("awayTeam") or raw_game.get("away") or {}, "Away")
    status = _normalize_status(raw_game.get("status") or raw_game.get("gameStatus") or raw_game.get("state"))
    start_time = (
        raw_game.get("startTime")
        or raw_game.get("gameTimeUTC")
        or raw_game.get("gameTime")
        or raw_game.get("date")
        or raw_game.get("start_Date")
        or raw_game.get("startDate")
    )
    header = raw_game.get("header") or raw_game.get("gameStatusText") or status.title()
    if status == "upcoming":
        header = format_start_time(start_time)
    elif status == "final":
        header = "Final"

    return {
        "gameId": str(raw_game.get("gameId") or raw_game.get("id") or ""),
        "sport": sport.upper(),
        "status": status,
        "home": _team_display_name(home_team, "Home"),
        "away": _team_display_name(away_team, "Away"),
        "homeTricode": _team_tricode(home_team),
        "awayTricode": _team_tricode(away_team),
        "homeScore": _safe_score(home_team),
        "awayScore": _safe_score(away_team),
        "startTime": start_time,
        "period": raw_game.get("period"),
        "clock": _extract_clock(raw_game),
        "shotClock": _extract_shotclock(raw_game),
        "gameStatusText": header,
        "header": header,
        "seasonYear": str(raw_game.get("seasonYear") or (raw_game.get("season") or {}).get("year") or "2025"),
        "homeTeam": dict(home_team),
        "awayTeam": dict(away_team),
    }


def _as_team_dict(value: Any, fallback: str) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        return {"teamName": value}
    return {"teamName": fallback}


def _normalize_status(raw: Any) -> str:
    if isinstance(raw, str):
        normalized = raw.lower()
        if normalized in {"pre", "pre-game", "pre game", "preview", "scheduled", "upcoming"}:
            return "upcoming"
        if normalized in {"post", "final"}:
            return "final"
        if normalized in {"live", "inprogress", "in progress", "ongoing"}:
            return "live"
        return normalized
    if isinstance(raw, int):
        if raw == 3:
            return "final"
        if raw in (0, 1):
            return "upcoming"
        return "live"
    return "upcoming"


def _extract_clock(game: Dict[str, Any]) -> str:
    for key in ("clock", "displayClock", "gameClock", "time"):
        val = game.get(key)
        if val:
            return str(val)
    return ""


def _extract_shotclock(game: Dict[str, Any]) -> str:
    for key in ("shotClock", "shotclock", "shot_clock"):
        val = game.get(key)
        if val not in (None, ""):
            return str(val)
    return "--"


def _team_display_name(team: Dict[str, Any], fallback: str) -> str:
    return (
        team.get("teamName")
        or team.get("displayName")
        or team.get("nickname")
        or team.get("teamCity")
        or team.get("city")
        or fallback
    )


def _team_tricode(team: Dict[str, Any]) -> str:
    tri = (
        team.get("teamTricode")
        or team.get("tricode")
        or team.get("abbreviation")
        or team.get("shortDisplayName")
        or ""
    )
    return str(tri).upper()


def _safe_score(team: Dict[str, Any]) -> int:
    for key in ("score", "points", "scoreTotal", "value"):
        val = team.get(key)
        if val not in (None, ""):
            try:
                return int(float(val))
            except Exception:
                continue
    return 0


# convenience global
logic = ScoreSourceLogic()
