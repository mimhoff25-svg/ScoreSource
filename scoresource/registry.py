from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from . import nba, nfl, nhl, mlb, ncaa_football, mls

ASSET_LOGO_DIR = Path(__file__).resolve().parent / "assets" / "logos"

SPORT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "NBA": {
        "backend": nba,
        "logo_path": str(ASSET_LOGO_DIR / "nba.png"),
        "icon_path": str(ASSET_LOGO_DIR / "nba.png"),
    },
    "NFL": {
        "backend": nfl,
        "logo_path": str(ASSET_LOGO_DIR / "nfl.png"),
        "icon_path": str(ASSET_LOGO_DIR / "nfl.png"),
    },
    "NHL": {
        "backend": nhl,
        "logo_path": str(ASSET_LOGO_DIR / "nhl.png"),
        "icon_path": str(ASSET_LOGO_DIR / "nhl.png"),
    },
    "MLB": {
        "backend": mlb,
        "logo_path": str(ASSET_LOGO_DIR / "mlb.png"),
        "icon_path": str(ASSET_LOGO_DIR / "mlb.png"),
    },
    "MLS": {
        "backend": mls,
        "logo_path": str(ASSET_LOGO_DIR / "mls.png"),
        "icon_path": str(ASSET_LOGO_DIR / "mls_icon.png"),
    },
    "NCAA Football": {
        "backend": ncaa_football,
        "logo_path": str(ASSET_LOGO_DIR / "ncaa.png"),
        "icon_path": str(ASSET_LOGO_DIR / "ncaa.png"),
    },
}

SPORT_ORDER = ["NBA", "NFL", "NCAA Football", "NHL", "MLS", "MLB"]
