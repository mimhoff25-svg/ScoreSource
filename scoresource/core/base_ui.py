"""Shared neon scoreboard scaffolding."""

from __future__ import annotations

from typing import Dict, Iterable, Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from .team_utils import mix_color


PALETTE = {
    "BG": "#050b16",
    "PANEL": "#0b1220",
    "CARD": "#111b2a",
    "ACCENT": "#45e0ff",
    "ACCENT_SOFT": "#7cf3c8",
    "TEXT": "#eaf4ff",
    "TEXT_MUTED": "#6d88ab",
}


class NeonCard(QFrame):
    def __init__(self, radius: int = 12, border: str = "#26344a"):
        super().__init__()
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {PALETTE['CARD']};
                border-radius: {radius}px;
                border: 2px solid {border};
            }}
            """
        )


class BaseScoreboardWindow(QMainWindow):
    """Lightweight shell to host sport-specific widgets."""

    def __init__(
        self,
        sport_name: str,
        *,
        switch_sport: Optional[Callable[[str, "BaseScoreboardWindow"], None]] = None,
        sport_options: Iterable[str] | None = None,
    ):
        super().__init__()
        self.sport_name = sport_name
        self._switch_sport = switch_sport
        self._sport_options = list(sport_options or [])
        self.setWindowTitle(f"ScoreSource - {sport_name}")
        self.resize(1280, 480)
        self.setStyleSheet(f"background-color: {PALETTE['BG']}; color: {PALETTE['TEXT']};")

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Top bar
        bar = QHBoxLayout()
        bar.setSpacing(10)
        if switch_sport and self._sport_options:
            self.sport_combo = QComboBox()
            self.sport_combo.addItems(self._sport_options)
            try:
                idx = self._sport_options.index(sport_name)
                self.sport_combo.setCurrentIndex(idx)
            except ValueError:
                pass
            self.sport_combo.setStyleSheet(
                f"""
                QComboBox {{
                    background-color: #0f1724;
                    padding: 8px 10px;
                    border-radius: 8px;
                    color: {PALETTE['TEXT']};
                    border: 2px solid {PALETTE['ACCENT']};
                    font-weight: 700;
                }}
                """
            )
        else:
            self.sport_combo = None
            self.sport_label = QLabel(sport_name.upper())
            self.sport_label.setStyleSheet(f"color: {PALETTE['ACCENT']}; font-size: 16px; font-weight: 800;")
        self.game_combo = QComboBox()
        self.game_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: #0f1724;
                padding: 8px 12px;
                border-radius: 8px;
                color: {PALETTE['TEXT']};
                border: 2px solid {PALETTE['ACCENT']};
                font-weight: 700;
            }}
            """
        )
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFixedHeight(32)
        self.refresh_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {PALETTE['ACCENT']};
                color: {PALETTE['BG']};
                border-radius: 8px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {mix_color(PALETTE['ACCENT'], '#ffffff', 0.7)}; }}
            """
        )
        bar.addWidget(self.game_combo, stretch=2)
        if self.sport_combo:
            bar.addWidget(self.sport_combo, stretch=1)
            self.sport_combo.currentTextChanged.connect(self._on_sport_change)
        else:
            bar.addWidget(self.sport_label, stretch=1)
        bar.addStretch(1)
        bar.addWidget(self.refresh_btn)
        layout.addLayout(bar)

        # Placeholder center panel that sport UIs can replace
        self.center_frame = QFrame()
        self.center_frame.setStyleSheet(
            f"background-color: {PALETTE['PANEL']}; border-radius: 12px; border: 1px solid #1c2b3c;"
        )
        layout.addWidget(self.center_frame, stretch=1)

    def set_center_widget(self, widget: QWidget):
        layout = self.centralWidget().layout()
        if self.center_frame:
            layout.replaceWidget(self.center_frame, widget)
            self.center_frame.deleteLater()
            self.center_frame = widget

    def set_games(self, lines: list[str]):
        self.game_combo.clear()
        self.game_combo.addItem("Select game")
        for line in lines:
            self.game_combo.addItem(line)

    def _on_sport_change(self, name: str):
        if self._switch_sport:
            self._switch_sport(name, self)
