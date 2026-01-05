"""Game list widget."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from scoresource.common import colors


class GameList(QListWidget):
    def __init__(self, on_select: Callable[[Dict[str, any]], None], parent=None):
        super().__init__(parent)
        self._on_select = on_select
        self.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {colors.PANEL};
                color: {colors.TEXT};
                border: 1px solid #1d2c3e;
                border-radius: 8px;
            }}
            QListWidget::item {{
                padding: 8px;
            }}
            QListWidget::item:selected {{
                background: {colors.ACCENT};
                color: {colors.BG};
            }}
            """
        )
        self.itemSelectionChanged.connect(self._handle_select)

    def populate(self, games: List[Dict[str, any]]):
        self.clear()
        for g in games:
            line = f"{g['away']} {g.get('awayScore',0)} @ {g['home']} {g.get('homeScore',0)}"
            if g.get("status") != "live":
                line = f"{g['away']} @ {g['home']} (Starts {g.get('startTimeLocal','--:--')})"
            item = QListWidgetItem(line)
            item.setData(Qt.UserRole, g)
            self.addItem(item)
        if self.count():
            self.setCurrentRow(0)

    def _handle_select(self):
        items = self.selectedItems()
        if not items:
            return
        g = items[0].data(Qt.UserRole)
        self._on_select(g)
