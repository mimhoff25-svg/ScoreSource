from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

SPORT = "ncaa_football"
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event={game_id}"
SCOREBOARD_GROUPS: Dict[int, str] = {80: "FBS", 81: "FCS"}


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

TEAM_PRIMARY_COLORS: Dict[str, str] = {}
TEAM_SECONDARY_COLORS: Dict[str, str] = {}
TEAM_ACCENT_COLORS: Dict[str, str] = {}
TEAM_ALT_COLORS: Dict[str, str] = {}
TEAM_COLORS = TEAM_PRIMARY_COLORS

_scoreboard_cache: Dict[str, Any] = {"ts": 0.0, "data": None}
_boxscore_cache: Dict[str, Tuple[float, Any]] = {}

SCOREBOARD_TTL = _env_float("SCORESOURCE_NCAA_FOOTBALL_SCOREBOARD_TTL", 15.0, min_value=0.0)
BOXSCORE_TTL = _env_float("SCORESOURCE_NCAA_FOOTBALL_BOXSCORE_TTL", 12.0, min_value=0.0)
SCOREBOARD_TIMEOUT_SEC = _env_float("SCORESOURCE_NCAA_FOOTBALL_SCOREBOARD_TIMEOUT_SEC", 5.0, min_value=1.0)
SUMMARY_TIMEOUT_SEC = _env_float("SCORESOURCE_NCAA_FOOTBALL_SUMMARY_TIMEOUT_SEC", 8.0, min_value=1.0)
LOGO_TIMEOUT_SEC = _env_float("SCORESOURCE_NCAA_FOOTBALL_LOGO_TIMEOUT_SEC", 3.0, min_value=1.0)

CACHE_ROOT = _cache_root_from_env()
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
SCOREBOARD_CACHE_PATH = CACHE_ROOT / f"{SPORT}_scoreboard.json"
BOXSCORE_CACHE_DIR = CACHE_ROOT / f"{SPORT}_boxscores"
BOXSCORE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOGO_VERSION = "2025-05"
LOGO_DIR = CACHE_ROOT / "logos" / SPORT
LOGO_DIR.mkdir(parents=True, exist_ok=True)
_logo_cache: Dict[Tuple[str, str, str], bytes | None] = {}
_logo_session = requests.Session()
_logo_url_map: Dict[str, str] = {}

sport_table_headers = ["#", "Player", "Pos", "Yds", "TD", "Tkl", "Ast", "Pen"]

STAT_MAP: Dict[str, List[str]] = {
    "points": ["points", "score"],
    "rebounds": ["rebounds"],
    "assists": ["assists"],
}


