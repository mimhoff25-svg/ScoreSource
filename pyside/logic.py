"""Legacy shim for direct ``pyside.logic`` imports."""

from __future__ import annotations

from typing import Any, Dict

from scoresource.logic import ScoreSourceLogic as _ScoreSourceLogic


class ScoreSourceLogic(_ScoreSourceLogic):
    """Thin wrapper to preserve old imports from ``pyside.logic``."""

    def __init__(self, backend_module: Any | None = None) -> None:
        sport = "NBA"
        try:
            sport = getattr(backend_module, "sport_name", "NBA") if backend_module else "NBA"
        except Exception:
            sport = "NBA"
        super().__init__(sport=sport)


def fetch_scores() -> Dict[str, Any]:
    return ScoreSourceLogic().fetch_scores()


def fetch_boxscore(game_id: str) -> Dict[str, Any]:
    return ScoreSourceLogic().fetch_boxscore("NBA", game_id)
