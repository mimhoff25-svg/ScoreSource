"""Shared sport UI layout mirroring the NBA scoreboard style across sports."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from scoresource import logic
from scoresource.common import colors
from scoresource.common.utils import iso_to_local
from scoresource.ui.widgets.teamcard import TeamCard


class BaseSportUI(QWidget):
    """Base widget that renders a full scoreboard layout reused by all sports."""

    def __init__(self, sport: str, on_switch_sport: Callable[[str], None], sport_options: List[str]):
        super().__init__()
        self.sport = sport
        self.on_switch_sport = on_switch_sport
        self.sport_options = sport_options
        self.games: List[Dict[str, any]] = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_scores)
        self._timer.start(15_000)

        self._build_layout()
        self.refresh_scores()

    # ---------- layout ----------
    def _build_layout(self):
        root = QGridLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setHorizontalSpacing(10)
        root.setVerticalSpacing(10)

        # Tabs bar
        tabs = QHBoxLayout()
        tabs.setSpacing(6)
        for name in self.sport_options:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setChecked(name == self.sport)
            btn.clicked.connect(lambda checked, n=name: self._handle_tab(n))
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {colors.CARD};
                    color: {colors.TEXT};
                    border-radius: 12px;
                    padding: 8px 12px;
                    border: 2px solid {colors.ACCENT};
                    font-weight: 800;
                }}
                QPushButton:checked {{
                    background-color: {colors.ACCENT};
                    color: {colors.BG};
                }}
                QPushButton:hover {{
                    background-color: {colors.ACCENT_SOFT};
                    color: {colors.BG};
                }}
                """
            )
            tabs.addWidget(btn)
        tabs.addStretch(1)
        root.addLayout(tabs, 0, 0, 1, 3)

        # Game select combo under tabs
        self.game_combo = QComboBox()
        self.game_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {colors.PANEL};
                color: {colors.TEXT};
                border: 2px solid {colors.ACCENT};
                border-radius: 8px;
                padding: 8px 10px;
                font-weight: 800;
            }}
            QComboBox QAbstractItemView {{
                background: {colors.PANEL};
                color: {colors.TEXT};
                selection-background-color: {colors.ACCENT};
                selection-color: {colors.BG};
            }}
            """
        )
        self.game_combo.currentIndexChanged.connect(self._on_game_selected)
        root.addWidget(self.game_combo, 1, 0, 1, 3)

        # Left game list
        self.game_list = QListWidget()
        self.game_list.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {colors.PANEL};
                border: 2px solid {colors.ACCENT};
                border-radius: 10px;
                color: {colors.TEXT};
            }}
            QListWidget::item {{
                padding: 10px;
            }}
            QListWidget::item:selected {{
                background: {colors.ACCENT};
                color: {colors.BG};
            }}
            """
        )
        self.game_list.itemSelectionChanged.connect(self._handle_list_select)
        root.addWidget(self.game_list, 2, 0, 3, 1)

        # Center header row (period + clock)
        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        self.period_label = QLabel("Q-")
        self.period_label.setAlignment(Qt.AlignCenter)
        self.period_label.setStyleSheet(
            f"color: {colors.TEXT}; background: {colors.CARD}; border: 2px solid {colors.ACCENT};"
            "border-radius: 10px; padding: 8px 14px; font-weight: 900; font-size: 16px; letter-spacing: 1px;"
        )
        self.clock_label = QLabel("--:--")
        self.clock_label.setAlignment(Qt.AlignCenter)
        self.clock_label.setStyleSheet(
            "color: #111; background: #d0d3d9; border-radius: 10px; padding: 12px 18px; font-weight: 900; font-size: 22px;"
        )
        header_row.addWidget(self.period_label)
        header_row.addWidget(self.clock_label, stretch=1)
        header_frame = QFrame()
        header_frame.setLayout(header_row)
        root.addWidget(header_frame, 2, 1, 1, 2)

        # Team panels and scores
        team_layout = QHBoxLayout()
        team_layout.setSpacing(12)
        self.away_card = TeamCard()
        self.home_card = TeamCard()
        self.away_score = QLabel("--")
        self.home_score = QLabel("--")
        for lbl in (self.away_score, self.home_score):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {colors.TEXT}; background: {colors.CARD}; border: 2px solid {colors.ACCENT};"
                "border-radius: 14px; padding: 14px; font-size: 38px; font-weight: 900;"
            )
            lbl.setFixedWidth(130)
            lbl.setFixedHeight(96)
        team_layout.addWidget(self.away_score, alignment=Qt.AlignBottom)
        team_layout.addWidget(self.away_card, stretch=1)
        team_layout.addWidget(self.home_card, stretch=1)
        team_layout.addWidget(self.home_score, alignment=Qt.AlignBottom)
        team_frame = QFrame()
        team_frame.setLayout(team_layout)
        root.addWidget(team_frame, 3, 1, 1, 2)

        # Stats tables
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)
        self.away_table = self._make_table("STATS")
        self.home_table = self._make_table("STATS")
        stats_layout.addWidget(self.away_table)
        stats_layout.addWidget(self.home_table)
        stats_frame = QFrame()
        stats_frame.setLayout(stats_layout)
        root.addWidget(stats_frame, 4, 1, 1, 2)

        # Footer bar
        self.footer = QLabel(" ")
        self.footer.setAlignment(Qt.AlignCenter)
        self.footer.setStyleSheet(
            f"background: {colors.PANEL}; color: {colors.TEXT_MUTED}; border: 1px solid #1d2c3e; border-radius: 8px; padding: 8px;"
        )
        root.addWidget(self.footer, 5, 0, 1, 3)

    def _make_table(self, title: str) -> QTableWidget:
        headers = ["#", "Player", "Pos", "Stat1", "Stat2", "Stat3", "Stat4", "Stat5"]
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        self._apply_table_column_layout(table)
        table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {colors.PANEL};
                color: {colors.TEXT};
                border: 1px solid #1d2c3e;
                border-radius: 10px;
            }}
            QHeaderView::section {{
                background: #1c2a3e;
                color: {colors.TEXT};
                border: 0px;
                padding: 6px;
                font-weight: 800;
            }}
            """
        )
        return table

    def _apply_table_column_layout(self, table: QTableWidget) -> None:
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Fixed)
        count = table.columnCount()
        if count == 0:
            return
        table.setColumnWidth(0, 48)
        if count > 2:
            table.setColumnWidth(2, 54)
        for idx in range(3, count):
            table.setColumnWidth(idx, 56)
        if count > 1:
            header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        if count > 2:
            header.setSectionResizeMode(2, QHeaderView.Fixed)
        for idx in range(3, count):
            header.setSectionResizeMode(idx, QHeaderView.Fixed)

    # ---------- data handling ----------
    def refresh_scores(self):
        data = logic.fetch_scores_for_sport(self.sport)
        games = data.get("games") or []
        for g in games:
            g["startTimeLocal"] = iso_to_local(g.get("startTime"))
        self.games = games
        self._populate_lists()
        if games:
            self._apply_game(games[0])

    def _populate_lists(self):
        self.game_list.blockSignals(True)
        self.game_combo.blockSignals(True)
        self.game_list.clear()
        self.game_combo.clear()
        for g in self.games:
            line = self._game_line(g)
            item = QListWidgetItem(line)
            item.setData(Qt.UserRole, g)
            self.game_list.addItem(item)
            self.game_combo.addItem(line, g)
        self.game_list.blockSignals(False)
        self.game_combo.blockSignals(False)
        if self.game_list.count():
            self.game_list.setCurrentRow(0)
            self.game_combo.setCurrentIndex(0)

    def _game_line(self, g: Dict[str, Any]) -> str:
        if g.get("status") == "live":
            return f"{g['away']} {g.get('awayScore',0)} @ {g['home']} {g.get('homeScore',0)} ({g.get('period','')} {g.get('clock','--')})"
        return f"{g['away']} @ {g['home']} (Starts {g.get('startTimeLocal','--:--')})"

    def _on_game_selected(self, index: int):
        if index < 0 or index >= len(self.games):
            return
        self._apply_game(self.games[index])

    def _handle_list_select(self):
        items = self.game_list.selectedItems()
        if not items:
            return
        g = items[0].data(Qt.UserRole)
        if g:
            self._apply_game(g)
            self.game_combo.blockSignals(True)
            self.game_combo.setCurrentIndex(self.game_list.currentRow())
            self.game_combo.blockSignals(False)

    def _apply_game(self, game: Dict[str, Any]):
        status = game.get("status")
        # logos
        self._apply_logo(self.away_card, game.get("awayTricode"))
        self._apply_logo(self.home_card, game.get("homeTricode"))
        # team info
        self.away_card.set_team(game.get("away", "Away"))
        self.home_card.set_team(game.get("home", "Home"))
        # scores and header
        if status == "live":
            self.period_label.setText(str(game.get("period", "")))
            self.clock_label.setText(str(game.get("clock", "--")))
            self.away_score.setText(str(game.get("awayScore", "--")))
            self.home_score.setText(str(game.get("homeScore", "--")))
            self._fill_table_live()
            self.footer.setText("Live")
        else:
            self.period_label.setText("PRE-GAME")
            start = game.get("startTimeLocal", "--:--")
            self.clock_label.setText(f"Starts at {start}")
            self.away_score.setText("--")
            self.home_score.setText("--")
            self._fill_table_pregame()
            self.footer.setText("Scheduled")

    def _fill_table_pregame(self):
        self._fill_placeholder(self.away_table)
        self._fill_placeholder(self.home_table)

    def _fill_placeholder(self, table: QTableWidget):
        table.setRowCount(1)
        for col in range(table.columnCount()):
            item = QTableWidgetItem("No stats available yet." if col == 1 else "--")
            item.setTextAlignment(Qt.AlignCenter)
            table.setItem(0, col, item)

    def _fill_table_live(self):
        # Placeholder until per-sport boxscores are wired; keep consistent message.
        self._fill_placeholder(self.away_table)
        self._fill_placeholder(self.home_table)

    def _apply_logo(self, card: TeamCard, tricode: Optional[str]):
        data = logic.load_logo(None, tricode or "")
        if data:
            pm = QPixmap()
            pm.loadFromData(data)
            card.set_logo(pm)
        else:
            card.set_logo(None)

    def _handle_tab(self, name: str):
        if name == self.sport:
            return
        self.on_switch_sport(name)

    def closeEvent(self, event):
        try:
            self._timer.stop()
        except Exception:
            pass
        super().closeEvent(event)