def _normalize_hex(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return None
    return f"#{text.lower()}"


def _scale(hex_color: str, factor: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    vals = [int(h[i : i + 2], 16) for i in (0, 2, 4)]
    scaled = [min(255, max(0, int(v * factor))) for v in vals]
    return "#%02x%02x%02x" % tuple(scaled)


def _register_team_colors(tri: str, team: Dict[str, Any]) -> tuple[str | None, str | None]:
    if not tri:
        return None, None
    primary = _normalize_hex(team.get("color"))
    secondary = _normalize_hex(team.get("alternateColor"))
    if primary and not secondary:
        secondary = _scale(primary, 0.7)
    if primary and tri not in TEAM_PRIMARY_COLORS:
        TEAM_PRIMARY_COLORS[tri] = primary
    if secondary:
        TEAM_SECONDARY_COLORS.setdefault(tri, secondary)
        TEAM_ACCENT_COLORS.setdefault(tri, secondary)
        TEAM_ALT_COLORS.setdefault(tri, secondary)
    return primary, secondary


def _seed_colors_from_games(games: list[Dict[str, Any]]) -> None:
    for g in games:
        for key in ("homeTeam", "awayTeam"):
            team = g.get(key) if isinstance(g, dict) else None
            if not isinstance(team, dict):
                continue
            tri = (team.get("teamTricode") or team.get("abbreviation") or team.get("shortDisplayName") or "").upper()
            primary = _normalize_hex(team.get("teamColor") or team.get("color"))
            secondary = _normalize_hex(team.get("teamAltColor") or team.get("alternateColor"))
            if primary and not secondary:
                secondary = _scale(primary, 0.7)
            if tri and primary and tri not in TEAM_PRIMARY_COLORS:
                TEAM_PRIMARY_COLORS[tri] = primary
            if tri and secondary:
                TEAM_SECONDARY_COLORS.setdefault(tri, secondary)
                TEAM_ACCENT_COLORS.setdefault(tri, secondary)
                TEAM_ALT_COLORS.setdefault(tri, secondary)


def _period_label(period: int | None) -> str:
    if not isinstance(period, int) or period <= 0:
        return ""
    if period <= 4:
        return f"Q{period}"
    return "OT" if period == 5 else f"OT{period - 4}"


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
    if value in (None, "", "--"):
        return "--"
    try:
        num = float(value)
        if num.is_integer():
            return str(int(num))
        return f"{num:.1f}".rstrip("0").rstrip(".")
    except Exception:
        return str(value)


def safe_score(team: Dict[str, Any]) -> int:
    val = team.get("score")
    if val in (None, ""):
        val = team.get("points") or team.get("scoreTotal")
    try:
        return int(val)
    except Exception:
        return int(val or 0)


def _extract_start_time_text(g: Dict[str, Any]) -> str:
    from ..common.timefmt import format_start_time, normalize_espn_time_str
    status_text = (g.get("gameStatusText") or g.get("statusText") or "").strip()
    if status_text and any(x in status_text.upper() for x in ("AM", "PM")):
        normalized = normalize_espn_time_str(status_text)
        if normalized:
            return normalized
    iso_val = g.get("gameTimeUTC") or g.get("startTime") or g.get("date")
    if isinstance(iso_val, str) and iso_val:
        result = format_start_time(iso_val)
        if result != "Starts TBA":
            return result
    return status_text or "Scheduled"


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


def _scoreboard_url(group_id: int | None) -> str:
    if group_id is None:
        return SCOREBOARD_URL
    joiner = "&" if "?" in SCOREBOARD_URL else "?"
    return f"{SCOREBOARD_URL}{joiner}groups={group_id}"


def _fetch_scoreboard(group_id: int | None) -> Dict[str, Any] | None:
    try:
        resp = _logo_session.get(_scoreboard_url(group_id), timeout=SCOREBOARD_TIMEOUT_SEC)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    tc = (tricode or "").upper()
    key = (team_id or "", tc, LOGO_VERSION)
    if key in _logo_cache:
        return _logo_cache[key]

    cache_ext = ".svg"
    cache_name = f"{team_id or tc or 'unknown'}-{LOGO_VERSION}{cache_ext}"
    cache_path = LOGO_DIR / cache_name

    def _try_load_file() -> bytes | None:
        if cache_path.exists():
            try:
                return cache_path.read_bytes()
            except Exception:
                return None
        return None

    def _fetch_urls(urls: List[str]) -> tuple[bytes | None, str]:
        for url in urls:
            try:
                resp = _logo_session.get(url, timeout=LOGO_TIMEOUT_SEC)
                resp.raise_for_status()
                ext = ".svg" if url.lower().endswith(".svg") else ".png"
                return resp.content, ext
            except Exception:
                continue
        return None, cache_ext

    cached = _try_load_file()
    if cached:
        _logo_cache[key] = cached
        return cached

    urls: List[str] = []
    for code in filter(None, [team_id, tc]):
        url = _logo_url_map.get(str(code))
        if url:
            urls.append(url)
    if not urls:
        if team_id:
            urls.append(f"https://a.espncdn.com/i/teamlogos/ncaa/500/{team_id}.png")
        if tc:
            urls.append(f"https://a.espncdn.com/i/teamlogos/ncaa/500/{tc.lower()}.png")

    content, used_ext = _fetch_urls(urls)
    if content:
        try:
            cache_path = cache_path.with_suffix(used_ext)
            cache_path.write_bytes(content)
        except Exception:
            pass
        _logo_cache[key] = content
        return content

    _logo_cache[key] = None
    return None


def _map_team(comp: Dict[str, Any], side: str) -> Dict[str, Any]:
    competitors = comp.get("competitors") or []
    raw = next((c for c in competitors if c.get("homeAway") == side), {})
    team = raw.get("team", {}) or {}
    tri = (team.get("abbreviation") or team.get("shortDisplayName") or "TM").upper()
    tid = str(team.get("id") or "")
    primary, secondary = _register_team_colors(tri, team)
    logo = team.get("logo") or ((team.get("logos") or [{}])[0]).get("href")
    if logo:
        _logo_url_map[tid or tri] = logo
        _logo_url_map[tri] = logo
    return {
        "teamId": tid,
        "teamName": team.get("displayName") or team.get("name") or "Team",
        "teamTricode": tri,
        "score": int(raw.get("score") or 0),
        "teamColor": primary,
        "teamAltColor": secondary,
        "players": [],
    }


def _build_line(g: Dict[str, Any]) -> str:
    home = g.get("homeTeam", {}) or {}
    away = g.get("awayTeam", {}) or {}
    hs = safe_score(home)
    as_ = safe_score(away)
    status = g.get("gameStatusText") or "Scheduled"
    return f"{away.get('teamName','Away')} {as_} @ {home.get('teamName','Home')} {hs} ({status})"


# Compatibility wrappers expected by the test-suite / external callers
def _normalize_game_for_tests(g: Dict[str, Any]) -> Dict[str, Any]:
    home = (g.get("homeTeam") or {}) or {}
    away = (g.get("awayTeam") or {}) or {}
    game_id = str(g.get("gameId") or g.get("id") or "")
    start_time = g.get("gameTimeUTC") or g.get("startTime") or g.get("date")
    period = g.get("period") or {}
    clock = format_clock(g.get("gameClock") or g.get("clock"))
    shot = format_shotclock(g.get("shotClock"))
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
        "home": home.get("teamName") or home.get("teamCity") or "Home",
        "away": away.get("teamName") or away.get("teamCity") or "Away",
        "homeTricode": home.get("teamTricode") or home.get("abbreviation") or "",
        "awayTricode": away.get("teamTricode") or away.get("abbreviation") or "",
        "homeScore": home_score,
        "awayScore": away_score,
        "startTime": start_time,
        "period": period,
        "clock": clock,
        "shotClock": shot,
        "division": g.get("division"),
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


def fetch_scores() -> Dict[str, Any]:
    now = time.monotonic()
    disk = None
    if _scoreboard_cache.get("data") is None:
        disk = _load_disk_scoreboard()

    cached = _scoreboard_cache.get("data")
    if cached and now - _scoreboard_cache.get("ts", 0) < SCOREBOARD_TTL:
        _seed_colors_from_games(cached.get("games", []) or [])
        return cached

    events_by_division: list[tuple[str, list[Dict[str, Any]]]] = []
    for group_id, label in SCOREBOARD_GROUPS.items():
        data = _fetch_scoreboard(group_id)
        if not data:
            continue
        events = data.get("events", []) or []
        if events:
            events_by_division.append((label, events))
    if not events_by_division:
        data = _fetch_scoreboard(None)
        if not data:
            if disk:
                _seed_colors_from_games(disk.get("games", []) or [])
                _scoreboard_cache["data"] = disk
                _scoreboard_cache["ts"] = now
                return disk
            return {"games": [], "lines": ["No games today."]}
        events_by_division.append(("NCAA", data.get("events", []) or []))
    games: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for division_label, events in events_by_division:
        for ev in events:
            game_id = str(ev.get("id") or "")
            if not game_id or game_id in seen_ids:
                continue
            seen_ids.add(game_id)
            comp = (ev.get("competitions") or [{}])[0]
            status = ev.get("status") or {}
            status_type = status.get("type") or {}
            state = status_type.get("state")
            period = status.get("period") or 0
            clock = status.get("displayClock") or status.get("clock")
            start_time = ev.get("date")
            status_text_raw = status_type.get("shortDetail") or status_type.get("detail")
            home = _map_team(comp, "home")
            away = _map_team(comp, "away")

            if state == "pre":
                game_status = 1
                status_text = _extract_start_time_text({"date": start_time, "gameStatusText": status_text_raw})
            elif state == "post":
                game_status = 3
                status_text = status_text_raw or "Final"
            else:
                game_status = 2
                if status_text_raw and "halftime" in status_text_raw.lower():
                    status_text = "Halftime"
                else:
                    label = _period_label(period)
                    status_text = status_text_raw or (f"{label} {clock}".strip() if (label or clock) else "Live")

            game = {
                "gameId": game_id,
                "homeTeam": home,
                "awayTeam": away,
                "gameStatus": game_status,
                "gameStatusText": status_text,
                "period": {"current": period} if period else {},
                "gameClock": clock,
                "gameTimeUTC": start_time,
                "division": division_label,
            }
            games.append(game)

    lines = [_build_line(g) for g in games] if games else ["No games today."]
    _seed_colors_from_games(games)
    result = {"games": games, "lines": lines}
    _scoreboard_cache["data"] = result
    _scoreboard_cache["ts"] = time.monotonic()
    _save_disk_scoreboard(result)
    return result


def _build_header(game: Dict[str, Any]) -> str:
    status_value = game.get("gameStatus")
    period = game.get("period") or {}
    current = period.get("current") if isinstance(period, dict) else period
    clock = format_clock(game.get("gameClock"))
    status_text = (game.get("gameStatusText") or "").strip()

    if status_value == 3 and status_text:
        return status_text
    if status_value in (None, 0, 1) or not current:
        return _extract_start_time_text(game)
    label = _period_label(current if isinstance(current, int) else None)
    return f"{label} {clock}".strip() if (label or clock) else (status_text or "Live")


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    match = re.search(r"-?\d+", str(value))
    if not match:
        return 0
    try:
        return int(match.group(0))
    except Exception:
        return 0


def _player_entry(athlete: Dict[str, Any]) -> Dict[str, Any]:
    first = str(athlete.get("firstName") or "").strip()
    last = str(athlete.get("lastName") or "").strip()
    return {
        "id": str(athlete.get("id") or ""),
        "firstName": first,
        "familyName": last,
        "displayName": str(athlete.get("displayName") or f"{first} {last}".strip()),
        "jerseyNum": str(athlete.get("jersey") or ""),
        "position": str((athlete.get("position") or {}).get("abbreviation") or ""),
        "headshot": ((athlete.get("headshot") or {}).get("href") or ""),
        "statistics": {},
        "group": "",
    }


def _merge_player_total(stats: Dict[str, Any], key: str, value: Any) -> None:
    stats[key] = _to_int(stats.get(key)) + _to_int(value)


def _apply_section_stat(stats: Dict[str, Any], section: str, key: str, value: Any) -> None:
    if value in (None, ""):
        return
    if section == "passing":
        if key == "passingYards":
            _merge_player_total(stats, "yardsTotal", value)
        elif key == "passingTouchdowns":
            _merge_player_total(stats, "touchdowns", value)
        elif key == "interceptions":
            _merge_player_total(stats, "interceptions", value)
    elif section == "rushing":
        if key == "rushingAttempts":
            _merge_player_total(stats, "carries", value)
        elif key == "rushingYards":
            _merge_player_total(stats, "yardsTotal", value)
        elif key == "rushingTouchdowns":
            _merge_player_total(stats, "touchdowns", value)
    elif section == "receiving":
        if key == "receptions":
            _merge_player_total(stats, "receptions", value)
        elif key == "receivingYards":
            _merge_player_total(stats, "yardsTotal", value)
        elif key == "receivingTouchdowns":
            _merge_player_total(stats, "touchdowns", value)
    elif section == "defensive":
        if key == "totalTackles":
            stats["tacklesTotal"] = _to_int(value)
            stats["reboundsTotal"] = _to_int(value)
        elif key == "soloTackles":
            total = _to_int(stats.get("tacklesTotal"))
            solo = _to_int(value)
            assists = max(total - solo, 0)
            stats["tacklesAssist"] = assists
            stats["assists"] = assists
        elif key == "sacks":
            _merge_player_total(stats, "sacks", value)
        elif key == "passesDefended":
            _merge_player_total(stats, "passesDefended", value)
        elif key == "defensiveTouchdowns":
            _merge_player_total(stats, "touchdowns", value)
    elif section == "interceptions":
        if key == "interceptions":
            _merge_player_total(stats, "interceptions", value)
        elif key == "interceptionTouchdowns":
            _merge_player_total(stats, "touchdowns", value)
    elif section in {"kickReturns", "puntReturns"}:
        if key.endswith("Yards"):
            _merge_player_total(stats, "yardsTotal", value)
        elif key.endswith("Touchdowns"):
            _merge_player_total(stats, "touchdowns", value)


def _parse_summary_players(summary: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    boxscore = (summary.get("boxscore") or {})
    blocks = boxscore.get("players") or []
    players_by_team: Dict[str, List[Dict[str, Any]]] = {}
    for block in blocks:
        if not isinstance(block, dict):
            continue
        team = block.get("team") or {}
        team_id = str(team.get("id") or "")
        if not team_id:
            continue
        athlete_map: Dict[str, Dict[str, Any]] = {}
        for section in block.get("statistics") or []:
            section_name = str(section.get("name") or "").strip()
            keys = [str(key or "") for key in (section.get("keys") or [])]
            for athlete_row in section.get("athletes") or []:
                athlete = athlete_row.get("athlete") or {}
                athlete_id = str(athlete.get("id") or "")
                if not athlete_id:
                    continue
                player = athlete_map.setdefault(athlete_id, _player_entry(athlete))
                if not player.get("position"):
                    player["position"] = str((athlete.get("position") or {}).get("abbreviation") or "")
                if not player.get("headshot"):
                    player["headshot"] = ((athlete.get("headshot") or {}).get("href") or "")
                if section_name in {"passing", "rushing", "receiving"}:
                    player["group"] = "offense"
                elif section_name in {"defensive", "interceptions"} and not player.get("group"):
                    player["group"] = "defense"
                stats_values = athlete_row.get("stats") or []
                for idx, key in enumerate(keys):
                    value = stats_values[idx] if idx < len(stats_values) else None
                    _apply_section_stat(player["statistics"], section_name, key, value)
        parsed_players = list(athlete_map.values())
        parsed_players.sort(
            key=lambda player: (
                -(player.get("statistics") or {}).get("touchdowns", 0),
                -(player.get("statistics") or {}).get("yardsTotal", 0),
                -((player.get("statistics") or {}).get("tacklesTotal", 0)),
                str(player.get("displayName") or ""),
            )
        )
        players_by_team[team_id] = parsed_players
    return players_by_team


def fetch_boxscore(game_id: str) -> Dict[str, Any]:
    now = time.monotonic()
    cached = _boxscore_cache.get(game_id)
    if cached and now - cached[0] < BOXSCORE_TTL:
        return cached[1]

    summary = None
    try:
        resp = requests.get(SUMMARY_URL.format(game_id=game_id), timeout=SUMMARY_TIMEOUT_SEC)
        resp.raise_for_status()
        summary = resp.json()
    except Exception:
        summary = None

    if isinstance(summary, dict):
        header = summary.get("header") or {}
        comp = (header.get("competitions") or [{}])[0]
        if isinstance(comp, dict) and comp:
            status = comp.get("status") or {}
            status_type = status.get("type") or {}
            state = status_type.get("state")
            period = status.get("period") or 0
            clock = status.get("displayClock") or status.get("clock")
            game_status_text = status_type.get("shortDetail") or status_type.get("detail") or "Scheduled"
            home = _map_team(comp, "home")
            away = _map_team(comp, "away")
            players_by_team = _parse_summary_players(summary)
            home["players"] = players_by_team.get(str(home.get("teamId") or ""), [])
            away["players"] = players_by_team.get(str(away.get("teamId") or ""), [])
            game_status = 3 if state == "post" else (1 if state == "pre" else 2)
            game = {
                "gameId": str(game_id),
                "homeTeam": home,
                "awayTeam": away,
                "gameStatus": game_status,
                "gameStatusText": game_status_text,
                "period": {"current": period} if period else {},
                "gameClock": clock,
                "gameTimeUTC": comp.get("date"),
            }
            result = {
                "game": game,
                "home": home,
                "away": away,
                "header": _build_header(game),
                "shotclock": "--",
            }
            _boxscore_cache[game_id] = (now, result)
            _save_disk_boxscore(game_id, result)
            return result

    board = _scoreboard_cache.get("data") or _load_disk_scoreboard() or fetch_scores()
    games = board.get("games", []) if isinstance(board, dict) else []
    game = next((g for g in games if str(g.get("gameId")) == str(game_id)), None)
    if game:
        header = _build_header(game)
        result = {
            "game": game,
            "home": game.get("homeTeam", {}),
            "away": game.get("awayTeam", {}),
            "header": header,
            "shotclock": "--",
        }
        _boxscore_cache[game_id] = (now, result)
        _save_disk_boxscore(game_id, result)
        return result

    disk = _load_disk_boxscore(game_id)
    if disk:
        _boxscore_cache[game_id] = (now, disk)
        return disk

    stub = {
        "game": {"gameStatusText": "Scheduled", "period": {"current": None}},
        "home": {"teamName": "Home", "teamTricode": "HME", "score": 0},
        "away": {"teamName": "Away", "teamTricode": "AWY", "score": 0},
        "header": "No data",
        "shotclock": "--",
    }
    _boxscore_cache[game_id] = (now, stub)
    return stub


def build_player_rows(team: Dict[str, Any]) -> List[List[str]]:
    rows: List[List[str]] = []
    players = team.get("players", []) or []
    for p in players:
        stats = p.get("statistics", {}) or {}
        jersey = p.get("jerseyNum") or ""
        name = p.get("displayName") or ""
        if not name:
            first = str(p.get("firstName") or "").strip()
            last = str(p.get("familyName") or "").strip()
            if first or last:
                name = f"{first[:1]}. {last}".strip()
        pos = p.get("position") or ""
        yards = stats.get("yardsTotal", 0)
        td = stats.get("touchdowns", 0)
        tackles = stats.get("tacklesTotal", stats.get("reboundsTotal", 0))
        assists = stats.get("tacklesAssist", stats.get("assists", 0))
        interceptions = stats.get("interceptions", 0)
        if str(p.get("group") or "").lower() == "defense" or tackles:
            rows.append([jersey, name, pos, tackles, assists, stats.get("sacks", 0), interceptions, stats.get("passesDefended", 0)])
        else:
            rows.append([jersey, name, pos, yards, td, stats.get("receptions", 0), stats.get("carries", 0), interceptions])
    return rows
