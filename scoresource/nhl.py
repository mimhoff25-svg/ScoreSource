from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, Tuple

import requests
import logging

from .common.lineups import apply_starting_lineups
from .common.timefmt import format_start_time, normalize_espn_time_str
from .common.utils import format_player_initial_name


def _env_float(name: str, default: float, *, min_value: float | None = None) -> float:
    raw = os.environ.get(name)
    if raw is None:
        value = default
    else:
        try:
            value = float(raw)
        except Exception as exc:
            logger.debug("_env_float: invalid float for %s=%r: %s", name, raw, exc)
            value = default
    if min_value is None:
        return value
    return value if value >= min_value else min_value


def _cache_root_from_env() -> Path:
    raw = os.environ.get("SCORESOURCE_CACHE_DIR")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".cache" / "scoresource"


SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"
BOXSCORE_URL = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary?event={game_id}"
HEADERS = {"User-Agent": "ScoreSource/1.0", "Referer": "https://www.espn.com"}

CACHE_ROOT = _cache_root_from_env()
SCOREBOARD_CACHE_PATH = CACHE_ROOT / "nhl_scoreboard.json"
LOGO_DIR = CACHE_ROOT / "logos" / "nhl"
LOGO_DIR.mkdir(parents=True, exist_ok=True)
LOGO_VERSION = "2025-05"
_logo_cache: Dict[Tuple[str, str, str], bytes | None] = {}
_session = requests.Session()
_boxscore_cache: Dict[str, Tuple[float, float, Dict[str, Any]]] = {}
_scoreboard_cache: Dict[str, Any] = {"ts": 0.0, "data": None}
_summary_cache: Dict[str, Tuple[float, float, Dict[str, Any]]] = {}
_cache_lock = threading.Lock()

logger = logging.getLogger(__name__)

SCOREBOARD_TTL = _env_float("SCORESOURCE_NHL_SCOREBOARD_TTL", 15.0, min_value=0.0)
SCOREBOARD_TTL_LIVE = _env_float("SCORESOURCE_NHL_SCOREBOARD_TTL_LIVE", min(SCOREBOARD_TTL, 5.0), min_value=0.0)
SCOREBOARD_TTL_PREGAME = _env_float("SCORESOURCE_NHL_SCOREBOARD_TTL_PREGAME", SCOREBOARD_TTL, min_value=0.0)
SCOREBOARD_TTL_FINAL = _env_float("SCORESOURCE_NHL_SCOREBOARD_TTL_FINAL", max(SCOREBOARD_TTL, 30.0), min_value=0.0)
BOXSCORE_TTL_LIVE = _env_float("SCORESOURCE_NHL_BOXSCORE_TTL_LIVE", 3.0, min_value=0.0)
BOXSCORE_TTL_PREGAME = _env_float("SCORESOURCE_NHL_BOXSCORE_TTL_PREGAME", 60.0, min_value=0.0)
BOXSCORE_TTL_FINAL = _env_float("SCORESOURCE_NHL_BOXSCORE_TTL_FINAL", 60.0 * 60 * 24 * 7, min_value=0.0)
SUMMARY_TTL_LIVE = _env_float("SCORESOURCE_NHL_SUMMARY_TTL_LIVE", 2.5, min_value=0.0)
SUMMARY_TTL_PREGAME = _env_float("SCORESOURCE_NHL_SUMMARY_TTL_PREGAME", 30.0, min_value=0.0)
SUMMARY_TTL_FINAL = _env_float("SCORESOURCE_NHL_SUMMARY_TTL_FINAL", 60.0 * 30, min_value=0.0)
SCOREBOARD_TIMEOUT_SEC = _env_float("SCORESOURCE_NHL_SCOREBOARD_TIMEOUT_SEC", 5.0, min_value=1.0)
BOXSCORE_TIMEOUT_SEC = _env_float("SCORESOURCE_NHL_BOXSCORE_TIMEOUT_SEC", 8.0, min_value=1.0)
LOGO_TIMEOUT_SEC = _env_float("SCORESOURCE_NHL_LOGO_TIMEOUT_SEC", 5.0, min_value=1.0)

from .common.colors import (
    TRICODE_ALIASES,
    TEAM_PRIMARY_COLORS,
    TEAM_SECONDARY_COLORS,
    TEAM_ACCENT_COLORS,
    TEAM_ALT_COLORS,
    get_team_colors,
)

sport_table_headers = ["#", "Player", "Pos", "G", "A", "PTS", "SOG", "PIM", "SV", "SV%"]


def _normalize_tricode(tricode: str | None) -> str:
    tri = (tricode or "").upper()
    return TRICODE_ALIASES.get(tri, tri)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        logger.exception("Failed to load JSON from %s: %s", path, exc)
        return None


