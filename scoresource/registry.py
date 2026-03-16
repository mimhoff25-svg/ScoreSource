from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from . import nba, nfl, nhl, mlb, ncaa_football, ncaa_basketball, mls

ASSET_LOGO_DIR = Path(__file__).resolve().parent / "assets" / "logos"
DEFAULT_SPORT_DISPLAY = "NBA"
DEFAULT_SPORT_KEY = "NBA"

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

SPORT_ORDER = ["NBA", "NCAA Basketball", "NFL", "NCAA Football", "NHL", "MLS", "MLB"]
SPORT_DISPLAY_TO_KEY: Dict[str, str] = {
    display_name: str(config["sport_key"])
    for display_name, config in SPORT_REGISTRY.items()
}
SPORT_KEY_TO_DISPLAY: Dict[str, str] = {
    sport_key: display_name
    for display_name, sport_key in SPORT_DISPLAY_TO_KEY.items()
}


def canonicalize_sport_name(sport: str | None, *, default: str = DEFAULT_SPORT_KEY) -> str:
    raw = str(sport or "").strip()
    if not raw:
        return default
    if raw in SPORT_DISPLAY_TO_KEY:
        return SPORT_DISPLAY_TO_KEY[raw]
    upper = raw.upper()
    if upper in SPORT_KEY_TO_DISPLAY:
        return upper
    for display_name, sport_key in SPORT_DISPLAY_TO_KEY.items():
        if raw.casefold() == display_name.casefold():
            return sport_key
    return upper


def display_name_for_sport(sport: str | None, *, default: str = DEFAULT_SPORT_DISPLAY) -> str:
    raw = str(sport or "").strip()
    if not raw:
        return default
    if raw in SPORT_REGISTRY:
        return raw
    sport_key = canonicalize_sport_name(raw)
    return SPORT_KEY_TO_DISPLAY.get(sport_key, raw)


def get_sport_config(sport: str | None) -> Dict[str, Any] | None:
    display_name = display_name_for_sport(sport)
    return SPORT_REGISTRY.get(display_name)
