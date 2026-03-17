from __future__ import annotations

import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

from .common.lineups import apply_starting_lineups
from .common.timefmt import format_start_time
from .common.utils import format_player_initial_name


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


MLB_LEAGUE_PATH = "mlb"
WBC_LEAGUE_PATH = "world-baseball-classic"
SCOREBOARD_URLS: Dict[str, str] = {
    MLB_LEAGUE_PATH: "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
    WBC_LEAGUE_PATH: "https://site.api.espn.com/apis/site/v2/sports/baseball/world-baseball-classic/scoreboard",
}
SUMMARY_URL_TEMPLATE = "https://site.api.espn.com/apis/site/v2/sports/baseball/{league_path}/summary?event={game_id}"
HEADERS = {"User-Agent": "ScoreSource/1.0", "Referer": "https://www.espn.com"}

CACHE_ROOT = _cache_root_from_env()
LOGO_DIR = CACHE_ROOT / "logos" / "mlb"
LOGO_DIR.mkdir(parents=True, exist_ok=True)
LOGO_VERSION = "2026-03-wbc"
_logo_cache: Dict[Tuple[str, str, str], bytes | None] = {}
_session = requests.Session()
_scoreboard_cache: Dict[str, Any] = {"ts": 0.0, "data": None}
_boxscore_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_summary_cache: Dict[str, Tuple[float, int, Dict[str, Any]]] = {}
_roster_number_cache: Dict[str, Tuple[float, Dict[str, str], Dict[str, str]]] = {}
_core_athlete_number_cache: Dict[str, Tuple[float, str]] = {}

SCOREBOARD_TTL = _env_float("SCORESOURCE_MLB_SCOREBOARD_TTL", 15.0, min_value=0.0)
SCOREBOARD_TIMEOUT_SEC = _env_float("SCORESOURCE_MLB_SCOREBOARD_TIMEOUT_SEC", 8.0, min_value=1.0)
SUMMARY_TIMEOUT_SEC = _env_float("SCORESOURCE_MLB_SUMMARY_TIMEOUT_SEC", 7.0, min_value=1.0)
SUMMARY_TTL_LIVE = _env_float("SCORESOURCE_MLB_SUMMARY_TTL_LIVE", 6.0, min_value=0.0)
SUMMARY_TTL_PREGAME = _env_float("SCORESOURCE_MLB_SUMMARY_TTL_PREGAME", 30.0, min_value=0.0)
SUMMARY_TTL_FINAL = _env_float("SCORESOURCE_MLB_SUMMARY_TTL_FINAL", 300.0, min_value=0.0)
BOXSCORE_TTL_LIVE = _env_float("SCORESOURCE_MLB_BOXSCORE_TTL_LIVE", 8.0, min_value=0.0)
BOXSCORE_TTL_PREGAME = _env_float("SCORESOURCE_MLB_BOXSCORE_TTL_PREGAME", 30.0, min_value=0.0)
BOXSCORE_TTL_FINAL = _env_float("SCORESOURCE_MLB_BOXSCORE_TTL_FINAL", 300.0, min_value=0.0)
LOGO_TIMEOUT_SEC = _env_float("SCORESOURCE_MLB_LOGO_TIMEOUT_SEC", 5.0, min_value=1.0)
ROSTER_NUMBER_TTL_SEC = _env_float("SCORESOURCE_MLB_ROSTER_NUMBER_TTL_SEC", 60.0 * 60.0 * 6.0, min_value=0.0)
CORE_ATHLETE_NUMBER_TTL_SEC = _env_float(
    "SCORESOURCE_MLB_CORE_ATHLETE_NUMBER_TTL_SEC", 60.0 * 60.0 * 24.0, min_value=0.0
)
CORE_ATHLETE_TIMEOUT_SEC = _env_float("SCORESOURCE_MLB_CORE_ATHLETE_TIMEOUT_SEC", 2.5, min_value=0.5)
CORE_ATHLETE_MAX_LOOKUPS_PER_TEAM = int(
    _env_float("SCORESOURCE_MLB_CORE_ATHLETE_MAX_LOOKUPS_PER_TEAM", 25.0, min_value=0.0)
)

TEAM_PRIMARY_COLORS: Dict[str, str] = {
    "ARI": "#A71930",
    "ATL": "#13274F",
    "BAL": "#DF4601",
    "BOS": "#BD3039",
    "CHC": "#0E3386",
    "CWS": "#27251F",
    "CIN": "#C6011F",
    "CLE": "#0C2340",
    "COL": "#33006F",
    "DET": "#0C2340",
    "HOU": "#002D62",
    "KC": "#004687",
    "LAA": "#BA0021",
    "LAD": "#005A9C",
    "MIA": "#00A3E0",
    "MIL": "#12284B",
    "MIN": "#002B5C",
    "NYM": "#002D72",
    "NYY": "#0C2340",
    "OAK": "#003831",
    "PHI": "#E81828",
    "PIT": "#FDB827",
    "SD": "#2F241D",
    "SEA": "#005C5C",
    "SF": "#FD5A1E",
    "STL": "#C41E3A",
    "TB": "#092C5C",
    "TEX": "#003278",
    "TOR": "#134A8E",
    "WSH": "#AB0003",
    "HME": "#4E4E4E",
    "AWY": "#2E2E2E",
}


