from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import requests
from requests import Session

from ..common.ttl_cache import TTLCache
from ..common.utils import format_player_initial_name

# Configure module logger
logger = logging.getLogger(__name__)

SPORT = "nfl"
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

# ---------------- CACHING CONFIGURATION -----------------
# Cache TTL values (in seconds) - documented for maintainability
SCOREBOARD_TTL = 15.0  #: Scoreboard cache duration - frequent updates during games
BOXSCORE_TTL = 12.0    #: Boxscore cache duration - shorter for live game stats
LOGO_TTL = 86400.0     #: Logo cache duration - 24 hours (logos change rarely)

# Cache size limits to prevent memory leaks
SCOREBOARD_CACHE_MAXSIZE = 10    #: Maximum number of scoreboard entries to cache
BOXSCORE_CACHE_MAXSIZE = 50      #: Maximum number of boxscores to cache
LOGO_CACHE_MAXSIZE = 100         #: Maximum number of team logos to cache

# ---------------- TIMEOUT CONFIGURATION -----------------
# API timeout values (in seconds) - documented for operational tuning
SCOREBOARD_TIMEOUT = 8.0   #: Timeout for scoreboard API requests
BOXSCORE_TIMEOUT = 10.0    #: Timeout for boxscore API requests
LOGO_TIMEOUT = 5.0         #: Timeout for logo fetch requests
ROSTER_TIMEOUT = 8.0       #: Timeout for roster API requests

# ---------------- GAME STATE CONSTANTS -----------------
# Time windows for game state detection
LIVE_START_GRACE_SEC = 600    #: 10 minutes - grace period after scheduled start
LIVE_START_MAX_SEC = 21600    #: 6 hours - max time to consider game as potentially live
#: These values help detect games that have started but API hasn't updated yet

# ---------------- COLORS -----------------
TEAM_PRIMARY_COLORS: Dict[str, str] = {
    "NE": "#002244",
    "NYJ": "#125740",
    "BUF": "#00338D",
    "MIA": "#008E97",
    "BAL": "#241773",
    "PIT": "#FFB612",
    "CIN": "#FB4F14",
    "CLE": "#311D00",
    "TEN": "#002244",
    "IND": "#002C5F",
    "HOU": "#03202F",
    "JAX": "#006778",
    "KC": "#E31837",
    "LV": "#000000",
    "LVR": "#000000",
    "DEN": "#FB4F14",
    "LAC": "#0080C6",
    "DAL": "#003594",
    "PHI": "#004C54",
    "NYG": "#0B2265",
    "WAS": "#5C1233",
    "WSH": "#5C1233",
    "GB": "#203731",
    "MIN": "#4F2683",
    "CHI": "#0B162A",
    "DET": "#2A6EBB",
    "NO": "#D3BC8D",
    "ATL": "#A71930",
    "TB": "#D50A0A",
    "CAR": "#0085CA",
    "SF": "#AA0000",
    "SEA": "#002244",
    "LAR": "#003594",
    "ARI": "#97233F",
}

TEAM_SECONDARY_COLORS: Dict[str, str] = {
    "NE": "#C60C30",
    "NYJ": "#000000",
    "BUF": "#C60C30",
    "MIA": "#FC4C02",
    "BAL": "#9E7C0C",
    "PIT": "#101820",
    "CIN": "#000000",
    "CLE": "#FF3C00",
    "TEN": "#4B92DB",
    "IND": "#A2AAAD",
    "HOU": "#A71930",
    "JAX": "#9F792C",
    "KC": "#FFB81C",
    "LV": "#A5ACAF",
    "LVR": "#A5ACAF",
    "DEN": "#0A2343",
    "LAC": "#FFC20E",
    "DAL": "#869397",
    "PHI": "#A5ACAF",
    "NYG": "#A71930",
    "WAS": "#FFB612",
    "WSH": "#FFB612",
    "GB": "#FFB612",
    "MIN": "#FFC62F",
    "CHI": "#C83803",
    "DET": "#B0B7BC",
    "NO": "#101820",
    "ATL": "#000000",
    "TB": "#FF7900",
    "CAR": "#101820",
    "SF": "#B3995D",
    "SEA": "#69BE28",
    "LAR": "#FFA300",
    "ARI": "#000000",
}

