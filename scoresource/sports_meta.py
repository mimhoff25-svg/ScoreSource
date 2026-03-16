from __future__ import annotations

from typing import Dict

DEFAULT_SPORT_KEY = "NBA"
DEFAULT_SPORT_DISPLAY = "NBA"

SPORT_KEY_TO_DISPLAY: Dict[str, str] = {
    "NBA": "NBA",
    "NCAA BASKETBALL": "NCAA Basketball",
    "NFL": "NFL",
    "NCAA FOOTBALL": "NCAA Football",
    "NHL": "NHL",
    "MLS": "MLS",
    "MLB": "MLB",
}
SPORT_DISPLAY_TO_KEY: Dict[str, str] = {display: key for key, display in SPORT_KEY_TO_DISPLAY.items()}
SPORT_ORDER_KEYS = [
    "NBA",
    "NCAA BASKETBALL",
    "NFL",
    "NCAA FOOTBALL",
    "NHL",
    "MLS",
    "MLB",
]
SPORT_ORDER = [SPORT_KEY_TO_DISPLAY[key] for key in SPORT_ORDER_KEYS]


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
    if raw in SPORT_DISPLAY_TO_KEY:
        return raw
    sport_key = canonicalize_sport_name(raw)
    return SPORT_KEY_TO_DISPLAY.get(sport_key, raw)
