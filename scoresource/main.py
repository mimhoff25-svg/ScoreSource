from __future__ import annotations

import sys
from typing import Dict

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication

from .common.paths import state_dir
from .ui import ScoreSourceWindow
from .logic import ScoreSourceLogic
from .registry import DEFAULT_SPORT_DISPLAY, SPORT_ORDER, get_sport_config

_INSTANCE_LOCK: QLockFile | None = None


def _acquire_instance_lock() -> bool:
    global _INSTANCE_LOCK
    lock_path = state_dir() / "scoresource.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(lock_path))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        return False
    _INSTANCE_LOCK = lock
    return True


def _switch_sport(name: str, window: ScoreSourceWindow) -> None:
    # Called when the user changes sport in the combo box.
    from .registry import get_sport_config  # re-import in case of hot-reload

    config = get_sport_config(name)
    if not config:
        return

    display_name = str(config["display_name"])
    sport_key = str(config["sport_key"])
    backend = config["backend"]
    sport_logo_path = config.get("logo_path")

    # Swap backend, sport name, and refresh.
    window.backend = backend
    window.sport_name = display_name
    window._sport_key = sport_key
    if getattr(window, "logic", None):
        window.logic.set_sport(sport_key)  # type: ignore[attr-defined]
    else:
        window.logic = ScoreSourceLogic(default_sport=sport_key)
    window.setWindowTitle(f"ScoreSource – {display_name}")
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
    if not _acquire_instance_lock():
        print("ScoreSource is already running.", file=sys.stderr)
        return

    app = QApplication(sys.argv)
    if hasattr(app, "setApplicationName"):
        app.setApplicationName("ScoreSource")
    if hasattr(app, "setApplicationDisplayName"):
        app.setApplicationDisplayName("ScoreSource")

    config = get_sport_config(DEFAULT_SPORT_DISPLAY)
    if not config:
        raise RuntimeError("Default sport registry entry is missing.")

    default_sport = str(config["display_name"])
    default_sport_key = str(config["sport_key"])
    backend = config["backend"]
    sport_logo_path = config.get("logo_path")

    logic = ScoreSourceLogic(default_sport=default_sport_key)

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
    window._sport_key = default_sport_key
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