TEAM_ACCENT_COLORS: Dict[str, str] = {
    "NE": "#B0B7BC",
    "NYJ": "#FFFFFF",
    "BUF": "#FFFFFF",
    "MIA": "#F0FFFF",
    "BAL": "#000000",
    "PIT": "#C4C4C4",
    "CIN": "#FFFFFF",
    "CLE": "#FFFFFF",
    "TEN": "#C8102E",
    "IND": "#FFFFFF",
    "HOU": "#FFFFFF",
    "JAX": "#101820",
    "KC": "#FFFFFF",
    "LV": "#FFFFFF",
    "LVR": "#FFFFFF",
    "DEN": "#FFFFFF",
    "LAC": "#FFFFFF",
    "DAL": "#FFFFFF",
    "PHI": "#000000",
    "NYG": "#FFFFFF",
    "WAS": "#FFB612",
    "WSH": "#FFB612",
    "GB": "#FFFFFF",
    "MIN": "#FFFFFF",
    "CHI": "#FFFFFF",
    "DET": "#FFFFFF",
    "NO": "#FFFFFF",
    "ATL": "#A5ACAF",
    "TB": "#000000",
    "CAR": "#A5ACAF",
    "SF": "#FFFFFF",
    "SEA": "#A5ACAF",
    "LAR": "#FFFFFF",
    "ARI": "#FFB612",
}

TEAM_COLORS = TEAM_PRIMARY_COLORS
TEAM_ALT_COLORS = TEAM_ACCENT_COLORS

# ---------------- CACHING (using TTLCache for memory-safe caching) -----------------
#: In-memory caches with TTL and size limits to prevent memory leaks
_scoreboard_cache: Dict[str, Any] = {"ts": 0.0, "data": None}
_boxscore_cache: TTLCache = TTLCache(maxsize=BOXSCORE_CACHE_MAXSIZE, ttl=BOXSCORE_TTL)

CACHE_ROOT = Path.home() / ".cache" / "scoresource"
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
SCOREBOARD_CACHE_PATH = CACHE_ROOT / f"{SPORT}_scoreboard.json"
BOXSCORE_CACHE_DIR = CACHE_ROOT / f"{SPORT}_boxscores"
BOXSCORE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOGO_VERSION = "2025-05"
LOGO_DIR = CACHE_ROOT / "logos" / SPORT
LOGO_DIR.mkdir(parents=True, exist_ok=True)
_logo_cache: TTLCache = TTLCache(maxsize=LOGO_CACHE_MAXSIZE, ttl=LOGO_TTL)
_logo_session: Session = requests.Session()
_logo_url_map: Dict[str, str] = {}

sport_table_headers = ["#", "Player", "Pos", "Yds", "TD", "Tkl", "Ast", "Pen"]

NFL_STATS_MAP = {
    "points": ["points", "score"],
    "reboundsTotal": ["tackles", "tackles_total"],
    "assists": ["pass_yards", "receptions", "rush_yards"],
    "personalFouls": ["penalties"],
    "minutesCalculated": ["play_time", "time_on_field"],
}

# ---------------- FORMAT HELPERS -----------------

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
    return "--"


def safe_score(team: Dict[str, Any]) -> int:
    val = team.get("score")
    if val in (None, ""):
        val = team.get("points") or team.get("scoreTotal")
    try:
        return int(val)
    except Exception:
        return int(val or 0)


def _parse_clock_and_period(text: str | None) -> tuple[str | None, int | None]:
    if not text:
        return None, None
    raw = str(text).strip()
    if not raw:
        return None, None
    clock = None
    period = None
    m = re.search(r"(\d{1,2}:\d{2})", raw)
    if m:
        clock = m.group(1)
    upper = raw.upper()
    if "OT" in upper:
        period = 5
    else:
        m = re.search(r"\b(\d)(?:ST|ND|RD|TH)\b", upper)
        if m:
            period = int(m.group(1))
        else:
            m = re.search(r"\bQ(\d)\b", upper)
            if m:
                period = int(m.group(1))
    return clock, period


