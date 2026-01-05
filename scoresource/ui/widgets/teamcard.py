"""Team card widget with gradient background and logo/record display."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap, QBrush, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QGraphicsDropShadowEffect

from scoresource.common import colors


class TeamCard(QWidget):
    """Broadcast-style team card with logo, name and record."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._primary = QColor(colors.ACCENT)
        self._secondary = QColor(colors.ACCENT_SOFT)
        self._accent = QColor(colors.ACCENT)
        self._logo: Optional[QPixmap] = None
        self._name = QLabel("TEAM", self)
        self._record = QLabel("", self)
        self._logo_label = QLabel(self)
        self._logo_label.setAlignment(Qt.AlignCenter)
        self._name.setAlignment(Qt.AlignCenter)
        self._name.setStyleSheet(f"color: {colors.TEXT}; font-weight: 900; font-size: 18px; letter-spacing: 1px;")
        self._record.setAlignment(Qt.AlignCenter)
        self._record.setStyleSheet(f"color: {colors.TEXT_MUTED}; font-size: 13px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addWidget(self._logo_label)
        layout.addWidget(self._name)
        layout.addWidget(self._record)
        self.setMinimumWidth(200)
        self.setMinimumHeight(240)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.setGraphicsEffect(shadow)

    def set_team(self, name: str, record: str = "", primary: str | None = None, secondary: str | None = None, accent: str | None = None):
        self._name.setText(name.upper())
        self._record.setText(record)
        if primary:
            self._primary = QColor(primary)
        if secondary:
            self._secondary = QColor(secondary)
        if accent:
            self._accent = QColor(accent)
        self.update()

    def set_logo(self, pixmap: Optional[QPixmap]):
        self._logo = pixmap
        if pixmap:
            scaled = pixmap.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._logo_label.setPixmap(scaled)
        else:
            self._logo_label.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(2, 2, -2, -2)
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, self._secondary.lighter(140))
        grad.setColorAt(0.5, self._primary)
        grad.setColorAt(1.0, QColor(colors.TEAM_GRADIENT_BOTTOM))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(self._accent, 2))
        painter.drawRoundedRect(rect, 14, 14)
