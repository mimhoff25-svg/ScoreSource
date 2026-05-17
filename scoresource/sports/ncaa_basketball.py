from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

from ..common.paths import cache_dir

SPORT = "ncaa_basketball"
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event={game_id}"
HEADERS = {"User-Agent": "ScoreSource/1.0", "Referer": "https://www.espn.com"}



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
    return cache_dir()


TEAM_PRIMARY_COLORS: Dict[str, str] = {}
TEAM_SECONDARY_COLORS: Dict[str, str] = {}
TEAM_ACCENT_COLORS: Dict[str, str] = {}
TEAM_ALT_COLORS: Dict[str, str] = {}
TEAM_COLORS = TEAM_PRIMARY_COLORS
sport_table_headers = ["#", "Player", "Min", "Pos", "Pts", "Reb", "Ast", "3PT"]

_scoreboard_cache: Dict[str, Any] = {"ts": 0.0, "data": None}
_boxscore_cache: Dict[str, Tuple[float, float, Dict[str, Any]]] = {}

SCOREBOARD_TTL = _env_float("SCORESOURCE_NCAA_BASKETBALL_SCOREBOARD_TTL", 15.0, min_value=0.0)
BOXSCORE_TTL_LIVE = _env_float("SCORESOURCE_NCAA_BASKETBALL_BOXSCORE_TTL_LIVE", 6.0, min_value=0.0)
BOXSCORE_TTL_PREGAME = _env_float("SCORESOURCE_NCAA_BASKETBALL_BOXSCORE_TTL_PREGAME", 30.0, min_value=0.0)
BOXSCORE_TTL_FINAL = _env_float("SCORESOURCE_NCAA_BASKETBALL_BOXSCORE_TTL_FINAL", 300.0, min_value=0.0)
SCOREBOARD_TIMEOUT_SEC = _env_float("SCORESOURCE_NCAA_BASKETBALL_SCOREBOARD_TIMEOUT_SEC", 6.0, min_value=1.0)
SUMMARY_TIMEOUT_SEC = _env_float("SCORESOURCE_NCAA_BASKETBALL_SUMMARY_TIMEOUT_SEC", 7.0, min_value=1.0)
LOGO_TIMEOUT_SEC = _env_float("SCORESOURCE_NCAA_BASKETBALL_LOGO_TIMEOUT_SEC", 4.0, min_value=1.0)

CACHE_ROOT = _cache_root_from_env()
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
SCOREBOARD_CACHE_PATH = CACHE_ROOT / f"{SPORT}_scoreboard.json"
BOXSCORE_CACHE_DIR = CACHE_ROOT / f"{SPORT}_boxscores"
BOXSCORE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOGO_VERSION = "2026-03"
LOGO_DIR = CACHE_ROOT / "logos" / SPORT
LOGO_DIR.mkdir(parents=True, exist_ok=True)
_logo_cache: Dict[Tuple[str, str, str], bytes | None] = {}
_logo_url_map: Dict[str, str] = {}
_session = requests.Session()



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
    text = hex_color.lstrip("#")
    if len(text) != 6:
        return hex_color
    values = [int(text[i : i + 2], 16) for i in (0, 2, 4)]
    scaled = [min(255, max(0, int(value * factor))) for value in values]
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



def _seed_colors_from_games(games: List[Dict[str, Any]]) -> None:
    for game in games:
        if not isinstance(game, dict):
            continue
        for key in ("homeTeam", "awayTeam"):
            team = game.get(key)
            if not isinstance(team, dict):
                continue
            tri = (team.get("teamTricode") or team.get("abbreviation") or "").upper()
            if tri:
                _register_team_colors(
                    tri,
                    {
                        "color": team.get("teamColor") or team.get("color"),
                        "alternateColor": team.get("teamAltColor") or team.get("alternateColor"),
                    },
                )



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
        seconds = int(float(match.group(2) or 0))
        return f"{minutes}:{seconds:02d}"
    return clock_raw



