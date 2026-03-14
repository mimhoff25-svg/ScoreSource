from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

import requests

LINEUP_TTL = 60 * 60  # 1 hour
EMPTY_LINEUP_TTL = 60 * 2  # Retry quickly when no lineup data was found.
TEAM_MAP_TTL = 60 * 60 * 12

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
_team_map_cache: Dict[str, Tuple[float, Dict[str, str]]] = {}


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
    path = ESPN_SPORT_PATH.get(sp)
    if not path:
        return []

    lookup_candidates = _team_lookup_candidates(path, sp, tid, tri)
    key_id = lookup_candidates[0] if lookup_candidates else ""
    if not key_id:
        return []
    cache_key = (sp, key_id)
    now = time.monotonic()
    cached = _lineup_cache.get(cache_key)
    if cached:
        cached_lineup = cached[1]
        ttl = LINEUP_TTL if cached_lineup else EMPTY_LINEUP_TTL
        if now - cached[0] < ttl:
            return cached_lineup

    lineup: List[Dict[str, Any]] = []
    for candidate in lookup_candidates:
        lineup = _fetch_depthchart_lineup(path, sp, candidate)
        if lineup:
            break
    if not lineup:
        for candidate in lookup_candidates:
            lineup = _fetch_roster_lineup(path, sp, candidate)
            if lineup:
                break
    _lineup_cache[cache_key] = (now, lineup)
    return lineup


def _team_lookup_candidates(path: str, sport: str, team_id: str, tricode: str) -> List[str]:
    candidates: List[str] = []

    def add(value: str) -> None:
        token = str(value or "").strip()
        if not token or token in candidates:
            return
        candidates.append(token)

    if _is_valid_team_lookup_token(team_id):
        add(team_id)
    mapped_id = _team_id_for_tricode(path, sport, tricode)
    if mapped_id:
        add(mapped_id)
    if tricode:
        add(tricode)
    return candidates


def _is_valid_team_lookup_token(value: str) -> bool:
    token = str(value or "").strip().upper()
    return token not in {"", "0", "AWY", "HOM"}


def _team_id_for_tricode(path: str, sport: str, tricode: str) -> str:
    tri = str(tricode or "").strip().upper()
    if not tri:
        return ""
    now = time.monotonic()
    cached = _team_map_cache.get(path)
    if cached and now - cached[0] < TEAM_MAP_TTL:
        return _team_id_from_map(sport, tri, cached[1])

    payload = _fetch_json(f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams") or {}
    mapped: Dict[str, str] = {}
    for sport_entry in payload.get("sports") or []:
        if not isinstance(sport_entry, dict):
            continue
        for league_entry in sport_entry.get("leagues") or []:
            if not isinstance(league_entry, dict):
                continue
            for team_entry in league_entry.get("teams") or []:
                _store_team_mapping(mapped, sport, team_entry)
    if not mapped:
        for team_entry in payload.get("teams") or []:
            _store_team_mapping(mapped, sport, team_entry)
    if mapped:
        _team_map_cache[path] = (now, mapped)
        return _team_id_from_map(sport, tri, mapped)
    if cached and now - cached[0] < (TEAM_MAP_TTL * 2):
        return _team_id_from_map(sport, tri, cached[1])
    return ""


def _store_team_mapping(mapped: Dict[str, str], sport: str, team_entry: Any) -> None:
    if not isinstance(team_entry, dict):
        return
    team_data = team_entry.get("team") if isinstance(team_entry.get("team"), dict) else team_entry
    if not isinstance(team_data, dict):
        return
    key = str(team_data.get("abbreviation") or "").strip().upper()
    value = str(team_data.get("id") or "").strip()
    if not key or not value:
        return
    mapped[key] = value
    alias = _team_tricode_alias(sport, key)
    if alias:
        mapped[alias] = value


def _team_id_from_map(sport: str, tricode: str, mapped: Dict[str, str]) -> str:
    candidates = [tricode]
    alias = _team_tricode_alias(sport, tricode)
    if alias:
        candidates.append(alias)
    seen: set[str] = set()
    for candidate in candidates:
        token = str(candidate or "").strip().upper()
        if not token or token in seen:
            continue
        seen.add(token)
        mapped_id = str(mapped.get(token) or "")
        if mapped_id:
            return mapped_id
    return ""


def _team_tricode_alias(sport: str, tricode: str) -> str:
    tri = str(tricode or "").strip().upper()
    if not tri:
        return ""
    aliases = {
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
    return aliases.get(str(sport or "").upper(), {}).get(tri, "")


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
    if sport == "MLS":
        return _roster_lineup_mls(items)
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


def _roster_lineup_mls(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Default to a 4-3-3 shape when match-specific XI is unavailable.
    lineup = []
    lineup += _take_from(_bucket(items, {"G", "GK"}), 1)
    lineup += _take_from(_bucket(items, {"D", "DF", "DEF"}), 4)
    lineup += _take_from(_bucket(items, {"M", "MF", "MID"}), 3)
    lineup += _take_from(_bucket(items, {"F", "FW", "ST", "ATT"}), 3)
    return _fill_with_remaining(lineup, items, 11)


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
    pos = item.get("position")
    if isinstance(pos, dict):
        abbr = pos.get("abbreviation") or pos.get("shortName") or pos.get("displayName")
    else:
        abbr = pos
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
    athlete_id = athlete.get("id") or athlete.get("alternateId") or ""
    return {
        "id": str(athlete_id or ""),
        "fullName": name or "",
        "position": pos_abbr or "",
        "jersey": str(jersey or ""),
    }