def _save_json(path: Path, payload: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
    except Exception as exc:
        logger.exception("Failed to save JSON to %s: %s", path, exc)


def _load_disk_scoreboard() -> Dict[str, Any] | None:
    data = _load_json(SCOREBOARD_CACHE_PATH)
    return data if isinstance(data, dict) else None


def _save_disk_scoreboard(payload: Dict[str, Any]) -> None:
    _save_json(SCOREBOARD_CACHE_PATH, payload)


def _fetch_summary_payload(game_id: str, *, status_hint: str | None = None) -> Dict[str, Any] | None:
    cache_key = str(game_id)
    now = time.monotonic()
    ttl = _summary_ttl_for_status(status_hint)
    with _cache_lock:
        cached = _summary_cache.get(cache_key)
        if cached and now - cached[0] < cached[1]:
            return cached[2]
    try:
        resp = _session.get(BOXSCORE_URL.format(game_id=game_id), headers=HEADERS, timeout=BOXSCORE_TIMEOUT_SEC)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.exception("_fetch_summary_payload failed for game_id=%s: %s", game_id, exc)
        with _cache_lock:
            cached = _summary_cache.get(cache_key)
            return cached[2] if cached else None
    if not isinstance(payload, dict):
        return None
    with _cache_lock:
        _summary_cache[cache_key] = (now, ttl, payload)
    return payload


def _to_int(val: Any) -> int:
    try:
        return int(float(val))
    except Exception:
        return 0


def _status_from_state(state: str | None) -> str:
    if state == "post":
        return "final"
    if state == "pre":
        return "upcoming"
    return "live"


def _boxscore_ttl_for_status(status: str | None) -> float:
    if status == "final":
        return BOXSCORE_TTL_FINAL
    if status == "upcoming":
        return BOXSCORE_TTL_PREGAME
    return BOXSCORE_TTL_LIVE


def _summary_ttl_for_status(status: str | None) -> float:
    if status == "final":
        return SUMMARY_TTL_FINAL
    if status == "upcoming":
        return SUMMARY_TTL_PREGAME
    return SUMMARY_TTL_LIVE


def _scoreboard_ttl_for_payload(payload: Dict[str, Any] | None) -> float:
    if not isinstance(payload, dict):
        return SCOREBOARD_TTL
    games = payload.get("games")
    if not isinstance(games, list) or not games:
        return SCOREBOARD_TTL
    statuses = {str((g or {}).get("status") or "").lower() for g in games if isinstance(g, dict)}
    if "live" in statuses:
        return SCOREBOARD_TTL_LIVE
    if "upcoming" in statuses:
        return SCOREBOARD_TTL_PREGAME
    if "final" in statuses:
        return SCOREBOARD_TTL_FINAL
    return SCOREBOARD_TTL


def _period_label(period: int | None, status_text: str | None = None) -> str:
    text = (status_text or "").upper()
    if "SHOOTOUT" in text or "SO" in text:
        return "SO"
    if period in (1, 2, 3):
        return f"P{period}"
    if period and period > 3:
        return "OT" if period == 4 else f"OT{period - 3}"
    return ""


def _parse_clock_and_period(status_text: str | None) -> tuple[str | None, int | None]:
    if not status_text:
        return None, None
    text = str(status_text).strip()
    clock_match = re.search(r"(\d{1,2}:\d{2})", text)
    clock = clock_match.group(1) if clock_match else None
    period = None
    upper = text.upper()
    match = re.search(r"\b([1-4])(ST|ND|RD|TH)\b", upper)
    if match:
        try:
            period = int(match.group(1))
        except Exception as exc:
            logger.debug("_parse_clock_and_period failed parsing period from %r: %s", match.group(1), exc)
            period = None
    if period is None:
        match = re.search(r"\bPERIOD\s*([1-4])\b", upper)
        if match:
            try:
                period = int(match.group(1))
            except Exception as exc:
                logger.debug("_parse_clock_and_period failed parsing PERIOD from %r: %s", match.group(1), exc)
                period = None
    return clock, period


def _clock_to_seconds(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    match = re.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", text)
    if match:
        minutes = int(match.group(1) or 0)
        seconds_val = float(match.group(2) or 0)
        return max(0, int(minutes * 60 + seconds_val))
    match = re.match(r"^(\d+):(\d{2})$", text)
    if match:
        return max(0, int(match.group(1)) * 60 + int(match.group(2)))
    return None


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
    match = re.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", text)
    if match:
        minutes = int(match.group(1) or 0)
        seconds_val = float(match.group(2) or 0)
        seconds = int(seconds_val)
        return f"{minutes}:{seconds:02d}"
    match = re.match(r"^(\d+):(\d{2})$", text)
    if match:
        return f"{int(match.group(1))}:{int(match.group(2)):02d}"
    return text


def _penalty_duration_seconds(play: Dict[str, Any]) -> int:
    for key in ("penaltyMinutes", "minutes"):
        val = play.get(key)
        if val is None and isinstance(play.get("penalty"), dict):
            val = play["penalty"].get(key)
        if val is None and isinstance(play.get("type"), dict):
            val = play["type"].get(key)
        if val is not None:
            try:
                return max(60, int(float(val)) * 60)
            except Exception as exc:
                logger.debug("_penalty_duration_seconds failed parsing val=%r: %s", val, exc)
                pass
    text = str(play.get("text") or "")
    lowered = text.lower()
    match = re.search(r"\b(\d+)\s*(?:min|minute)", lowered)
    if match:
        try:
            return max(60, int(match.group(1)) * 60)
        except Exception as exc:
            logger.debug("_penalty_duration_seconds failed parsing match %r: %s", match.group(1), exc)
            pass
    if "double minor" in lowered:
        return 4 * 60
    if "major" in lowered:
        return 5 * 60
    if "misconduct" in lowered:
        return 10 * 60
    return 2 * 60


def _penalty_is_cancelable(play: Dict[str, Any], duration: int) -> bool:
    if duration <= 0:
        return False
    text = str(play.get("text") or "").lower()
    if isinstance(play.get("type"), dict):
        type_info = play["type"]
        text = f"{text} {type_info.get('text') or ''} {type_info.get('penaltyType') or ''}".lower()
    if "major" in text or "misconduct" in text or "match" in text:
        return False
    return duration <= 4 * 60


def _is_shootout_status(status_text: str | None) -> bool:
    if not status_text:
        return False
    text = str(status_text).upper()
    return "SHOOTOUT" in text or re.search(r"\bSO\b", text) is not None


def _linescore_value(entry: Dict[str, Any]) -> int | None:
    for key in ("displayValue", "value", "score"):
        if key in entry:
            try:
                return int(float(entry.get(key) or 0))
            except Exception as exc:
                logger.debug("_linescore_value failed for key=%s entry=%r: %s", key, entry, exc)
                return None
    return None


def _shootout_score_from_linescores(linescores: list[Dict[str, Any]] | None, status_text: str | None) -> int | None:
    if not linescores or not _is_shootout_status(status_text):
        return None
    for entry in linescores:
        if entry.get("period") == 5:
            value = _linescore_value(entry)
            if value is not None:
                return value
    if len(linescores) >= 5:
        value = _linescore_value(linescores[4])
        if value is not None:
            return value
    return None


def _shootout_scores_from_competitors(
    competitors: list[Dict[str, Any]] | None, status_text: str | None
) -> Dict[str, int]:
    scores: Dict[str, int] = {}
    if not competitors or not _is_shootout_status(status_text):
        return scores
    for comp in competitors:
        team = comp.get("team", {}) or {}
        team_id = str(team.get("id") or "")
        tri = _normalize_tricode(team.get("abbreviation") or team.get("shortDisplayName") or "")
        so_score = _shootout_score_from_linescores(comp.get("linescores"), status_text)
        if so_score is None:
            continue
        if team_id:
            scores[team_id] = so_score
        if tri:
            scores[tri] = so_score
    return scores


def _apply_shootout_score(team: Dict[str, Any], scores: Dict[str, int]) -> None:
    if not scores:
        return
    for key in (str(team.get("teamId") or ""), str(team.get("teamTricode") or "")):
        if key and key in scores:
            team["shootoutScore"] = scores[key]
            return


def _plays_indicate_shootout(plays: list[Dict[str, Any]] | None) -> bool:
    if not plays:
        return False
    for play in plays:
        text = str(play.get("text") or "").lower()
        if "shootout" in text:
            return True
        play_type = str((play.get("type") or {}).get("text") or "").lower()
        if "shootout" in play_type:
            return True
        period = (play.get("period") or {}).get("number")
        period_label = str((play.get("period") or {}).get("displayValue") or "").lower()
        if period == 5 and "so" in period_label:
            return True
    return False


def _penalty_clocks_from_plays(
    plays: list[Dict[str, Any]], current_period: int, current_clock_secs: int
) -> Dict[str, list[int]]:
    if current_period is None or current_clock_secs is None:
        return {}
    period_len = 20 * 60
    max_clock_by_period: Dict[int, int] = {}
    for play in plays:
        period_num = (play.get("period") or {}).get("number")
        if not isinstance(period_num, int) or period_num < 4:
            continue
        clock_secs = _clock_to_seconds((play.get("clock") or {}).get("displayValue"))
        if clock_secs is None:
            continue
        max_clock_by_period[period_num] = max(max_clock_by_period.get(period_num, 0), clock_secs)
    period_lengths: Dict[int, int] = {1: period_len, 2: period_len, 3: period_len}
    if current_period >= 4:
        period_lengths[current_period] = period_len if current_clock_secs > 5 * 60 else 5 * 60
    for per, max_clock in max_clock_by_period.items():
        if max_clock >= 10 * 60:
            period_lengths[per] = period_len
        elif per not in period_lengths:
            period_lengths[per] = 5 * 60

    def _period_start_elapsed(period_num: int) -> int:
        total = 0
        for per in range(1, period_num):
            total += period_lengths.get(per, period_len)
        return total

    current_period_len = period_lengths.get(current_period, period_len)
    current_elapsed_in_period = max(0, current_period_len - current_clock_secs)
    current_elapsed = _period_start_elapsed(current_period) + current_elapsed_in_period

    events: list[tuple[int, int, Dict[str, Any]]] = []
    for idx, play in enumerate(plays):
        period_num = (play.get("period") or {}).get("number")
        if not isinstance(period_num, int):
            continue
        clock_secs = _clock_to_seconds((play.get("clock") or {}).get("displayValue"))
        if clock_secs is None:
            continue
        period_len_for_play = period_lengths.get(period_num, period_len)
        if clock_secs > period_len_for_play:
            continue
        play_elapsed = _period_start_elapsed(period_num) + max(0, period_len_for_play - clock_secs)
        if play_elapsed > current_elapsed:
            continue
        seq_raw = play.get("sequenceNumber")
        try:
            seq = int(seq_raw)
        except Exception as exc:
            logger.debug("_penalty_clocks_from_plays: invalid seq %r, using idx=%s: %s", seq_raw, idx, exc)
            seq = idx
        events.append((play_elapsed, seq, play))

    events.sort(key=lambda item: (item[0], item[1]))
    active: list[Dict[str, Any]] = []
    last_elapsed = 0

    def _advance_time(delta: int) -> None:
        if delta <= 0:
            return
        for penalty in active:
            penalty["remaining"] -= delta
        active[:] = [penalty for penalty in active if penalty["remaining"] > 0]

    def _is_power_play_goal(play: Dict[str, Any]) -> bool:
        if str((play.get("type") or {}).get("text") or "").lower() != "goal":
            return False
        strength = str((play.get("strength") or {}).get("text") or "").lower()
        return "power play" in strength

    def _is_penalty_play(play: Dict[str, Any]) -> bool:
        penalty = play.get("penalty")
        if isinstance(penalty, dict) and any(penalty.get(key) not in (None, "") for key in ("penaltyMinutes", "minutes", "penaltyType")):
            return True
        play_type = play.get("type")
        if isinstance(play_type, dict) and any(
            play_type.get(key) not in (None, "") for key in ("penaltyMinutes", "minutes", "penaltyType")
        ):
            return True
        play_type_text = str((play_type or {}).get("text") or "").lower()
        if play_type_text == "penalty":
            return True
        lowered = str(play.get("text") or "").lower()
        return " penalty" in lowered or lowered.startswith("penalty ")

    for play_elapsed, _, play in events:
        _advance_time(play_elapsed - last_elapsed)
        last_elapsed = play_elapsed

        if _is_penalty_play(play):
            team_id = str((play.get("team") or {}).get("id") or "")
            if not team_id:
                continue
            duration = _penalty_duration_seconds(play)
            if duration <= 0:
                continue
            active.append(
                {
                    "team_id": team_id,
                    "remaining": duration,
                    "duration": duration,
                    "start_elapsed": play_elapsed,
                    "cancelable": _penalty_is_cancelable(play, duration),
                }
            )
            continue
        if _is_power_play_goal(play):
            scoring_team = str((play.get("team") or {}).get("id") or "")
            if not scoring_team:
                continue
            candidates = [pen for pen in active if pen["team_id"] != scoring_team and pen["cancelable"]]
            if not candidates:
                continue
            victim = min(candidates, key=lambda pen: pen["remaining"])
            victim["remaining"] = max(0, victim["remaining"] - 120)
            if victim["remaining"] <= 0:
                active.remove(victim)

    _advance_time(current_elapsed - last_elapsed)

    visible_indices = set(range(len(active)))
    for idx, penalty in enumerate(active):
        if idx not in visible_indices:
            continue
        for other_idx in range(idx + 1, len(active)):
            if other_idx not in visible_indices:
                continue
            other = active[other_idx]
            if penalty.get("team_id") == other.get("team_id"):
                continue
            if penalty.get("start_elapsed") != other.get("start_elapsed"):
                continue
            if int(penalty.get("duration") or 0) != int(other.get("duration") or 0):
                continue
            visible_indices.discard(idx)
            visible_indices.discard(other_idx)
            break

    by_team: Dict[str, list[int]] = {}
    for idx, penalty in enumerate(active):
        if idx not in visible_indices:
            continue
        remaining = int(penalty.get("remaining") or 0)
        if remaining <= 0:
            continue
        team_id = penalty.get("team_id")
        if not team_id:
            continue
        by_team.setdefault(team_id, []).append(remaining)
    for team_id, penalties in list(by_team.items()):
        if not penalties:
            by_team.pop(team_id, None)
            continue
        by_team[team_id] = sorted(penalties)
    return by_team


def _header_from_event(status: str, status_text: str | None, period: int | None, clock: str | None, start: Any) -> str:
    if status == "upcoming":
        # Prefer converting the raw ISO start time; fall back to normalizing
        # ESPN's "7:00 PM EST"-style shortDetail string.
        ct = format_start_time(start)
        if ct == "Starts TBA" and status_text:
            ct = normalize_espn_time_str(status_text) or status_text
        return ct
    if status == "final":
        return status_text or "Final"
    if status_text:
        return status_text
    label = _period_label(period, status_text)
    if label or clock:
        return f"{label} {clock or ''}".strip()
    return "Live"


def _extract_team_shots(stats_list: list[Dict[str, Any]]) -> int | None:
    preferred_names = {"shotstotal", "shots", "shotsongoal"}
    preferred_labels = {"shots", "shots on goal"}
    for stat in stats_list:
        name = str(stat.get("name") or "").lower()
        label = str(stat.get("label") or stat.get("displayName") or "").lower()
        if name == "shootoutgoals" or label == "shootout goals":
            continue
        if name in preferred_names or label in preferred_labels:
            raw = stat.get("displayValue")
            if raw in (None, ""):
                raw = stat.get("value")
            return _to_int(raw)
    for stat in stats_list:
        abbreviation = str(stat.get("abbreviation") or "").lower()
        name = str(stat.get("name") or "").lower()
        label = str(stat.get("label") or stat.get("displayName") or "").lower()
        if name == "shootoutgoals" or label == "shootout goals":
            continue
        if abbreviation == "sog":
            raw = stat.get("displayValue")
            if raw in (None, ""):
                raw = stat.get("value")
            return _to_int(raw)
    return None


def _sum_player_shots(players: list[Dict[str, Any]]) -> int:
    total = 0
    for player in players:
        stats = player.get("statistics", {}) or {}
        total += _to_int(stats.get("shotsOnGoal"))
    return total


def _fetch_boxscore_players(
    game_id: str,
    *,
    current_period: int | None = None,
    current_clock: Any = None,
    status_hint: str | None = None,
) -> tuple[
    Dict[str, list[Dict[str, Any]]],
    Dict[str, Dict[str, Any]],
    Dict[str, list[int]],
    str | None,
    int | None,
    str | None,
    Dict[str, int],
    Dict[str, int | None],
]:
    data = _fetch_summary_payload(game_id, status_hint=status_hint)
    if not isinstance(data, dict):
        return {}, {}, {}, None, None, None, {}, {"home": None, "away": None}

    box = data.get("boxscore", {}) if isinstance(data, dict) else {}
    players_block = box.get("players") or []
    players_by_team: Dict[str, list[Dict[str, Any]]] = {}
    team_stats_by_team: Dict[str, Dict[str, Any]] = {}
    penalty_clocks: Dict[str, list[int]] = {}
    on_ice_by_team: Dict[str, list[str]] = {}
    on_ice_order_by_team: Dict[str, Dict[str, int]] = {}
    summary_clock: str | None = None
    summary_period: int | None = None
    summary_status_text: str | None = None
    shootout_scores: Dict[str, int] = {}
    summary_scores: Dict[str, int | None] = {"home": None, "away": None}
    plays: list[Dict[str, Any]] | None = None
    if isinstance(data, dict):
        comps = (data.get("header") or {}).get("competitions") or []
        comp = comps[0] if comps else {}
        for competitor in comp.get("competitors") or []:
            side = str(competitor.get("homeAway") or "").lower()
            if side in summary_scores:
                summary_scores[side] = _to_int(competitor.get("score"))
        status = comp.get("status") or {}
        summary_clock = status.get("displayClock") or status.get("clock")
        summary_period = status.get("period") if isinstance(status.get("period"), int) else None
        status_type = status.get("type") or {}
        summary_status_text = status_type.get("shortDetail") or status_type.get("detail")
        plays = data.get("plays") if isinstance(data.get("plays"), list) else None
        shootout_status = summary_status_text
        if not _is_shootout_status(shootout_status) and _plays_indicate_shootout(plays):
            shootout_status = "SO"
        shootout_scores = _shootout_scores_from_competitors(comp.get("competitors") or [], shootout_status)
        if summary_period is not None:
            current_period = summary_period
        if summary_clock:
            current_clock = summary_clock
    if isinstance(data, dict) and isinstance(current_period, int):
        current_clock_secs = _clock_to_seconds(current_clock)
        if current_clock_secs is not None:
            if isinstance(plays, list):
                penalty_clocks = _penalty_clocks_from_plays(plays, current_period, current_clock_secs)
    if isinstance(data, dict):
        on_ice_list = data.get("onIce") or []
        if isinstance(on_ice_list, list):
            for block in on_ice_list:
                if not isinstance(block, dict):
                    continue
                team_id = str(block.get("teamId") or "")
                if not team_id:
                    continue
                entries = block.get("entries") or []
                ids: list[str] = []
                for entry in entries if isinstance(entries, list) else []:
                    if not isinstance(entry, dict):
                        continue
                    where = entry.get("whereabouts") or {}
                    where_name = str(where.get("name") or where.get("description") or "").lower()
                    if where_name and "in" in where_name and "play" in where_name:
                        is_in_play = True
                    else:
                        is_in_play = not where_name
                    if not is_in_play:
                        continue
                    athlete_id = entry.get("athleteid") or entry.get("athleteId") or entry.get("athleteID")
                    if not athlete_id and isinstance(entry.get("athlete"), dict):
                        athlete_id = entry["athlete"].get("id") or entry["athlete"].get("uid")
                    if athlete_id:
                        ids.append(str(athlete_id))
                if ids:
                    on_ice_by_team[team_id] = ids
                    on_ice_order_by_team[team_id] = {pid: idx for idx, pid in enumerate(ids)}

    for team_block in players_block if isinstance(players_block, list) else []:
        team_info = team_block.get("team", {}) or {}
        tid = str(team_info.get("id") or "")
        tri = _normalize_tricode(team_info.get("abbreviation") or team_info.get("shortDisplayName") or "")
        on_ice_order = on_ice_order_by_team.get(tid, {})
        roster: Dict[str, Dict[str, Any]] = {}
        for stat_group in team_block.get("statistics") or []:
            group_name = str(stat_group.get("name") or "").lower()
            is_goalie_group = "goalie" in group_name
            labels = stat_group.get("labels") or []
            for athlete_entry in stat_group.get("athletes") or []:
                athlete = athlete_entry.get("athlete") or {}
                aid = str(athlete.get("id") or athlete.get("uid") or athlete.get("displayName") or "")
                if not aid:
                    continue
                pos = (athlete.get("position") or {}).get("abbreviation") or (
                    athlete.get("position") or {}
                ).get("displayName") or ""
                player = roster.setdefault(
                    aid,
                    {
                        "id": aid,
                        "firstName": (athlete.get("firstName") or athlete.get("displayName") or "").split(" ")[0],
                        "familyName": (
                            athlete.get("lastName")
                            or " ".join((athlete.get("displayName") or "").split(" ")[1:])
                        ).strip(),
                        "position": pos,
                        "jerseyNum": str(athlete.get("jersey") or ""),
                        "_stats": {},
                        "_is_goalie": False,
                    },
                )
                if is_goalie_group:
                    player["_is_goalie"] = True
                stats_vals = athlete_entry.get("stats") or []
                for idx, label in enumerate(labels):
                    if idx < len(stats_vals):
                        player["_stats"][label] = stats_vals[idx]

        players: list[Dict[str, Any]] = []
        for p in roster.values():
            stats = p.pop("_stats", {})
            on_ice_flag = str(p.get("id") or "") in on_ice_order
            is_goalie = bool(p.pop("_is_goalie", False)) or (p.get("position") or "").upper() == "G"
            if is_goalie:
                saves = _to_int(stats.get("SV"))
                shots_against = _to_int(stats.get("SA"))
                save_pct = stats.get("SV%")
                if save_pct is None and shots_against:
                    save_pct = f"{saves / shots_against:.3f}".lstrip("0")
                pim = _to_int(stats.get("PIM"))
                p["statistics"] = {
                    "saves": saves,
                    "shotsAgainst": shots_against,
                    "savePct": save_pct or "",
                    "pim": pim,
                }
            else:
                goals = _to_int(stats.get("G"))
                assists = _to_int(stats.get("A"))
                points = _to_int(stats.get("PTS"))
                if points == 0 and (goals or assists):
                    points = goals + assists
                # ESPN's NHL skater groups expose live shots in "S"; "SOG" can be
                # the shootout-goals column and stays zero for all skaters.
                sog = _to_int(stats.get("S") or stats.get("SOG"))
                pim = _to_int(stats.get("PIM"))
                hits = _to_int(stats.get("HT"))
                blocked_shots = _to_int(stats.get("BS"))
                p["statistics"] = {
                    "goals": goals,
                    "assists": assists,
                    "points": points,
                    "shotsOnGoal": sog,
                    "pim": pim,
                    "plusMinus": stats.get("+/-") or "",
                    "toi": stats.get("TOI") or "",
                    "hits": hits,
                    "blockedShots": blocked_shots,
                }
            if on_ice_flag:
                p["statistics"]["onIce"] = True
                p["statistics"]["onIceOrder"] = on_ice_order.get(str(p.get("id") or ""), 0)
            players.append(p)

        if tid:
            players_by_team[tid] = players
        if tri:
            players_by_team[tri] = players

    for team_block in box.get("teams") or []:
        team_info = team_block.get("team", {}) or {}
        tid = str(team_info.get("id") or "")
        tri = _normalize_tricode(team_info.get("abbreviation") or team_info.get("shortDisplayName") or "")
        stats_list = team_block.get("statistics") or []
        shots = _extract_team_shots(stats_list) if isinstance(stats_list, list) else None
        if shots is None:
            continue
        stats_entry = {"shotsOnGoal": shots}
        if tid:
            team_stats_by_team[tid] = stats_entry
        if tri:
            team_stats_by_team[tri] = stats_entry

    return (
        players_by_team,
        team_stats_by_team,
        penalty_clocks,
        summary_clock,
        summary_period,
        summary_status_text,
        shootout_scores,
        summary_scores,
    )


def get_scoreboard() -> Dict[str, Any]:
    now = time.monotonic()
    if _scoreboard_cache.get("data") is None:
        disk = _load_disk_scoreboard()
        if disk:
            _scoreboard_cache["data"] = disk
            # Seed from disk but force an immediate live refresh attempt.
            _scoreboard_cache["ts"] = 0.0

    cached = _scoreboard_cache.get("data")
    cache_ttl = _scoreboard_ttl_for_payload(cached)
    if cached and now - _scoreboard_cache.get("ts", 0) < cache_ttl:
        return cached

    try:
        resp = _session.get(SCOREBOARD_URL, headers=HEADERS, timeout=SCOREBOARD_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        events = (data.get("content", {}).get("sbData", {}).get("events", [])) or data.get("events", []) or []
    except Exception as exc:
        logger.exception("get_scoreboard failed fetching/parsing scoreboard: %s", exc)
        disk = _load_disk_scoreboard()
        if disk:
            return disk
        return _demo_scoreboard()

    games = []
    for ev in events:
        comp = (ev.get("competitions") or [{}])[0]
        status = ev.get("status") or {}
        status_type = status.get("type") or {}
        state = status_type.get("state")
        clock = status.get("displayClock") or status.get("clock")
        period = status.get("period")
        if isinstance(period, int) and period <= 0:
            period = None
        start = ev.get("date")
        home_raw = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "home"), {})
        away_raw = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "away"), {})
        home = _map_team(home_raw)
        away = _map_team(away_raw)
        status = _status_from_state(state)
        game_status_value = 2
        if status == "upcoming":
            game_status_value = 1
        elif status == "final":
            game_status_value = 3
        status_text = status_type.get("shortDetail") or status_type.get("detail") or ""
        if "intermission" in status_text.lower():
            status_text = "Intermission"
        shootout_scores = _shootout_scores_from_competitors(comp.get("competitors") or [], status_text)
        if status_text and (not clock or period is None):
            parsed_clock, parsed_period = _parse_clock_and_period(status_text)
            if not clock and parsed_clock:
                clock = parsed_clock
            if period is None and parsed_period:
                period = parsed_period
        header = _header_from_event(status, status_text, period, clock, start)
        _apply_shootout_score(home, shootout_scores)
        _apply_shootout_score(away, shootout_scores)
        games.append(
            {
                "gameId": str(ev.get("id")),
                "homeTeam": home,
                "awayTeam": away,
                "status": status,
                "gameStatus": game_status_value,
                "startTime": start,
                "header": header,
                "gameStatusText": header,
                "gameClock": clock,
                "period": {"current": period} if period else {},
                "seasonYear": str(ev.get("season", {}).get("year") or "2025"),
            }
        )
    if not games:
        return _demo_scoreboard()
    lines = [_line(g) for g in games]
    result = {"games": games, "lines": lines}
    _scoreboard_cache["data"] = result
    _scoreboard_cache["ts"] = time.monotonic()
    _save_disk_scoreboard(result)
    return result