def format_time_played(value: Any) -> str:
    if value in (None, "", 0):
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        if ":" in text:
            return text
        if text.isdigit():
            return text
        match = re.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", text)
        if match:
            minutes = int(match.group(1) or 0)
            seconds = int(float(match.group(2) or 0))
            return f"{minutes}:{seconds:02d}"
        return text
    try:
        minutes = int(float(value))
    except Exception:
        return str(value or "")
    return str(minutes)



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
    value = team.get("score")
    if value in (None, ""):
        value = team.get("points") or team.get("scoreTotal")
    try:
        return int(value)
    except Exception:
        return int(value or 0)



def _extract_start_time_text(game: Dict[str, Any]) -> str:
    from ..common.timefmt import format_start_time, normalize_espn_time_str

    status_text = (game.get("gameStatusText") or game.get("statusText") or "").strip()
    if status_text and any(token in status_text.upper() for token in ("AM", "PM")):
        normalized = normalize_espn_time_str(status_text)
        if normalized:
            return normalized
    start_time = game.get("gameTimeUTC") or game.get("startTime") or game.get("date")
    if isinstance(start_time, str) and start_time:
        result = format_start_time(start_time)
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
    data = _load_json(BOXSCORE_CACHE_DIR / f"{game_id}.json")
    return data if isinstance(data, dict) else None



def _save_disk_boxscore(game_id: str, payload: Dict[str, Any]) -> None:
    _save_json(BOXSCORE_CACHE_DIR / f"{game_id}.json", payload)



def _fetch_json(url: str, *, timeout: float) -> Dict[str, Any] | None:
    try:
        resp = _session.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None



def _status_from_state(state: str | None) -> str:
    if state == "post":
        return "final"
    if state == "pre":
        return "upcoming"
    return "live"



def _status_value(state: str | None) -> int:
    normalized = _status_from_state(state)
    if normalized == "final":
        return 3
    if normalized == "upcoming":
        return 1
    return 2



def _event_note(comp: Dict[str, Any], event: Dict[str, Any]) -> str:
    for container in (comp.get("notes"), event.get("notes")):
        if not isinstance(container, list):
            continue
        for note in container:
            if not isinstance(note, dict):
                continue
            headline = str(note.get("headline") or note.get("text") or "").strip()
            if headline:
                return headline
    return ""



def _event_group_names(comp: Dict[str, Any]) -> tuple[str, str]:
    groups = comp.get("groups")
    if isinstance(groups, dict):
        name = str(groups.get("name") or "").strip()
        short_name = str(groups.get("shortName") or name or "").strip()
        return name, short_name
    return "", ""



def _event_bucket(note: str, group_short: str, group_name: str) -> str:
    if note:
        return note.split(" - ", 1)[0].strip() or group_short or group_name or "NCAA Basketball"
    return group_short or group_name or "NCAA Basketball"



def _event_stage(note: str) -> str:
    if " - " not in note:
        return ""
    return note.split(" - ", 1)[1].strip()



def _is_march_date(raw: Any) -> bool:
    text = str(raw or "").strip()
    if not text:
        return False
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        month = datetime.fromisoformat(text).month
    except Exception:
        return "-03-" in text
    return month == 3