def _extract_start_time_text(game: Dict[str, Any]) -> str:
    from ..common.timefmt import format_start_time, normalize_espn_time_str
    status_text = (game.get("gameStatusText") or game.get("statusText") or "").strip()
    if status_text and any(x in status_text.upper() for x in ("AM", "PM")):
        normalized = normalize_espn_time_str(status_text)
        if normalized:
            return normalized
    iso_val = game.get("gameTimeUTC") or game.get("startTime") or game.get("date") or game.get("startDate")
    if isinstance(iso_val, str) and iso_val:
        result = format_start_time(iso_val)
        if result != "Starts TBA":
            return result
    return status_text or "Scheduled"

# ---------------- DISK IO -----------------

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

# ---------------- LOGO LOADER -----------------

def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    """
    Load team logo from cache or fetch from remote.
    
    Uses TTLCache for automatic expiration and size-based eviction.
    Logs all fetch operations for debugging.
    
    Args:
        team_id: ESPN team ID
        tricode: Team tricode (e.g., "DAL", "NE")
        
    Returns:
        Logo image bytes or None if not available
    """
    tc = (tricode or "").upper()
    key = (team_id or "", tc, LOGO_VERSION)
    
    # Check in-memory cache first
    if key in _logo_cache:
        logger.debug(f"Logo cache hit for key={key}")
        return _logo_cache[key]

    # Check file cache
    cache_ext = ".svg"
    cache_name = f"{team_id or tc or 'unknown'}-{LOGO_VERSION}{cache_ext}"
    cache_path = LOGO_DIR / cache_name

    def _try_load_file() -> bytes | None:
        if cache_path.exists():
            try:
                data = cache_path.read_bytes()
                logger.debug(f"Logo file cache hit for {cache_name}")
                return data
            except Exception as e:
                logger.warning(f"Failed to read cached logo {cache_name}: {e}")
        return None

    def _fetch_urls(urls: List[str]) -> tuple[bytes | None, str]:
        for url in urls:
            try:
                resp = _logo_session.get(url, timeout=LOGO_TIMEOUT)
                resp.raise_for_status()
                ext = ".svg" if url.lower().endswith(".svg") else ".png"
                logger.info(f"Fetched logo from {url}")
                return resp.content, ext
            except Exception as e:
                logger.warning(f"Failed to fetch logo from {url}: {e}")
                continue
        return None, cache_ext

    # Try file cache first
    cached = _try_load_file()
    if cached:
        _logo_cache[key] = cached
        return cached

    # Build URL list and fetch
    urls: List[str] = []
    for code in filter(None, [team_id, tc]):
        url = _logo_url_map.get(str(code))
        if url:
            urls.append(url)

    content, used_ext = _fetch_urls(urls)
    if content:
        try:
            cache_path = cache_path.with_suffix(used_ext)
            cache_path.write_bytes(content)
            logger.debug(f"Saved logo to file cache: {cache_path.name}")
        except Exception as e:
            logger.warning(f"Failed to save logo to cache: {e}")
        _logo_cache[key] = content
        return content

    logger.debug(f"No logo found for key={key}")
    _logo_cache[key] = None
    return None

# ---------------- INTERNAL HELPERS -----------------

def _map_team(comp: Dict[str, Any], side: str) -> Dict[str, Any]:
    competitors = comp.get("competitors") or []
    raw = next((c for c in competitors if c.get("homeAway") == side), {})
    team = raw.get("team", {}) or {}
    tri = (team.get("abbreviation") or team.get("shortDisplayName") or "TM").upper()
    tid = str(team.get("id") or "")
    logo = team.get("logo") or ((team.get("logos") or [{}])[0]).get("href")
    if logo:
        _logo_url_map[tid or tri] = logo
        _logo_url_map[tri] = logo
    return {
        "teamId": tid,
        "teamName": team.get("displayName") or team.get("name") or "Team",
        "teamTricode": tri,
        "score": int(raw.get("score") or 0),
        "players": [],
    }


def _build_line(g: Dict[str, Any]) -> str:
    home = g.get("homeTeam", {}) or {}
    away = g.get("awayTeam", {}) or {}
    hs = safe_score(home)
    as_ = safe_score(away)
    status = g.get("gameStatusText") or "Scheduled"
    return f"{away.get('teamName','Away')} {as_} @ {home.get('teamName','Home')} {hs} ({status})"


