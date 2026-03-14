from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

from ..common.timefmt import format_start_time

SPORT = "mls"
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/summary?event={game_id}"


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

SCOREBOARD_TTL = _env_float("SCORESOURCE_MLS_SCOREBOARD_TTL", 15.0, min_value=0.0)
BOXSCORE_TTL = _env_float("SCORESOURCE_MLS_BOXSCORE_TTL", 12.0, min_value=0.0)
SCOREBOARD_TIMEOUT_SEC = _env_float("SCORESOURCE_MLS_SCOREBOARD_TIMEOUT_SEC", 5.0, min_value=1.0)
LOGO_TIMEOUT_SEC = _env_float("SCORESOURCE_MLS_LOGO_TIMEOUT_SEC", 3.0, min_value=1.0)

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

sport_table_headers = ["#", "Player", "Pos", "G", "A", "SOG", "YC", "RC"]


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


def format_clock(clock_raw: Any) -> str:
    if not clock_raw:
        return "--:--"
    if isinstance(clock_raw, (int, float)):
        minutes = int(clock_raw // 60)
        seconds = int(clock_raw % 60)
        return f"{minutes}:{seconds:02d}"
    if not isinstance(clock_raw, str):
        return str(clock_raw)
    text = clock_raw.strip()
    if not text:
        return "--:--"
    if text.endswith("'"):
        return text
    if ":" in text:
        return text
    match = re.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", text)
    if match:
        minutes = int(match.group(1) or 0)
        seconds_val = float(match.group(2) or 0)
        seconds = int(seconds_val)
        return f"{minutes}:{seconds:02d}"
    return text


def format_time_played(value: Any) -> str:
    if value in (None, "", 0):
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


def _game_status_int_from_value(value: Any) -> int:
    if isinstance(value, int):
        if value in (1, 2, 3):
            return value
        return 2
    text = str(value or "").strip().lower()
    if text in ("final", "post"):
        return 3
    if text in ("upcoming", "pre", "scheduled"):
        return 1
    if text in ("live", "in", "in_progress"):
        return 2
    return 2


def _coerce_cached_game_shape(game: Dict[str, Any]) -> Dict[str, Any]:
    # Accept cache data written by either canonical or normalized MLS paths.
    status_int = _game_status_int_from_value(game.get("gameStatus") if "gameStatus" in game else game.get("status"))
    period = game.get("period")
    if isinstance(period, int):
        period = {"current": period} if period else {}
    elif not isinstance(period, dict):
        period = {}
    status_text = game.get("gameStatusText") or game.get("header") or ""
    return {
        **game,
        "gameStatus": status_int,
        "gameStatusText": status_text,
        "period": period,
        "gameClockText": game.get("gameClockText") or (game.get("gameClock") if isinstance(game.get("gameClock"), str) else ""),
        "gameTimeUTC": game.get("gameTimeUTC") or game.get("startTime") or game.get("date"),
    }


def _coerce_cached_scoreboard_shape(payload: Dict[str, Any]) -> Dict[str, Any]:
    games = payload.get("games")
    if not isinstance(games, list):
        return payload
    normalized_games: List[Dict[str, Any]] = []
    for game in games:
        if not isinstance(game, dict):
            continue
        normalized_games.append(_coerce_cached_game_shape(game))
    return {"games": normalized_games, "lines": payload.get("lines") or []}


def _extract_start_time_text(g: Dict[str, Any]) -> str:
    from ..common.timefmt import format_start_time, normalize_espn_time_str
    status_text = (g.get("gameStatusText") or g.get("statusText") or "").strip()
    iso_val = g.get("gameTimeUTC") or g.get("startTime") or g.get("date")
    formatted = format_start_time(iso_val)
    if formatted != "Starts TBA":
        return formatted
    if status_text and any(x in status_text.upper() for x in ("AM", "PM")):
        normalized = normalize_espn_time_str(status_text)
        if normalized:
            return normalized
    return status_text or "Scheduled"


def _period_from_status(text: str | None) -> int | None:
    if not text:
        return None
    upper = text.upper()
    if "1ST" in upper or "FIRST" in upper or "1H" in upper:
        return 1
    if "2ND" in upper or "SECOND" in upper or "2H" in upper:
        return 2
    if "ET" in upper or "EXTRA" in upper or "AET" in upper:
        return 3
    if "PEN" in upper or "PK" in upper or "SHOOT" in upper:
        return 4
    if "HALF" in upper or "HT" in upper:
        return 1
    return None


def _period_label(period: int | None, status_text: str | None) -> str:
    text = (status_text or "").upper()
    if "PEN" in text or "PK" in text or "SHOOT" in text:
        return "PK"
    if "ET" in text or "AET" in text or "EXTRA" in text:
        return "ET"
    if "HALF" in text or text == "HT":
        return "HT"
    if period == 1:
        return "1H"
    if period == 2:
        return "2H"
    if period and period > 2:
        return "ET"
    return ""


def _coerce_number(value: Any) -> int | float | str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return ""
    try:
        number = float(text)
    except Exception:
        return text
    if number.is_integer():
        return int(number)
    return number


def _record_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    for rec in records:
        if not isinstance(rec, dict):
            continue
        summary = rec.get("summary") or rec.get("displayValue") or rec.get("shortDisplayName")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    return ""


def _record_tuple(summary: str | None) -> tuple[int, int, int | None] | None:
    if not summary:
        return None
    parts = re.findall(r"\d+", str(summary))
    if len(parts) < 2:
        return None
    try:
        wins = int(parts[0])
        losses = int(parts[1])
        draws = int(parts[2]) if len(parts) >= 3 else None
    except Exception:
        return None
    return wins, losses, draws


def _set_record_fields(mapped: Dict[str, Any], summary: str) -> None:
    if not summary:
        return
    mapped["record"] = summary
    mapped["recordSummary"] = summary
    record_tuple = _record_tuple(summary)
    if not record_tuple:
        return
    mapped["wins"] = record_tuple[0]
    mapped["losses"] = record_tuple[1]
    if record_tuple[2] is not None:
        mapped["draws"] = record_tuple[2]
        mapped["ties"] = record_tuple[2]


def _team_logo(team: Dict[str, Any]) -> str:
    logos = team.get("logos")
    if isinstance(logos, list):
        for entry in logos:
            href = entry.get("href") if isinstance(entry, dict) else None
            if href:
                return str(href)
    return str(team.get("logo") or "")


def _apply_team_identity(target: Dict[str, Any], team: Dict[str, Any]) -> None:
    if not isinstance(team, dict):
        return
    tri = (team.get("abbreviation") or team.get("shortDisplayName") or target.get("teamTricode") or "TM").upper()
    tid = str(team.get("id") or target.get("teamId") or "")
    primary, secondary = _register_team_colors(tri, team)
    target["teamId"] = tid
    target["teamName"] = team.get("displayName") or team.get("name") or target.get("teamName") or "Team"
    target["teamTricode"] = tri
    target["teamCity"] = team.get("location") or target.get("teamCity") or target.get("teamName") or ""
    target["nickname"] = team.get("nickname") or team.get("shortDisplayName") or target.get("nickname") or ""
    if primary:
        target["teamColor"] = primary
    if secondary:
        target["teamAltColor"] = secondary
    logo = _team_logo(team)
    if logo:
        target["teamLogo"] = logo
        _logo_url_map[tid or tri] = logo
        _logo_url_map[tri] = logo


def _apply_team_statistics(target: Dict[str, Any], stats: Any) -> None:
    if not isinstance(stats, list):
        return
    stat_map: Dict[str, Any] = dict(target.get("statistics") or {})
    for entry in stats:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        raw = entry.get("displayValue")
        if raw in (None, ""):
            raw = entry.get("value")
        value = _coerce_number(raw)
        stat_map[name] = value
    if "shotsOnGoal" not in stat_map and "shotsOnTarget" in stat_map:
        stat_map["shotsOnGoal"] = stat_map["shotsOnTarget"]
    if "shots" not in stat_map and "totalShots" in stat_map:
        stat_map["shots"] = stat_map["totalShots"]
    target["statistics"] = stat_map
    for key in (
        "shotsOnGoal",
        "shotsOnTarget",
        "shots",
        "totalShots",
        "yellowCards",
        "redCards",
        "wonCorners",
        "offsides",
        "possessionPct",
        "goalAssists",
        "goalsConceded",
        "saves",
    ):
        if key in stat_map:
            target[key] = stat_map[key]


def _player_stat_map(stats: Any) -> Dict[str, Any]:
    stat_map: Dict[str, Any] = {}
    if not isinstance(stats, list):
        return stat_map
    for entry in stats:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        raw = entry.get("displayValue")
        if raw in (None, ""):
            raw = entry.get("value")
        stat_map[name] = _coerce_number(raw)
    return stat_map


def _roster_sort_key(player: Dict[str, Any]) -> tuple[int, int, int, int, str]:
    starter_rank = 0 if player.get("starter") else 1
    active_rank = 0 if player.get("active", True) else 1
    formation_place = player.get("formationPlace")
    try:
        formation_rank = int(str(formation_place).strip())
    except Exception:
        formation_rank = 999
    sub_rank = 0 if player.get("subbedIn") else 1
    athlete = player.get("athlete") if isinstance(player.get("athlete"), dict) else {}
    name = str(
        player.get("fullName")
        or player.get("displayName")
        or athlete.get("fullName")
        or athlete.get("displayName")
        or ""
    )
    return starter_rank, formation_rank, sub_rank, active_rank, name


def _map_roster_player(entry: Dict[str, Any]) -> Dict[str, Any]:
    athlete = entry.get("athlete") if isinstance(entry.get("athlete"), dict) else {}
    position = entry.get("position")
    if isinstance(position, dict):
        position_abbr = position.get("abbreviation") or position.get("shortDisplayName") or position.get("displayName")
    else:
        position_abbr = position
    stats = _player_stat_map(entry.get("stats"))
    mapped = {
        "id": str(athlete.get("id") or ""),
        "playerId": str(athlete.get("id") or ""),
        "athleteId": str(athlete.get("id") or ""),
        "athlete": athlete,
        "displayName": athlete.get("displayName") or athlete.get("shortName") or "",
        "fullName": athlete.get("fullName") or athlete.get("displayName") or "",
        "familyName": athlete.get("lastName") or "",
        "jerseyNum": str(entry.get("jersey") or ""),
        "jersey": str(entry.get("jersey") or ""),
        "position": str(position_abbr or ""),
        "statistics": stats,
        "starter": bool(entry.get("starter")),
        "subbedIn": bool(entry.get("subbedIn")),
        "subbedOut": bool(entry.get("subbedOut")),
        "active": bool(entry.get("active", True)),
        "formationPlace": entry.get("formationPlace"),
    }
    headshot = athlete.get("headshot") if isinstance(athlete.get("headshot"), dict) else {}
    if headshot.get("href"):
        mapped["headshotUrl"] = headshot.get("href")
    return mapped


def _apply_roster_team(target: Dict[str, Any], roster_entry: Dict[str, Any]) -> None:
    if not isinstance(roster_entry, dict):
        return
    _apply_team_identity(target, roster_entry.get("team") or {})
    formation = roster_entry.get("formation")
    if formation:
        target["formation"] = str(formation)
    roster = roster_entry.get("roster")
    if not isinstance(roster, list) or not roster:
        return
    players = [_map_roster_player(entry) for entry in roster if isinstance(entry, dict)]
    players = [player for player in players if player.get("playerId") or player.get("fullName") or player.get("displayName")]
    if not players:
        return
    players.sort(key=_roster_sort_key)
    target["players"] = players
    starters = [player for player in players if player.get("starter")]
    if starters:
        target["startingLineup"] = starters


def _summary_status_payload(
    comp: Dict[str, Any],
    fallback_game: Dict[str, Any] | None = None,
) -> tuple[int, str, int | None, Any, str]:
    fallback_game = fallback_game or {}
    status = comp.get("status") if isinstance(comp, dict) else {}
    status_type = status.get("type") if isinstance(status, dict) else {}
    state = str(status_type.get("state") or "").strip().lower()
    detail = str(status_type.get("shortDetail") or status_type.get("detail") or "").strip()
    period = status.get("period")
    if period is None:
        fallback_period = fallback_game.get("period")
        if isinstance(fallback_period, dict):
            period = fallback_period.get("current")
        elif isinstance(fallback_period, int):
            period = fallback_period
    if period is None:
        period = _period_from_status(detail)
    clock_display = str(
        status.get("displayClock")
        or status_type.get("statusPrimary")
        or fallback_game.get("gameClockText")
        or ""
    )
    clock = status.get("clock")
    if clock in (None, ""):
        clock = fallback_game.get("gameClock")
    if clock in (None, ""):
        clock = clock_display
    if state == "pre":
        status_int = 1
        status_text = _extract_start_time_text(
            {
                "date": comp.get("date") or fallback_game.get("gameTimeUTC"),
                "gameStatusText": detail,
            }
        )
        clock = ""
        clock_display = ""
    elif state == "post":
        status_int = 3
        status_text = detail or "FT"
        clock = ""
        clock_display = ""
    else:
        status_int = 2
        lowered = detail.lower()
        if lowered in ("ht", "halftime", "half time"):
            status_text = "HT"
            clock = ""
            clock_display = ""
        else:
            status_text = detail or clock_display or format_clock(clock) or "Live"
    return status_int, status_text, period, clock, clock_display


def _merge_summary_team(base: Dict[str, Any], comp_entry: Dict[str, Any] | None, box_entry: Dict[str, Any] | None) -> Dict[str, Any]:
    team = dict(base or {})
    if isinstance(comp_entry, dict):
        _apply_team_identity(team, comp_entry.get("team") or {})
        summary = _record_summary(comp_entry.get("records"))
        if summary:
            _set_record_fields(team, summary)
        score = comp_entry.get("score")
        if score not in (None, ""):
            try:
                team["score"] = int(score)
            except Exception:
                team["score"] = safe_score({"score": score})
        if comp_entry.get("winner") is not None:
            team["winner"] = bool(comp_entry.get("winner"))
        form = comp_entry.get("form")
        if form:
            team["form"] = form
        _apply_team_statistics(team, comp_entry.get("statistics"))
    if isinstance(box_entry, dict):
        _apply_team_identity(team, box_entry.get("team") or {})
        _apply_team_statistics(team, box_entry.get("statistics"))
    team.setdefault("players", [])
    return team


def _fetch_summary_payload(game_id: str) -> Dict[str, Any] | None:
    try:
        resp = _logo_session.get(SUMMARY_URL.format(game_id=game_id), timeout=SCOREBOARD_TIMEOUT_SEC)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


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
            urls.append(f"https://a.espncdn.com/i/teamlogos/soccer/500/{team_id}.png")
        if tc:
            urls.append(f"https://a.espncdn.com/i/teamlogos/soccer/500/{tc.lower()}.png")

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
    mapped: Dict[str, Any] = {
        "teamId": str(team.get("id") or ""),
        "teamName": team.get("displayName") or team.get("name") or "Team",
        "teamTricode": tri,
        "score": safe_score(raw),
        "players": [],
    }
    _apply_team_identity(mapped, team)
    summary = _record_summary(raw.get("records"))
    if summary:
        _set_record_fields(mapped, summary)
    _apply_team_statistics(mapped, raw.get("statistics"))
    return mapped


def _build_line(g: Dict[str, Any]) -> str:
    home = g.get("homeTeam", {}) or {}
    away = g.get("awayTeam", {}) or {}
    hs = safe_score(home)
    as_ = safe_score(away)
    status = g.get("gameStatusText") or "Scheduled"
    return f"{away.get('teamName','Away')} {as_} @ {home.get('teamName','Home')} {hs} ({status})"


def fetch_scores() -> Dict[str, Any]:
    now = time.monotonic()
    cached = _scoreboard_cache.get("data")
    if cached and now - _scoreboard_cache.get("ts", 0) < SCOREBOARD_TTL:
        return cached

    try:
        resp = _logo_session.get(SCOREBOARD_URL, timeout=SCOREBOARD_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        disk = _load_disk_scoreboard()
        if disk:
            result = _coerce_cached_scoreboard_shape(disk)
            _seed_colors_from_games(result.get("games", []) or [])
            _scoreboard_cache["data"] = result
            _scoreboard_cache["ts"] = now
            return result
        if cached:
            return cached
        return {"games": [], "lines": ["No matches scheduled."]}

    events = data.get("events", []) or []
    games: List[Dict[str, Any]] = []
    for ev in events:
        comp = (ev.get("competitions") or [{}])[0]
        status = ev.get("status") or {}
        status_type = status.get("type") or {}
        state = status_type.get("state")
        period = status.get("period")
        clock_display = status.get("displayClock") or ""
        clock = status.get("clock")
        if clock in (None, ""):
            clock = clock_display
        start_time = ev.get("date")
        status_text_raw = status_type.get("shortDetail") or status_type.get("detail")
        if period is None:
            period = _period_from_status(status_text_raw)
        home = _map_team(comp, "home")
        away = _map_team(comp, "away")

        if state == "pre":
            game_status = 1
            status_text = _extract_start_time_text({"date": start_time, "gameStatusText": status_text_raw})
            clock = ""
            clock_display = ""
        elif state == "post":
            game_status = 3
            status_text = status_text_raw or "Final"
            clock = ""
            clock_display = ""
        else:
            game_status = 2
            lowered = (status_text_raw or "").lower()
            if lowered in ("ht", "halftime", "half time"):
                status_text = "HT"
                clock = ""
                clock_display = ""
            else:
                status_text = status_text_raw or clock_display or "Live"

        game = {
            "gameId": str(ev.get("id")),
            "homeTeam": home,
            "awayTeam": away,
            "gameStatus": game_status,
            "gameStatusText": status_text,
            "period": {"current": period} if period else {},
            "gameClock": clock,
            "gameClockText": clock_display,
            "gameTimeUTC": start_time,
            "seasonYear": str(ev.get("season", {}).get("year") or "2025"),
        }
        games.append(game)

    lines = [_build_line(g) for g in games] if games else ["No matches scheduled."]
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
    clock = game.get("gameClockText") or format_clock(game.get("gameClock"))
    status_text = (game.get("gameStatusText") or "").strip()

    if status_value == 3:
        return status_text or "Final"
    if status_value in (None, 0, 1) or not current:
        return _extract_start_time_text(game)
    label = _period_label(current if isinstance(current, int) else None, status_text)
    return f"{label} {clock}".strip() if (label or clock) else (status_text or "Live")


def fetch_boxscore(game_id: str) -> Dict[str, Any]:
    now = time.monotonic()
    cached = _boxscore_cache.get(game_id)
    if cached and now - cached[0] < BOXSCORE_TTL:
        return cached[1]

    board = _scoreboard_cache.get("data") or fetch_scores()
    games = board.get("games", []) if isinstance(board, dict) else []
    game = next((g for g in games if str(g.get("gameId")) == str(game_id)), None)
    summary = _fetch_summary_payload(game_id)
    if summary:
        comp = ((summary.get("header") or {}).get("competitions") or [{}])[0]
        boxscore = summary.get("boxscore") or {}
        team_entries = boxscore.get("teams") or []
        home_comp = next((entry for entry in (comp.get("competitors") or []) if entry.get("homeAway") == "home"), None)
        away_comp = next((entry for entry in (comp.get("competitors") or []) if entry.get("homeAway") == "away"), None)
        home_box = next((entry for entry in team_entries if entry.get("homeAway") == "home"), None)
        away_box = next((entry for entry in team_entries if entry.get("homeAway") == "away"), None)
        home = _merge_summary_team((game or {}).get("homeTeam", {}), home_comp, home_box)
        away = _merge_summary_team((game or {}).get("awayTeam", {}), away_comp, away_box)
        for roster_entry in summary.get("rosters") or []:
            if not isinstance(roster_entry, dict):
                continue
            side = roster_entry.get("homeAway")
            if side == "home":
                _apply_roster_team(home, roster_entry)
            elif side == "away":
                _apply_roster_team(away, roster_entry)
        game_payload = dict(game or {})
        status_int, status_text, period, clock, clock_text = _summary_status_payload(comp, game or {})
        game_payload.update(
            {
                "gameId": str(comp.get("id") or game_id),
                "gameStatus": status_int,
                "gameStatusText": status_text,
                "period": {"current": period} if period else {},
                "gameClock": clock,
                "gameClockText": clock_text,
                "gameTimeUTC": comp.get("date") or game.get("gameTimeUTC"),
            }
        )
        header = _build_header(game_payload)
        result = {
            "game": game_payload,
            "home": home,
            "away": away,
            "header": header,
            "shotclock": "--",
        }
        _boxscore_cache[game_id] = (now, result)
        _save_disk_boxscore(game_id, result)
        return result
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
    players = team.get("players") or []
    if isinstance(players, list) and players:
        for player in sorted((entry for entry in players if isinstance(entry, dict)), key=_roster_sort_key):
            stats = player.get("statistics") if isinstance(player.get("statistics"), dict) else {}
            athlete = player.get("athlete") if isinstance(player.get("athlete"), dict) else {}
            name = (
                player.get("fullName")
                or player.get("displayName")
                or athlete.get("fullName")
                or athlete.get("displayName")
                or athlete.get("shortName")
                or ""
            )
            jersey = str(player.get("jerseyNum") or player.get("jersey") or "")
            position = str(player.get("position") or "")
            goals = stats.get("totalGoals", 0)
            assists = stats.get("goalAssists", 0)
            shots_on_target = stats.get("shotsOnTarget", 0)
            yellow_cards = stats.get("yellowCards", 0)
            red_cards = stats.get("redCards", 0)
            rows.append(
                [
                    jersey,
                    str(name),
                    position,
                    str(goals),
                    str(assists),
                    str(shots_on_target),
                    str(yellow_cards),
                    str(red_cards),
                ]
            )
        if rows:
            return rows

    lineup = team.get("startingLineup") or []
    if isinstance(lineup, list):
        for player in lineup:
            if not isinstance(player, dict):
                continue
            athlete = player.get("athlete") if isinstance(player.get("athlete"), dict) else {}
            name = (
                player.get("fullName")
                or player.get("displayName")
                or athlete.get("fullName")
                or athlete.get("displayName")
                or athlete.get("shortName")
                or ""
            )
            jersey = str(player.get("jerseyNum") or player.get("jersey") or "")
            position = str(player.get("position") or "")
            if not (name or jersey or position):
                continue
            rows.append([jersey, str(name), position, "", "", "", "", ""])
    return rows


# Compatibility wrappers expected by the test-suite / external callers
def _normalize_game_for_tests(g: Dict[str, Any]) -> Dict[str, Any]:
    home = (g.get("homeTeam") or {}) or {}
    away = (g.get("awayTeam") or {}) or {}
    game_id = str(g.get("gameId") or g.get("id") or "")
    start_time = g.get("gameTimeUTC") or g.get("startTime") or g.get("date")
    period_field = g.get("period")
    if isinstance(period_field, dict):
        period = period_field.get("current")
    elif isinstance(period_field, int):
        period = period_field
    else:
        period = None
    clock = str(g.get("gameClockText") or format_clock(g.get("gameClock") or g.get("clock")))
    shot = format_shotclock(g.get("shotClock"))
    status_value = g.get("gameStatus")
    if status_value in (None, ""):
        status_value = _game_status_int_from_value(g.get("status"))
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
        "status": status_value,
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