def _event_meta(comp: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    note = _event_note(comp, event)
    group_name, group_short = _event_group_names(comp)
    bucket = _event_bucket(note, group_short, group_name)
    stage = _event_stage(note)
    lowered = note.lower()
    is_tournament = bool(comp.get("tournamentId")) or any(
        token in lowered
        for token in (
            "tournament",
            "championship",
            "quarterfinal",
            "quarterfinals",
            "semifinal",
            "semifinals",
            "sweet 16",
            "elite eight",
            "final four",
            "first four",
            "round of",
        )
    )
    is_march_madness = bool(
        "march madness" in lowered
        or "ncaa tournament" in lowered
        or (is_tournament and _is_march_date(event.get("date") or comp.get("date")))
    )
    return {
        "eventNote": note,
        "eventBucket": bucket,
        "eventStage": stage,
        "groupName": group_name,
        "groupShortName": group_short,
        "tournamentId": str(comp.get("tournamentId") or "").strip(),
        "isTournament": is_tournament,
        "isMarchMadness": is_march_madness,
    }



def _record_summary(raw: Dict[str, Any]) -> str:
    records = raw.get("records") or []
    if not isinstance(records, list):
        return ""
    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get("type") or "").lower() in {"total", "overall", "record"}:
            return str(record.get("summary") or "").strip()
    for record in records:
        if not isinstance(record, dict):
            continue
        summary = str(record.get("summary") or "").strip()
        if summary:
            return summary
    return ""



def _map_team(comp: Dict[str, Any], side: str) -> Dict[str, Any]:
    competitors = comp.get("competitors") or []
    raw = next((entry for entry in competitors if entry.get("homeAway") == side), {})
    team = raw.get("team") or {}
    tri = (team.get("abbreviation") or team.get("shortDisplayName") or team.get("displayName") or "TM").upper()
    team_id = str(team.get("id") or "")
    primary, secondary = _register_team_colors(tri, team)
    logos = team.get("logos") or []
    logo = team.get("logo") or ((logos[0] if logos else {}) or {}).get("href")
    if logo:
        _logo_url_map[team_id or tri] = logo
        _logo_url_map[tri] = logo
    rank = None
    curated_rank = raw.get("curatedRank") or {}
    try:
        current_rank = int(curated_rank.get("current"))
        if 0 < current_rank < 99:
            rank = current_rank
    except Exception:
        rank = None
    return {
        "teamId": team_id,
        "teamName": team.get("displayName") or team.get("name") or "Team",
        "teamCity": team.get("location") or team.get("shortDisplayName") or "",
        "nickname": team.get("name") or team.get("nickname") or "",
        "teamTricode": tri,
        "score": int(raw.get("score") or 0),
        "teamColor": primary,
        "teamAltColor": secondary,
        "record": _record_summary(raw),
        "recordShort": _record_summary(raw),
        "rank": rank,
        "logoUrl": logo,
        "players": [],
        "statistics": {},
    }



def _status_text(state: str | None, raw_text: str, *, start_time: Any, period: int, clock: Any) -> str:
    if state == "pre":
        return _extract_start_time_text({"gameTimeUTC": start_time, "gameStatusText": raw_text})
    if state == "post":
        return raw_text or "Final"
    if raw_text and "halftime" in raw_text.lower():
        return "Halftime"
    if period == 1:
        label = "1st Half"
    elif period == 2:
        label = "2nd Half"
    elif period == 3:
        label = "OT"
    elif period > 3:
        label = f"OT{period - 2}"
    else:
        label = "Live"
    clock_text = format_clock(clock)
    if clock_text and clock_text != "--:--":
        return f"{label} {clock_text}".strip()
    return raw_text or label



def _game_from_event(event: Dict[str, Any]) -> Dict[str, Any]:
    comp = (event.get("competitions") or [{}])[0] if isinstance(event.get("competitions"), list) else {}
    status = event.get("status") or comp.get("status") or {}
    status_type = status.get("type") or {}
    state = status_type.get("state")
    period = int(status.get("period") or 0)
    clock = status.get("displayClock") or status.get("clock")
    start_time = event.get("date") or comp.get("date")
    home = _map_team(comp, "home")
    away = _map_team(comp, "away")
    meta = _event_meta(comp, event)
    game = {
        "gameId": str(event.get("id") or comp.get("id") or ""),
        "homeTeam": home,
        "awayTeam": away,
        "gameStatus": _status_value(state),
        "status": _status_from_state(state),
        "gameStatusText": _status_text(
            state,
            str(status_type.get("shortDetail") or status_type.get("detail") or "").strip(),
            start_time=start_time,
            period=period,
            clock=clock,
        ),
        "period": {"current": period} if period else {},
        "gameClock": clock,
        "gameTimeUTC": start_time,
        "startTime": start_time,
        "neutralSite": bool(comp.get("neutralSite")),
        "conferenceCompetition": bool(comp.get("conferenceCompetition")),
        "seasonType": (event.get("season") or {}).get("type"),
    }
    game.update(meta)
    return game



