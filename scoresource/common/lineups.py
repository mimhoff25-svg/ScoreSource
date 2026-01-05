from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

import requests

LINEUP_TTL = 60 * 60  # 1 hour

ESPN_SPORT_PATH: Dict[str, str] = {
    "NBA": "basketball/nba",
    "WNBA": "basketball/wnba",
    "NFL": "football/nfl",
    "NHL": "hockey/nhl",
    "MLB": "baseball/mlb",
    "NCAA FOOTBALL": "football/college-football",
    "MLS": "soccer/usa.1",
}

DEPTHCHART_ORDER: Dict[str, List[str]] = {
    "NBA": ["pg", "sg", "sf", "pf", "c"],
    "MLB": ["p", "c", "1b", "2b", "3b", "ss", "lf", "cf", "rf"],
    "NFL": ["qb", "rb", "wr1", "wr2", "wr3", "te", "lt", "lg", "c", "rg", "rt"],
}

_session = requests.Session()
_lineup_cache: Dict[Tuple[str, str], Tuple[float, List[Dict[str, Any]]]] = {}


def apply_starting_lineups(sport: str, home: Dict[str, Any], away: Dict[str, Any]) -> None:
    for team in (home, away):
        if not isinstance(team, dict):
            continue
        if team.get("startingLineup") or team.get("lineup") or team.get("starters"):
            continue
        lineup = get_starting_lineup(sport, team.get("teamId"), team.get("teamTricode"))
        if lineup:
            team["startingLineup"] = lineup


def get_starting_lineup(sport: str, team_id: str | None, tricode: str | None = None) -> List[Dict[str, Any]]:
    sp = (sport or "").upper()
    tid = str(team_id or "").strip()
    tri = (tricode or "").upper()
    key_id = tid or tri
    if not key_id:
        return []
    cache_key = (sp, key_id)
    now = time.monotonic()
    cached = _lineup_cache.get(cache_key)
    if cached and now - cached[0] < LINEUP_TTL:
        return cached[1]

    path = ESPN_SPORT_PATH.get(sp)
    if not path:
        _lineup_cache[cache_key] = (now, [])
        return []

    lineup = _fetch_depthchart_lineup(path, sp, tid) if tid else []
    if not lineup and tri and tri != tid:
        lineup = _fetch_depthchart_lineup(path, sp, tri)
    if not lineup:
        lineup = _fetch_roster_lineup(path, sp, tid) if tid else []
        if not lineup and tri and tri != tid:
            lineup = _fetch_roster_lineup(path, sp, tri)
    _lineup_cache[cache_key] = (now, lineup)
    return lineup


def _fetch_json(url: str) -> Dict[str, Any] | None:
    try:
        resp = _session.get(url, timeout=6)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _fetch_depthchart_lineup(path: str, sport: str, team_id: str) -> List[Dict[str, Any]]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams/{team_id}/depthcharts"
    data = _fetch_json(url)
    if not data:
        return []
    charts = data.get("depthchart") or []
    if isinstance(charts, dict):
        charts = [charts]
    if not isinstance(charts, list) or not charts:
        return []

    chart = _select_depthchart(sport, charts)
    if not chart:
        return []
    positions = chart.get("positions") or {}
    if not isinstance(positions, dict):
        return []
    pos_map = {str(k).lower(): v for k, v in positions.items() if isinstance(k, str)}

    order = DEPTHCHART_ORDER.get(sport)
    if not order:
        return []

    lineup: List[Dict[str, Any]] = []
    used_ids: set[str] = set()
    for key in order:
        entry = pos_map.get(key)
        if not entry:
            fallback_abbr = _fallback_abbr_for_key(sport, key)
            if fallback_abbr:
                entry = _find_position_entry(pos_map, fallback_abbr)
        if not entry:
            continue
        athlete = _pick_athlete(entry.get("athletes") or [], used_ids)
        if not athlete:
            continue
        pos_block = entry.get("position") or {}
        pos_abbr = pos_block.get("abbreviation") or pos_block.get("displayName") or key.upper()
        lineup.append(_lineup_entry_from_athlete(athlete, pos_abbr))
    return lineup