def get_boxscore(game_id: str) -> Dict[str, Any]:
    now = time.time()
    cached = _boxscore_cache.get(str(game_id))
    if cached:
        cached_ts, cached_ttl, cached_payload = cached
        if now - cached_ts < cached_ttl:
            return cached_payload

    board = get_scoreboard()
    game = next((g for g in board.get("games", []) if str(g.get("gameId")) == str(game_id)), None)
    if not game:
        return _demo_boxscore(game_id)
    header = game.get("header")
    game_status_text = str(game.get("status") or "").lower().strip()
    game_status_value = game.get("gameStatus")
    if not isinstance(game_status_value, int):
        if game_status_text == "upcoming":
            game_status_value = 1
        elif game_status_text == "final":
            game_status_value = 3
        else:
            game_status_value = 2
    boxscore_ttl = _boxscore_ttl_for_status(game.get("status"))
    home_team = game.get("homeTeam", {})
    away_team = game.get("awayTeam", {})
    period_field = game.get("period")
    if isinstance(period_field, dict):
        current_period = period_field.get("current")
    elif isinstance(period_field, int):
        current_period = period_field
    else:
        current_period = None
    is_pregame = game_status_text == "upcoming" or game_status_value == 1
    if is_pregame:
        home = {**home_team, "players": []}
        away = {**away_team, "players": []}
        apply_starting_lineups("NHL", home, away)
        result = {
            "game": {
                "gameClock": game.get("gameClock"),
                "shotClock": None,
                "period": game.get("period") or {},
                "gameStatusText": header,
                "gameStatus": game_status_value,
            },
            "home": home,
            "away": away,
            "header": header,
            "shotclock": "--",
        }
        _boxscore_cache[str(game_id)] = (now, boxscore_ttl, result)
        return result
    (
        players_by_team,
        team_stats_by_team,
        penalty_clocks,
        summary_clock,
        summary_period,
        summary_status_text,
        shootout_scores,
        summary_scores,
    ) = _fetch_boxscore_players(
        str(game_id),
        current_period=current_period,
        current_clock=game.get("gameClock"),
        status_hint=game.get("status"),
    )
    home_players = players_by_team.get(home_team.get("teamId")) or players_by_team.get(home_team.get("teamTricode")) or []
    away_players = players_by_team.get(away_team.get("teamId")) or players_by_team.get(away_team.get("teamTricode")) or []
    home_stats = team_stats_by_team.get(home_team.get("teamId")) or team_stats_by_team.get(home_team.get("teamTricode")) or {}
    away_stats = team_stats_by_team.get(away_team.get("teamId")) or team_stats_by_team.get(away_team.get("teamTricode")) or {}
    if "shotsOnGoal" not in home_stats:
        home_stats = {**home_stats, "shotsOnGoal": _sum_player_shots(home_players)}
    if "shotsOnGoal" not in away_stats:
        away_stats = {**away_stats, "shotsOnGoal": _sum_player_shots(away_players)}
    home = {**home_team, **home_stats, "players": home_players}
    away = {**away_team, **away_stats, "players": away_players}
    if isinstance(summary_scores.get("home"), int):
        home["score"] = summary_scores["home"]
    if isinstance(summary_scores.get("away"), int):
        away["score"] = summary_scores["away"]
    _apply_shootout_score(home, shootout_scores)
    _apply_shootout_score(away, shootout_scores)
    home_penalties = penalty_clocks.get(str(home_team.get("teamId") or "")) or []
    away_penalties = penalty_clocks.get(str(away_team.get("teamId") or "")) or []
    if home_penalties:
        home["penaltySecondsList"] = list(home_penalties)
        home["penaltyClocks"] = [format_clock(value) for value in home_penalties]
        home["penaltySeconds"] = home_penalties[0]
        home["penaltyClock"] = format_clock(home_penalties[0])
    if away_penalties:
        away["penaltySecondsList"] = list(away_penalties)
        away["penaltyClocks"] = [format_clock(value) for value in away_penalties]
        away["penaltySeconds"] = away_penalties[0]
        away["penaltyClock"] = format_clock(away_penalties[0])
    apply_starting_lineups("NHL", home, away)
    live_clock = summary_clock or game.get("gameClock")
    live_period = summary_period if isinstance(summary_period, int) and summary_period > 0 else current_period
    live_status_text = summary_status_text or game.get("gameStatusText") or header
    header = _header_from_event(game.get("status") or "live", live_status_text, live_period, live_clock, game.get("startTime"))
    _overlay_scoreboard_game(
        str(game_id),
        clock=live_clock,
        period=live_period,
        status_text=live_status_text,
        home_score=home.get("score"),
        away_score=away.get("score"),
    )
    result = {
        "game": {
            "gameClock": live_clock,
            "shotClock": None,
            "period": {"current": live_period} if live_period else (game.get("period") or {}),
            "gameStatusText": header,
            "gameStatus": game_status_value,
        },
        "home": home,
        "away": away,
        "header": header,
        "shotclock": "--",
    }
    _boxscore_cache[str(game_id)] = (now, boxscore_ttl, result)
    return result


