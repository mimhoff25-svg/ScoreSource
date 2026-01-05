from __future__ import annotations

import sys
from typing import Dict, Any

from PySide6.QtWidgets import QApplication

from .ui import ScoreSourceWindow
from .logic import ScoreSourceLogic
from .registry import SPORT_REGISTRY, SPORT_ORDER


def _switch_sport(name: str, window: ScoreSourceWindow) -> None:
    # Called when the user changes sport in the combo box.
    from .registry import SPORT_REGISTRY  # re-import in case of hot-reload

    config = SPORT_REGISTRY.get(name)
    if not config:
        return

    backend = config["backend"]
    sport_logo_path = config.get("logo_path")

    # Swap backend, sport name, and refresh.
    window.backend = backend
    window.sport_name = name
    if getattr(window, "logic", None):
        window.logic.set_sport(name)  # type: ignore[attr-defined]
    else:
        window.logic = ScoreSourceLogic(default_sport=name)
    window.setWindowTitle(f"ScoreSource – {name}")
    window._sport_options = SPORT_ORDER
    window._sport_logo_path = sport_logo_path
    window.update_table_headers(getattr(backend, "sport_table_headers", None))
    window.update_league_logo(sport_logo_path)
    if hasattr(window, "_apply_cached_state_if_available"):
        try:
            window._apply_cached_state_if_available()
        except Exception:
            pass
    if hasattr(window, "_update_rss_mode"):
        try:
            window._update_rss_mode(force=True)
        except Exception:
            pass
    window.refresh_scores()  # kick off new sport fetch


def main() -> None:
    app = QApplication(sys.argv)

    default_sport = "NBA"
    config = SPORT_REGISTRY[default_sport]
    backend = config["backend"]
    sport_logo_path = config.get("logo_path")

    logic = ScoreSourceLogic(default_sport=default_sport)

    # Build optional icon map if you have icons; otherwise leave empty:
    sport_icon_map: Dict[str, str] = {
        # "NBA": "assets/icons/nba.png",
        # "NFL": "assets/icons/nfl.png",
        # ...
    }

    window = ScoreSourceWindow(
        logic=logic,
        switch_sport=_switch_sport,
        sport_options=SPORT_ORDER,
        backend_module=backend,
        sport_name=default_sport,
        sport_logo_path=sport_logo_path,
        sport_icon_map=sport_icon_map,
    )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
