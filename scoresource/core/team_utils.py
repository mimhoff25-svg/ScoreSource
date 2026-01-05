"""Shared team utilities: colors, logos, text helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Tuple

from PySide6.QtGui import QPixmap

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def mix_color(color_hex: str, base_hex: str, factor: float) -> str:
    """Linear mix of two hex colors."""
    def _to_rgb(h: str):
        h = h.lstrip("#")
        if len(h) != 6:
            return (0, 0, 0)
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))

    def _to_hex(rgb: Tuple[int, int, int]) -> str:
        return "#%02x%02x%02x" % rgb

    c = _to_rgb(color_hex)
    b = _to_rgb(base_hex)
    mix = tuple(int(c[i] * factor + b[i] * (1 - factor)) for i in range(3))
    return _to_hex(mix)


def safe_team_name(name: str | None, default: str = "TEAM") -> str:
    if not name:
        return default
    return name.upper()


def load_logo(path: str | Path | None, fallback_color: str = "#0d1523") -> QPixmap:
    """Best-effort local logo loader from assets; returns tinted placeholder on failure."""
    if path:
        p = Path(path)
        if p.exists():
            try:
                pix = QPixmap(str(p))
                if not pix.isNull():
                    return pix
            except Exception:
                pass
    # placeholder
    pix = QPixmap(96, 96)
    pix.fill(fallback_color)
    return pix


def logo_path_for(team_code: str, sport: str) -> Path:
    return ASSETS / "logos" / sport / f"{team_code.lower()}.png"
