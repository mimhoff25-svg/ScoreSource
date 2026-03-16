from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from . import nba, nfl, nhl, mlb, ncaa_football, ncaa_basketball, mls
from .sports_meta import (
    DEFAULT_SPORT_DISPLAY,
    DEFAULT_SPORT_KEY,
    SPORT_DISPLAY_TO_KEY,
    SPORT_KEY_TO_DISPLAY,
    SPORT_ORDER,
    display_name_for_sport,
    canonicalize_sport_name,
)

ASSET_LOGO_DIR = Path(__file__).resolve().parent / "assets" / "logos"

SPORT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "NBA": {
        "display_name": "NBA",
        "sport_key": "NBA",
        "backend": nba,
        "logo_path": str(ASSET_LOGO_DIR / "nba.png"),
        "icon_path": str(ASSET_LOGO_DIR / "nba.png"),
    },
    "NFL": {
        "display_name": "NFL",
        "sport_key": "NFL",
        "backend": nfl,
        "logo_path": str(ASSET_LOGO_DIR / "nfl.png"),
        "icon_path": str(ASSET_LOGO_DIR / "nfl.png"),
    },
    "NCAA Basketball": {
        "display_name": "NCAA Basketball",
        "sport_key": "NCAA BASKETBALL",
        "backend": ncaa_basketball,
        "logo_path": str(ASSET_LOGO_DIR / "ncaa.png"),
        "icon_path": str(ASSET_LOGO_DIR / "ncaa.png"),
    },
    "NHL": {
        "display_name": "NHL",
        "sport_key": "NHL",
        "backend": nhl,
        "logo_path": str(ASSET_LOGO_DIR / "nhl.png"),
        "icon_path": str(ASSET_LOGO_DIR / "nhl.png"),
    },
    "MLB": {
        "display_name": "MLB",
        "sport_key": "MLB",
        "backend": mlb,
        "logo_path": str(ASSET_LOGO_DIR / "mlb.png"),
        "icon_path": str(ASSET_LOGO_DIR / "mlb.png"),
    },
    "MLS": {
        "display_name": "MLS",
        "sport_key": "MLS",
        "backend": mls,
        "logo_path": str(ASSET_LOGO_DIR / "mls.png"),
        "icon_path": str(ASSET_LOGO_DIR / "mls_icon.png"),
    },
    "NCAA Football": {
        "display_name": "NCAA Football",
        "sport_key": "NCAA FOOTBALL",
        "backend": ncaa_football,
        "logo_path": str(ASSET_LOGO_DIR / "ncaa.png"),
        "icon_path": str(ASSET_LOGO_DIR / "ncaa.png"),
    },
}

def get_sport_config(sport: str | None) -> Dict[str, Any] | None:
    display_name = display_name_for_sport(sport)
    return SPORT_REGISTRY.get(display_name)
