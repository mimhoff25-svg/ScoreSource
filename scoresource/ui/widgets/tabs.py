"""Tab bar widget for sports selection."""

from __future__ import annotations

from typing import Callable, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from scoresource.common import colors


class TabBar(QWidget):
    def __init__(self, sports: List[str], on_change: Callable[[str], None], parent=None):
        super().__init__(parent)
        self._on_change = on_change
        self._sports = sports
        self._buttons: List[QPushButton] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for name in sports:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, n=name: self._select(n))
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {colors.CARD};
                    color: {colors.TEXT};
                    border-radius: 10px;
                    padding: 8px 14px;
                    border: 1px solid #1d2c3e;
                    font-weight: 800;
                }}
                QPushButton:hover {{
                    background-color: {colors.ACCENT};
                    color: {colors.BG};
                }}
                QPushButton:checked {{
                    background-color: {colors.ACCENT};
                    color: {colors.BG};
                    border: 1px solid {colors.ACCENT};
                }}
                """
            )
            layout.addWidget(btn)
            self._buttons.append(btn)
        if self._buttons:
            self._buttons[0].setChecked(True)

    def _select(self, name: str):
        for b in self._buttons:
            b.setChecked(b.text() == name)
        self._on_change(name)