def _scale(hex_color: str, factor: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    vals = [int(h[i : i + 2], 16) for i in (0, 2, 4)]
    scaled = [min(255, max(0, int(v * factor))) for v in vals]
    return "#%02x%02x%02x" % tuple(scaled)


TEAM_SECONDARY_COLORS: Dict[str, str] = {k: _scale(v, 0.65) for k, v in TEAM_PRIMARY_COLORS.items()}
TEAM_ACCENT_COLORS: Dict[str, str] = {k: _scale(v, 1.35) for k, v in TEAM_PRIMARY_COLORS.items()}
TEAM_ALT_COLORS: Dict[str, str] = dict(TEAM_ACCENT_COLORS)
TEAM_COLORS: Dict[str, str] = TEAM_PRIMARY_COLORS
sport_table_headers = ["#", "Player", "Pos", "AVG", "HR", "RBI", "OBP", "SLG"]
TRICODE_ALIASES: Dict[str, str] = {
    "CHW": "CWS",
    "WSN": "WSH",
    "AZ": "ARI",
    "SDP": "SD",
}


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _coerce_stat_value(value: Any) -> Any:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return ""
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def _normalize_player_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text)


def _team_roster_number_maps(team_id: str) -> tuple[Dict[str, str], Dict[str, str]]:
    key = str(team_id or "").strip()
    if not key:
        return {}, {}
    now = time.monotonic()
    cached = _roster_number_cache.get(key)
    if cached and now - cached[0] <= ROSTER_NUMBER_TTL_SEC:
        return dict(cached[1]), dict(cached[2])

    url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams/{key}/roster"
    try:
        resp = _session.get(url, headers=HEADERS, timeout=SUMMARY_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return (dict(cached[1]), dict(cached[2])) if cached else ({}, {})

    athletes = data.get("athletes") or []
    items: List[Dict[str, Any]] = []
    if isinstance(athletes, list):
        for entry in athletes:
            if not isinstance(entry, dict):
                continue
            grouped = entry.get("items")
            if isinstance(grouped, list):
                for athlete in grouped:
                    if isinstance(athlete, dict):
                        items.append(athlete)
                continue
            items.append(entry)

    by_id: Dict[str, str] = {}
    by_name: Dict[str, str] = {}
    for athlete in items:
        jersey = athlete.get("jersey") or athlete.get("jerseyNum") or athlete.get("jerseyNumber")
        jersey_text = str(jersey or "").strip()
        if not jersey_text:
            continue
        aid = str(athlete.get("id") or "").strip()
        if aid:
            by_id[aid] = jersey_text
        full_name = (
            athlete.get("displayName")
            or athlete.get("fullName")
            or f"{athlete.get('firstName') or ''} {athlete.get('lastName') or athlete.get('familyName') or ''}"
        )
        norm_name = _normalize_player_name(full_name)
        if norm_name:
            by_name[norm_name] = jersey_text

    _roster_number_cache[key] = (now, dict(by_id), dict(by_name))
    return by_id, by_name


def _apply_roster_numbers(team: Dict[str, Any]) -> None:
    if not isinstance(team, dict):
        return
    team_id = str(team.get("teamId") or "").strip()
    if not team_id:
        return
    by_id, by_name = _team_roster_number_maps(team_id)

    players = team.get("players") or []
    core_lookups = 0
    if isinstance(players, list):
        for player in players:
            if not isinstance(player, dict):
                continue
            jersey = str(player.get("jerseyNum") or player.get("jersey") or "").strip()
            if jersey:
                continue
            pid = str(player.get("id") or player.get("personId") or player.get("playerId") or "").strip()
            resolved = by_id.get(pid, "") if pid else ""
            if not resolved:
                name = player.get("fullName") or player.get("displayName")
                if not name:
                    first = str(player.get("firstName") or "").strip()
                    last = str(player.get("familyName") or player.get("lastName") or "").strip()
                    name = f"{first} {last}".strip()
                resolved = by_name.get(_normalize_player_name(name), "")
            if not resolved and pid and core_lookups < CORE_ATHLETE_MAX_LOOKUPS_PER_TEAM:
                resolved = _core_athlete_number(pid)
                if resolved:
                    core_lookups += 1
            if resolved:
                player["jerseyNum"] = resolved
                player["jersey"] = resolved

    lineup = team.get("startingLineup") or []
    if isinstance(lineup, list):
        for player in lineup:
            if not isinstance(player, dict):
                continue
            jersey = str(player.get("jersey") or player.get("jerseyNum") or "").strip()
            if jersey:
                continue
            pid = str(player.get("id") or player.get("playerId") or "").strip()
            resolved = by_id.get(pid, "") if pid else ""
            if not resolved:
                resolved = by_name.get(_normalize_player_name(player.get("fullName") or player.get("displayName")), "")
            if not resolved and pid and core_lookups < CORE_ATHLETE_MAX_LOOKUPS_PER_TEAM:
                resolved = _core_athlete_number(pid)
                if resolved:
                    core_lookups += 1
            if resolved:
                player["jersey"] = resolved
                player["jerseyNum"] = resolved


def _core_athlete_number(player_id: str) -> str:
    pid = str(player_id or "").strip()
    if not pid:
        return ""
    now = time.monotonic()
    cached = _core_athlete_number_cache.get(pid)
    if cached and now - cached[0] <= CORE_ATHLETE_NUMBER_TTL_SEC:
        return str(cached[1] or "")

    url = f"https://sports.core.api.espn.com/v2/sports/baseball/leagues/mlb/athletes/{pid}?lang=en&region=us"
    jersey = ""
    try:
        resp = _session.get(url, headers=HEADERS, timeout=CORE_ATHLETE_TIMEOUT_SEC)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict):
            jersey = str(payload.get("jersey") or "").strip()
    except Exception:
        jersey = ""

    _core_athlete_number_cache[pid] = (now, jersey)
    return jersey


def _status_int_from_state(state: str | None, status_text: str) -> int:
    normalized = str(state or "").lower()
    if normalized == "post":
        return 3
    if normalized == "pre":
        return 1
    lowered = str(status_text or "").lower()
    if any(token in lowered for token in ("final", "postponed", "canceled", "cancelled", "suspended")):
        return 3
    if any(token in lowered for token in ("am", "pm", "scheduled", "starts", "start")):
        return 1
    return 2