def _build_line(game: Dict[str, Any]) -> str:
    home = game.get("homeTeam") or {}
    away = game.get("awayTeam") or {}
    return (
        f"{away.get('teamName', 'Away')} {safe_score(away)} @ "
        f"{home.get('teamName', 'Home')} {safe_score(home)} "
        f"({game.get('gameStatusText') or 'Scheduled'})"
    )



def _normalize_game_for_tests(game: Dict[str, Any]) -> Dict[str, Any]:
    home = game.get("homeTeam") or {}
    away = game.get("awayTeam") or {}
    return {
        "gameId": str(game.get("gameId") or ""),
        "sport": SPORT,
        "status": game.get("gameStatus"),
        "home": home.get("teamName") or "Home",
        "away": away.get("teamName") or "Away",
        "homeTricode": home.get("teamTricode") or "",
        "awayTricode": away.get("teamTricode") or "",
        "homeScore": safe_score(home),
        "awayScore": safe_score(away),
        "startTime": game.get("gameTimeUTC") or game.get("startTime"),
        "period": game.get("period") or {},
        "clock": format_clock(game.get("gameClock")),
        "shotClock": "--",
        "eventNote": game.get("eventNote") or "",
        "eventBucket": game.get("eventBucket") or "",
    }



def fetch_live() -> Dict[str, Any]:
    raw = fetch_scores()
    games = [_normalize_game_for_tests(game) for game in (raw.get("games") or []) if isinstance(game, dict)]
    if not games:
        games = [
            {
                "gameId": "0",
                "sport": SPORT,
                "status": 1,
                "home": "Home",
                "away": "Away",
                "homeTricode": "HOME",
                "awayTricode": "AWAY",
                "homeScore": 0,
                "awayScore": 0,
                "startTime": None,
                "period": {},
                "clock": "--:--",
                "shotClock": "--",
                "eventNote": "",
                "eventBucket": "",
            }
        ]
    return {"games": games, "lines": raw.get("lines") or []}



def fetch_schedule() -> Dict[str, Any]:
    return fetch_live()



def fetch_scores() -> Dict[str, Any]:
    now = time.monotonic()
    disk = _load_disk_scoreboard() if _scoreboard_cache.get("data") is None else None
    cached = _scoreboard_cache.get("data")
    if cached and now - _scoreboard_cache.get("ts", 0.0) < SCOREBOARD_TTL:
        _seed_colors_from_games(cached.get("games") or [])
        return cached

    payload = _fetch_json(SCOREBOARD_URL, timeout=SCOREBOARD_TIMEOUT_SEC)
    if not payload:
        if disk:
            _seed_colors_from_games(disk.get("games") or [])
            _scoreboard_cache["data"] = disk
            _scoreboard_cache["ts"] = now
            return disk
        return {"games": [], "lines": ["No games today."]}

    games: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        game = _game_from_event(event)
        game_id = str(game.get("gameId") or "")
        if not game_id or game_id in seen:
            continue
        seen.add(game_id)
        games.append(game)

    lines = [_build_line(game) for game in games] if games else ["No games today."]
    result = {"games": games, "lines": lines}
    _seed_colors_from_games(games)
    _scoreboard_cache["data"] = result
    _scoreboard_cache["ts"] = now
    _save_disk_scoreboard(result)
    return result



