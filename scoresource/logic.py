"""
Sport-agnostic orchestrator for ScoreSource.

- Unified API for all sports
- Backends live in scoresource/<sport>.py modules
- Provides caching, logo loading, and start time formatting
"""

from __future__ import annotations

import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict
import logging
from urllib.parse import quote_plus

import requests

from .common.lineups import ESPN_SPORT_PATH
from .common.paths import cache_dir
from .common.utils import iso_to_local
from .common.timefmt import format_start_time
from .sports_meta import canonicalize_sport_name
from . import nba, nfl, mlb, nhl, ncaa_football, ncaa_basketball, mls
from .sports import (
    mlb as sports_mlb,
    nba as sports_nba,
    nfl as sports_nfl,
    nhl as sports_nhl,
    mls as sports_mls,
    ncaa_basketball as sports_ncaa_basketball,
)
from .sports import ncaa_football as sports_ncaa_football

BACKENDS: Dict[str, Any] = {
    "NBA": nba,
    "NCAA BASKETBALL": ncaa_basketball,
    "NFL": nfl,
    "MLB": mlb,
    "NHL": nhl,
    "NCAA FOOTBALL": ncaa_football,
    "MLS": mls,
}

NORMALIZED_FETCHERS: Dict[str, Callable[[], Dict[str, Any]]] = {
    "NBA": sports_nba.fetch_live,
    "NCAA BASKETBALL": sports_ncaa_basketball.fetch_live,
    "NFL": sports_nfl.fetch_live,
    "MLB": sports_mlb.fetch_live,
    "NHL": sports_nhl.fetch_live,
    "NCAA FOOTBALL": sports_ncaa_football.fetch_live,
    "MLS": sports_mls.fetch_live,
}

LOGO_CACHE_ROOT = cache_dir() / "logos"
LOGO_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