def _summary_ttl(status_value: Any) -> float:
    status = _safe_int(status_value)
    if status == 3:
        return SUMMARY_TTL_FINAL
    if status == 2:
        return SUMMARY_TTL_LIVE
    return SUMMARY_TTL_PREGAME


def _inning_half_from_text(text: str | None) -> str | None:
    lowered = str(text or "").strip().lower()
    if lowered.startswith("top ") or lowered.startswith("t "):
        return "TOP"
    if lowered.startswith("bottom ") or lowered.startswith("bot ") or lowered.startswith("b "):
        return "BOT"
    if lowered.startswith("mid "):
        return "MID"
    if lowered.startswith("end "):
        return "END"
    return None


def _inning_from_text(text: str | None) -> int | None:
    raw = str(text or "")
    match = re.search(r"\b(?:top|bottom|bot|mid|end)\s+(\d+)(?:st|nd|rd|th)?\b", raw, re.IGNORECASE)
    if match:
        return _safe_int(match.group(1))
    match = re.search(r"\b(?:t|b)\s*(\d+)\b", raw, re.IGNORECASE)
    if match:
        return _safe_int(match.group(1))
    match = re.search(r"\b(\d+)(?:st|nd|rd|th)\b", raw, re.IGNORECASE)
    if match:
        return _safe_int(match.group(1))
    return None


def _normalize_period_for_state(state: str | None, period_raw: Any, status_text: str) -> int | None:
    if str(state or "").lower() != "in":
        return None
    period = _safe_int(period_raw)
    if isinstance(period, int) and period > 0:
        return period
    return _inning_from_text(status_text)


def _normalize_game_clock(game_status: int, raw_clock: Any) -> str | None:
    if game_status != 2:
        return None
    text = str(raw_clock or "").strip()
    if text in ("", "0", "0:00", "00:00"):
        return None
    return text


