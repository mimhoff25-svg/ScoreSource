"""Main PySide6 window for ScoreSource."""

from __future__ import annotations

from functools import partial
from typing import Dict, List

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow

from scoresource import logic
from scoresource.common import colors
from scoresource.ui.layout import build_main_widget

SPORTS = ["NBA", "NFL", "NHL", "MLS", "MLB", "NCAA Football"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ScoreSource")
        self.resize(1280, 720)
        self._current_sport = SPORTS[0]
        self._games: List[Dict[str, any]] = []
        widget, game_list, center, ticker = build_main_widget(SPORTS, self._on_tab_change, self._on_game_select)
        self.setCentralWidget(widget)
        self.game_list = game_list
        self.center_panel = center
        self.ticker = ticker

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_scores)
        self.refresh_timer.start(15_000)
        self.refresh_scores()

    def _on_tab_change(self, sport: str):
        self._current_sport = sport
        self.refresh_scores()

    def refresh_scores(self):
        data = logic.fetch_scores_for_sport(self._current_sport)
        games = data.get("games") or []
        # enrich with local start time
        for g in games:
            from scoresource.common.utils import iso_to_local
            g["startTimeLocal"] = iso_to_local(g.get("startTime"))
        self._games = games
        self.game_list.populate(games)
        self.ticker.setText(f"{self._current_sport}: {len(games)} games (updated)")

    def _on_game_select(self, game: Dict[str, any]):
        if not game:
            return
        self._apply_logos(game)
        if game.get("status") == "live":
            self.center_panel.show_live(game)
        else:
            self.center_panel.show_pregame(game)

    def _apply_logos(self, game: Dict[str, any]):
        home_logo = logic.load_logo(None, game.get("homeTricode"))
        away_logo = logic.load_logo(None, game.get("awayTricode"))
        if home_logo:
            from PySide6.QtGui import QPixmap

            pm = QPixmap()
            pm.loadFromData(home_logo)
            self.center_panel.home_card.set_logo(pm)
        if away_logo:
            from PySide6.QtGui import QPixmap

            pm = QPixmap()
            pm.loadFromData(away_logo)
            self.center_panel.away_card.set_logo(pm)


def run_app():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.show()
    return app.exec()