def _build_header(game: Dict[str, Any]) -> str:
    status_value = game.get("gameStatus")
    period = game.get("period") or {}
    current = period.get("current") if isinstance(period, dict) else period
    clock = format_clock(game.get("gameClock"))
    status_text = str(game.get("gameStatusText") or "").strip()
    if status_value == 3 or "final" in status_text.lower():
        return status_text or "Final"
    if status_value in (None, 0, 1) or not current:
        return _extract_start_time_text(game)
    if current == 1 and clock == "0:00":
        return "Halftime"
    if current == 1:
        return f"1st Half {clock}".strip()
    if current == 2:
        return f"2nd Half {clock}".strip()
    if current == 3:
        return f"OT {clock}".strip()
    if current > 3:
        return f"OT{current - 2} {clock}".strip()
    return str(game.get("gameStatusText") or "Live")



def _boxscore_ttl_for_status(status: str | None) -> float:
    if status == "final":
        return BOXSCORE_TTL_FINAL
    if status == "upcoming":
        return BOXSCORE_TTL_PREGAME
    return BOXSCORE_TTL_LIVE



def _stat_display_value(entry: Dict[str, Any]) -> str:
    for key in ("displayValue", "value", "formattedValue"):
        value = entry.get(key)
        if value not in (None, ""):
            return str(value)
    return ""



def _normalize_stat_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())



def _team_statistics_map(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    mapped: Dict[str, Any] = {}
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        display = _stat_display_value(entry)
        if not display:
            continue
        keys = [
            entry.get("name"),
            entry.get("abbreviation"),
            entry.get("label"),
        ]
        for raw in keys:
            token = _normalize_stat_name(raw)
            if token:
                mapped[token] = display
        if _normalize_stat_name(entry.get("name")) == "fouls":
            mapped["teamFouls"] = display
            mapped["foulsPersonal"] = display
            mapped["foulsTeam"] = display
            mapped["personalFouls"] = display
    return mapped



def _split_full_name(full_name: str) -> tuple[str, str]:
    text = str(full_name or "").strip()
    if not text:
        return "", ""
    parts = text.split()
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]



def _parse_number(value: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"-?\d+", text):
        try:
            return int(text)
        except Exception:
            return text
    if re.fullmatch(r"-?\d+\.\d+", text):
        try:
            return float(text)
        except Exception:
            return text
    return text



def _player_statistics_map(labels: List[str], keys: List[str], values: List[Any]) -> Dict[str, Any]:
    mapped: Dict[str, Any] = {}
    for index, raw_value in enumerate(values or []):
        if raw_value in (None, ""):
            continue
        key = keys[index] if index < len(keys) else labels[index] if index < len(labels) else f"stat{index}"
        token = _normalize_stat_name(key)
        parsed = _parse_number(raw_value)
        if token:
            mapped[token] = parsed
    result: Dict[str, Any] = {}
    if "minutes" in mapped:
        result["minutes"] = mapped.get("minutes")
    if "points" in mapped:
        result["points"] = mapped.get("points")
    rebounds = mapped.get("rebounds")
    if rebounds not in (None, ""):
        result["reboundsTotal"] = rebounds
        result["rebounds"] = rebounds
    if "assists" in mapped:
        result["assists"] = mapped.get("assists")
    if "turnovers" in mapped:
        result["turnovers"] = mapped.get("turnovers")
    if "steals" in mapped:
        result["steals"] = mapped.get("steals")
    if "blocks" in mapped:
        result["blocks"] = mapped.get("blocks")
    if "fouls" in mapped:
        result["personalFouls"] = mapped.get("fouls")
    three_pt = mapped.get("threepointfieldgoalsmadethreepointfieldgoalsattempted")
    if isinstance(three_pt, str):
        made = three_pt.split("-", 1)[0].strip()
        if made.isdigit():
            result["threePointFieldGoalsMade"] = int(made)
            result["threePointMade"] = int(made)
    return result