def _truthy_base(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", 0, "0"):
        return False
    if isinstance(value, str):
        return value.strip().lower() not in ("", "false", "none", "null", "off", "no")
    return bool(value)


def _person_short_name(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    athlete = value.get("athlete")
    if isinstance(athlete, dict):
        for key in ("shortName", "displayName", "fullName", "name"):
            name = athlete.get(key)
            if isinstance(name, str) and name.strip():
                return name.strip()
    for key in ("shortName", "displayName", "fullName", "name"):
        name = value.get(key)
        if isinstance(name, str) and name.strip():
            return name.strip()
    return ""


def _extract_situation(sit: Dict[str, Any] | None, status_text: str | None = None) -> Dict[str, Any]:
    source = sit if isinstance(sit, dict) else {}
    count = source.get("count") if isinstance(source.get("count"), dict) else {}

    balls = source.get("balls")
    strikes = source.get("strikes")
    outs = source.get("outs")
    if balls is None:
        balls = count.get("balls")
    if strikes is None:
        strikes = count.get("strikes")
    if outs is None:
        outs = count.get("outs")

    on_first = _truthy_base(source.get("onFirst"))
    on_second = _truthy_base(source.get("onSecond"))
    on_third = _truthy_base(source.get("onThird"))

    occupied = source.get("occupiedBases")
    if isinstance(occupied, list):
        for base in occupied:
            b = _safe_int(base)
            if b == 1:
                on_first = True
            elif b == 2:
                on_second = True
            elif b == 3:
                on_third = True

    runners = source.get("runners") or source.get("bases") or []
    if isinstance(runners, list):
        for runner in runners:
            if not isinstance(runner, dict):
                continue
            b = _safe_int(runner.get("base") or runner.get("baseNumber") or runner.get("baseIndex"))
            if b == 1:
                on_first = True
            elif b == 2:
                on_second = True
            elif b == 3:
                on_third = True

    situation: Dict[str, Any] = {
        "balls": _safe_int(balls),
        "strikes": _safe_int(strikes),
        "outs": _safe_int(outs),
        "onFirst": on_first,
        "onSecond": on_second,
        "onThird": on_third,
        "batter": _person_short_name(source.get("batter")),
        "pitcher": _person_short_name(source.get("pitcher")),
        "inningHalf": _inning_half_from_text(status_text),
    }
    situation["basesLoaded"] = bool(on_first and on_second and on_third)
    return situation


def _situation_has_data(situation: Dict[str, Any] | None) -> bool:
    if not isinstance(situation, dict):
        return False
    if any(situation.get(key) not in (None, "", False) for key in ("balls", "strikes", "outs")):
        return True
    if any(bool(situation.get(key)) for key in ("onFirst", "onSecond", "onThird", "basesLoaded")):
        return True
    if any(str(situation.get(key) or "").strip() for key in ("batter", "pitcher")):
        return True
    return False


def _boxscore_ttl(status_value: Any) -> float:
    status = _safe_int(status_value)
    if status == 3:
        return BOXSCORE_TTL_FINAL
    if status == 2:
        return BOXSCORE_TTL_LIVE
    return BOXSCORE_TTL_PREGAME


def _record_summary(raw: Dict[str, Any]) -> str | None:
    records = raw.get("records") or raw.get("record") or []
    if isinstance(records, dict):
        records = [records]
    summary = None
    for rec in records:
        if not isinstance(rec, dict):
            continue
        value = rec.get("summary") or rec.get("displayValue") or rec.get("shortDisplayName")
        if not value:
            continue
        rec_type = str(rec.get("type") or rec.get("name") or "").lower()
        if rec_type in ("total", "overall", "ytd", "game"):
            summary = value
            break
        if summary is None:
            summary = value
    return str(summary) if summary else None


def _wins_losses_from_summary(summary: str | None) -> tuple[int, int] | None:
    if not summary:
        return None
    nums = re.findall(r"\d+", str(summary))
    if len(nums) < 2:
        return None
    try:
        return int(nums[0]), int(nums[1])
    except Exception:
        return None


def _map_linescores(raw_linescores: Any) -> List[Dict[str, Any]]:
    mapped: List[Dict[str, Any]] = []
    if not isinstance(raw_linescores, list):
        return mapped
    for entry in raw_linescores:
        if not isinstance(entry, dict):
            continue
        inning = _safe_int(entry.get("period") or entry.get("periodNumber") or entry.get("inning"))
        runs = _safe_int(entry.get("value") if entry.get("value") is not None else entry.get("displayValue"))
        row: Dict[str, Any] = {}
        if inning is not None:
            row["inning"] = inning
        if runs is not None:
            row["runs"] = runs
        hits = _safe_int(entry.get("hits"))
        errors = _safe_int(entry.get("errors"))
        if hits is not None:
            row["hits"] = hits
        if errors is not None:
            row["errors"] = errors
        if row:
            mapped.append(row)
    return mapped


def _extract_probable_pitcher(raw: Dict[str, Any]) -> str:
    probables = raw.get("probables") or []
    if not isinstance(probables, list):
        return ""
    for item in probables:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").lower()
        abbr = str(item.get("abbreviation") or "").upper()
        if "starting" in name or abbr == "SP" or not name:
            athlete = item.get("athlete") or {}
            short = athlete.get("shortName") or athlete.get("displayName") or athlete.get("fullName")
            if isinstance(short, str) and short.strip():
                return short.strip()
    return ""


def _map_team(raw: Dict[str, Any]) -> Dict[str, Any]:
    team = raw.get("team", {}) or {}
    tri_raw = (team.get("abbreviation") or team.get("shortDisplayName") or "TM").upper()
    tri = TRICODE_ALIASES.get(tri_raw, tri_raw)
    mapped = {
        "teamId": str(team.get("id") or ""),
        "teamName": team.get("displayName") or team.get("name") or "Team",
        "teamTricode": tri,
        "score": int(raw.get("score") or 0),
    }

    summary = _record_summary(raw)
    wins_losses = _wins_losses_from_summary(summary)
    if summary:
        mapped["record"] = summary
    if wins_losses:
        mapped["wins"], mapped["losses"] = wins_losses

    hits = _safe_int(raw.get("hits"))
    errors = _safe_int(raw.get("errors"))
    if hits is not None:
        mapped["hits"] = hits
    if errors is not None:
        mapped["errors"] = errors

    linescores = _map_linescores(raw.get("linescores"))
    if linescores:
        mapped["linescores"] = linescores

    probable_pitcher = _extract_probable_pitcher(raw)
    if probable_pitcher:
        mapped["probablePitcher"] = probable_pitcher

    return mapped


def _line(g: Dict[str, Any]) -> str:
    away = g.get("awayTeam", {}) or {}
    home = g.get("homeTeam", {}) or {}
    return f"{away.get('teamTricode','AWY')} {away.get('score',0)} @ {home.get('teamTricode','HME')} {home.get('score',0)} ({g.get('header','')})"


def _scoreboard_event_to_game(ev: Dict[str, Any], *, league_path: str = MLB_LEAGUE_PATH) -> Dict[str, Any]:
    comp = (ev.get("competitions") or [{}])[0]
    status_outer = ev.get("status") or {}
    status_block = status_outer.get("type", {})
    state = status_block.get("state")
    raw_period = status_outer.get("period") or status_block.get("period")
    start_time = ev.get("date")
    status_text_raw = status_block.get("shortDetail") or status_block.get("detail") or ""

    home_raw = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "home"), {})
    away_raw = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "away"), {})
    home = _map_team(home_raw)
    away = _map_team(away_raw)

    game_status = _status_int_from_state(state, status_text_raw)
    period = _normalize_period_for_state(state, raw_period, status_text_raw)
    if game_status == 1:
        header = format_start_time(start_time)
    elif game_status == 3:
        header = "Final"
    else:
        header = status_text_raw or (f"Inning {period}" if isinstance(period, int) else "Live")

    game_clock = _normalize_game_clock(game_status, status_outer.get("displayClock") or status_block.get("displayClock"))

    return {
        "gameId": str(ev.get("id")),
        "homeTeam": home,
        "awayTeam": away,
        "leaguePath": str(league_path or MLB_LEAGUE_PATH),
        "gameStatus": game_status,
        "status": "final" if game_status == 3 else ("upcoming" if game_status == 1 else "live"),
        "startTime": start_time,
        "header": header,
        "gameStatusText": header,
        "period": {"current": period} if isinstance(period, int) and period > 0 else {},
        "gameClock": game_clock,
        "situation": _extract_situation(comp.get("situation"), header),
        "seasonYear": str(ev.get("season", {}).get("year") or "2025"),
    }


