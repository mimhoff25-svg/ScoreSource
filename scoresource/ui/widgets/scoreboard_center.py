"""Center panel for ScoreSource scoreboard."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget

from scoresource.common import colors
from scoresource.ui.widgets.teamcard import TeamCard


class ScoreboardCenter(QWidget):
    """Displays two teams and status."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.away_card = TeamCard()
        self.home_card = TeamCard()
        self.status_label = QLabel(" ")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(f"color: {colors.TEXT}; font-weight: 900; font-size: 20px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        cards.addWidget(self.away_card, stretch=1)
        cards.addWidget(self.home_card, stretch=1)
        layout.addLayout(cards)
        layout.addWidget(self.status_label)

    def show_live(self, game):
        self.away_card.set_team(game["away"], record="", primary=None)
        self.home_card.set_team(game["home"], record="", primary=None)
        status = f"{game.get('period','')} {game.get('clock','--')}".strip()
        score = f"{game.get('awayScore',0)} - {game.get('homeScore',0)}"
        self.status_label.setText(f"{status}   |   {score}")

    def show_pregame(self, game):
        self.away_card.set_team(game["away"], record="", primary=None)
        self.home_card.set_team(game["home"], record="", primary=None)
        self.status_label.setText(f"Starts at {game.get('startTimeLocal','--:--')}")
