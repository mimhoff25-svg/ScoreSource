"""UI package for ScoreSource.

There are two UI layers in this repo:
- `scoresource/ui.py` (root file) contains the full neon scoreboard window (ScoreSourceWindow)
- `scoresource/ui/` (this package) hosts supporting widgets and a lightweight MainWindow prototype

To keep the package importable, we lazy-load ScoreSourceWindow from the root
module via a file loader (avoids the name clash with this package).
"""

from __future__ import annotations

import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

from scoresource.ui.app import MainWindow

ScoreSourceWindow = None
_LOAD_ERROR: Exception | None = None
try:
    _root_ui_path = Path(__file__).resolve().parent.parent / "ui.py"
    if _root_ui_path.exists():
        spec = spec_from_loader(
            "scoresource._ui_window", SourceFileLoader("scoresource._ui_window", str(_root_ui_path))
        )
        if spec and spec.loader:
            module = module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)  # type: ignore[arg-type]
            ScoreSourceWindow = getattr(module, "ScoreSourceWindow", None)
except Exception as exc:  # capture to surface meaningful error
    _LOAD_ERROR = exc
    ScoreSourceWindow = None

if ScoreSourceWindow is None:
    # Bubble a clearer message so callers know why the window isn't available.
    hint = (
        f"ScoreSource UI failed to load ({_LOAD_ERROR}). "
        "Ensure PySide6 is installed and all UI dependencies are available."
    )
    raise ImportError(hint)

__all__ = ["MainWindow", "ScoreSourceWindow"]
