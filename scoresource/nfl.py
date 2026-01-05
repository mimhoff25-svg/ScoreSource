from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

from .common.utils import format_player_initial_name
from .common.lineups import apply_starting_lineups
from .common.timefmt import format_start_time


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


SCOREBOARD_URL = "https://cdn.espn.com/core/nfl/scoreboard?xhr=1&render=false"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={game_id}"
HEADERS = {"User-Agent": "ScoreSource/1.0", "Referer": "https://www.espn.com"}

CACHE_ROOT = _cache_root_from_env()
LOGO_DIR = CACHE_ROOT / "logos" / "nfl"
LOGO_DIR.mkdir(parents=True, exist_ok=True)
_logo_cache: Dict[Tuple[str, str], bytes | None] = {}
_session = requests.Session()
_boxscore_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_roster_cache: Dict[str, Tuple[float, Dict[str, str]]] = {}

BOXSCORE_TTL_FINAL = _env_float("SCORESOURCE_NFL_BOXSCORE_TTL_FINAL", 60 * 60 * 24 * 7, min_value=0.0)
BOXSCORE_TTL_PREGAME = _env_float("SCORESOURCE_NFL_BOXSCORE_TTL_PREGAME", 60.0, min_value=0.0)
BOXSCORE_TTL_LIVE = _env_float("SCORESOURCE_NFL_BOXSCORE_TTL_LIVE", 10.0, min_value=0.0)
LIVE_START_GRACE_SEC = _env_float("SCORESOURCE_NFL_LIVE_START_GRACE_SEC", 10 * 60, min_value=0.0)
LIVE_START_MAX_SEC = _env_float("SCORESOURCE_NFL_LIVE_START_MAX_SEC", 6 * 60 * 60, min_value=0.0)
ROSTER_TTL = _env_float("SCORESOURCE_NFL_ROSTER_TTL", 60 * 60 * 24, min_value=0.0)
ALT_SCORE_TTL = _env_float("SCORESOURCE_NFL_ALT_SCORE_TTL", 8.0, min_value=0.0)
ALT_SCORE_SOURCES = (
    "https://static.nfl.com/liveupdate/scores/scores.json",
    "https://liveupdate.nfl.com/scorestrip/scorestrip.json",
    "https://static.nfl.com/liveupdate/scorestrip/scorestrip.json",
)
_alt_score_cache: Dict[str, Any] = {"ts": 0.0, "games": []}
_drive_cache: Dict[str, Tuple[float, Dict[str, str]]] = {}
DRIVE_TTL = _env_float("SCORESOURCE_NFL_DRIVE_TTL", 4.0, min_value=0.0)

SCOREBOARD_TIMEOUT_SEC = _env_float("SCORESOURCE_NFL_SCOREBOARD_TIMEOUT_SEC", 8.0, min_value=1.0)
SUMMARY_TIMEOUT_SEC = _env_float("SCORESOURCE_NFL_SUMMARY_TIMEOUT_SEC", 8.0, min_value=1.0)
ALT_SCORE_TIMEOUT_SEC = _env_float("SCORESOURCE_NFL_ALT_SCORE_TIMEOUT_SEC", 6.0, min_value=1.0)
ROSTER_TIMEOUT_SEC = _env_float("SCORESOURCE_NFL_ROSTER_TIMEOUT_SEC", 8.0, min_value=1.0)
BOXSCORE_TIMEOUT_SEC = _env_float("SCORESOURCE_NFL_BOXSCORE_TIMEOUT_SEC", 10.0, min_value=1.0)
LOGO_TIMEOUT_SEC = _env_float("SCORESOURCE_NFL_LOGO_TIMEOUT_SEC", 5.0, min_value=1.0)


def _to_int(value: Any) -> int:
    try:
        m = re.search(r"-?\d+(?:\.\d+)?", str(value))
        if not m:
            return 0
        return int(float(m.group(0)))
    except Exception:
        return 0


# Official team colors (primary / secondary / accent)
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
    "LVR": "#000000",
    "LV": "#000000",
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
    "LVR": "#A5ACAF",
    "LV": "#A5ACAF",
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
    "LVR": "#FFFFFF",
    "LV": "#FFFFFF",
    "DEN": "#FFFFFF",
    "LAC": "#FFFFFF",
    "DAL": "#FFFFFF",
    "PHI": "#000000",
    "NYG": "#FFFFFF",
    "WAS": "#FFFFFF",
    "WSH": "#FFFFFF",
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
NFL_TABLE_HEADERS = ["#", "Player", "Pos", "Yds", "TD", "Tkl", "Ast", "Pen"]
sport_table_headers = NFL_TABLE_HEADERS


def _status(state: str | None) -> str:
    if state == "post":
        return "final"
    if state == "pre":
        return "upcoming"
    return "live"


def _header(state: str, period: int | None, clock: str | None, start: Any) -> str:
    if state == "post":
        return "Final"
    if state == "pre":
        return format_start_time(start)
    if period:
        return f"Q{period} {clock or ''}".strip()
    return clock or "Live"


def _parse_clock_and_period(text: str | None) -> tuple[str | None, int | None]:
    if not text:
        return None, None
    raw = str(text).strip()
    if not raw:
        return None, None
    upper = raw.upper()
    has_live_tag = any(tag in upper for tag in ("Q1", "Q2", "Q3", "Q4", "1ST", "2ND", "3RD", "4TH", "OT", "HALF"))
    if not has_live_tag:
        if "AM" in upper or "PM" in upper or re.search(r"\b\d{1,2}/\d{1,2}\b", upper):
            return None, None
    clock = None
    period = None
    m = re.search(r"(\d{1,2}:\d{2})", raw)
    if m:
        clock = m.group(1)
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


def _start_time_epoch(start: Any) -> float | None:
    if start in (None, ""):
        return None
    if isinstance(start, (int, float)):
        return float(start)
    if isinstance(start, str):
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            return None
    return None