def _parse_players_block(block: Dict[str, Any]) -> List[Dict[str, Any]]:
    players: List[Dict[str, Any]] = []
    order = 0
    for stat_group in block.get("statistics") or []:
        if not isinstance(stat_group, dict):
            continue
        labels = [str(value or "") for value in (stat_group.get("labels") or stat_group.get("names") or [])]
        keys = [str(value or "") for value in (stat_group.get("keys") or labels)]
        for athlete_entry in stat_group.get("athletes") or []:
            if not isinstance(athlete_entry, dict):
                continue
            athlete = athlete_entry.get("athlete") or {}
            full_name = str(athlete.get("displayName") or athlete.get("fullName") or "").strip()
            first_name = str(athlete.get("firstName") or "").strip()
            family_name = str(athlete.get("lastName") or athlete.get("familyName") or "").strip()
            if full_name and (not first_name or not family_name):
                split_first, split_last = _split_full_name(full_name)
                first_name = first_name or split_first
                family_name = family_name or split_last
            stats = _player_statistics_map(labels, keys, athlete_entry.get("stats") or [])
            stats["isOnCourt"] = bool(athlete_entry.get("active"))
            player = {
                "id": str(athlete.get("id") or "").strip(),
                "firstName": first_name,
                "familyName": family_name,
                "displayName": full_name,
                "fullName": full_name,
                "jerseyNum": str(athlete.get("jersey") or "").strip(),
                "position": (
                    (athlete.get("position") or {}).get("abbreviation")
                    or (athlete.get("position") or {}).get("displayName")
                    or ""
                ),
                "starter": bool(athlete_entry.get("starter")),
                "didNotPlay": bool(athlete_entry.get("didNotPlay")),
                "order": order,
                "statistics": stats,
                "athlete": athlete,
            }
            players.append(player)
            order += 1
    return players



def _team_entry_by_side(entries: List[Dict[str, Any]], side: str) -> Dict[str, Any]:
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("homeAway") == side:
            return entry
    return {}



def _players_block_by_team_id(entries: List[Dict[str, Any]], team_id: str) -> Dict[str, Any]:
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        team = entry.get("team") or {}
        if str(team.get("id") or "") == str(team_id or ""):
            return entry
    return {}