def get_team_colors(tricode: str) -> Dict[str, str]:
    tri = _normalize_tricode(tricode)
    return {
        "primary": TEAM_PRIMARY_COLORS.get(tri, "#444444"),
        "secondary": TEAM_SECONDARY_COLORS.get(tri, "#2b2b2b"),
        "accent": TEAM_ACCENT_COLORS.get(tri, "#777777"),
        "alt": TEAM_ALT_COLORS.get(tri, "#777777"),
    }


def get_team_logo(team_id: str | None, tricode: str | None) -> bytes | None:
    tri = _normalize_tricode(tricode)
    key = (team_id or "", tri, LOGO_VERSION)
    if key in _logo_cache:
        return _logo_cache[key]
    cache_path = LOGO_DIR / f"{team_id or tri or 'unknown'}-{LOGO_VERSION}.png"
    if cache_path.exists():
        try:
            data = cache_path.read_bytes()
            _logo_cache[key] = data
            return data
        except Exception as exc:
            logger.exception("Failed to read team logo cache %s: %s", cache_path, exc)
            pass
    urls = []
    if tri:
        urls.append(f"https://assets.nhle.com/logos/nhl/png/{tri}_light.png")
        urls.append(f"https://assets.nhle.com/logos/nhl/png/{tri}_dark.png")
    if team_id:
        urls.append(f"https://a.espncdn.com/i/teamlogos/nhl/500/{team_id}.png")
    if tri:
        urls.append(f"https://a.espncdn.com/i/teamlogos/nhl/500/{tri}.png")
    for url in urls:
        try:
            resp = _session.get(url, headers=HEADERS, timeout=LOGO_TIMEOUT_SEC)
            resp.raise_for_status()
            data = resp.content
            cache_path.write_bytes(data)
            _logo_cache[key] = data
            return data
        except Exception as exc:
            logger.debug("get_team_logo fetch failed for %s: %s", url, exc)
            continue
    _logo_cache[key] = None
    return None


