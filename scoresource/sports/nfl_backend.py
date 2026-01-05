"""NFL backend for ScoreSource using ESPN public API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import requests

TEAM_COLORS: Dict[str, str] = {
    "DAL": "#003594",
    "SF": "#AA0000",
    "KC": "#E31837",
    "PHI": "#004C54",
    "BUF": "#00338D",
    "MIA": "#008E97",
    "NYJ": "#125740",
    "NYG": "#0B2265",
    "NE": "#002244",
    "GB": "#203731",
    "CHI": "#0B162A",
    "MIN": "#4F2683",
    "NO": "#D3BC8D",
    "LAR": "#003594",
    "LAC": "#0080C6",
    "PIT": "#FFB612",
    "BAL": "#241773",
    "CLE": "#311D00",
    "DET": "#0076B6",
    "CIN": "#FB4F14",
    "SEA": "#002244",
    "DEN": "#FB4F14",
    "LV": "#000000",
    "JAX": "#006778",
    "TEN": "#0C2340",
    "HOU": "#03202F",
    "CAR": "#0085CA",
    "ATL": "#A71930",
    "TB": "#D50A0A",
    "IND": "#002C5F",
    "WAS": "#773141",
    "ARI": "#97233F",
}
TEAM_ACCENT_COLORS: Dict[str, str] = {k: "#FFFFFF" for k in TEAM_COLORS}
TEAM_SECONDARY_COLORS: Dict[str, str] = {k: "#1d2430" for k in TEAM_COLORS}
TEAM_LOGOS: Dict[str, bytes] = {}
sport_table_headers = ["#", "Player", "Min", "Pos", "Pts", "Reb", "Ast", "PF"]

ACCENT_DEFAULT = "#45e0ff"
DEMO_MODE = os.environ.get("SCORESOURCE_DEMO") == "1"

DEMO_GAMES = [
    {
        "label": "Cowboys 31 @ Texans 28 (Q4 2:12)",
        "gameId": "NFL_DEMO1",
        "sport": "NFL",
        "quarter": 4,
        "clock": "2:12",
        "awayTeam": {
            "teamName": "Cowboys",
            "teamCity": "Dallas",
            "teamTricode": "DAL",
            "score": 31,
            "players": [],
        },
        "homeTeam": {
            "teamName": "Texans",
            "teamCity": "Houston",
            "teamTricode": "HOU",
            "score": 28,
            "players": [],
        },
    }
]

_LOGO_CACHE: Dict[str, bytes | None] = {}
_SESSION = requests.Session()
_LOGO_DIR = Path.home() / ".cache" / "scoresource" / "logos"
_LOGO_DIR.mkdir(parents=True, exist_ok=True)


def safe_score(team: Dict[str, Any]) -> int:
    val = team.get("score") or team.get("points")
    try:
        return int(val)
    except Exception:
        return 0


def format_time_played(value: Any) -> str:
    return ""


def format_shotclock(value: Any) -> str:
    return "--"


def _espn_scoreboard() -> Dict[str, Any]:
    url = "https://site.web.api.espn.com/apis/v2/sports/football/nfl/scoreboard"
    resp = _SESSION.get(url, timeout=5)
    resp.raise_for_status()
    return resp.json()


def fetch_scoreboard() -> Dict[str, Any]:
    if DEMO_MODE:
        return {"games": DEMO_GAMES, "lines": [g["label"] for g in DEMO_GAMES]}
    try:
        data = _espn_scoreboard()
        games: List[Dict[str, Any]] = []
        lines: List[str] = []

        for event in data.get("events", []):
            game_id = event.get("id")
            status = event.get("status", {}).get("type", {}).get("shortDetail", "Scheduled")
            comp_list = event.get("competitions") or []
            if not comp_list:
                continue
            comp = comp_list[0]
            competitors = comp.get("competitors") or []

            home_raw = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away_raw = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not home_raw or not away_raw:
                continue

            def _team_from_comp(c: Dict[str, Any]) -> Dict[str, Any]:
                team = c.get("team") or {}
                abbrev = (team.get("abbreviation") or "").upper()
                loc = team.get("location") or ""
                return {
                    "teamId": str(team.get("id") or ""),
                    "teamName": team.get("displayName") or abbrev or "Team",
                    "teamTricode": abbrev,
                    "teamCity": loc,
                    "score": int(c.get("score") or 0),
                    "players": [],
                }

            home = _team_from_comp(home_raw)
            away = _team_from_comp(away_raw)

            games.append(
                {
                    "gameId": game_id,
                    "homeTeam": home,
                    "awayTeam": away,
                    "gameStatusText": status,
                }
            )
            lines.append(f"{away['teamName']} {away['score']} @ {home['teamName']} {home['score']} ({status})")

        if games:
            return {"games": games, "lines": lines}
    except Exception:
        pass
    return {"games": DEMO_GAMES, "lines": [g["label"] for g in DEMO_GAMES]}


def fetch_boxscore(game_id: str) -> Dict[str, Any]:
    if DEMO_MODE:
        demo = next((g for g in DEMO_GAMES if g["gameId"] == game_id), DEMO_GAMES[0])
        return {
            "game": demo,
            "home": demo["homeTeam"],
            "away": demo["awayTeam"],
            "header": demo["label"],
            "shotclock": None,
        }
    try:
        data = _espn_scoreboard()
        event = next((e for e in data.get("events", []) if e.get("id") == game_id), None)
        if not event:
            return _fallback_boxscore()

        status = event.get("status", {}).get("type", {}).get("shortDetail", "Scheduled")
        comp_list = event.get("competitions") or []
        comp = comp_list[0] if comp_list else {}
        competitors = comp.get("competitors") or []

        home_raw = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away_raw = next((c for c in competitors if c.get("homeAway") == "away"), None)

        def _team_from_comp(c: Dict[str, Any]) -> Dict[str, Any]:
            team = c.get("team") or {}
            abbrev = (team.get("abbreviation") or "").upper()
            loc = team.get("location") or ""
            return {
                "teamId": str(team.get("id") or ""),
                "teamName": team.get("displayName") or abbrev or "Team",
                "teamTricode": abbrev,
                "teamCity": loc,
                "score": int(c.get("score") or 0),
                "players": [],
            }

        home = _team_from_comp(home_raw or {})
        away = _team_from_comp(away_raw or {})

        game = {
            "gameClock": None,
            "shotClock": None,
            "period": {"current": None},
            "gameStatusText": status,
        }

        return {
            "game": game,
            "home": home,
            "away": away,
            "header": status,
            "shotclock": None,
        }
    except Exception:
        return _fallback_boxscore()


def _fallback_boxscore() -> Dict[str, Any]:
    return {
        "game": {"gameClock": None, "period": {"current": None}, "gameStatusText": "No Data"},
        "home": {"teamName": "HOME", "teamTricode": "HME", "score": 0, "players": []},
        "away": {"teamName": "AWAY", "teamTricode": "AWY", "score": 0, "players": []},
        "header": "No Data",
        "shotclock": None,
    }


def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    key = f"{team_id or tricode}"
    if key in _LOGO_CACHE:
        return _LOGO_CACHE[key]

    logo_url_candidates = []
    if team_id:
        logo_url_candidates.append(f"https://a.espncdn.com/i/teamlogos/nfl/500/{team_id}.png")
    code = (tricode or "").lower()
    if code:
        logo_url_candidates.append(f"https://a.espncdn.com/i/teamlogos/nfl/500/{code}.png")

    content: bytes | None = None
    for url in logo_url_candidates:
        try:
            resp = _SESSION.get(url, timeout=4)
            resp.raise_for_status()
            content = resp.content
            break
        except Exception:
            continue

    _LOGO_CACHE[key] = content
    if content:
        try:
            path = _LOGO_DIR / f"nfl_{key}.png"
            path.write_bytes(content)
        except Exception:
            pass
    return content