def fetch_boxscore(game_id: str) -> Dict[str, Any]:
    now = time.monotonic()
    cached = _boxscore_cache.get(str(game_id))
    if cached and now - cached[0] < cached[1]:
        return cached[2]

    board = _scoreboard_cache.get("data") or _load_disk_scoreboard() or fetch_scores()
    board_games = board.get("games") or [] if isinstance(board, dict) else []
    scoreboard_game = next((game for game in board_games if str(game.get("gameId") or "") == str(game_id)), None)

    payload = _fetch_json(SUMMARY_URL.format(game_id=game_id), timeout=SUMMARY_TIMEOUT_SEC)
    if not payload:
        if scoreboard_game:
            result = {
                "game": scoreboard_game,
                "home": scoreboard_game.get("homeTeam") or {},
                "away": scoreboard_game.get("awayTeam") or {},
                "header": _build_header(scoreboard_game),
                "shotclock": "--",
            }
            ttl = _boxscore_ttl_for_status(str(scoreboard_game.get("status") or ""))
            _boxscore_cache[str(game_id)] = (now, ttl, result)
            _save_disk_boxscore(str(game_id), result)
            return result
        disk = _load_disk_boxscore(str(game_id))
        if disk:
            _boxscore_cache[str(game_id)] = (now, BOXSCORE_TTL_PREGAME, disk)
            return disk
        stub = {
            "game": {"gameStatus": 1, "status": "upcoming", "gameStatusText": "Scheduled", "period": {}},
            "home": {"teamName": "Home", "teamTricode": "HOME", "score": 0, "players": []},
            "away": {"teamName": "Away", "teamTricode": "AWAY", "score": 0, "players": []},
            "header": "No data",
            "shotclock": "--",
        }
        _boxscore_cache[str(game_id)] = (now, BOXSCORE_TTL_PREGAME, stub)
        return stub

    header = payload.get("header") or {}
    competition = (header.get("competitions") or [{}])[0] if isinstance(header.get("competitions"), list) else {}
    status = competition.get("status") or {}
    status_type = status.get("type") or {}
    state = status_type.get("state")
    period = int(status.get("period") or 0)
    clock = status.get("displayClock") or status.get("clock")
    start_time = competition.get("date") or (scoreboard_game or {}).get("gameTimeUTC")

    away = _map_team(competition, "away")
    home = _map_team(competition, "home")
    team_entries = (payload.get("boxscore") or {}).get("teams") or []
    player_blocks = (payload.get("boxscore") or {}).get("players") or []

    away_stats_entry = _team_entry_by_side(team_entries, "away")
    home_stats_entry = _team_entry_by_side(team_entries, "home")
    away_players_block = _players_block_by_team_id(player_blocks, away.get("teamId") or "")
    home_players_block = _players_block_by_team_id(player_blocks, home.get("teamId") or "")

    away["statistics"] = _team_statistics_map(away_stats_entry.get("statistics") or [])
    home["statistics"] = _team_statistics_map(home_stats_entry.get("statistics") or [])
    away["players"] = _parse_players_block(away_players_block) if away_players_block else []
    home["players"] = _parse_players_block(home_players_block) if home_players_block else []

    game = dict(scoreboard_game or {})
    game.update(
        {
            "gameId": str(game_id),
            "homeTeam": home,
            "awayTeam": away,
            "gameStatus": _status_value(state),
            "status": _status_from_state(state),
            "gameStatusText": _status_text(
                state,
                str(status_type.get("shortDetail") or status_type.get("detail") or "").strip(),
                start_time=start_time,
                period=period,
                clock=clock,
            ),
            "period": {"current": period} if period else {},
            "gameClock": clock,
            "gameTimeUTC": start_time,
            "startTime": start_time,
            "neutralSite": bool(competition.get("neutralSite")),
            "conferenceCompetition": bool(competition.get("conferenceCompetition")),
            "seasonType": (header.get("season") or {}).get("type") or game.get("seasonType"),
        }
    )
    if not game.get("eventNote"):
        game.update(_event_meta(competition, {"date": start_time}))

    result = {
        "game": game,
        "home": home,
        "away": away,
        "header": _build_header(game),
        "shotclock": "--",
    }
    ttl = _boxscore_ttl_for_status(game.get("status"))
    _boxscore_cache[str(game_id)] = (now, ttl, result)
    _save_disk_boxscore(str(game_id), result)
    return result



def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    tri = (tricode or "").upper()
    key = (str(team_id or ""), tri, LOGO_VERSION)
    if key in _logo_cache:
        return _logo_cache[key]

    cache_ext = ".png"
    cache_path = LOGO_DIR / f"{team_id or tri or 'unknown'}-{LOGO_VERSION}{cache_ext}"
    if cache_path.exists():
        try:
            content = cache_path.read_bytes()
        except Exception:
            content = None
        if content:
            _logo_cache[key] = content
            return content

    urls: List[str] = []
    for token in filter(None, [str(team_id or ""), tri]):
        mapped_url = _logo_url_map.get(token)
        if mapped_url:
            urls.append(mapped_url)
    if team_id and str(team_id) not in {"0", "AWY", "HOM"}:
        urls.append(f"https://a.espncdn.com/i/teamlogos/ncaa/500/{team_id}.png")
    if tri:
        urls.append(f"https://a.espncdn.com/i/teamlogos/ncaa/500/{tri.lower()}.png")

    for url in urls:
        try:
            resp = _session.get(url, headers=HEADERS, timeout=LOGO_TIMEOUT_SEC)
            resp.raise_for_status()
            content = resp.content
        except Exception:
            continue
        try:
            cache_path.write_bytes(content)
        except Exception:
            pass
        _logo_cache[key] = content
        return content

    _logo_cache[key] = None
    return None