_REALTIME_DISABLED_VALUES = {"0", "false", "no", "off"}
PLAYER_PROFILE_TTL_SEC = 60 * 30
PLAYER_PROFILE_TIMEOUT_SEC = 7.0
PLAYER_PROFILE_HEADERS = {"User-Agent": "ScoreSource/1.0", "Referer": "https://www.espn.com"}
NBA_ESPN_TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
ESPN_TEAM_ID_MAP_TTL_SEC = 60 * 60 * 12
REMOTE_BINARY_TTL_SEC = 60 * 60 * 24
REMOTE_BINARY_TIMEOUT_SEC = 6.0
REMOTE_BINARY_MAX_BYTES = 3_000_000
MLB_STATS_TIMEOUT_SEC = 6.0
MLB_STATS_TEAM_TTL_SEC = 60 * 60 * 24
MLB_HEADSHOT_LOOKUP_TTL_SEC = 60 * 60 * 24
CORE_ATHLETE_PATHS: Dict[str, tuple[str, str]] = {
    "NBA": ("basketball", "nba"),
    "NCAA BASKETBALL": ("basketball", "mens-college-basketball"),
    "NFL": ("football", "nfl"),
    "NHL": ("hockey", "nhl"),
    "MLB": ("baseball", "mlb"),
    "NCAA FOOTBALL": ("football", "college-football"),
    "MLS": ("soccer", "usa.1"),
}
ESPN_HEADSHOT_SPORT_PATHS: Dict[str, tuple[str, ...]] = {
    "NBA": ("nba",),
    "NCAA BASKETBALL": ("mens-college-basketball", "ncb"),
    "NFL": ("nfl",),
    "NHL": ("nhl",),
    "MLB": ("mlb",),
    "NCAA FOOTBALL": ("ncf", "college-football"),
    "MLS": ("soccer", "mls"),
}
SPORT_TEAM_TRICODE_ALIASES: Dict[str, Dict[str, str]] = {
    "NBA": {
        "GS": "GSW",
        "GSW": "GS",
        "NO": "NOP",
        "NOP": "NO",
        "NY": "NYK",
        "NYK": "NY",
        "SA": "SAS",
        "SAS": "SA",
        "WAS": "WSH",
        "WSH": "WAS",
        "UTA": "UTAH",
        "UTAH": "UTA",
    },
    "NHL": {
        "LA": "LAK",
        "LAK": "LA",
        "NJ": "NJD",
        "NJD": "NJ",
        "SJ": "SJS",
        "SJS": "SJ",
        "TB": "TBL",
        "TBL": "TB",
        "UTA": "UTAH",
        "UTAH": "UTA",
    },
}
ESPN_TO_NBA_TRICODE_ALIASES: Dict[str, str] = {
    "GS": "GSW",
    "NO": "NOP",
    "NY": "NYK",
    "SA": "SAS",
    "WSH": "WAS",
    "UTAH": "UTA",
}
NBA_TO_ESPN_TRICODE_ALIASES: Dict[str, str] = {nba: espn for espn, nba in ESPN_TO_NBA_TRICODE_ALIASES.items()}
CAREER_STATS_MAX_FIELDS = 12
CAREER_STAT_ALIASES: Dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "NBA": [
        ("GP", ("gp", "gamesplayed", "games")),
        ("PTS", ("pts", "points", "avgpoints", "ppg")),
        ("REB", ("reb", "rebounds", "totalrebounds", "avgrebounds", "rpg")),
        ("AST", ("ast", "assists", "avgassists", "apg")),
        ("STL", ("stl", "steals", "avgsteals", "spg")),
        ("BLK", ("blk", "blocks", "avgblocks", "bpg")),
        ("FG%", ("fg", "fgpct", "fieldgoalpct")),
        ("3P%", ("3p", "3ppct", "threepointpct", "threepointfieldgoalpct")),
        ("FT%", ("ft", "ftpct", "freethrowpct")),
    ],
    "NCAA BASKETBALL": [
        ("GP", ("gp", "gamesplayed", "games")),
        ("PTS", ("pts", "points", "avgpoints", "ppg")),
        ("REB", ("reb", "rebounds", "totalrebounds", "avgrebounds", "rpg")),
        ("AST", ("ast", "assists", "avgassists", "apg")),
        ("STL", ("stl", "steals", "avgsteals", "spg")),
        ("BLK", ("blk", "blocks", "avgblocks", "bpg")),
        ("FG%", ("fg", "fgpct", "fieldgoalpct")),
        ("3P%", ("3p", "3ppct", "threepointpct", "threepointfieldgoalpct")),
        ("FT%", ("ft", "ftpct", "freethrowpct")),
    ],
    "NFL": [
        ("GP", ("gp", "gamesplayed", "games")),
        ("PASS YDS", ("passingyards", "netpassingyards", "nyds", "passyds")),
        ("PASS TD", ("passingtouchdowns", "passtd", "passingtd", "ptd")),
        ("INT", ("interceptions",)),
        ("RUSH YDS", ("rushingyards", "rushyds")),
        ("RUSH TD", ("rushingtouchdowns", "rushtd")),
        ("REC", ("receptions", "rec")),
        ("REC YDS", ("receivingyards", "recyards", "recyds")),
        ("REC TD", ("receivingtouchdowns", "rectd")),
        ("TKL", ("totaltackles", "tackles", "tacklestotal", "comb", "tkl")),
        ("SACK", ("sacks", "sack")),
    ],
    "NCAA FOOTBALL": [
        ("GP", ("gp", "gamesplayed", "games")),
        ("PASS YDS", ("passingyards", "netpassingyards", "nyds", "passyds")),
        ("PASS TD", ("passingtouchdowns", "passtd", "passingtd", "ptd")),
        ("INT", ("interceptions",)),
        ("RUSH YDS", ("rushingyards", "rushyds")),
        ("RUSH TD", ("rushingtouchdowns", "rushtd")),
        ("REC", ("receptions", "rec")),
        ("REC YDS", ("receivingyards", "recyards", "recyds")),
        ("REC TD", ("receivingtouchdowns", "rectd")),
        ("TKL", ("totaltackles", "tackles", "tacklestotal", "comb", "tkl")),
        ("SACK", ("sacks", "sack")),
    ],
    "MLB": [
        ("GP", ("gp", "gamesplayed", "games")),
        ("AVG", ("avg", "battingaverage", "battingavg")),
        ("HR", ("hr", "homeruns")),
        ("RBI", ("rbi", "rbis")),
        ("H", ("hits", "h")),
        ("OBP", ("obp", "onbasepct")),
        ("SLG", ("slg", "slugavg")),
        ("OPS", ("ops",)),
        ("SB", ("sb", "stolenbases")),
        ("SO", ("so", "strikeouts")),
        ("ERA", ("era",)),
        ("W", ("wins", "w")),
        ("L", ("losses", "l")),
        ("SV", ("saves", "sv")),
    ],
    "NHL": [
        ("GP", ("gp", "gamesplayed", "games")),
        ("G", ("g", "goals")),
        ("A", ("a", "assists")),
        ("PTS", ("pts", "points")),
        ("+/-", ("plusminus",)),
        ("PIM", ("pim", "penaltyminutes")),
        ("SOG", ("sog", "shotsongoal", "shots")),
        ("SV%", ("svpct", "savepct")),
        ("GAA", ("gaa", "avggoalsagainst")),
        ("W", ("wins", "w")),
        ("L", ("losses", "l")),
        ("SO", ("shutouts", "so")),
        ("TOI/G", ("toig", "timeonicepergame")),
    ],
    "MLS": [
        ("APP", ("app", "apps", "appearances")),
        ("G", ("g", "goals")),
        ("A", ("a", "assists")),
        ("SOG", ("sog", "shotsongoal")),
        ("MIN", ("minutes", "mins", "timeplayed")),
        ("YC", ("yc", "yellowcards")),
        ("RC", ("rc", "redcards")),
        ("CS", ("cs", "cleansheets", "cleensheet")),
        ("SV", ("sv", "saves")),
        ("GA", ("ga", "goalsagainst")),
    ],
}


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
        self.current_sport = canonicalize_sport_name(active)
        self._realtime_client = None
        self._http_session = requests.Session()
        self._player_profile_lock = threading.Lock()
        self._player_profile_cache: Dict[tuple[str, str, str, str, str, str], tuple[float, Dict[str, Any]]] = {}
        self._team_map_lock = threading.Lock()
        self._team_id_map_cache: Dict[str, tuple[float, Dict[str, str]]] = {}
        self._mlb_stats_lock = threading.Lock()
        self._mlb_team_map_cache: tuple[float, Dict[str, str]] = (0.0, {})
        self._mlb_headshot_cache: Dict[tuple[str, str], tuple[float, str]] = {}
        self._remote_binary_lock = threading.Lock()
        self._remote_binary_cache: Dict[str, tuple[float, bytes]] = {}

    # compatibility
    def get_scoreboard(self) -> Dict[str, Any]:
        return self.fetch_scores(self.current_sport)

    def get_boxscore(self, game_id: str) -> Dict[str, Any]:
        return self.fetch_boxscore(self.current_sport, game_id)

    def set_sport(self, sport: str) -> None:
        self.current_sport = canonicalize_sport_name(sport)

    def fetch_scores(self, sport: str | None = None) -> Dict[str, Any]:
        sp = canonicalize_sport_name(sport or self.current_sport)
        backend = BACKENDS.get(sp)
        if not backend:
            return _demo_scoreboard(sp)
        try:
            if hasattr(backend, "get_scoreboard"):
                return backend.get_scoreboard()
            if hasattr(backend, "fetch_scoreboard"):
                return backend.fetch_scoreboard()
            return _demo_scoreboard(sp)
        except Exception as exc:
            logger.exception("fetch_scores failed for sport=%s backend=%s", sp, getattr(backend, "__name__", repr(backend)))
            return _demo_scoreboard(sp)

    def fetch_boxscore(self, sport: str | None, game_id: str) -> Dict[str, Any]:
        sp = canonicalize_sport_name(sport or self.current_sport)
        backend = BACKENDS.get(sp)
        if not backend:
            return _demo_boxscore(sp, game_id)
        try:
            if hasattr(backend, "get_boxscore"):
                return backend.get_boxscore(game_id)
            if hasattr(backend, "fetch_boxscore"):
                return backend.fetch_boxscore(game_id)
            return _demo_boxscore(sp, game_id)
        except Exception as exc:
            logger.exception("fetch_boxscore failed for sport=%s backend=%s game_id=%s", sp, getattr(backend, "__name__", repr(backend)), game_id)
            return _demo_boxscore(sp, game_id)

    def fetch_scores_for_sport(self, sport: str | None = None) -> Dict[str, Any]:
        sp = canonicalize_sport_name(sport or self.current_sport)
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

    def load_logo(self, sport: str, team_id: str | None, tricode: str | None, is_super_bowl: bool = False) -> bytes | None:
        sp = canonicalize_sport_name(sport or self.current_sport)
        backend = BACKENDS.get(sp)
        if backend and hasattr(backend, "get_team_logo"):
            try:
                return backend.get_team_logo(team_id, tricode, is_super_bowl=is_super_bowl)
            except Exception:
                pass
        return None

    def fetch_player_profile(
        self,
        sport: str | None,
        team_id: str | None,
        *,
        player_id: str | None = None,
        player_name: str | None = None,
        player_jersey: str | None = None,
        team_tricode: str | None = None,
    ) -> Dict[str, Any]:
        sp = canonicalize_sport_name(sport or self.current_sport)
        path = ESPN_SPORT_PATH.get(sp)
        team_key = str(team_id or "").strip()
        player_key = str(player_id or "").strip()
        name_key = str(player_name or "").strip()
        jersey_key = str(player_jersey or "").strip()
        tricode_key = str(team_tricode or "").strip().upper()
        resolved_team_key = self._resolve_profile_team_id(sp, team_key, tricode_key)
        cache_key = (sp, resolved_team_key, tricode_key, player_key, name_key.lower(), jersey_key)
        now = time.monotonic()
        with self._player_profile_lock:
            cached = self._player_profile_cache.get(cache_key)
            if cached and now - cached[0] < PLAYER_PROFILE_TTL_SEC:
                cached_profile = dict(cached[1])
                # MLB profiles can temporarily cache a team-logo placeholder when
                # ESPN headshots are missing. Re-fetch so an MLB person headshot can replace it.
                if sp == "MLB" and _is_team_logo_url(cached_profile.get("headshotUrl")):
                    pass
                else:
                    return cached_profile

        profile: Dict[str, Any] = {}
        if path and resolved_team_key:
            url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams/{resolved_team_key}/roster"
            payload = self._fetch_json(url)
            athletes = _extract_roster_athletes(payload)
            athlete = _match_roster_athlete(athletes, player_key, name_key, jersey_key)
            profile = _profile_from_athlete(athlete)
        if not profile and player_key:
            core_path = CORE_ATHLETE_PATHS.get(sp)
            if core_path:
                sport_path, league_path = core_path
                core_url = (
                    "https://sports.core.api.espn.com/v2/sports/"
                    f"{sport_path}/leagues/{league_path}/athletes/{player_key}?lang=en&region=us"
                )
                core_payload = self._fetch_json(core_url)
                profile = _profile_from_athlete(core_payload)
        common_payload: Dict[str, Any] | None = None
        athlete_payload: Dict[str, Any] = {}
        if player_key and path and (not profile or not str(profile.get("headshotUrl") or "").strip()):
            common_url = f"https://site.api.espn.com/apis/common/v3/sports/{path}/athletes/{player_key}"
            common_payload = self._fetch_json(common_url)
            if isinstance(common_payload, dict):
                athlete = common_payload.get("athlete")
                if isinstance(athlete, dict):
                    athlete_payload = athlete
            common_profile = _profile_from_athlete(athlete_payload)
            if common_profile:
                if profile:
                    for key, value in common_profile.items():
                        if str(profile.get(key) or "").strip():
                            continue
                        profile[key] = value
                else:
                    profile = dict(common_profile)
        if not str(profile.get("headshotUrl") or "").strip() and sp == "MLB":
            lookup_name = (
                str(profile.get("displayName") or profile.get("fullName") or name_key).strip()
            )
            mlb_headshot = self._mlb_headshot_url(lookup_name, tricode_key)
            if mlb_headshot:
                profile["headshotUrl"] = mlb_headshot
        if not str(profile.get("headshotUrl") or "").strip():
            fallback_headshot = self._espn_headshot_url(
                sp,
                athlete_payload or profile,
                source_player_id=player_key,
            )
            if fallback_headshot:
                profile["headshotUrl"] = fallback_headshot

        career_id = str(profile.get("id") or player_key).strip()
        if career_id:
            career_stats = self._fetch_career_stats(
                sp,
                career_id,
                path=path,
                source_player_id=player_key,
                common_payload=common_payload,
            )
            if career_stats:
                profile["careerStats"] = career_stats

        with self._player_profile_lock:
            self._player_profile_cache[cache_key] = (now, profile)
        return dict(profile)

    def _resolve_profile_team_id(self, sport: str, team_id: str, team_tricode: str) -> str:
        if _looks_like_espn_team_id(team_id):
            return team_id
        mapped_id = self._espn_team_id_for_tricode(sport, team_tricode)
        if mapped_id:
            return mapped_id
        return team_id

    def _nba_team_id_for_tricode(self, tricode: str) -> str:
        return self._espn_team_id_for_tricode("NBA", tricode)

    def _espn_team_id_for_tricode(self, sport: str, tricode: str) -> str:
        sp = canonicalize_sport_name(sport)
        tri = str(tricode or "").strip().upper()
        if not tri:
            return ""
        path = ESPN_SPORT_PATH.get(sp)
        if not path:
            return ""
        now = time.monotonic()
        with self._team_map_lock:
            cached = self._team_id_map_cache.get(sp)
            if cached and now - cached[0] < ESPN_TEAM_ID_MAP_TTL_SEC:
                return self._team_id_from_map(sp, tri, cached[1])

        payload = self._fetch_json(NBA_ESPN_TEAMS_URL if sp == "NBA" else f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams")
        mapped: Dict[str, str] = {}
        if isinstance(payload, dict):
            for sport_entry in payload.get("sports") or []:
                if not isinstance(sport_entry, dict):
                    continue
                for league_entry in sport_entry.get("leagues") or []:
                    if not isinstance(league_entry, dict):
                        continue
                    for team_entry in league_entry.get("teams") or []:
                        if not isinstance(team_entry, dict):
                            continue
                        team_data = team_entry.get("team") if isinstance(team_entry.get("team"), dict) else team_entry
                        if not isinstance(team_data, dict):
                            continue
                        key = str(team_data.get("abbreviation") or "").strip().upper()
                        value = str(team_data.get("id") or "").strip()
                        if key and value:
                            mapped[key] = value
                            alias_key = _team_tricode_alias(sp, key) or key
                            mapped[alias_key] = value
            if not mapped:
                for team_entry in payload.get("teams") or []:
                    if not isinstance(team_entry, dict):
                        continue
                    team_data = team_entry.get("team") if isinstance(team_entry.get("team"), dict) else team_entry
                    if not isinstance(team_data, dict):
                        continue
                    key = str(team_data.get("abbreviation") or "").strip().upper()
                    value = str(team_data.get("id") or "").strip()
                    if key and value:
                        mapped[key] = value
                        alias_key = _team_tricode_alias(sp, key) or key
                        mapped[alias_key] = value

        with self._team_map_lock:
            if mapped:
                self._team_id_map_cache[sp] = (now, mapped)
                return self._team_id_from_map(sp, tri, mapped)
            cached = self._team_id_map_cache.get(sp)
            if cached and now - cached[0] < (ESPN_TEAM_ID_MAP_TTL_SEC * 2):
                return self._team_id_from_map(sp, tri, cached[1])
        return ""

    def _team_id_from_map(self, sport: str, tricode: str, mapped: Dict[str, str]) -> str:
        candidates = [str(tricode or "").strip().upper()]
        alias_key = _team_tricode_alias(sport, candidates[0])
        if alias_key:
            candidates.append(alias_key)
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            mapped_id = str(mapped.get(candidate) or "")
            if mapped_id:
                return mapped_id
        return ""

    def _fetch_json(self, url: str) -> Dict[str, Any] | None:
        try:
            resp = self._http_session.get(url, headers=PLAYER_PROFILE_HEADERS, timeout=PLAYER_PROFILE_TIMEOUT_SEC)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _fetch_career_stats(
        self,
        sport: str,
        player_id: str,
        *,
        path: str | None = None,
        source_player_id: str | None = None,
        common_payload: Dict[str, Any] | None = None,
    ) -> Dict[str, str]:
        sp = canonicalize_sport_name(sport)
        pid = str(player_id or "").strip()
        if not pid:
            return {}

        core_path = CORE_ATHLETE_PATHS.get(sp)
        if core_path:
            sport_path, league_path = core_path
            core_url = (
                "https://sports.core.api.espn.com/v2/sports/"
                f"{sport_path}/leagues/{league_path}/athletes/{pid}/statistics?lang=en&region=us"
            )
            core_payload = self._fetch_json(core_url)
            stats = _career_stats_from_statistics_payload(sp, core_payload)
            if stats:
                return stats

        fallback_payload = common_payload
        source_id = str(source_player_id or player_id or "").strip()
        if not fallback_payload and path and source_id:
            common_url = f"https://site.api.espn.com/apis/common/v3/sports/{path}/athletes/{source_id}"
            fallback_payload = self._fetch_json(common_url)
        return _career_stats_from_common_payload(sp, fallback_payload)

    def _mlb_headshot_url(self, player_name: str, team_tricode: str) -> str:
        name = str(player_name or "").strip()
        tri = str(team_tricode or "").strip().upper()
        if not name:
            return ""
        cache_key = (_normalize_name(name), tri)
        if not cache_key[0]:
            return ""

        now = time.monotonic()
        with self._mlb_stats_lock:
            cached = self._mlb_headshot_cache.get(cache_key)
            if cached and now - cached[0] < MLB_HEADSHOT_LOOKUP_TTL_SEC:
                return str(cached[1] or "")

        team_id = self._mlb_team_id_for_tricode(tri)
        search_url = f"https://statsapi.mlb.com/api/v1/people/search?sportId=1&names={quote_plus(name)}"
        if team_id:
            search_url += f"&teamId={team_id}"
        payload = self._fetch_json(search_url) or {}
        people = payload.get("people") if isinstance(payload.get("people"), list) else []
        if not people:
            with self._mlb_stats_lock:
                self._mlb_headshot_cache[cache_key] = (now, "")
            return ""

        target = _normalize_name(name)
        person_id = ""
        for person in people:
            if not isinstance(person, dict):
                continue
            pid = str(person.get("id") or "").strip()
            if not pid:
                continue
            full_name = str(person.get("fullName") or "").strip()
            if target and _normalize_name(full_name) == target:
                person_id = pid
                break
            if not person_id:
                person_id = pid

        url = ""
        if person_id:
            candidates = [
                f"https://img.mlbstatic.com/mlb-photos/image/upload/w_213,q_auto:best/v1/people/{person_id}/headshot/67/current",
                f"https://img.mlbstatic.com/mlb-photos/image/upload/w_213,q_auto:best/v1/people/{person_id}/headshot/silo/current",
            ]
            for candidate in candidates:
                if self.fetch_remote_bytes(candidate):
                    url = candidate
                    break

        with self._mlb_stats_lock:
            self._mlb_headshot_cache[cache_key] = (now, url)
        return url

    def _mlb_team_id_for_tricode(self, tricode: str) -> str:
        tri = str(tricode or "").strip().upper()
        if not tri:
            return ""
        now = time.monotonic()
        with self._mlb_stats_lock:
            cached_ts, cached_map = self._mlb_team_map_cache
            if cached_map and now - cached_ts < MLB_STATS_TEAM_TTL_SEC:
                return str(cached_map.get(tri) or "")

        payload = self._fetch_json("https://statsapi.mlb.com/api/v1/teams?sportId=1") or {}
        mapped: Dict[str, str] = {}
        teams = payload.get("teams") if isinstance(payload.get("teams"), list) else []
        for team in teams:
            if not isinstance(team, dict):
                continue
            tid = str(team.get("id") or "").strip()
            if not tid:
                continue
            for key in (
                str(team.get("abbreviation") or "").strip().upper(),
                str(team.get("teamCode") or "").strip().upper(),
                str(team.get("fileCode") or "").strip().upper(),
            ):
                if key:
                    mapped[key] = tid

        with self._mlb_stats_lock:
            if mapped:
                self._mlb_team_map_cache = (now, mapped)
        return str(mapped.get(tri) or "")

    def _espn_headshot_url(
        self,
        sport: str,
        athlete: Dict[str, Any] | None,
        *,
        source_player_id: str | None = None,
    ) -> str:
        sport_key = canonicalize_sport_name(sport)
        if sport_key == "MLB":
            return ""

        athlete_id = ""
        if isinstance(athlete, dict):
            athlete_id = _normalize_id(athlete.get("id") or athlete.get("alternateId"))
        athlete_id = athlete_id or _normalize_id(source_player_id)
        if not athlete_id:
            return ""

        sport_paths = ESPN_HEADSHOT_SPORT_PATHS.get(sport_key, ())
        for segment in sport_paths:
            candidate = f"https://a.espncdn.com/i/headshots/{segment}/players/full/{athlete_id}.png"
            if self.fetch_remote_bytes(candidate):
                return candidate
        return ""

    def fetch_remote_bytes(self, url: str | None) -> bytes | None:
        key = str(url or "").strip()
        if not key:
            return None
        now = time.monotonic()
        with self._remote_binary_lock:
            cached = self._remote_binary_cache.get(key)
            if cached and now - cached[0] < REMOTE_BINARY_TTL_SEC:
                return cached[1]
        try:
            resp = self._http_session.get(key, headers=PLAYER_PROFILE_HEADERS, timeout=REMOTE_BINARY_TIMEOUT_SEC)
            resp.raise_for_status()
            data = resp.content or b""
        except Exception:
            return None
        if not data or len(data) > REMOTE_BINARY_MAX_BYTES:
            return None
        payload = bytes(data)
        with self._remote_binary_lock:
            self._remote_binary_cache[key] = (now, payload)
        return payload

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


def _extract_roster_athletes(payload: Dict[str, Any] | None) -> list[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    athletes = payload.get("athletes") or []
    if not isinstance(athletes, list):
        return []
    items: list[Dict[str, Any]] = []
    for entry in athletes:
        if not isinstance(entry, dict):
            continue
        grouped = entry.get("items")
        if isinstance(grouped, list):
            for athlete in grouped:
                if not isinstance(athlete, dict):
                    continue
                merged = dict(athlete)
                # NHL/NFL grouped rosters carry the position label at the group level.
                if not merged.get("position") and entry.get("position"):
                    group_pos = entry.get("position")
                    if isinstance(group_pos, dict):
                        merged["position"] = group_pos
                    elif isinstance(group_pos, str):
                        merged["position"] = {"abbreviation": group_pos}
                items.append(merged)
            continue
        items.append(entry)
    return items


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_name(value: Any) -> str:
    text = _normalize_text(value).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text)


def _is_team_logo_url(value: Any) -> bool:
    url = _normalize_text(value).lower()
    if not url:
        return False
    return "teamlogos" in url or "/i/team/" in url


def _normalize_stat_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _stat_display_value(stat: Dict[str, Any]) -> str:
    raw = stat.get("displayValue")
    if raw in (None, ""):
        raw = stat.get("formattedValue")
    if raw in (None, ""):
        raw = stat.get("value")
    text = _normalize_text(raw)
    if not text:
        return ""
    if text in {"--", "N/A", "None"}:
        return ""
    return text


def _career_stat_entries(stats: list[Dict[str, Any]]) -> list[tuple[set[str], str, Dict[str, Any]]]:
    entries: list[tuple[set[str], str, Dict[str, Any]]] = []
    for stat in stats:
        if not isinstance(stat, dict):
            continue
        value = _stat_display_value(stat)
        if not value:
            continue
        tokens: set[str] = set()
        for key in ("name", "abbreviation", "shortDisplayName", "displayName"):
            token = _normalize_stat_token(stat.get(key))
            if token:
                tokens.add(token)
        if str(stat.get("abbreviation") or "").strip() == "+/-":
            tokens.add("plusminus")
        if not tokens:
            continue
        entries.append((tokens, value, stat))
    return entries


def _select_career_stats(sport: str, stats: list[Dict[str, Any]]) -> Dict[str, str]:
    entries = _career_stat_entries(stats)
    if not entries:
        return {}
    selected: Dict[str, str] = {}
    used: set[int] = set()
    alias_rows = CAREER_STAT_ALIASES.get(canonicalize_sport_name(sport), [])

    def _match_score(label: str, alias: str, stat: Dict[str, Any], tokens: set[str]) -> int:
        if not alias:
            return 0
        name_token = _normalize_stat_token(stat.get("name"))
        short_token = _normalize_stat_token(stat.get("shortDisplayName"))
        display_token = _normalize_stat_token(stat.get("displayName"))
        abbr_raw = str(stat.get("abbreviation") or "").strip()
        abbr_token = _normalize_stat_token(abbr_raw)
        score = 0
        if alias == name_token:
            score = 45
        elif alias == short_token:
            score = 35
        elif alias == display_token:
            score = 30
        elif alias == abbr_token:
            score = 24
        elif alias in tokens:
            score = 14
        if score <= 0:
            return 0
        if name_token.startswith("team") and label not in {"GP"}:
            score -= 18
        is_pct = "%" in abbr_raw or name_token.endswith("pct")
        if is_pct and "pct" not in alias and "%" not in label:
            score -= 10
        if name_token.startswith("avg") and label in {"G", "A", "PTS", "HR", "RBI", "H", "SB", "SO", "W", "L", "SV"}:
            score -= 8
        return score

    for label, aliases in alias_rows:
        alias_tokens = [_normalize_stat_token(alias) for alias in aliases]
        best_idx = -1
        best_score = 0
        for idx, (tokens, _value, stat) in enumerate(entries):
            if idx in used:
                continue
            score = max((_match_score(label, alias, stat, tokens) for alias in alias_tokens), default=0)
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx >= 0 and best_score > 0:
            selected[label] = entries[best_idx][1]
            used.add(best_idx)
        if len(selected) >= CAREER_STATS_MAX_FIELDS:
            break

    if len(selected) < min(4, CAREER_STATS_MAX_FIELDS):
        for idx, (_tokens, value, stat) in enumerate(entries):
            if idx in used:
                continue
            label = _normalize_text(
                stat.get("abbreviation")
                or stat.get("shortDisplayName")
                or stat.get("displayName")
                or stat.get("name")
            ).upper()
            if not label:
                continue
            if label in selected:
                continue
            selected[label] = value
            used.add(idx)
            if len(selected) >= CAREER_STATS_MAX_FIELDS:
                break
    return selected


def _career_stats_from_statistics_payload(sport: str, payload: Dict[str, Any] | None) -> Dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    splits = payload.get("splits")
    if not isinstance(splits, dict):
        return {}
    stats: list[Dict[str, Any]] = []
    categories = splits.get("categories")
    if isinstance(categories, list):
        for category in categories:
            if not isinstance(category, dict):
                continue
            values = category.get("stats")
            if not isinstance(values, list):
                continue
            for stat in values:
                if isinstance(stat, dict):
                    stats.append(stat)
    values = splits.get("stats")
    if isinstance(values, list):
        for stat in values:
            if isinstance(stat, dict):
                stats.append(stat)
    return _select_career_stats(sport, stats)


def _career_stats_from_common_payload(sport: str, payload: Dict[str, Any] | None) -> Dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    athlete = payload.get("athlete")
    if not isinstance(athlete, dict):
        return {}
    summary = athlete.get("statsSummary")
    if not isinstance(summary, dict):
        return {}
    stats = summary.get("statistics")
    if not isinstance(stats, list):
        return {}
    normalized_stats = [item for item in stats if isinstance(item, dict)]
    return _select_career_stats(sport, normalized_stats)


def _name_parts(value: Any) -> tuple[str, str]:
    text = _normalize_text(value).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    parts = [part for part in re.split(r"[^a-z0-9]+", text) if part]
    if not parts:
        return "", ""
    return parts[0], parts[-1]


def _normalize_id(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    digits = re.sub(r"\D+", "", text)
    return digits or text.lower()


def _looks_like_espn_team_id(value: Any) -> bool:
    token = _normalize_text(value)
    if not token:
        return False
    if not token.isdigit():
        return False
    team_id = int(token)
    if team_id <= 0:
        return False
    # ESPN team IDs stay compact; giant league-specific ids like 1610612744 are not ESPN roster ids.
    return team_id < 10_000_000


def _team_tricode_alias(sport: str, tricode: str) -> str:
    tri = _normalize_text(tricode).upper()
    if not tri:
        return ""
    return SPORT_TEAM_TRICODE_ALIASES.get(canonicalize_sport_name(sport), {}).get(tri, "")


def _athlete_id_candidates(athlete: Dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("id", "alternateId"):
        token = _normalize_id(athlete.get(key))
        if token:
            values.append(token)
    alt = athlete.get("alternateIds")
    if isinstance(alt, dict):
        for raw in alt.values():
            token = _normalize_id(raw)
            if token:
                values.append(token)
    seen: set[str] = set()
    ordered: list[str] = []
    for token in values:
        if token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def _athlete_names(athlete: Dict[str, Any]) -> list[str]:
    names = [
        athlete.get("fullName"),
        athlete.get("displayName"),
        athlete.get("shortName"),
    ]
    first = _normalize_text(athlete.get("firstName"))
    last = _normalize_text(athlete.get("lastName") or athlete.get("familyName"))
    if first or last:
        names.append(f"{first} {last}".strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for name in names:
        token = _normalize_text(name)
        if not token:
            continue
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def _match_roster_athlete(
    athletes: list[Dict[str, Any]],
    player_id: str,
    player_name: str,
    player_jersey: str = "",
) -> Dict[str, Any]:
    if not athletes:
        return {}
    pid = _normalize_id(player_id)
    if pid:
        for athlete in athletes:
            if pid in _athlete_id_candidates(athlete):
                return athlete

    query_jersey = _normalize_text(player_jersey)
    if query_jersey:
        jersey_matches = [athlete for athlete in athletes if _normalize_text(athlete.get("jersey")) == query_jersey]
        if len(jersey_matches) == 1:
            return jersey_matches[0]
    else:
        jersey_matches = []

    query_name = _normalize_text(player_name)
    normalized_query = _normalize_name(query_name)
    if normalized_query:
        exact_matches: list[Dict[str, Any]] = []
        search_pool = jersey_matches or athletes
        for athlete in search_pool:
            for candidate in _athlete_names(athlete):
                if normalized_query == _normalize_name(candidate):
                    exact_matches.append(athlete)
                    break
        if len(exact_matches) == 1:
            return exact_matches[0]

    if query_name:
        query_first, query_last = _name_parts(query_name)
        query_initial = query_first[:1]
        if query_last:
            initial_matches: list[Dict[str, Any]] = []
            search_pool = jersey_matches or athletes
            for athlete in search_pool:
                names = _athlete_names(athlete)
                for candidate in names:
                    cand_first, cand_last = _name_parts(candidate)
                    if cand_last != query_last:
                        continue
                    if not query_initial or cand_first.startswith(query_initial):
                        initial_matches.append(athlete)
                        break
            if len(initial_matches) == 1:
                return initial_matches[0]
    return {}


def _profile_from_athlete(athlete: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(athlete, dict):
        return {}

    position = athlete.get("position")
    if isinstance(position, dict):
        pos_text = (
            position.get("abbreviation")
            or position.get("shortName")
            or position.get("displayName")
            or position.get("name")
        )
    else:
        pos_text = position

    birth_place = athlete.get("birthPlace")
    if isinstance(birth_place, dict):
        birth_place_text = (
            birth_place.get("displayText")
            or ", ".join(
                str(part).strip()
                for part in (birth_place.get("city"), birth_place.get("state"), birth_place.get("country"))
                if str(part or "").strip()
            )
        )
    else:
        birth_place_text = birth_place

    college = athlete.get("college")
    if isinstance(college, dict):
        college_text = college.get("displayName") or college.get("name")
    else:
        college_text = college

    experience = athlete.get("experience")
    if isinstance(experience, dict):
        years = experience.get("years")
        display = experience.get("displayValue") or experience.get("name") or experience.get("abbreviation")
        if years not in (None, "") and display:
            experience_text = f"{display} ({years})"
        elif years not in (None, ""):
            experience_text = str(years)
        else:
            experience_text = display
    else:
        experience_text = experience

    status = athlete.get("status")
    if isinstance(status, dict):
        status_text = status.get("displayName") or status.get("name") or status.get("type")
    else:
        status_text = status

    bats = athlete.get("bats")
    if isinstance(bats, dict):
        bats_text = bats.get("abbreviation") or bats.get("displayValue") or bats.get("name")
    else:
        bats_text = bats

    throws = athlete.get("throws")
    if isinstance(throws, dict):
        throws_text = throws.get("abbreviation") or throws.get("displayValue") or throws.get("name")
    else:
        throws_text = throws

    shoots_catches = athlete.get("shootsCatches")
    if isinstance(shoots_catches, dict):
        shoots_catches_text = (
            shoots_catches.get("abbreviation") or shoots_catches.get("displayValue") or shoots_catches.get("name")
        )
    else:
        shoots_catches_text = shoots_catches

    headshot = athlete.get("headshot")
    if isinstance(headshot, dict):
        headshot_url = headshot.get("href")
    else:
        headshot_url = None
    player_card_url = _athlete_link(athlete, "playercard")
    stats_url = _athlete_link(athlete, "stats")

    profile = {
        "id": _normalize_text(athlete.get("id") or athlete.get("alternateId")),
        "displayName": _normalize_text(athlete.get("displayName") or athlete.get("fullName")),
        "fullName": _normalize_text(athlete.get("fullName") or athlete.get("displayName")),
        "firstName": _normalize_text(athlete.get("firstName")),
        "lastName": _normalize_text(athlete.get("lastName") or athlete.get("familyName")),
        "jersey": _normalize_text(athlete.get("jersey")),
        "position": _normalize_text(pos_text),
        "height": _normalize_text(athlete.get("displayHeight") or athlete.get("height")),
        "weight": _normalize_text(athlete.get("displayWeight") or athlete.get("weight")),
        "age": _normalize_text(athlete.get("age")),
        "dateOfBirth": _normalize_text(athlete.get("dateOfBirth")),
        "birthPlace": _normalize_text(birth_place_text),
        "college": _normalize_text(college_text),
        "experience": _normalize_text(experience_text),
        "status": _normalize_text(status_text),
        "bats": _normalize_text(bats_text),
        "throws": _normalize_text(throws_text),
        "shootsCatches": _normalize_text(shoots_catches_text),
        "headshotUrl": _normalize_text(headshot_url),
        "playerCardUrl": _normalize_text(player_card_url),
        "statsUrl": _normalize_text(stats_url),
    }
    meaningful = any(
        profile.get(key)
        for key in (
            "displayName",
            "fullName",
            "firstName",
            "lastName",
            "jersey",
            "position",
            "height",
            "weight",
            "headshotUrl",
            "playerCardUrl",
            "statsUrl",
        )
    )
    return profile if meaningful else {}


def _athlete_link(athlete: Dict[str, Any], rel_name: str) -> str:
    links = athlete.get("links")
    if not isinstance(links, list):
        return ""
    target = rel_name.strip().lower()
    for link in links:
        if not isinstance(link, dict):
            continue
        rel = link.get("rel")
        rel_tokens = [str(token).lower() for token in rel] if isinstance(rel, list) else []
        if target in rel_tokens:
            href = link.get("href")
            if href:
                return str(href)
    return ""


def _athlete_team_logo(athlete: Dict[str, Any]) -> str:
    team = athlete.get("team")
    if not isinstance(team, dict):
        return ""
    logos = team.get("logos")
    if isinstance(logos, list):
        for logo in logos:
            if not isinstance(logo, dict):
                continue
            href = str(logo.get("href") or "").strip()
            if href:
                return href
    logo = str(team.get("logo") or "").strip()
    return logo


# ---------------- demo helpers ----------------
def _demo_scoreboard(sport: str) -> Dict[str, Any]:
    sport = canonicalize_sport_name(sport)
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
    sport_key = canonicalize_sport_name(sport)
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
        "sport": sport_key,
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