def _summary_competition_from_payload(payload: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    header = payload.get("header") or {}
    competitions = header.get("competitions") or []
    if not competitions:
        return None
    competition = competitions[0]
    return competition if isinstance(competition, dict) else None


def _summary_payload(game_id: str, *, league_path: str | None = None) -> Dict[str, Any] | None:
    key = str(game_id)
    now = time.monotonic()
    preferred_league = str(league_path or MLB_LEAGUE_PATH).strip().lower() or MLB_LEAGUE_PATH
    candidates = [preferred_league]
    for fallback in (MLB_LEAGUE_PATH, WBC_LEAGUE_PATH):
        if fallback not in candidates:
            candidates.append(fallback)

    best_cached_payload: Dict[str, Any] | None = None
    best_cached_age: float | None = None
    for league in candidates:
        cache_key = f"{league}:{key}"
        cached = _summary_cache.get(cache_key)
        if not cached:
            continue
        ttl = _summary_ttl(cached[1])
        age = now - cached[0]
        if age <= ttl:
            return cached[2]
        if best_cached_age is None or age < best_cached_age:
            best_cached_age = age
            best_cached_payload = cached[2]

    for league in candidates:
        summary_url = SUMMARY_URL_TEMPLATE.format(league_path=league, game_id=key)
        try:
            resp = _session.get(summary_url, headers=HEADERS, timeout=SUMMARY_TIMEOUT_SEC)
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            continue
        competition = _summary_competition_from_payload(payload)
        status_int = 2
        if competition:
            status_outer = competition.get("status") or {}
            status_block = status_outer.get("type", {})
            state = status_block.get("state")
            status_text = status_block.get("shortDetail") or status_block.get("detail") or ""
            status_int = _status_int_from_state(state, status_text)
        _summary_cache[f"{league}:{key}"] = (now, status_int, payload)
        return payload

    return best_cached_payload


def _summary_competition(game_id: str, *, league_path: str | None = None) -> Dict[str, Any] | None:
    return _summary_competition_from_payload(_summary_payload(game_id, league_path=league_path))


def _merge_summary_into_game(game: Dict[str, Any], competition: Dict[str, Any]) -> None:
    status_outer = competition.get("status") or {}
    status_block = status_outer.get("type", {})
    state = status_block.get("state")
    status_text_raw = status_block.get("shortDetail") or status_block.get("detail") or ""
    period = _normalize_period_for_state(state, status_outer.get("period") or status_block.get("period"), status_text_raw)

    game_status = _status_int_from_state(state, status_text_raw)
    if game_status == 1:
        header = format_start_time(game.get("startTime"))
    elif game_status == 3:
        header = "Final"
    else:
        header = status_text_raw or (f"Inning {period}" if isinstance(period, int) else "Live")

    game["gameStatus"] = game_status
    game["status"] = "final" if game_status == 3 else ("upcoming" if game_status == 1 else "live")
    game["header"] = header
    game["gameStatusText"] = header
    game["period"] = {"current": period} if isinstance(period, int) and period > 0 else {}
    game["gameClock"] = _normalize_game_clock(game_status, status_outer.get("displayClock") or status_block.get("displayClock"))

    summary_situation = _extract_situation(competition.get("situation"), header)
    if _situation_has_data(summary_situation):
        game["situation"] = summary_situation
    else:
        existing = game.get("situation") if isinstance(game.get("situation"), dict) else {}
        merged = dict(existing)
        if summary_situation.get("inningHalf") and not merged.get("inningHalf"):
            merged["inningHalf"] = summary_situation["inningHalf"]
        merged["basesLoaded"] = bool(merged.get("onFirst") and merged.get("onSecond") and merged.get("onThird"))
        game["situation"] = merged

    home_raw = next((c for c in competition.get("competitors", []) if c.get("homeAway") == "home"), {})
    away_raw = next((c for c in competition.get("competitors", []) if c.get("homeAway") == "away"), {})
    if home_raw:
        game["homeTeam"] = _map_team(home_raw)
    if away_raw:
        game["awayTeam"] = _map_team(away_raw)


def _normalize_stat_key(raw: Any) -> str:
    text = re.sub(r"[^a-z0-9#]+", "", str(raw or "").strip().lower())
    mapping = {
        "hab": "hitsAtBats",
        "ab": "atBats",
        "r": "runs",
        "h": "hits",
        "rbi": "rbi",
        "rbis": "rbi",
        "hr": "homeRuns",
        "bb": "walks",
        "k": "strikeouts",
        "so": "strikeouts",
        "p": "pitches",
        "avg": "avg",
        "obp": "obp",
        "slg": "slg",
        "ops": "ops",
        "ip": "inningsPitched",
        "er": "earnedRuns",
        "era": "era",
        "pc": "pitchCount",
        "pcst": "pitchCountStrikes",
    }
    return mapping.get(text, text or "stat")


def _map_player_stats(stat_values: Any, labels: Any, keys: Any, group_name: str) -> Dict[str, Any]:
    stats: Dict[str, Any] = {}
    values = stat_values if isinstance(stat_values, list) else []
    labels_list = labels if isinstance(labels, list) else []
    keys_list = keys if isinstance(keys, list) else []

    for idx, value in enumerate(values):
        key_raw = ""
        if idx < len(keys_list) and keys_list[idx] not in (None, ""):
            key_raw = str(keys_list[idx])
        elif idx < len(labels_list) and labels_list[idx] not in (None, ""):
            key_raw = str(labels_list[idx])
        key = _normalize_stat_key(key_raw)
        stats[key] = _coerce_stat_value(value)

    group = str(group_name or "").strip().lower()
    if not group:
        if any(k in stats for k in ("inningsPitched", "earnedRuns", "era")):
            group = "pitching"
        elif any(k in stats for k in ("avg", "atBats", "hitsAtBats")):
            group = "batting"
    if group:
        stats["group"] = group

    hab = stats.get("hitsAtBats")
    if isinstance(hab, str) and "-" in hab:
        left, _, right = hab.partition("-")
        left_int = _safe_int(left)
        right_int = _safe_int(right)
        if left_int is not None and "hits" not in stats:
            stats["hits"] = left_int
        if right_int is not None and "atBats" not in stats:
            stats["atBats"] = right_int

    return stats


def _parse_boxscore_players(payload: Dict[str, Any] | None) -> Dict[str, List[Dict[str, Any]]]:
    by_team: Dict[str, List[Dict[str, Any]]] = {}
    box = (payload or {}).get("boxscore") or {}
    blocks = box.get("players") or []
    if not isinstance(blocks, list):
        return by_team

    for block in blocks:
        if not isinstance(block, dict):
            continue
        team_block = block.get("team") or {}
        team_id = str(team_block.get("id") or "")
        tri_raw = (team_block.get("abbreviation") or team_block.get("shortDisplayName") or "").upper()
        tri = TRICODE_ALIASES.get(tri_raw, tri_raw)

        players: List[Dict[str, Any]] = []
        for stat_group in block.get("statistics") or []:
            if not isinstance(stat_group, dict):
                continue
            labels = stat_group.get("labels")
            keys = stat_group.get("keys")
            group_name = str(stat_group.get("name") or stat_group.get("displayName") or "")
            athletes = stat_group.get("athletes") or []
            if not isinstance(athletes, list):
                continue

            for idx, entry in enumerate(athletes):
                if not isinstance(entry, dict):
                    continue
                athlete = entry.get("athlete") or {}
                first = str(athlete.get("firstName") or "").strip()
                last = str(athlete.get("lastName") or athlete.get("familyName") or "").strip()
                full_name = str(
                    athlete.get("fullName")
                    or athlete.get("displayName")
                    or entry.get("fullName")
                    or entry.get("displayName")
                    or ""
                ).strip()
                jersey = athlete.get("jersey") or entry.get("jerseyNum") or ""
                pos_block = entry.get("position") or athlete.get("position") or {}
                if isinstance(pos_block, dict):
                    position = pos_block.get("abbreviation") or pos_block.get("shortName") or pos_block.get("displayName") or ""
                else:
                    position = str(pos_block or "")

                order = _safe_int(entry.get("batOrder"))
                if order is None:
                    order = idx + 1

                player = {
                    "id": str(athlete.get("id") or entry.get("id") or ""),
                    "firstName": first,
                    "familyName": last,
                    "fullName": full_name,
                    "displayName": full_name,
                    "jerseyNum": str(jersey or ""),
                    "position": str(position or ""),
                    "order": order,
                    "starter": bool(entry.get("starter")),
                    "statistics": _map_player_stats(entry.get("stats"), labels, keys, group_name),
                }
                players.append(player)

        merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for player in players:
            stats = player.get("statistics") or {}
            group = str(stats.get("group") or "")
            pid = str(player.get("id") or player.get("fullName") or "")
            key = (pid, group)
            existing = merged.get(key)
            if existing is None:
                merged[key] = player
                continue
            existing_stats = existing.get("statistics") or {}
            for stat_key, stat_val in stats.items():
                if stat_key not in existing_stats or existing_stats[stat_key] in (None, ""):
                    existing_stats[stat_key] = stat_val
            if not existing.get("position") and player.get("position"):
                existing["position"] = player.get("position")

        final_players = list(merged.values())
        final_players.sort(
            key=lambda p: (
                0 if str((p.get("statistics") or {}).get("group") or "").startswith("bat") else 1,
                _safe_int(p.get("order")) or 999,
                str(p.get("fullName") or ""),
            )
        )

        if team_id:
            by_team[team_id] = final_players
        if tri:
            by_team[tri] = final_players

    return by_team


def _flatten_stat_groups(groups: Any) -> Dict[str, Dict[str, Any]]:
    flattened: Dict[str, Dict[str, Any]] = {}
    if not isinstance(groups, list):
        return flattened
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_name = str(group.get("name") or group.get("displayName") or "stats")
        stat_map: Dict[str, Any] = {}
        for stat in group.get("stats") or []:
            if not isinstance(stat, dict):
                continue
            key = stat.get("name") or stat.get("abbreviation") or stat.get("displayName")
            if not key:
                continue
            value = stat.get("displayValue")
            if value in (None, ""):
                value = stat.get("value")
            stat_map[str(key)] = value
        if stat_map:
            flattened[group_name] = stat_map
    return flattened


def _parse_boxscore_team_blocks(payload: Dict[str, Any] | None) -> Dict[str, Dict[str, Any]]:
    by_team: Dict[str, Dict[str, Any]] = {}
    box = (payload or {}).get("boxscore") or {}
    teams = box.get("teams") or []
    if not isinstance(teams, list):
        return by_team

    for block in teams:
        if not isinstance(block, dict):
            continue
        team_block = block.get("team") or {}
        team_id = str(team_block.get("id") or "")
        tri_raw = (team_block.get("abbreviation") or team_block.get("shortDisplayName") or "").upper()
        tri = TRICODE_ALIASES.get(tri_raw, tri_raw)

        mapped: Dict[str, Any] = {}
        stat_groups = block.get("statistics") or []
        detail_groups = block.get("details") or []
        flat_stats = _flatten_stat_groups(stat_groups)
        flat_details = _flatten_stat_groups(detail_groups)
        if flat_stats:
            mapped["teamStats"] = flat_stats
        if flat_details:
            mapped["teamDetails"] = flat_details
        if isinstance(stat_groups, list) and stat_groups:
            mapped["teamStatGroups"] = stat_groups
        if isinstance(detail_groups, list) and detail_groups:
            mapped["teamDetailGroups"] = detail_groups

        if mapped:
            if team_id:
                by_team[team_id] = mapped
            if tri:
                by_team[tri] = mapped

    return by_team


def _merge_boxscore_data_into_team(team: Dict[str, Any], team_extras: Dict[str, Dict[str, Any]], team_players: Dict[str, List[Dict[str, Any]]]) -> None:
    team_id = str(team.get("teamId") or "")
    tri = str(team.get("teamTricode") or "").upper()

    extras = team_extras.get(team_id) or team_extras.get(tri)
    if isinstance(extras, dict):
        team.update(extras)

    players = team_players.get(team_id) or team_players.get(tri)
    if isinstance(players, list) and players:
        team["players"] = players


def _pbp_team_tricodes(payload: Dict[str, Any] | None) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    competition = _summary_competition_from_payload(payload)
    if not competition:
        return mapping
    for comp in competition.get("competitors") or []:
        if not isinstance(comp, dict):
            continue
        team = comp.get("team") or {}
        team_id = str(team.get("id") or "")
        tri_raw = (team.get("abbreviation") or team.get("shortDisplayName") or "").upper()
        tri = TRICODE_ALIASES.get(tri_raw, tri_raw)
        if team_id and tri:
            mapping[team_id] = tri
    return mapping


def get_scoreboard() -> Dict[str, Any]:
    now = time.monotonic()
    cached = _scoreboard_cache.get("data")
    if isinstance(cached, dict) and now - float(_scoreboard_cache.get("ts") or 0.0) < SCOREBOARD_TTL:
        return cached

    mapped_events: List[tuple[Dict[str, Any], str]] = []
    seen_ids: set[str] = set()
    for league_path, scoreboard_url in SCOREBOARD_URLS.items():
        try:
            resp = _session.get(scoreboard_url, headers=HEADERS, timeout=SCOREBOARD_TIMEOUT_SEC)
            resp.raise_for_status()
            data = resp.json()
            events = data.get("events", []) or []
        except Exception:
            continue
        for ev in events:
            if not isinstance(ev, dict):
                continue
            game_id = str(ev.get("id") or "")
            if not game_id or game_id in seen_ids:
                continue
            seen_ids.add(game_id)
            mapped_events.append((ev, league_path))

    if not mapped_events:
        if isinstance(cached, dict):
            return cached
        return _demo_scoreboard()

    games = []
    for ev, league_path in mapped_events:
        games.append(_scoreboard_event_to_game(ev, league_path=league_path))
    if not games:
        return _demo_scoreboard()
    lines = [_line(g) for g in games]
    result = {"games": games, "lines": lines}
    _scoreboard_cache["data"] = result
    _scoreboard_cache["ts"] = now
    return result


def get_boxscore(game_id: str) -> Dict[str, Any]:
    key = str(game_id)
    now = time.monotonic()
    cached = _boxscore_cache.get(key)
    if cached:
        cached_game = (cached[1].get("game") or {})
        ttl = _boxscore_ttl(cached_game.get("gameStatus"))
        if now - cached[0] <= ttl:
            return cached[1]

    board = get_scoreboard()
    game = next((g for g in board.get("games", []) if g.get("gameId") == key), None)
    if not game:
        return _demo_boxscore(key)

    league_path = str(game.get("leaguePath") or MLB_LEAGUE_PATH)
    payload = _summary_payload(key, league_path=league_path)
    competition = _summary_competition_from_payload(payload)
    if competition:
        _merge_summary_into_game(game, competition)

    header = game.get("header")
    home = {**game.get("homeTeam", {}), "players": []}
    away = {**game.get("awayTeam", {}), "players": []}

    team_extras = _parse_boxscore_team_blocks(payload)
    team_players = _parse_boxscore_players(payload)
    _merge_boxscore_data_into_team(home, team_extras, team_players)
    _merge_boxscore_data_into_team(away, team_extras, team_players)

    apply_starting_lineups("MLB", home, away)
    _apply_roster_numbers(home)
    _apply_roster_numbers(away)

    game_block = {
        "leaguePath": league_path,
        "gameClock": game.get("gameClock"),
        "shotClock": None,
        "period": game.get("period") or {"current": None},
        "gameStatusText": header,
        "gameStatus": game.get("gameStatus"),
        "situation": game.get("situation") or {},
        "linescore": {
            "away": away.get("linescores") or [],
            "home": home.get("linescores") or [],
        },
    }

    result = {
        "game": game_block,
        "home": home,
        "away": away,
        "header": header,
        "shotclock": "--",
    }
    _boxscore_cache[key] = (now, result)
    return result


def fetch_play_by_play(game_id: str, limit: int = 18) -> List[Dict[str, Any]]:
    payload = _summary_payload(str(game_id))
    if not isinstance(payload, dict):
        return []
    plays = payload.get("plays") or []
    if not isinstance(plays, list):
        return []

    team_lookup = _pbp_team_tricodes(payload)
    cleaned: List[Dict[str, Any]] = []
    for play in plays:
        if not isinstance(play, dict):
            continue
        description = str(play.get("text") or "").strip()
        if not description:
            continue
        period = (play.get("period") or {}).get("number")
        team_id = str((play.get("team") or {}).get("id") or "")
        cleaned.append(
            {
                "id": play.get("id") or play.get("sequenceNumber"),
                "period": period,
                "clock": play.get("clock") or play.get("displayClock"),
                "description": description,
                "teamTricode": team_lookup.get(team_id, ""),
                "scoreHome": _safe_int(play.get("homeScore")),
                "scoreAway": _safe_int(play.get("awayScore")),
            }
        )

    if not cleaned:
        return []
    return cleaned[-max(1, int(limit)) :]


def get_team_colors(tricode: str) -> Dict[str, str]:
    tri = (tricode or "").upper()
    return {
        "primary": TEAM_PRIMARY_COLORS.get(tri, "#444444"),
        "secondary": TEAM_SECONDARY_COLORS.get(tri, "#2b2b2b"),
        "accent": TEAM_ACCENT_COLORS.get(tri, "#777777"),
    }


def get_team_logo(team_id: str | None, tricode: str | None) -> bytes | None:
    tri = (tricode or "").upper()
    key = (team_id or "", tri, LOGO_VERSION)
    if key in _logo_cache:
        return _logo_cache[key]
    # Use tricode-first cache names to avoid collisions between MLB numeric IDs and WBC country teams.
    cache_path = LOGO_DIR / f"{tri or team_id or 'unknown'}-{LOGO_VERSION}.png"
    if cache_path.exists():
        try:
            data = cache_path.read_bytes()
            _logo_cache[key] = data
            return data
        except Exception:
            pass
    urls = []
    is_country_team = bool(tri and tri not in TEAM_PRIMARY_COLORS)
    if is_country_team and tri:
        urls.append(f"https://a.espncdn.com/i/teamlogos/countries/500/{tri}.png")
        urls.append(f"https://a.espncdn.com/i/teamlogos/countries/500/{tri.lower()}.png")
    if tri:
        urls.append(f"https://www.mlbstatic.com/team-logos/{tri}.svg")
        urls.append(f"https://a.espncdn.com/i/teamlogos/mlb/500/{tri}.png")
    if not is_country_team and tri:
        urls.append(f"https://a.espncdn.com/i/teamlogos/countries/500/{tri}.png")
        urls.append(f"https://a.espncdn.com/i/teamlogos/countries/500/{tri.lower()}.png")
    for url in urls:
        try:
            resp = _session.get(url, headers=HEADERS, timeout=LOGO_TIMEOUT_SEC)
            resp.raise_for_status()
            data = resp.content
            cache_path.write_bytes(data)
            _logo_cache[key] = data
            return data
        except Exception:
            continue
    _logo_cache[key] = None
    return None


def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    return get_team_logo(team_id, tricode)


def safe_score(team: Dict[str, Any]) -> int:
    try:
        return int(team.get("score") or 0)
    except Exception:
        return 0


def format_time_played(value: Any) -> str:
    if value in (None, "", 0):
        return ""
    return str(value)


def format_shotclock(value: Any) -> str:
    return "--"


def _player_name(player: Dict[str, Any]) -> str:
    first = str(player.get("firstName") or "").strip()
    last = str(player.get("familyName") or "").strip()
    if first or last:
        return format_player_initial_name(first, last)
    for key in ("fullName", "displayName", "name"):
        value = player.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    athlete = player.get("athlete") if isinstance(player.get("athlete"), dict) else {}
    for key in ("fullName", "displayName", "name"):
        value = athlete.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _stat_text(stats: Dict[str, Any], keys: tuple[str, ...], *, default: str = "") -> str:
    for key in keys:
        value = stats.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, float):
            if key in ("avg", "obp", "slg") and 0 <= value < 1:
                return f"{value:.3f}".lstrip("0")
            return f"{value:.3f}".rstrip("0").rstrip(".")
        return str(value)
    return default