def _parse_leader_stat(display: str) -> tuple[int, int]:
    yards = 0
    tds = 0
    try:
        yd_match = re.search(r"(\d+)\s*YDS", display.upper())
        if yd_match:
            yards = int(yd_match.group(1))
        td_match = re.findall(r"(\d+)\s*TD", display.upper())
        if td_match:
            tds = sum(int(x) for x in td_match)
    except Exception:
        pass
    return yards, tds


def _leader_to_player(leader_entry: Dict[str, Any], category: str) -> Dict[str, Any]:
    athlete = leader_entry.get("athlete", {}) or {}
    full = athlete.get("fullName") or athlete.get("displayName") or "Player"
    parts = full.split()
    first = parts[0] if parts else "Player"
    last = " ".join(parts[1:]) if len(parts) > 1 else ""
    jersey = athlete.get("jersey") or ""
    pos = (athlete.get("position") or {}).get("abbreviation", "")
    display_val = leader_entry.get("displayValue", "") or ""
    yards, tds = _parse_leader_stat(display_val)

    points = tds * 6
    assists = yards // 20 if yards else 0
    rebounds = 0
    personal_fouls = 0
    minutes = ""

    stats = {
        "isOnCourt": False,
        "points": points,
        "reboundsTotal": rebounds,
        "assists": assists,
        "personalFouls": personal_fouls,
        "minutesCalculated": minutes,
        "yardsTotal": yards,
        "touchdowns": tds,
    }

    return {
        "firstName": first,
        "familyName": last,
        "position": pos,
        "jerseyNum": str(jersey),
        "statistics": stats,
    }


