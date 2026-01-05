from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Dict, List, Type

from scoresource.sports.ui_nba import NBAScoreboardUI
from scoresource.sports.ui_nfl import NFLScoreboardUI
from scoresource.sports.ui_nhl import NHLScoreboardUI
from scoresource.sports.ui_mlb import MLBScoreboardUI
from scoresource.sports.ui_ncaa_football import NCAAFootballScoreboardUI
from scoresource.sports.ui_mls import MLSScoreboardUI


@dataclass(frozen=True)
class SportConfig:
    name: str
    backend_path: str
    ui_class: Type
    logo_path: str | None = None
    icon_path: str | None = None


ROOT = Path(__file__).resolve().parents[1]
_LOGO_DIR = ROOT / "assets" / "logos"

SPORTS: Dict[str, SportConfig] = {
    "NBA": SportConfig(
        name="NBA",
        backend_path="scoresource.nba_backend",
        ui_class=NBAScoreboardUI,
        logo_path=str(_LOGO_DIR / "nba.png"),
        icon_path=str(_LOGO_DIR / "nba_icon.png"),
    ),
    "NFL": SportConfig(
        name="NFL",
        backend_path="scoresource.nfl_backend",
        ui_class=NFLScoreboardUI,
        logo_path=str(_LOGO_DIR / "nfl.png"),
        icon_path=str(_LOGO_DIR / "nfl_icon.png"),
    ),
    "NHL": SportConfig(
        name="NHL",
        backend_path="scoresource.nhl_backend",
        ui_class=NHLScoreboardUI,
        logo_path=str(_LOGO_DIR / "nhl.png"),
        icon_path=str(_LOGO_DIR / "nhl_icon.png"),
    ),
    "MLB": SportConfig(
        name="MLB",
        backend_path="scoresource.mlb_backend",
        ui_class=MLBScoreboardUI,
        logo_path=str(_LOGO_DIR / "mlb.png"),
        icon_path=str(_LOGO_DIR / "mlb_icon.png"),
    ),
    "MLS": SportConfig(
        name="MLS",
        backend_path="scoresource.mls_backend",
        ui_class=MLSScoreboardUI,
        logo_path=str(_LOGO_DIR / "mls.png"),
        icon_path=str(_LOGO_DIR / "mls_icon.png"),
    ),
    "NCAA Football": SportConfig(
        name="NCAA Football",
        backend_path="scoresource.ncaa_football_backend",
        ui_class=NCAAFootballScoreboardUI,
        logo_path=str(_LOGO_DIR / "ncaa.png"),
        icon_path=str(_LOGO_DIR / "ncaa_icon.png"),
    ),
}


def get_config(name: str) -> SportConfig:
    return SPORTS.get(name, SPORTS["NBA"])


def get_sport_names() -> List[str]:
    return list(SPORTS.keys())


def load_backend(name: str):
    cfg = get_config(name)
    return import_module(cfg.backend_path)


def icon_map() -> Dict[str, str]:
    return {cfg.name: cfg.icon_path or cfg.logo_path or "" for cfg in SPORTS.values()}