def build_player_rows(team: Dict[str, Any]) -> List[List[str]]:
    rows: List[List[str]] = []
    players = team.get("players", []) or []
    if not isinstance(players, list):
        return rows

    hitters: List[Dict[str, Any]] = []
    for player in players:
        if not isinstance(player, dict):
            continue
        stats = player.get("statistics") if isinstance(player.get("statistics"), dict) else {}
        group = str(stats.get("group") or player.get("statGroup") or "").lower()
        if group.startswith("pitch"):
            continue
        if not any(k in stats for k in ("avg", "homeRuns", "rbi", "obp", "slg", "atBats", "hits")):
            continue
        hitters.append(player)

    hitters.sort(key=lambda p: (_safe_int(p.get("order")) or 999, _player_name(p)))

    for player in hitters:
        stats = player.get("statistics") if isinstance(player.get("statistics"), dict) else {}
        jersey = str(player.get("jerseyNum") or player.get("jersey") or "")
        name = _player_name(player)
        position = str(player.get("position") or "")
        avg = _stat_text(stats, ("avg", "battingAverage"))
        hr = _stat_text(stats, ("homeRuns", "hr"), default="0")
        rbi = _stat_text(stats, ("rbi",), default="0")
        obp = _stat_text(stats, ("obp",))
        slg = _stat_text(stats, ("slg",))
        rows.append([jersey, name, position, avg, hr, rbi, obp, slg])

    if rows:
        return rows

    # Fallback for pre-game lineups when stat lines are not available yet.
    lineup = team.get("startingLineup") or []
    if isinstance(lineup, list):
        for player in lineup:
            if not isinstance(player, dict):
                continue
            jersey = str(player.get("jersey") or player.get("jerseyNum") or "")
            name = _player_name(player)
            position = str(player.get("position") or "")
            if not (name or jersey or position):
                continue
            rows.append([jersey, name, position, "", "", "", "", ""])

    return rows