def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    return get_team_logo(team_id, tricode)


def safe_score(team: Dict[str, Any]) -> int:
    try:
        return int(team.get("score") or 0)
    except Exception as exc:
        logger.debug("safe_score failed for team=%r: %s", team, exc)
        return 0


def format_time_played(value: Any) -> str:
    if value in (None, "", 0):
        return ""
    return str(value)


def format_shotclock(value: Any) -> str:
    return "--"


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
    except Exception as exc:
        logger.debug("_wins_losses_from_summary failed parsing %r: %s", nums, exc)
        return None


def build_player_rows(team: Dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    players = team.get("players", []) or []
    for p in players:
        stats = p.get("statistics", {}) or {}
        jersey = p.get("jerseyNum") or ""
        name = format_player_initial_name(p.get("firstName"), p.get("familyName"))
        pos = p.get("position") or ""
        is_goalie = (pos or "").upper() == "G" or "saves" in stats or "savePct" in stats
        if is_goalie:
            saves = _to_int(stats.get("saves"))
            save_pct = stats.get("savePct") or ""
            pim = _to_int(stats.get("pim"))
            rows.append([jersey, name, pos, "", "", "", "", str(pim), str(saves), str(save_pct)])
        else:
            goals = _to_int(stats.get("goals"))
            assists = _to_int(stats.get("assists"))
            points = _to_int(stats.get("points") or (goals + assists))
            sog = _to_int(stats.get("shotsOnGoal"))
            pim = _to_int(stats.get("pim"))
            rows.append([jersey, name, pos, str(goals), str(assists), str(points), str(sog), str(pim), "", ""])
    return rows


def _map_team(raw: Dict[str, Any]) -> Dict[str, Any]:
    team = raw.get("team", {}) or {}
    tri_raw = team.get("abbreviation") or team.get("shortDisplayName") or "TM"
    tri = _normalize_tricode(tri_raw)
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


def _line(g: Dict[str, Any]) -> str:
    away = g.get("awayTeam", {}) or {}
    home = g.get("homeTeam", {}) or {}
    return f"{away.get('teamTricode','AWY')} {away.get('score',0)} @ {home.get('teamTricode','HME')} {home.get('score',0)} ({g.get('header','')})"


def _overlay_scoreboard_game(
    game_id: str,
    *,
    clock: str | None = None,
    period: int | None = None,
    status_text: str | None = None,
    home_score: int | None = None,
    away_score: int | None = None,
) -> None:
    with _cache_lock:
        board = _scoreboard_cache.get("data")
        if not isinstance(board, dict):
            return
        games = board.get("games")
        if not isinstance(games, list):
            return
        updated = False
        for game in games:
            if str(game.get("gameId") or "") != str(game_id):
                continue
            status = str(game.get("status") or "").lower() or _status_from_state(None)
            if isinstance(home_score, int):
                home = game.get("homeTeam")
                if isinstance(home, dict):
                    home["score"] = home_score
                    updated = True
            if isinstance(away_score, int):
                away = game.get("awayTeam")
                if isinstance(away, dict):
                    away["score"] = away_score
                    updated = True
            if clock not in (None, ""):
                game["gameClock"] = clock
                updated = True
            if isinstance(period, int) and period > 0:
                game["period"] = {"current": period}
                updated = True
            merged_status_text = status_text or game.get("gameStatusText") or game.get("header")
            header = _header_from_event(status, merged_status_text, period, clock, game.get("startTime"))
            if header:
                game["header"] = header
                game["gameStatusText"] = header
                updated = True
            break
        if updated:
            board["lines"] = [_line(g) for g in games if isinstance(g, dict)]
            _scoreboard_cache["ts"] = time.monotonic()


def _demo_scoreboard() -> Dict[str, Any]:
    now = time.time()
    games = [
        {
            "gameId": "NHL_DEMO",
            "homeTeam": {"teamId": "STL", "teamName": "Blues", "teamTricode": "STL", "score": 0},
            "awayTeam": {"teamId": "CHI", "teamName": "Blackhawks", "teamTricode": "CHI", "score": 0},
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
        "game": {"gameClock": None, "shotClock": None, "period": {"current": None}, "gameStatusText": g["header"]},
        "home": {**g["homeTeam"], "players": []},
        "away": {**g["awayTeam"], "players": []},
        "header": g["header"],
        "shotclock": "--",
    }


# compatibility
fetch_scoreboard = get_scoreboard
fetch_boxscore = get_boxscore
