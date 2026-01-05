"""NBA backend adapter using existing pyside/nba module."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure pyside modules are importable
ROOT = Path(__file__).resolve().parents[2]
PYSIDE_DIR = ROOT / "pyside"
if str(PYSIDE_DIR) not in sys.path:
    sys.path.insert(0, str(PYSIDE_DIR))

import nba  # type: ignore

TEAM_COLORS = nba.TEAM_PRIMARY_COLORS
TEAM_ACCENT_COLORS = nba.TEAM_ACCENT_COLORS
TEAM_SECONDARY_COLORS = getattr(nba, "TEAM_SECONDARY_COLORS", {})
TEAM_LOGOS: Dict[str, bytes] = {}
sport_table_headers = ["#", "Player", "Min", "Pos", "Pts", "Reb", "Ast", "3pt"]


def safe_score(team: Dict[str, Any]) -> int:
    return nba.safe_score(team)


def format_time_played(value: Any) -> str:
    return nba.format_time_played(value)


def format_shotclock(value: Any) -> str:
    return nba.format_shotclock(value)


def fetch_scoreboard() -> Dict[str, Any]:
    return nba.fetch_scores()


def fetch_boxscore(game_id: str) -> Dict[str, Any]:
    return nba.fetch_boxscore(game_id)


def load_logo(team_id: str | None, tricode: str | None = "") -> bytes | None:
    return nba.load_logo(team_id, tricode)