def _demo_scoreboard() -> Dict[str, Any]:
    now = time.time()
    games = [
        {
            "gameId": "MLB_DEMO",
            "homeTeam": {"teamId": "SF", "teamName": "Giants", "teamTricode": "SF", "score": 0},
            "awayTeam": {"teamId": "LAD", "teamName": "Dodgers", "teamTricode": "LAD", "score": 0},
            "status": "upcoming",
            "startTime": now + 3600,
            "header": format_start_time(now + 3600),
            "gameStatusText": format_start_time(now + 3600),
            "seasonYear": "2025",
        }
    ]
    return {"games": games, "lines": [_line(games[0])]}


def _demo_boxscore(game_id: str) -> Dict[str, Any]:
    board = _demo_scoreboard()
    g = board["games"][0]
    return {
        "game": {
            "gameClock": None,
            "shotClock": None,
            "period": {"current": 0},
            "gameStatusText": g["header"],
            "gameStatus": 1,
            "situation": {},
            "linescore": {"away": [], "home": []},
        },
        "home": {**g["homeTeam"], "players": []},
        "away": {**g["awayTeam"], "players": []},
        "header": g["header"],
        "shotclock": "--",
    }


# compatibility aliases
fetch_scoreboard = get_scoreboard
fetch_boxscore = get_boxscore