def _force_live_by_start(state: str | None, start: Any) -> str | None:
    if state != "pre":
        return state
    ts = _start_time_epoch(start)
    if ts is None:
        return state
    now = time.time()
    if now >= ts + LIVE_START_GRACE_SEC and now - ts <= LIVE_START_MAX_SEC:
        return "in"
    return state


def _format_clock_seconds(seconds: float) -> str:
    minutes = int(max(0, seconds) // 60)
    secs = int(max(0, seconds) % 60)
    return f"{minutes}:{secs:02d}"


def _estimate_period_and_clock(start: Any) -> tuple[str, int] | None:
    ts = _start_time_epoch(start)
    if ts is None:
        return None
    now = time.time()
    elapsed = now - ts
    if elapsed < 0:
        return None
    quarter_len = 15 * 60
    max_game = 4 * quarter_len
    if elapsed >= max_game:
        return "0:00", 4
    period = int(elapsed // quarter_len) + 1
    remaining = quarter_len - (elapsed % quarter_len)
    return _format_clock_seconds(remaining), period


def _coerce_state(state: str | None, status_text: str | None, clock: str | None, period: int | None) -> str | None:
    lower = str(status_text or "").lower()
    if any(token in lower for token in ("final", "postponed", "canceled", "cancelled")):
        return "post"
    live_tokens = ("q1", "q2", "q3", "q4", "ot", "halftime", "end of", "end 1st", "end 2nd", "end 3rd")
    is_live_hint = any(token in lower for token in live_tokens)
    if period and period > 0:
        is_live_hint = True
    if clock and clock not in ("0:00", "00:00"):
        is_live_hint = True
    if is_live_hint:
        return "in"
    return state


def _is_final_header(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(token in lowered for token in ("final", "postponed", "canceled", "cancelled"))


def _is_pregame_header(text: str) -> bool:
    lowered = str(text or "").lower()
    if any(token in lowered for token in ("q1", "q2", "q3", "q4", "ot", "half")):
        return False
    if any(token in lowered for token in ("tba", "scheduled", "am", "pm")):
        return True
    if re.search(r"\b(?:sun|mon|tue|wed|thu|fri|sat)\b", lowered):
        return True
    if re.search(r"\b\d{1,2}/\d{1,2}\b", lowered):
        return True
    return False


def _boxscore_ttl_from_header(text: str) -> int:
    if _is_final_header(text):
        return BOXSCORE_TTL_FINAL
    if _is_pregame_header(text):
        return BOXSCORE_TTL_PREGAME
    return BOXSCORE_TTL_LIVE


def _down_distance_text(situation: Dict[str, Any]) -> str:
    if not situation:
        return ""
    for key in ("shortDownDistanceText", "downDistanceText"):
        val = situation.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    down = situation.get("down")
    dist = situation.get("distance")
    if isinstance(down, int) and down > 0 and isinstance(dist, int) and dist > 0:
        suffix = "th"
        if down == 1:
            suffix = "st"
        elif down == 2:
            suffix = "nd"
        elif down == 3:
            suffix = "rd"
        return f"{down}{suffix} & {dist}"
    return ""


def _last_drive_play(drive: Any) -> Dict[str, Any] | None:
    if not isinstance(drive, dict):
        return None
    plays = drive.get("plays") or []
    if isinstance(plays, list) and plays:
        return plays[-1]
    return None


def _drive_state_from_play(play: Dict[str, Any]) -> Dict[str, str]:
    end = play.get("end") or {}
    start = play.get("start") or {}
    short_down = end.get("shortDownDistanceText") or start.get("shortDownDistanceText")
    long_down = end.get("downDistanceText") or start.get("downDistanceText")
    if not short_down or not long_down:
        down_val = end.get("down") or start.get("down")
        dist_val = end.get("distance") or start.get("distance")
        if isinstance(down_val, int) and isinstance(dist_val, int) and down_val > 0 and dist_val >= 0:
            computed = _down_distance_text({"down": down_val, "distance": dist_val})
            if computed:
                if not short_down:
                    short_down = computed
                if not long_down:
                    long_down = computed
    possession_text = end.get("possessionText") or start.get("possessionText")
    state: Dict[str, str] = {}
    if isinstance(short_down, str) and short_down.strip():
        state["short"] = short_down.strip()
    if isinstance(long_down, str) and long_down.strip():
        state["long"] = long_down.strip()
    if isinstance(possession_text, str) and possession_text.strip():
        state["possession"] = possession_text.strip()
    clock_val = play.get("clock")
    clock_text = None
    if isinstance(clock_val, dict):
        clock_text = clock_val.get("displayValue")
    elif isinstance(clock_val, str):
        clock_text = clock_val
    if isinstance(clock_text, str) and clock_text.strip():
        state["play_clock"] = clock_text.strip()
    return state


def _clock_to_seconds(val: Any) -> int | None:
    if not val:
        return None
    match = re.search(r"(\d{1,2}):(\d{2})", str(val))
    if not match:
        return None
    try:
        mins = int(match.group(1))
        secs = int(match.group(2))
    except Exception:
        return None
    return (mins * 60) + secs


def _select_live_clock(primary: str | None, summary_clock: str | None, play_clock: str | None) -> str | None:
    primary_secs = _clock_to_seconds(primary)
    play_secs = _clock_to_seconds(play_clock)
    summary_secs = _clock_to_seconds(summary_clock)
    if primary_secs is None:
        if play_secs is not None:
            return play_clock
        if summary_secs is not None:
            return summary_clock
        return primary or play_clock or summary_clock
    # prefer play/summary clocks only if they are slightly ahead (lower) of primary
    for candidate, cand_secs in ((play_clock, play_secs), (summary_clock, summary_secs)):
        if cand_secs is None:
            continue
        diff = primary_secs - cand_secs
        if 0 <= diff <= 120:
            return candidate
    return primary


def _apply_drive_state_overrides(
    game: Dict[str, Any],
    home_team: Dict[str, Any],
    away_team: Dict[str, Any],
    drive_state: Dict[str, Any],
) -> tuple[str | None, int | None]:
    if not drive_state:
        period_val = (game.get("period") or {}).get("current") if isinstance(game.get("period"), dict) else None
        return game.get("gameClock"), period_val
    short_drive = drive_state.get("short")
    long_drive = drive_state.get("long")
    if short_drive:
        game["shortDownDistanceText"] = short_drive
    if long_drive:
        game["downDistanceText"] = long_drive
    possession_override = drive_state.get("possession")
    if possession_override:
        game["possessionText"] = possession_override
    current_clock = game.get("gameClock")
    chosen_clock = _select_live_clock(current_clock, drive_state.get("clock"), drive_state.get("play_clock"))
    if chosen_clock and chosen_clock != current_clock:
        game["gameClock"] = chosen_clock
    current_period = (game.get("period") or {}).get("current") if isinstance(game.get("period"), dict) else None
    period_override = drive_state.get("period")
    if (not current_period or current_period <= 0) and isinstance(period_override, int) and period_override > 0:
        game["period"] = {"current": period_override}
        current_period = period_override
    home_score = drive_state.get("home_score")
    away_score = drive_state.get("away_score")
    if home_score is not None:
        home_team["score"] = home_score
    if away_score is not None:
        away_team["score"] = away_score
    return game.get("gameClock"), current_period


def _fetch_drive_state(game_id: str) -> Dict[str, Any]:
    now = time.monotonic()
    cached = _drive_cache.get(str(game_id))
    if cached and now - cached[0] < DRIVE_TTL:
        return cached[1]
    try:
        resp = _session.get(SUMMARY_URL.format(game_id=game_id), headers=HEADERS, timeout=SUMMARY_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return {}
    drives = data.get("drives") or {}
    play = _last_drive_play(drives.get("current"))
    if play is None:
        prev = drives.get("previous") or []
        if isinstance(prev, list) and prev:
            play = _last_drive_play(prev[-1])
        elif isinstance(prev, dict):
            play = _last_drive_play(prev)
    state: Dict[str, Any] = _drive_state_from_play(play) if play else {}

    comp = (data.get("header") or {}).get("competitions") or []
    comp0 = comp[0] if comp else {}
    status_block = (comp0.get("status") or {}).get("type", {}) if isinstance(comp0, dict) else {}
    status_text = status_block.get("shortDetail") or status_block.get("detail") or ""
    clock, period = _parse_clock_and_period(status_text)
    if clock:
        state["clock"] = clock
    if period:
        state["period"] = period
    if "clock" not in state and state.get("play_clock"):
        state["clock"] = state.get("play_clock")

    competitors = comp0.get("competitors") if isinstance(comp0, dict) else None
    if isinstance(competitors, list):
        for entry in competitors:
            if not isinstance(entry, dict):
                continue
            side = entry.get("homeAway")
            score = entry.get("score")
            if side == "home" and score not in (None, ""):
                state["home_score"] = _to_int(score)
            elif side == "away" and score not in (None, ""):
                state["away_score"] = _to_int(score)

    _drive_cache[str(game_id)] = (now, state)
    return state


def _fetch_scoreboard_events() -> List[Dict[str, Any]]:
    resp = _session.get(SCOREBOARD_URL, headers=HEADERS, timeout=SCOREBOARD_TIMEOUT_SEC)
    resp.raise_for_status()
    data = resp.json()
    content = data.get("content", {})
    sb = content.get("sbData", {})
    events = sb.get("events", []) or data.get("events", []) or []
    return events


def _normalize_match_tricode(tricode: Any) -> str:
    tri = str(tricode or "").upper()
    aliases = {
        "JAC": "JAX",
        "WSH": "WAS",
        "LVR": "LV",
        "LV": "LV",
        "LA": "LAR",
        "STL": "LAR",
        "SD": "LAC",
    }
    return aliases.get(tri, tri)


def _extract_alt_score(val: Any) -> int:
    if isinstance(val, dict):
        for key in ("T", "total", "score", "points"):
            if key in val:
                val = val.get(key)
                break
    return _to_int(val)


def _normalize_alt_game(
    home_tri: Any,
    away_tri: Any,
    home_score: Any,
    away_score: Any,
    period: Any,
    clock: Any,
    status: Any,
) -> Dict[str, Any] | None:
    home = _normalize_match_tricode(home_tri)
    away = _normalize_match_tricode(away_tri)
    if not home or not away:
        return None
    per = _to_int(period)
    if per <= 0:
        per = None
    clock_text = str(clock or "").strip()
    return {
        "home": home,
        "away": away,
        "home_score": _extract_alt_score(home_score),
        "away_score": _extract_alt_score(away_score),
        "period": per,
        "clock": clock_text,
        "status": str(status or "").strip(),
    }


def _parse_alt_games(payload: Any) -> List[Dict[str, Any]]:
    games: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        for key in ("games", "g", "ss"):
            block = payload.get(key)
            if isinstance(block, list):
                for entry in block:
                    if isinstance(entry, dict):
                        games.extend(_parse_alt_games(entry))
                return games
        if payload and all(isinstance(v, dict) for v in payload.values()):
            for entry in payload.values():
                if not isinstance(entry, dict):
                    continue
                home = entry.get("home") or {}
                away = entry.get("away") or {}
                game = _normalize_alt_game(
                    home.get("abbr") or home.get("team") or entry.get("home"),
                    away.get("abbr") or away.get("team") or entry.get("away"),
                    home.get("score") or entry.get("home_score") or entry.get("hs") or entry.get("homeScore"),
                    away.get("score") or entry.get("away_score") or entry.get("as") or entry.get("awayScore"),
                    entry.get("qtr") or entry.get("quarter") or entry.get("q"),
                    entry.get("clock") or entry.get("time") or entry.get("t"),
                    entry.get("phase") or entry.get("status") or entry.get("p"),
                )
                if game:
                    games.append(game)
            return games
        if "h" in payload and "a" in payload:
            game = _normalize_alt_game(
                payload.get("h"),
                payload.get("a"),
                payload.get("hs") or payload.get("homeScore"),
                payload.get("as") or payload.get("awayScore"),
                payload.get("q") or payload.get("qtr"),
                payload.get("t") or payload.get("clock"),
                payload.get("p") or payload.get("status"),
            )
            if game:
                games.append(game)
            return games
    if isinstance(payload, list):
        for entry in payload:
            if isinstance(entry, dict):
                games.extend(_parse_alt_games(entry))
    return games


def _fetch_alt_games() -> List[Dict[str, Any]]:
    now = time.monotonic()
    cached = _alt_score_cache.get("games") or []
    if cached and now - float(_alt_score_cache.get("ts") or 0) < ALT_SCORE_TTL:
        return cached
    for url in ALT_SCORE_SOURCES:
        try:
            resp = _session.get(url, headers=HEADERS, timeout=ALT_SCORE_TIMEOUT_SEC)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            continue
        games = _parse_alt_games(data)
        if games:
            _alt_score_cache["ts"] = now
            _alt_score_cache["games"] = games
            return games
    _alt_score_cache["ts"] = now
    _alt_score_cache["games"] = []
    return []


def _alt_game_status(alt: Dict[str, Any]) -> str | None:
    status = str(alt.get("status") or "").lower()
    if any(tag in status for tag in ("final", "post", "ended", "complete")):
        return "final"
    period = alt.get("period")
    clock = alt.get("clock")
    if isinstance(period, int) and period > 0:
        return "live"
    if isinstance(clock, str) and re.search(r"\\d{1,2}:\\d{2}", clock):
        return "live"
    if status in ("in", "live", "progress", "inprogress"):
        return "live"
    return None


def _alt_game_header(alt: Dict[str, Any], status: str | None) -> str | None:
    if status == "final":
        return "Final"
    period = alt.get("period")
    clock = alt.get("clock") or ""
    if isinstance(period, int) and period > 0 and clock:
        return f"Q{period} {clock}".strip()
    if clock:
        return str(clock)
    return None


def _match_alt_game(
    alt_games: List[Dict[str, Any]], home_tri: str, away_tri: str
) -> tuple[Dict[str, Any] | None, bool]:
    home_norm = _normalize_match_tricode(home_tri)
    away_norm = _normalize_match_tricode(away_tri)
    for alt in alt_games:
        if alt.get("home") == home_norm and alt.get("away") == away_norm:
            return alt, False
        if alt.get("home") == away_norm and alt.get("away") == home_norm:
            return alt, True
    return None, False


def _apply_alt_override(
    home_team: Dict[str, Any],
    away_team: Dict[str, Any],
    game: Dict[str, Any],
    header: str,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], str]:
    alt_games = _fetch_alt_games()
    if not alt_games:
        return home_team, away_team, game, header
    alt, swapped = _match_alt_game(alt_games, home_team.get("teamTricode") or "", away_team.get("teamTricode") or "")
    if not alt:
        return home_team, away_team, game, header
    status = _alt_game_status(alt)
    if not status:
        return home_team, away_team, game, header
    alt_header = _alt_game_header(alt, status) or header
    home_score = alt.get("home_score")
    away_score = alt.get("away_score")
    if swapped:
        home_score, away_score = away_score, home_score
    if home_score is not None:
        home_team["score"] = home_score
    if away_score is not None:
        away_team["score"] = away_score
    period = alt.get("period")
    if isinstance(period, int) and period > 0:
        game["period"] = {"current": period}
    clock = alt.get("clock")
    if clock:
        game["gameClock"] = clock
    game["gameStatusText"] = alt_header
    game["status"] = status
    return home_team, away_team, game, alt_header


def _get_roster_positions(team_id: str) -> Dict[str, str]:
    tid = str(team_id or "")
    if not tid:
        return {}
    now = time.time()
    cached = _roster_cache.get(tid)
    if cached and (now - cached[0] <= ROSTER_TTL):
        return cached[1]
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{tid}?enable=roster"
    try:
        resp = _session.get(url, headers=HEADERS, timeout=ROSTER_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        team = (data.get("team") or {}) if isinstance(data, dict) else {}
        athletes = team.get("athletes") or []
    except Exception:
        return {}
    positions: Dict[str, str] = {}
    for athlete in athletes if isinstance(athletes, list) else []:
        aid = str(athlete.get("id") or "")
        pos = (athlete.get("position") or {}).get("abbreviation") or (athlete.get("position") or {}).get(
            "displayName"
        )
        if aid and pos:
            positions[aid] = pos
    _roster_cache[tid] = (now, positions)
    return positions


def _fetch_summary_players(
    game_id: str, home_tid: str | None = None, away_tid: str | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Pull player-level stats from ESPN boxscore feed to populate box tables.
    Falls back to empty lists on error.
    """
    url = f"https://cdn.espn.com/core/nfl/boxscore?gameId={game_id}&xhr=1&render=false"
    try:
        resp = _session.get(url, headers=HEADERS, timeout=BOXSCORE_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        box = (data.get("gamepackageJSON") or {}).get("boxscore", {}) or {}
    except Exception:
        return [], []

    players_block = box.get("players") or []
    teams_order: list[str] = []
    team_rosters: Dict[str, Dict[str, Any]] = {}
    roster_positions_by_team: Dict[str, Dict[str, str]] = {}

    for team_block in players_block:
        team_info = team_block.get("team", {}) or {}
        tid = str(team_info.get("id") or "")
        teams_order.append(tid)
        roster_positions = roster_positions_by_team.get(tid)
        if roster_positions is None:
            roster_positions = _get_roster_positions(tid) if tid else {}
            roster_positions_by_team[tid] = roster_positions
        roster = team_rosters.setdefault(tid, {})
        for stat_group in team_block.get("statistics", []) or []:
            labels = stat_group.get("labels") or []
            group_name = stat_group.get("name") or ""
            for athlete_entry in stat_group.get("athletes", []) or []:
                athlete = athlete_entry.get("athlete") or {}
                aid = str(athlete.get("id") or "")
                if not aid:
                    continue
                position = (athlete.get("position", {}) or {}).get("abbreviation") or (
                    athlete.get("position", {}) or {}
                ).get("displayName")
                if not position and roster_positions:
                    position = roster_positions.get(aid, "")
                player = roster.setdefault(
                    aid,
                    {
                        "firstName": (athlete.get("firstName") or athlete.get("displayName") or "").split(" ")[0],
                        "familyName": (
                            athlete.get("lastName")
                            or " ".join((athlete.get("displayName") or "").split(" ")[1:])
                        ).strip(),
                        "position": position or "",
                        "jerseyNum": str(athlete.get("jersey") or ""),
                        "_raw_stats": [],
                    },
                )
                stats_vals = athlete_entry.get("stats") or []
                for idx, val in enumerate(stats_vals):
                    label = labels[idx] if idx < len(labels) else f"stat_{idx}"
                    player["_raw_stats"].append((group_name, label, val))

    def _build_player(p: Dict[str, Any]) -> Dict[str, Any]:
        raw_stats = p.pop("_raw_stats", [])
        yards = 0
        touchdowns = 0
        penalties = 0
        receptions = 0
        targets = 0
        carries = 0
        interceptions = 0
        sacks = 0
        tfl = 0
        passes_defended = 0
        qb_hits = 0
        fumbles = 0
        tackles_total: int | None = None
        tackles_solo: int | None = None
        for group_name, label, val in raw_stats:
            group = str(group_name or "").lower()
            label_u = str(label or "").upper()
            iv = _to_int(val)

            if "PEN" in label_u:
                penalties += iv
            if group == "defensive":
                if label_u in ("TOT", "TOTAL"):
                    tackles_total = iv
                elif label_u == "SOLO":
                    tackles_solo = iv
                elif label_u == "SACKS":
                    sacks += iv
                elif label_u == "TFL":
                    tfl += iv
                elif label_u == "PD":
                    passes_defended += iv
                elif label_u == "QB HTS":
                    qb_hits += iv
                elif label_u == "TD":
                    touchdowns += iv
                continue
            if group == "interceptions":
                if label_u == "INT":
                    interceptions += iv
                elif label_u == "YDS":
                    yards += iv
                elif label_u == "TD":
                    touchdowns += iv
                continue
            if group == "receiving":
                if label_u == "REC":
                    receptions += iv
                elif label_u == "TGTS":
                    targets += iv
                if label_u == "YDS":
                    yards += iv
                elif label_u == "TD":
                    touchdowns += iv
                continue
            if group == "rushing":
                if label_u == "CAR":
                    carries += iv
                if label_u == "YDS":
                    yards += iv
                elif label_u == "TD":
                    touchdowns += iv
                continue
            if group == "passing":
                if label_u == "INT":
                    interceptions += iv
                if label_u == "YDS":
                    yards += iv
                elif label_u == "TD":
                    touchdowns += iv
                continue
            if group in ("kickreturns", "puntreturns"):
                if label_u == "YDS":
                    yards += iv
                elif label_u == "TD":
                    touchdowns += iv
                continue
            if group == "fumbles":
                if label_u == "FUM":
                    fumbles += iv
                continue
            if label_u == "TD":
                touchdowns += iv

        if tackles_total is None:
            if tackles_solo is not None:
                tackles_total = tackles_solo
            else:
                tackles_total = 0
        if tackles_solo is None:
            tackles_solo = 0
        tackles_assist = max(tackles_total - tackles_solo, 0)
        points = touchdowns * 6
        return {
            "firstName": p.get("firstName", ""),
            "familyName": p.get("familyName", ""),
            "position": p.get("position", ""),
            "jerseyNum": p.get("jerseyNum", ""),
            "statistics": {
                "isOnCourt": False,
                "points": points,
                "reboundsTotal": tackles_total,
                "assists": tackles_assist,
                "personalFouls": penalties,
                "yardsTotal": yards,
                "touchdowns": touchdowns,
                "tacklesTotal": tackles_total,
                "tacklesSolo": tackles_solo,
                "tacklesAssist": tackles_assist,
                "penalties": penalties,
                "receptions": receptions,
                "targets": targets,
                "carries": carries,
                "interceptions": interceptions,
                "sacks": sacks,
                "tacklesForLoss": tfl,
                "passesDefended": passes_defended,
                "qbHits": qb_hits,
                "fumbles": fumbles,
                "minutesCalculated": "",
            },
        }

    def _players_for_tid(tid: str | None) -> list[dict[str, Any]] | None:
        if not tid:
            return None
        roster = team_rosters.get(str(tid))
        if not roster:
            return None
        return [_build_player(p.copy()) for p in roster.values()]

    home_players = _players_for_tid(home_tid)
    away_players = _players_for_tid(away_tid)

    if home_players is None or away_players is None:
        if teams_order:
            if home_players is None:
                home_players = _players_for_tid(teams_order[0]) or []
            if away_players is None:
                fallback_away = teams_order[1] if len(teams_order) > 1 else None
                away_players = _players_for_tid(fallback_away) or []
        else:
            # fallback to roster order
            for _, roster in team_rosters.items():
                built = [_build_player(p.copy()) for p in roster.values()]
                if home_players is None:
                    home_players = built
                elif away_players is None:
                    away_players = built

    return home_players or [], away_players or []


def get_scoreboard() -> Dict[str, Any]:
    try:
        events = _fetch_scoreboard_events()
    except Exception:
        return _demo_scoreboard()

    games = []
    for ev in events:
        comp = (ev.get("competitions") or [{}])[0]
        status_block = (ev.get("status") or {}).get("type", {})
        state = status_block.get("state")
        period = status_block.get("period")
        if isinstance(period, str) and period.isdigit():
            period = int(period)
        clock = status_block.get("displayClock")
        start_time = ev.get("date")
        situation = comp.get("situation") or {}
        status_text_raw = status_block.get("shortDetail") or status_block.get("detail") or ""
        parsed_clock, parsed_period = _parse_clock_and_period(status_text_raw)
        if not clock:
            clock = parsed_clock
        if not period:
            period = parsed_period
        if isinstance(period, int) and period <= 0:
            period = None
        state = _coerce_state(state, status_text_raw, clock, period)
        state = _force_live_by_start(state, start_time)
        if period is None and state == "in" and clock and clock not in ("0:00", "00:00"):
            period = 1
        if state == "in" and (not clock or period is None):
            estimate = _estimate_period_and_clock(start_time)
            if estimate:
                est_clock, est_period = estimate
                if not clock:
                    clock = est_clock
                if period is None:
                    period = est_period
        short_down = situation.get("shortDownDistanceText") if isinstance(situation.get("shortDownDistanceText"), str) else ""
        long_down = situation.get("downDistanceText") if isinstance(situation.get("downDistanceText"), str) else ""
        computed_down = _down_distance_text(situation)
        if not short_down and computed_down:
            short_down = computed_down
        if not long_down and computed_down:
            long_down = computed_down
        down_text = short_down or long_down
        possession_text = situation.get("possessionText") or ""
        home_raw = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "home"), {})
        away_raw = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "away"), {})
        home_team = _map_team(home_raw)
        away_team = _map_team(away_raw)
        header = _header(state, period, clock, start_time)
        if "halftime" in status_text_raw.lower():
            if (period in (None, 2)) and (not clock or clock in ("0:00", "00:00")):
                header = "Halftime"
        game = {
            "gameId": str(ev.get("id")),
            "homeTeam": home_team,
            "awayTeam": away_team,
            "status": _status(state),
            "startTime": start_time,
            "header": header,
            "gameStatusText": header,
            "shortDownDistanceText": short_down or "",
            "downDistanceText": down_text or "",
            "possessionText": possession_text,
            "seasonYear": str(ev.get("season", {}).get("year") or "2025"),
        }
        home_team, away_team, game, header = _apply_alt_override(home_team, away_team, game, header)
        game["homeTeam"] = home_team
        game["awayTeam"] = away_team
        game["header"] = header
        game["gameStatusText"] = header
        games.append(game)
    lines = [_line(g) for g in games] if games else ["No games today."]
    if not games:
        return _demo_scoreboard()
    return {"games": games, "lines": lines}


def get_boxscore(game_id: str) -> Dict[str, Any]:
    now = time.time()
    cached = _boxscore_cache.get(str(game_id))
    if cached:
        cached_header = (
            (cached[1].get("game") or {}).get("gameStatusText")
            or cached[1].get("header")
            or ""
        )
        ttl = _boxscore_ttl_from_header(cached_header)
        if now - cached[0] <= ttl:
            if ttl == BOXSCORE_TTL_LIVE:
                cached_game = cached[1].get("game") or {}
                cached_home = cached[1].get("home") or {}
                cached_away = cached[1].get("away") or {}
                drive_state = _fetch_drive_state(str(game_id))
                _apply_drive_state_overrides(cached_game, cached_home, cached_away, drive_state)
            return cached[1]

    # Use scoreboard data as lightweight boxscore; augment with leaders as pseudo-players.
    try:
        events = _fetch_scoreboard_events()
    except Exception:
        events = []
        if cached:
            return cached[1]

    game = None
    home_players: list[dict[str, Any]] = []
    away_players: list[dict[str, Any]] = []

    for ev in events:
        if str(ev.get("id")) != str(game_id):
            continue
        comp = (ev.get("competitions") or [{}])[0]
        status_block = (ev.get("status") or {}).get("type", {})
        state = status_block.get("state")
        period = status_block.get("period")
        if isinstance(period, str) and period.isdigit():
            period = int(period)
        clock = status_block.get("displayClock")
        start_time = ev.get("date")
        situation = comp.get("situation") or {}
        status_text_raw = status_block.get("shortDetail") or status_block.get("detail") or ""
        parsed_clock, parsed_period = _parse_clock_and_period(status_text_raw)
        if not clock:
            clock = parsed_clock
        if not period:
            period = parsed_period
        if isinstance(period, int) and period <= 0:
            period = None
        state = _coerce_state(state, status_text_raw, clock, period)
        state = _force_live_by_start(state, start_time)
        if period is None and state == "in" and clock and clock not in ("0:00", "00:00"):
            period = 1
        if state == "in" and (not clock or period is None):
            estimate = _estimate_period_and_clock(start_time)
            if estimate:
                est_clock, est_period = estimate
                if not clock:
                    clock = est_clock
                if period is None:
                    period = est_period
        short_down = situation.get("shortDownDistanceText") if isinstance(situation.get("shortDownDistanceText"), str) else ""
        long_down = situation.get("downDistanceText") if isinstance(situation.get("downDistanceText"), str) else ""
        computed_down = _down_distance_text(situation)
        if not short_down and computed_down:
            short_down = computed_down
        if not long_down and computed_down:
            long_down = computed_down
        down_text = short_down or long_down
        possession_text = situation.get("possessionText") or ""
        header = _header(state, period, clock, start_time)
        if "halftime" in status_text_raw.lower():
            if (period in (None, 2)) and (not clock or clock in ("0:00", "00:00")):
                header = "Halftime"
        home_raw = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "home"), {})
        away_raw = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "away"), {})
        home_team = _map_team(home_raw)
        away_team = _map_team(away_raw)
        # prefer summary players; fall back to leaders and finally team totals
        home_players, away_players = _fetch_summary_players(
            game_id, home_team.get("teamId"), away_team.get("teamId")
        )
        if not home_players and not away_players:
            home_players = _build_players_from_leaders(home_raw.get("leaders") or [])
            away_players = _build_players_from_leaders(away_raw.get("leaders") or [])
        if not home_players:
            home_players = _build_team_totals_player(home_raw)
        if not away_players:
            away_players = _build_team_totals_player(away_raw)
        game = {
            "gameClock": clock,
            "shotClock": None,
            "period": {"current": period} if period else {},
            "gameStatusText": header,
            "shortDownDistanceText": short_down or "",
            "downDistanceText": down_text or "",
            "possessionText": possession_text,
        }
        home_team, away_team, game, header = _apply_alt_override(home_team, away_team, game, header)
        drive_state = _fetch_drive_state(str(game_id))
        clock, period = _apply_drive_state_overrides(game, home_team, away_team, drive_state)
        header = _header(state, period, clock, start_time)
        game["gameStatusText"] = header
        game_entry = {
            "gameId": str(ev.get("id")),
            "homeTeam": home_team,
            "awayTeam": away_team,
            "status": game.get("status") or _status(state),
            "startTime": start_time,
            "header": header,
            "gameStatusText": header,
            "seasonYear": str(ev.get("season", {}).get("year") or "2025"),
        }
        break

    if not game:
        # fallback to lighter scoreboard cache
        board = get_scoreboard()
        game_entry = next((g for g in board.get("games", []) if g.get("gameId") == game_id), None)
        if not game_entry:
            return _demo_boxscore(game_id)
        header = game_entry.get("header") or _header(game_entry.get("status"), None, None, game_entry.get("startTime"))
        game = {"gameClock": None, "shotClock": None, "period": {"current": None}, "gameStatusText": header}
        home_team = game_entry.get("homeTeam", {})
        away_team = game_entry.get("awayTeam", {})
    else:
        header = game_entry["header"]
        home_team = game_entry["homeTeam"]
        away_team = game_entry["awayTeam"]

    result = {
        "game": game,
        "home": {**home_team, "players": home_players},
        "away": {**away_team, "players": away_players},
        "header": header,
        "shotclock": "--",
    }
    apply_starting_lineups("NFL", result["home"], result["away"])
    _boxscore_cache[str(game_id)] = (now, result)
    return result


def get_team_colors(tricode: str) -> Dict[str, str]:
    tri = (tricode or "").upper()
    return {
        "primary": TEAM_PRIMARY_COLORS.get(tri, "#444444"),
        "secondary": TEAM_SECONDARY_COLORS.get(tri, "#2b2b2b"),
        "accent": TEAM_ACCENT_COLORS.get(tri, "#777777"),
    }


def get_team_logo(team_id: str | None, tricode: str | None) -> bytes | None:
    tri = (tricode or "").upper()
    key = (team_id or "", tri)
    if key in _logo_cache:
        return _logo_cache[key]
    cache_path = LOGO_DIR / f"{team_id or tri or 'unknown'}.png"
    if cache_path.exists():
        try:
            data = cache_path.read_bytes()
            _logo_cache[key] = data
            return data
        except Exception:
            pass
    urls = []
    if tri:
        urls.append(f"https://static.www.nfl.com/league/api/clubs/logos/{tri}.png")
        urls.append(f"https://a.espncdn.com/i/teamlogos/nfl/500/{tri}.png")
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


# legacy compat
def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    return get_team_logo(team_id, tricode)


def safe_score(team: Dict[str, Any]) -> int:
    try:
        return int(team.get("score") or 0)
    except Exception:
        return 0


def format_time_played(value: Any) -> str:
    # NFL doesn't use minutes; return empty or passthrough string.
    if value in (None, "", 0):
        return ""
    return str(value)


def format_shotclock(value: Any) -> str:
    return "--"


# -------------- record helpers --------------
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


# -------------- helpers --------------
def _map_team(raw: Dict[str, Any]) -> Dict[str, Any]:
    team = raw.get("team", {}) or {}
    tri = (team.get("abbreviation") or team.get("shortDisplayName") or "TM").upper()
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
    return mapped


def _parse_leader_display(display: Any) -> tuple[int, int]:
    text = str(display or "").upper()
    yards = 0
    tds = 0
    yd_match = re.search(r"(\d+)\s*YDS", text)
    if yd_match:
        yards = int(yd_match.group(1))
    td_matches = re.findall(r"(\d+)\s*TD", text)
    if td_matches:
        tds = sum(int(x) for x in td_matches)
    return yards, tds


def _parse_leader_tackles(display: Any) -> int:
    text = str(display or "").upper()
    match = re.search(r"(\d+)\s*(?:TACKLES|TACKLE|TKL|TOT)", text)
    if match:
        return int(match.group(1))
    return 0


def _build_players_from_leaders(leaders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert ESPN leaders into pseudo-player rows for the table.
    """
    players: List[Dict[str, Any]] = []
    for lead in leaders:
        cat = (lead.get("name") or lead.get("displayName") or "").lower()
        entries = lead.get("leaders") or []
        for ent in entries:
            athlete = ent.get("athlete") or {}
            display = athlete.get("displayName") or athlete.get("fullName") or "Player"
            names = display.split(" ", 1)
            first = names[0]
            last = names[1] if len(names) > 1 else ""
            pos = athlete.get("position", {}).get("abbreviation") or athlete.get("position", {}).get("displayName") or ""
            jersey = athlete.get("jersey") or ""
            value = ent.get("value")
            display_val = ent.get("displayValue") or ""
            yards, touchdowns = _parse_leader_display(display_val)
            if yards == 0 and any(tok in cat for tok in ("yard", "passing", "rushing", "receiving")):
                yards = _to_int(value)
            if touchdowns == 0 and ("touchdown" in cat or cat.endswith("td") or "td" in cat):
                touchdowns = _to_int(value or display_val)
            tackles = 0
            if "tack" in cat:
                tackles = _to_int(value or display_val)
                if tackles == 0:
                    tackles = _parse_leader_tackles(display_val)
            penalties = _to_int(value or display_val) if "pen" in cat else 0
            points = touchdowns * 6
            stats = {
                "isOnCourt": False,
                "points": points,
                "reboundsTotal": tackles,
                "assists": 0,
                "personalFouls": penalties,
                "yardsTotal": yards,
                "touchdowns": touchdowns,
                "tacklesTotal": tackles,
                "tacklesSolo": 0,
                "tacklesAssist": 0,
                "penalties": penalties,
                "minutesCalculated": "",
            }
            players.append(
                {
                    "firstName": first,
                    "familyName": last,
                    "position": pos,
                    "jerseyNum": str(jersey),
                    "statistics": stats,
                }
            )
    # If nothing, return a single team summary row.
    if not players:
        players.append(
            {
                "firstName": "Team",
                "familyName": "Totals",
                "position": "",
                "jerseyNum": "",
                "statistics": {
                    "isOnCourt": False,
                    "points": 0,
                    "reboundsTotal": 0,
                    "assists": 0,
                    "personalFouls": 0,
                    "yardsTotal": 0,
                    "touchdowns": 0,
                    "tacklesTotal": 0,
                    "tacklesSolo": 0,
                    "tacklesAssist": 0,
                    "penalties": 0,
                    "minutesCalculated": "",
                },
            }
        )
    return players


def _build_team_totals_player(comp: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Create a single pseudo-player row from competitor statistics.
    """
    stats_block = comp.get("statistics") or []
    pts = 0
    tackles = 0
    assists = 0
    penalties = 0
    yards = 0
    touchdowns = 0
    for stat in stats_block:
        name = (stat.get("name") or "").lower()
        try:
            ivalue = int(float(stat.get("displayValue") or 0))
        except Exception:
            ivalue = 0
        if "points" in name or name == "score":
            pts += ivalue
        if "tackle" in name or name in ("totaltackle", "totaltackles"):
            tackles += ivalue
        if "assist" in name:
            assists += ivalue
        if "penal" in name:
            penalties += ivalue
        if "touchdown" in name or name in ("td", "tds", "touchdowns"):
            touchdowns += ivalue
        if yards == 0 and "yard" in name and "pen" not in name:
            yards = ivalue
    return [
        {
            "firstName": "Team",
            "familyName": "Totals",
            "position": "",
            "jerseyNum": "",
            "statistics": {
                "isOnCourt": False,
                "points": pts,
                "reboundsTotal": tackles,
                "assists": assists,
                "personalFouls": penalties,
                "yardsTotal": yards,
                "touchdowns": touchdowns,
                "tacklesTotal": tackles,
                "tacklesSolo": 0,
                "tacklesAssist": assists,
                "penalties": penalties,
                "minutesCalculated": "",
            },
        }
    ]


def build_player_rows(team: Dict[str, Any]) -> List[List[str]]:
    rows: List[List[str]] = []
    players = team.get("players", []) or []
    for p in players:
        stats = p.get("statistics", {}) or {}
        jersey = p.get("jerseyNum") or ""
        name = format_player_initial_name(p.get("firstName"), p.get("familyName"))
        pos = p.get("position") or ""

        yards_val = stats.get("yardsTotal")
        if yards_val is None:
            yards = _to_int(stats.get("assists"))
            if yards:
                yards *= 10
        else:
            yards = _to_int(yards_val)

        td_val = stats.get("touchdowns")
        if td_val is None:
            td_val = _to_int(stats.get("points")) // 6
        touchdowns = _to_int(td_val)

        tackles_val = stats.get("tacklesTotal")
        if tackles_val is None:
            tackles_val = stats.get("reboundsTotal")
        tackles = _to_int(tackles_val)

        assists_val = stats.get("tacklesAssist")
        if assists_val is None:
            solo_val = stats.get("tacklesSolo")
            if solo_val is not None:
                assists_val = max(tackles - _to_int(solo_val), 0)
            else:
                assists_val = 0
        assists = _to_int(assists_val)

        penalties_val = stats.get("penalties")
        if penalties_val is None:
            penalties_val = stats.get("personalFouls")
        penalties = _to_int(penalties_val)

        rows.append([jersey, name, pos, str(yards), str(touchdowns), str(tackles), str(assists), str(penalties)])
    return rows


def _line(g: Dict[str, Any]) -> str:
    away = g.get("awayTeam", {}) or {}
    home = g.get("homeTeam", {}) or {}
    return f"{away.get('teamTricode','AWY')} {away.get('score',0)} @ {home.get('teamTricode','HME')} {home.get('score',0)} ({g.get('header','')})"


def _demo_scoreboard() -> Dict[str, Any]:
    now = time.time()
    games = [
        {
            "gameId": "NFL_DEMO",
            "homeTeam": {"teamId": "DAL", "teamName": "Cowboys", "teamTricode": "DAL", "score": 0},
            "awayTeam": {"teamId": "PHI", "teamName": "Eagles", "teamTricode": "PHI", "score": 0},
            "status": "upcoming",
            "startTime": now + 3600,
            "header": format_start_time(now + 3600),
            "seasonYear": "2025",
        }
    ]
    return {"games": games, "lines": [_line(games[0])]}


def _demo_boxscore(game_id: str) -> Dict[str, Any]:
    board = _demo_scoreboard()
    g = board["games"][0]
    return {
        "game": {"gameClock": None, "shotClock": None, "period": {"current": 0}, "gameStatusText": g["header"]},
        "home": {**g["homeTeam"], "players": []},
        "away": {**g["awayTeam"], "players": []},
        "header": g["header"],
        "shotclock": "--",
    }


# compatibility aliases for UI that still expects fetch_* names
fetch_scoreboard = get_scoreboard
fetch_boxscore = get_boxscore
