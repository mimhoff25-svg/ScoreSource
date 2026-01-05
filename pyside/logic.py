"""
Legacy shim to keep direct `pyside/` entrypoints working.

Delegates to the unified scoresource.logic facade so there is a single
source of truth for sport switching, caching, and realtime hooks.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Dict

# Ensure project root is on sys.path when launching this file directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scoresource.logic import ScoreSourceLogic as _ScoreSourceLogic  # type: ignore


class ScoreSourceLogic(_ScoreSourceLogic):
    """
    Thin wrapper to preserve old imports (from pyside.logic import ScoreSourceLogic).
    All functionality lives in scoresource.logic.
    """

    def __init__(self, backend_module: Any | None = None) -> None:
        sport = "NBA"
        try:
            # If a backend module is provided, infer its name; otherwise default to NBA.
            sport = getattr(backend_module, "sport_name", "NBA") if backend_module else "NBA"
        except Exception:
            sport = "NBA"
        super().__init__(sport=sport)


# legacy aliases
def fetch_scores() -> Dict[str, Any]:
    return ScoreSourceLogic().fetch_scores()


def fetch_boxscore(game_id: str) -> Dict[str, Any]:
    return ScoreSourceLogic().fetch_boxscore("NBA", game_id)