def _select_depthchart(sport: str, charts: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    if sport == "NFL":
        for chart in charts:
            positions = chart.get("positions") or {}
            if isinstance(positions, dict) and any(str(k).lower() == "qb" for k in positions.keys()):
                return chart
    return charts[0] if charts else None


def _fallback_abbr_for_key(sport: str, key: str) -> str | None:
    if sport == "NFL" and key.startswith("wr"):
        return "WR"
    return None


def _find_position_entry(pos_map: Dict[str, Any], abbr: str) -> Dict[str, Any] | None:
    target = abbr.lower()
    for entry in pos_map.values():
        pos = entry.get("position") or {}
        if str(pos.get("abbreviation") or "").lower() == target:
            return entry
    return None


def _pick_athlete(athletes: List[Dict[str, Any]], used_ids: set[str]) -> Dict[str, Any] | None:
    for athlete in athletes:
        aid = str(athlete.get("id") or "")
        if aid and aid in used_ids:
            continue
        if aid:
            used_ids.add(aid)
        return athlete
    return None


def _fetch_roster_lineup(path: str, sport: str, team_id: str) -> List[Dict[str, Any]]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams/{team_id}/roster"
    data = _fetch_json(url)
    if not data:
        return []
    items, groups = _roster_items(data)
    if not items:
        return []
    return _roster_lineup_for_sport(sport, items, groups)


def _roster_items(data: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    athletes = data.get("athletes") or []
    if not isinstance(athletes, list) or not athletes:
        return [], []
    first = athletes[0]
    if isinstance(first, dict) and "items" in first:
        items: List[Dict[str, Any]] = []
        for group in athletes:
            items.extend(group.get("items") or [])
        return items, athletes
    if isinstance(first, dict):
        return athletes, []
    return [], []


def _roster_lineup_for_sport(
    sport: str, items: List[Dict[str, Any]], groups: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    if sport in ("NFL", "NCAA FOOTBALL"):
        offense_items = _offense_items(groups) or items
        return _roster_lineup_football(offense_items)
    if sport == "NHL":
        return _roster_lineup_nhl(items)
    if sport == "NBA":
        return _roster_lineup_nba(items)
    if sport == "MLB":
        return _roster_lineup_mlb(items)
    return []


def _offense_items(groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for group in groups or []:
        if str(group.get("position") or "").lower() == "offense":
            return group.get("items") or []
    return []


def _roster_lineup_nba(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    guards = _bucket(items, {"PG", "SG", "G"})
    forwards = _bucket(items, {"SF", "PF", "F"})
    centers = _bucket(items, {"C"})
    lineup = _take_from(guards, 2) + _take_from(forwards, 2) + _take_from(centers, 1)
    return _fill_with_remaining(lineup, items, 5)


def _roster_lineup_nhl(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    centers = _bucket(items, {"C"})
    lws = _bucket(items, {"LW"})
    rws = _bucket(items, {"RW"})
    defs = _bucket(items, {"D", "LD", "RD"})
    goalies = _bucket(items, {"G"})
    lineup = (
        _take_from(centers, 1)
        + _take_from(lws, 1)
        + _take_from(rws, 1)
        + _take_from(defs, 2)
        + _take_from(goalies, 1)
    )
    return _fill_with_remaining(lineup, items, 6)


def _roster_lineup_mlb(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    lineup = []
    lineup += _take_from(_bucket(items, {"P", "SP"}), 1)
    lineup += _take_from(_bucket(items, {"C"}), 1)
    lineup += _take_from(_bucket(items, {"1B"}), 1)
    lineup += _take_from(_bucket(items, {"2B"}), 1)
    lineup += _take_from(_bucket(items, {"3B"}), 1)
    lineup += _take_from(_bucket(items, {"SS"}), 1)
    lineup += _take_from(_bucket(items, {"LF"}), 1)
    lineup += _take_from(_bucket(items, {"CF"}), 1)
    lineup += _take_from(_bucket(items, {"RF"}), 1)
    return _fill_with_remaining(lineup, items, 9)


def _roster_lineup_football(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    lineup = []
    lineup += _take_from(_bucket(items, {"QB"}), 1)
    lineup += _take_from(_bucket(items, {"RB"}), 1)
    lineup += _take_from(_bucket(items, {"WR"}), 3)
    lineup += _take_from(_bucket(items, {"TE"}), 1)
    lineup += _take_from(_bucket(items, {"C"}), 1)
    lineup += _take_from(_bucket(items, {"G", "LG", "RG"}), 2)
    lineup += _take_from(_bucket(items, {"OT", "T", "LT", "RT"}), 2)
    return _fill_with_remaining(lineup, items, 11)


def _bucket(items: List[Dict[str, Any]], positions: set[str]) -> List[Dict[str, Any]]:
    pos_set = {p.upper() for p in positions}
    bucket: List[Dict[str, Any]] = []
    for item in items:
        abbr = _position_abbr(item)
        if abbr and abbr in pos_set:
            bucket.append(item)
    return bucket


def _position_abbr(item: Dict[str, Any]) -> str:
    pos = item.get("position") or {}
    abbr = pos.get("abbreviation") or pos.get("shortName") or pos.get("displayName")
    return str(abbr or "").upper()


def _take_from(items: List[Dict[str, Any]], count: int) -> List[Dict[str, Any]]:
    return [item for item in items[:count]]


def _fill_with_remaining(lineup: List[Dict[str, Any]], items: List[Dict[str, Any]], target: int) -> List[Dict[str, Any]]:
    if len(lineup) >= target:
        return [_lineup_entry_from_athlete(a) for a in lineup[:target]]
    used_ids = {str(item.get("id") or "") for item in lineup}
    for item in items:
        if len(lineup) >= target:
            break
        aid = str(item.get("id") or "")
        if aid and aid in used_ids:
            continue
        lineup.append(item)
    return [_lineup_entry_from_athlete(a) for a in lineup[:target]]


def _lineup_entry_from_athlete(athlete: Dict[str, Any], position_override: str | None = None) -> Dict[str, Any]:
    name = athlete.get("displayName") or athlete.get("fullName")
    if not name:
        first = (athlete.get("firstName") or "").strip()
        last = (athlete.get("lastName") or athlete.get("familyName") or "").strip()
        name = f"{first} {last}".strip()
    pos_abbr = position_override or _position_abbr(athlete)
    jersey = athlete.get("jersey") or athlete.get("jerseyNumber") or athlete.get("jerseyNum") or ""
    return {"fullName": name or "", "position": pos_abbr or "", "jersey": str(jersey or "")}