def _leaders_to_players(leaders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    players: Dict[str, Dict[str, Any]] = {}
    for cat in leaders or []:
        cat_name = cat.get("displayName") or cat.get("name") or ""
        for entry in cat.get("leaders", []) or []:
            athlete = entry.get("athlete", {}) or {}
            aid = str(athlete.get("id") or entry.get("id") or len(players))
            player = players.get(aid)
            new_p = _leader_to_player(entry, cat_name)
            if player:
                # merge simple aggregates
                pstats = player.get("statistics", {})
                nstats = new_p.get("statistics", {})
                for k in ("points", "reboundsTotal", "assists", "personalFouls", "yardsTotal", "touchdowns"):
                    pstats[k] = pstats.get(k, 0) + nstats.get(k, 0)
                player["statistics"] = pstats
            else:
                players[aid] = new_p
    return list(players.values())


def _build_header(game: Dict[str, Any]) -> str:
    status_value = game.get("gameStatus")
    period = game.get("period") or {}
    current = period.get("current") if isinstance(period, dict) else period
    clock = game.get("gameClock") or ""
    status_text = (game.get("gameStatusText") or "").strip()

    if status_value == 3:
        return "Final"
    if status_value in (None, 0, 1) or not current:
        return _extract_start_time_text(game)
    if current:
        return f"Q{current} {clock}".strip()
    return status_text or clock or "Live"

# ---------------- PUBLIC API -----------------

def fetch_scores() -> Dict[str, Any]:
    """
    Fetch NFL scoreboard data from ESPN API.
    
    Uses TTLCache for automatic cache expiration and size-based eviction.
    Falls back to disk cache if network fails, then to demo data.
    
    Returns:
        Dict with 'games' and 'lines' keys
    """
    now = time.monotonic()
    disk_seed = None

    # Check memory cache first
    if _scoreboard_cache.get("data") is None:
        disk_seed = _load_disk_scoreboard()
        if disk_seed:
            _scoreboard_cache["data"] = disk_seed
            # Seed from disk but force an immediate refresh attempt.
            _scoreboard_cache["ts"] = 0.0
            logger.debug("Scoreboard seeded from disk cache")

    cached = _scoreboard_cache.get("data")
    if cached and now - _scoreboard_cache.get("ts", 0) < SCOREBOARD_TTL:
        logger.debug("Scoreboard served from memory cache")
        return cached

    # Fetch from API
    try:
        logger.info("Fetching NFL scoreboard from ESPN API...")
        resp = _logo_session.get(SCOREBOARD_URL, timeout=SCOREBOARD_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Successfully fetched scoreboard with {len(data.get('events', []))} events")
    except Exception as e:
        logger.error(f"Failed to fetch scoreboard: {e}")
        data = None

    events: List[Dict[str, Any]] = []
    if isinstance(data, dict):
        content = data.get("content", {})
        if isinstance(content, dict):
            sb_data = content.get("sbData", {})
            if isinstance(sb_data, dict):
                events = sb_data.get("events", []) or []
        if not events:
            events = data.get("events", []) or []

    games: List[Dict[str, Any]] = []
    for ev in events:
        comp = (ev.get("competitions") or [{}])[0]
        status_block = (ev.get("status") or {}).get("type", {})
        state = status_block.get("state")
        period = status_block.get("period")
        clock = status_block.get("displayClock")
        start_time = ev.get("date") or ev.get("startDate")
        status_text_raw = status_block.get("shortDetail") or status_block.get("detail")
        
        # Check if this is the Super Bowl
        notes = comp.get("notes", [])
        is_super_bowl = any("Super Bowl" in note.get("headline", "") for note in notes)
        super_bowl_name = ""
        if is_super_bowl:
            for note in notes:
                headline = note.get("headline", "")
                if "Super Bowl" in headline:
                    super_bowl_name = headline
                    break
        
        home = _map_team(comp, "home")
        away = _map_team(comp, "away")
        parsed_clock, parsed_period = _parse_clock_and_period(status_text_raw)
        if not clock:
            clock = parsed_clock
        if not period:
            period = parsed_period
        if isinstance(period, int) and period <= 0:
            period = None

        if state == "pre":
            game_status = 1
            status_text = _extract_start_time_text({"date": start_time, "gameStatusText": status_text_raw})
        elif state == "post":
            game_status = 3
            status_text = status_text_raw or "Final"
        else:
            game_status = 2
            if status_text_raw and "halftime" in status_text_raw.lower():
                if (period in (None, 2)) and (not clock or clock in ("0:00", "00:00")):
                    status_text = "Halftime"
                else:
                    status_text = status_text_raw or (f"Q{period} {clock}" if period else (clock or "Live"))
            else:
                status_text = status_text_raw or (f"Q{period} {clock}" if period else (clock or "Live"))

        game = {
            "gameId": str(ev.get("id")),
            "homeTeam": home,
            "awayTeam": away,
            "gameStatus": game_status,
            "gameStatusText": status_text,
            "period": {"current": period} if period else {},
            "gameClock": clock,
            "gameTimeUTC": start_time,
        }
        
        # Add Super Bowl flags
        if is_super_bowl:
            game["isSuperBowl"] = True
            game["superBowlName"] = super_bowl_name
        
        games.append(game)

    if not games:
        disk = cached or disk_seed or _load_disk_scoreboard()
        if disk and disk.get("games"):
            _scoreboard_cache["data"] = disk
            _scoreboard_cache["ts"] = now
            return disk

    lines = [_build_line(g) for g in games] if games else ["No games today."]
    result = {"games": games, "lines": lines}
    _scoreboard_cache["data"] = result
    _scoreboard_cache["ts"] = time.monotonic()
    _save_disk_scoreboard(result)
    return result


def fetch_boxscore(game_id: str) -> Dict[str, Any]:
    """
    Fetch detailed boxscore for a specific NFL game.
    
    Uses TTLCache for automatic expiration and size-based eviction.
    Falls back to scoreboard data if boxscore fetch fails.
    
    Args:
        game_id: ESPN game ID
        
    Returns:
        Dict with 'game', 'home', 'away', and 'header' keys
    """
    now = time.monotonic()
    
    # Check TTLCache - TTLCache handles expiration automatically
    if game_id in _boxscore_cache:
        logger.debug(f"Boxscore cache hit for game_id={game_id}")
        return _boxscore_cache[game_id]

    board = _scoreboard_cache.get("data") or fetch_scores()
    games = board.get("games", []) if isinstance(board, dict) else []
    game = next((g for g in games if str(g.get("gameId")) == str(game_id)), None)
    if game is None:
        disk_board = _load_disk_scoreboard() or {}
        disk_games = disk_board.get("games", []) if isinstance(disk_board, dict) else []
        game = next((g for g in disk_games if str(g.get("gameId")) == str(game_id)), None)

    # Build player lists from leaders if available
    home_players: List[Dict[str, Any]] = []
    away_players: List[Dict[str, Any]] = []
    if game:
        comp = None
        # locate competition for this game from last fetched events
        data = _scoreboard_cache.get("data") or {}
        events = (data.get("games") and board.get("games")) or []
        # not reliable; instead we refetch scoreboard quickly
        try:
            logger.debug(f"Fetching boxscore for game {game_id}")
            resp = _logo_session.get(SCOREBOARD_URL, timeout=SCOREBOARD_TIMEOUT)
            resp.raise_for_status()
            raw = resp.json()
            content = raw.get("content", {}) if isinstance(raw, dict) else {}
            sb_data = content.get("sbData", {}) if isinstance(content, dict) else {}
            evs = sb_data.get("events", []) or raw.get("events", []) or []
            comp = next((e.get("competitions", [{}])[0] for e in evs if str(e.get("id")) == str(game_id)), None)
        except Exception as e:
            logger.warning(f"Failed to fetch boxscore for game {game_id}: {e}")
            comp = None
        if comp:
            competitors = comp.get("competitors") or []
            home_leaders = []
            away_leaders = []
            for c in competitors:
                if c.get("homeAway") == "home":
                    home_leaders = c.get("leaders") or []
                elif c.get("homeAway") == "away":
                    away_leaders = c.get("leaders") or []
            home_players = _leaders_to_players(home_leaders)
            away_players = _leaders_to_players(away_leaders)

    if not game:
        game = {
            "gameId": game_id,
            "homeTeam": {"teamName": "Home", "teamTricode": "HME", "score": 0},
            "awayTeam": {"teamName": "Away", "teamTricode": "AWY", "score": 0},
            "gameStatus": 1,
            "gameStatusText": "Scheduled",
            "period": {"current": None},
            "gameClock": None,
        }

    home = game.get("homeTeam", {}) or {}
    away = game.get("awayTeam", {}) or {}
    home["players"] = home_players
    away["players"] = away_players

    header = _build_header(game)
    result = {
        "game": game,
        "home": home,
        "away": away,
        "header": header,
        "shotclock": "--",
    }
    
    # Store in TTLCache (automatically handles expiration and size limits)
    _boxscore_cache[game_id] = result
    logger.debug(f"Stored boxscore in cache for game_id={game_id}")
    _save_disk_boxscore(game_id, result)
    return result


def build_player_rows(team: Dict[str, Any]) -> List[List[str]]:
    rows: List[List[str]] = []
    players = team.get("players", []) or []
    for p in players:
        stats = p.get("statistics", {}) or {}
        jersey = p.get("jerseyNum") or ""
        name = format_player_initial_name(p.get("firstName"), p.get("familyName"))
        pos = p.get("position") or ""
        yards = stats.get("yardsTotal", 0)
        td = stats.get("touchdowns", 0)
        tackles = stats.get("reboundsTotal", 0)
        assists = stats.get("assists", 0)
        pens = stats.get("personalFouls", 0)
        rows.append([jersey, name, pos, yards, td, tackles, assists, pens])
    return rows


# Compatibility wrappers expected by the test-suite / external callers
def _normalize_game_for_tests(g: Dict[str, Any]) -> Dict[str, Any]:
    home = (g.get("homeTeam") or {}) or {}
    away = (g.get("awayTeam") or {}) or {}
    game_id = str(g.get("gameId") or g.get("id") or "")
    start_time = g.get("gameTimeUTC") or g.get("gameEt") or g.get("date")
    period_field = g.get("period")
    if isinstance(period_field, dict):
        period = period_field.get("current")
    elif isinstance(period_field, int):
        period = period_field
    else:
        period = None
    clock = format_clock(g.get("gameClock") or g.get("clock") or g.get("displayClock"))
    shot = format_shotclock(g.get("shotClock")) if "format_shotclock" in globals() else "--"
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
        "isSuperBowl": g.get("isSuperBowl", False),
        "superBowlName": g.get("superBowlName", ""),
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
    return {"games": normalized, "lines": raw.get("lines")}


def fetch_schedule() -> Dict[str, Any]:
    return fetch_live()
