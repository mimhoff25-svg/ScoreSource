"""Layout builder and styling helpers."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from scoresource.common import colors
from scoresource.ui.widgets.gamelist import GameList
from scoresource.ui.widgets.scoreboard_center import ScoreboardCenter
from scoresource.ui.widgets.tabs import TabBar


def build_main_widget(sports, on_tab_change, on_game_select) -> QWidget:
    root = QWidget()
    root.setStyleSheet(
        f"""
        QWidget {{
            background-color: {colors.BG};
            color: {colors.TEXT};
        }}
        """
    )
    layout = QVBoxLayout(root)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)

    tabs = TabBar(sports, on_change=on_tab_change)
    layout.addWidget(tabs)

    body = QHBoxLayout()
    body.setSpacing(10)

    left_frame = QFrame()
    left_frame.setStyleSheet(
        f"QFrame {{ background-color: {colors.PANEL}; border: 1px solid #1d2c3e; border-radius: 10px; }}"
    )
    left_layout = QVBoxLayout(left_frame)
    left_layout.setContentsMargins(8, 8, 8, 8)
    left_layout.setSpacing(6)
    left_layout.addWidget(QLabel("GAMES"))
    game_list = GameList(on_game_select)
    left_layout.addWidget(game_list)

    center = ScoreboardCenter()

    body.addWidget(left_frame, stretch=1)
    body.addWidget(center, stretch=2)
    layout.addLayout(body)

    ticker = QLabel("ScoreSource ready.")
    ticker.setStyleSheet(f"color: {colors.TEXT_MUTED};")
    layout.addWidget(ticker)

    return root, game_list, center, ticker
