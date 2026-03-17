"""
PySide6 UI for ScoreSource.
Layout: neon night 1280x400 scoreboard with team panels, center clock/shot clock,
and player stat tables. Periodically polls the active sport backend.
"""

import json
import os
import re
import time
from colorsys import hls_to_rgb, rgb_to_hls
from datetime import datetime
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Callable

from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QPoint, QRect, QSize, QPropertyAnimation, QEasingCurve, QEvent, QPointF
from PySide6.QtGui import (
    QPalette,
    QColor,
    QPixmap,
    QIcon,
    QShortcut,
    QPainter,
    QLinearGradient,
    QPen,
    QRadialGradient,
    QBrush,
    QAction,
    QActionGroup,
    QFont,
    QFontMetrics,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QLabel,
    QLCDNumber,
    QFrame,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QComboBox,
    QPushButton,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QScroller,
    QSizePolicy,
    QApplication,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QToolButton,
    QMenu,
    QStackedLayout,
    QDialog,
    QScrollArea,
)

PLAYER_DIVIDER_ROLE = Qt.UserRole + 1
GAME_DATA_ROLE = Qt.UserRole
GAME_LOGO_AWAY_ROLE = Qt.UserRole + 10
GAME_LOGO_HOME_ROLE = Qt.UserRole + 11
GAME_LOGO_AWAY_KEY_ROLE = Qt.UserRole + 12
GAME_LOGO_HOME_KEY_ROLE = Qt.UserRole + 13
PLAYER_CONTEXT_ROLE = Qt.UserRole + 20
GAME_LOGO_SIZE = 36

from .. import nba as default_backend
from ..logic import ScoreSourceLogic
from ..sports_meta import canonicalize_sport_name
from ..realtime import RealTimeGameState
from ..common.utils import extract_three_point_made, format_player_initial_name, iso_to_local

# Palette
BG = "#050b16"
PANEL = "#0b1220"
CARD = "#111b2a"
ACCENT = "#45e0ff"
ACCENT_SOFT = "#7cf3c8"
TEXT = "#eaf4ff"
TEXT_MUTED = "#6d88ab"
TIMEOUT_ACTIVE = "#d44b4b"
TIMEOUT_INACTIVE = "#f0a1a1"
POSSESSION_HIGHLIGHT = "#f6b33c"
POSSESSION_HIGHLIGHT_BORDER = "#c98a18"
POSSESSION_HIGHLIGHT_TEXT = "#1f1300"
THREE_POINT_FLASH = "#ffd34d"
TICKER_SPEED_PX = 16.0
TICKER_LOGO_SIZE = 36
TICKER_LOGO_GAP = 6
TICKER_TEXT_GAP = 8
TICKER_SEGMENT_GAP = 24
PBP_TICKER_SPEED_MULTIPLIER = 1.6
PBP_TICKER_MAX = 12
PBP_TICKER_SEPARATOR = "  |  "
FADE_DURATION_MS = 180
CITY_FONT_SIZE = 16
NBA_PLAYER_COL_WIDTH = 150
NBA_POS_COL_WIDTH = 46
NBA_MIN_COL_WIDTH = 70
NBA_STAT_COL_WIDTH = 58
NBA_THREE_COL_WIDTH = 62
MULTIWORD_NICKNAMES = {
    "TRAIL BLAZERS",
    "RED SOX",
    "WHITE SOX",
    "BLUE JAYS",
    "BLUE JACKETS",
    "RED WINGS",
    "MAPLE LEAFS",
    "GOLDEN KNIGHTS",
}
CENTER_BOTTOM_LEFT_STYLE = f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;"
CENTER_BOTTOM_CENTER_STYLE = f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 700;"
CENTER_BOTTOM_RIGHT_STYLE = f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;"
NBA_CENTER_BOTTOM_LEFT_STYLE = f"color: {TEXT_MUTED}; font-size: 16px; font-weight: 900;"
NBA_CENTER_BOTTOM_CENTER_STYLE = f"color: {TEXT_MUTED}; font-size: 14px; font-weight: 900; letter-spacing: 0.4px;"
NBA_CENTER_BOTTOM_RIGHT_STYLE = f"color: {TEXT_MUTED}; font-size: 16px; font-weight: 900;"
DEFAULT_TABLE_HEADERS = ["#", "Player", "Min", "Pos", "Pts", "Reb", "Ast", "3pt"]
NBA_SCROLL_HEADERS = ["#", "Player", "Pos", "Min", "Pts", "Reb", "Ast", "3PT", "Stl", "Blk", "TO", "+/-"]
NFL_OFFENSE_HEADERS = ["#", "Player", "Pos", "Yds", "TD", "Rec", "Car", "Int"]
NFL_DEFENSE_HEADERS = ["#", "Player", "Pos", "Tkl", "Ast", "Sack", "Int", "PD"]
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 400
TOP_SECTION_HEIGHT = 190
BOTTOM_SECTION_HEIGHT = WINDOW_HEIGHT - TOP_SECTION_HEIGHT
CENTER_PANEL_WIDTH = 200
SIDE_SECTION_WIDTH = (WINDOW_WIDTH - CENTER_PANEL_WIDTH) // 2
LOGO_HEIGHT = min(int(TOP_SECTION_HEIGHT * 0.90), (int(TOP_SECTION_HEIGHT * 0.60) + 2) * 2)
LOGO_WIDTH = LOGO_HEIGHT * 2
DEFAULT_LOGO_SCALE = 0.95
LOGO_SCALE_OVERRIDES = {
    "OKC": 1.5,
    "LAL": 1.5,
}
LOGO_Y_OFFSET_OVERRIDES = {
    "OKC": 2,
}
LOGO_SHADOW_OVERRIDES = {
    "TOR": {"dx": 0, "dy": 2, "alpha": 130},
}
MLB_BG_COLOR_OVERRIDES = {
    # Keep Pirates side darker so the mark doesn't fight the yellow-heavy panel tint.
    "PIT": ("#141922", "#2a303b"),
}
NHL_BG_COLOR_OVERRIDES = {
    # Hold Dallas on a stronger Victory Green panel instead of drifting toward teal/neon.
    "DAL": ("#006847", "#0a7a55"),
}
CENTER_SEAM_WIDTH = 220
TOP_H_MARGIN = 24
TOP_V_MARGIN = 24
TOP_BOTTOM_MARGIN = 6
CONTROL_BAR_HEIGHT = 22
BOTTOM_H_MARGIN = 12
BOTTOM_V_MARGIN = 2
TABLE_GAP = 18
SCORE_CARD_WIDTH = 150
SCORE_CARD_HEIGHT = 90
BOTTOM_SECTION_SPACING = 2
PBP_BAR_HEIGHT = 0
BOTTOM_BAR_HEIGHT = 22
TABLES_HEIGHT = BOTTOM_SECTION_HEIGHT - PBP_BAR_HEIGHT - BOTTOM_BAR_HEIGHT - (BOTTOM_V_MARGIN * 2) - (BOTTOM_SECTION_SPACING * 2)
STATE_PATH = Path.home() / ".cache" / "scoresource" / "state.json"
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


class CircularLogoGlow(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(LOGO_WIDTH, LOGO_HEIGHT)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background-color: transparent;")
        self._primary = QColor(ACCENT)
        self._secondary = QColor(ACCENT)
        self._accent = QColor(ACCENT)
        self._pixmap: QPixmap | None = None
        self._logo_scale = DEFAULT_LOGO_SCALE
        self._logo_y_offset = 0
        self._shadow_offset = QPoint(0, 0)
        self._shadow_alpha = 0
        self._shadow_scale = 1.0

    def set_colors(self, primary: str, secondary: str, accent: str):
        self._primary = QColor(primary)
        self._secondary = QColor(secondary)
        self._accent = QColor(accent)
        self.update()

    def set_logo(self, pixmap: QPixmap | None):
        self._pixmap = pixmap
        self.update()

    def set_logo_scale(self, scale: float) -> None:
        try:
            self._logo_scale = float(scale)
        except Exception:
            self._logo_scale = DEFAULT_LOGO_SCALE
        self.update()

    def set_logo_y_offset(self, offset: int) -> None:
        try:
            self._logo_y_offset = int(offset)
        except Exception:
            self._logo_y_offset = 0
        self.update()

    def set_logo_shadow(self, dx: int, dy: int, alpha: int, scale: float = 1.0) -> None:
        self._shadow_offset = QPoint(int(dx), int(dy))
        self._shadow_alpha = max(0, min(255, int(alpha)))
        try:
            self._shadow_scale = float(scale)
        except Exception:
            self._shadow_scale = 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), Qt.transparent)
        if self._pixmap:
            scale = max(0.6, min(2.2, self._logo_scale))
            max_w = max(1, int(self.width() * scale))
            max_h = max(1, int(self.height() * scale))
            scaled = self._pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.width() - scaled.width()) / 2
            y = (self.height() - scaled.height()) / 2 + self._logo_y_offset
            if self._shadow_alpha > 0 and (self._shadow_offset.x() or self._shadow_offset.y()):
                shadow_src = scaled
                if abs(self._shadow_scale - 1.0) > 0.01:
                    shadow_src = scaled.scaled(
                        max(1, int(scaled.width() * self._shadow_scale)),
                        max(1, int(scaled.height() * self._shadow_scale)),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                shadow = QPixmap(shadow_src.size())
                shadow.fill(Qt.transparent)
                shadow_painter = QPainter(shadow)
                shadow_painter.setCompositionMode(QPainter.CompositionMode_Source)
                shadow_painter.drawPixmap(0, 0, shadow_src)
                shadow_painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
                shadow_painter.fillRect(shadow.rect(), QColor(0, 0, 0, self._shadow_alpha))
                shadow_painter.end()
                shadow_dx = (shadow.width() - scaled.width()) / 2
                shadow_dy = (shadow.height() - scaled.height()) / 2
                painter.drawPixmap(
                    int(x - shadow_dx + self._shadow_offset.x()),
                    int(y - shadow_dy + self._shadow_offset.y()),
                    shadow,
                )
            painter.drawPixmap(int(x), int(y), scaled)


class TeamGradientHeader(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedSize(WINDOW_WIDTH, TOP_SECTION_HEIGHT)
        self.setStyleSheet("background: transparent;")


class DragBar(QWidget):
    """Invisible bar to drag the window when using custom chrome."""

    def __init__(self, window: QMainWindow):
        super().__init__()
        self._window = window
        self._drag_pos: QPoint | None = None
        self.setFixedHeight(18)
        self.setStyleSheet("background-color: transparent;")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        event.accept()


class GameLineDelegate(QStyledItemDelegate):
    """Custom paint for game select items: highlight leader and right-align status."""

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), 44))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        data = index.data(GAME_DATA_ROLE)
        display = index.data(Qt.DisplayRole) or ""

        painter.save()
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.instance().style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter)

        rect = opt.rect.adjusted(6, 4, -6, -4)
        base_font = QFont(opt.font)
        base_font.setWeight(QFont.Medium)
        painter.setFont(base_font)
        fm = painter.fontMetrics()
        time_font = QFont(opt.font)
        time_font.setPointSize(max(opt.font.pointSize() - 1, 9))
        time_font.setWeight(QFont.Normal)
        time_fm = QFontMetrics(time_font)

        # If no structured data, fall back to default text.
        if not isinstance(data, dict):
            painter.setPen(opt.palette.text().color())
            painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, display)
            painter.restore()
            return

        away_name = data.get("away_name", "")
        home_name = data.get("home_name", "")
        away_code = (data.get("away_tricode") or "").upper()
        home_code = (data.get("home_tricode") or "").upper()
        away_score = int(data.get("away_score") or 0)
        home_score = int(data.get("home_score") or 0)
        away_logo = index.data(GAME_LOGO_AWAY_ROLE)
        home_logo = index.data(GAME_LOGO_HOME_ROLE)
        status_state = (data.get("status_state") or "").lower()
        status_text = data.get("status_text") or ""
        start_time_raw = data.get("startTime") or ""
        time_text = data.get("startTimeLocal") or iso_to_local(start_time_raw)
        if not time_text or time_text == "--:--":
            time_text = "TBA"

        top_h = rect.height() // 2
        top_rect = QRect(rect.left(), rect.top(), rect.width(), top_h)
        bottom_rect = QRect(rect.left(), rect.top() + top_h, rect.width(), rect.height() - top_h)

        def _abbr(name: str) -> str:
            parts = name.split()
            if parts:
                return parts[0][:3].upper()
            return name[:3].upper()

        away_seg = f"{away_code or _abbr(away_name)} {away_score}"
        home_seg = f"{home_code or _abbr(home_name)} {home_score}"
        at_seg = " @ "

        w_away = fm.horizontalAdvance(away_seg)
        w_home = fm.horizontalAdvance(home_seg)
        w_at = fm.horizontalAdvance(at_seg)

        x = bottom_rect.left() + 6
        center_y = bottom_rect.center().y()
        logo_size = min(GAME_LOGO_SIZE, max(0, bottom_rect.height() - 4))
        logo_padding = 6
        logo_y = center_y - (logo_size // 2)

        leader = "away" if away_score > home_score else ("home" if home_score > away_score else None)

        underline_y = bottom_rect.bottom() - 2

        if status_state == "upcoming":
            top_text = time_text
        elif status_state == "live":
            top_text = status_text or "Live"
        elif status_state == "final":
            top_text = status_text or "Final"
        else:
            top_text = status_text or time_text

        painter.setFont(time_font)
        painter.setPen(QColor("#95a3bd"))
        if top_text:
            top_draw = time_fm.elidedText(top_text, Qt.ElideRight, top_rect.width())
            painter.drawText(top_rect, Qt.AlignVCenter | Qt.AlignLeft, top_draw)
        painter.setFont(base_font)

        # Draw away segment
        painter.setPen(opt.palette.text().color())
        if logo_size > 0 and isinstance(away_logo, QPixmap) and not away_logo.isNull():
            painter.drawPixmap(QRect(x, logo_y, logo_size, logo_size), away_logo)
            x += logo_size + logo_padding
        away_text_x = x
        painter.drawText(
            QRect(away_text_x, bottom_rect.top(), w_away, bottom_rect.height()), Qt.AlignVCenter | Qt.AlignLeft, away_seg
        )
        if leader == "away":
            painter.setPen(QPen(QColor(TEXT), 1.3))
            painter.drawLine(away_text_x, underline_y, away_text_x + w_away, underline_y)
            painter.setPen(opt.palette.text().color())
        x = away_text_x + w_away

        # Separator
        painter.drawText(QRect(x, bottom_rect.top(), w_at, bottom_rect.height()), Qt.AlignVCenter | Qt.AlignLeft, at_seg)
        x += w_at

        # Home segment
        if logo_size > 0 and isinstance(home_logo, QPixmap) and not home_logo.isNull():
            painter.drawPixmap(QRect(x, logo_y, logo_size, logo_size), home_logo)
            x += logo_size + logo_padding
        home_text_x = x
        painter.drawText(
            QRect(home_text_x, bottom_rect.top(), w_home, bottom_rect.height()), Qt.AlignVCenter | Qt.AlignLeft, home_seg
        )
        if leader == "home":
            painter.setPen(QPen(QColor(TEXT), 1.3))
            painter.drawLine(home_text_x, underline_y, home_text_x + w_home, underline_y)
            painter.setPen(opt.palette.text().color())
        painter.setPen(opt.palette.text().color())
        painter.restore()


class PlayerRowDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, *, line_color: str = "#2b3e55", line_width: int = 2):
        super().__init__(parent)
        self._line_color = QColor(line_color)
        self._line_width = line_width

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        super().paint(painter, option, index)
        if not index.data(PLAYER_DIVIDER_ROLE):
            return
        painter.save()
        pen = QPen(self._line_color, self._line_width)
        painter.setPen(pen)
        y = option.rect.bottom() - 1
        painter.drawLine(option.rect.left(), y, option.rect.right(), y)
        painter.restore()


class _BasesDiamondWidget(QWidget):
    """Baseball bases diamond — clean broadcast TV style (ESPN/Fox corner graphic)."""

    _EMPTY    = QColor( 45,  50,  60)   # dark unfilled base
    _EMPTY_BD = QColor(120, 125, 135)   # border for empty base
    _OCCUPIED = QColor(255, 200,   0)   # bright yellow — runner on base
    _OCC_BD   = QColor(255, 230, 100)   # lighter border when occupied
    _PATH     = QColor(100, 105, 115)   # thin baseline connectors
    _LIGHT_OFF = QColor(62, 68, 78)
    _BALL_ON = QColor(255, 200, 0)
    _STRIKE_ON = QColor(110, 200, 255)
    _OUT_ON = QColor(235, 90, 90)
    _LABEL = QColor(168, 180, 198)

    def __init__(self):
        super().__init__()
        self._first  = False
        self._second = False
        self._third  = False
        self._balls = 0
        self._strikes = 0
        self._outs = 0

    def set_bases(self, first: bool = False, second: bool = False, third: bool = False) -> None:
        self._first  = first
        self._second = second
        self._third  = third
        self.update()

    @staticmethod
    def _clamp_count(value: Any, max_value: int) -> int:
        try:
            if value in (None, ""):
                return 0
            parsed = int(value)
        except Exception:
            return 0
        return max(0, min(int(max_value), parsed))

    def set_count(self, balls: Any = None, strikes: Any = None, outs: Any = None) -> None:
        self._balls = self._clamp_count(balls, 3)
        self._strikes = self._clamp_count(strikes, 2)
        self._outs = self._clamp_count(outs, 2)
        self.update()

    def sizeHint(self):
        return QSize(CENTER_PANEL_WIDTH, 110)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Center of the diamond, shifted slightly up so it feels balanced
        cx = w // 2
        cy = h // 2 - int(h * 0.05)

        # Distance from center to each base
        r = int(min(w, h) * 0.36)

        home   = QPointF(cx,     cy + r)
        first  = QPointF(cx + r, cy)
        second = QPointF(cx,     cy - r)
        third  = QPointF(cx - r, cy)

        # ── Basepath lines ───────────────────────────────────────────────
        p.setPen(QPen(self._PATH, 1.5))
        for a, b in [(home, first), (first, second), (second, third), (third, home)]:
            p.drawLine(a, b)

        # ── Base squares (rotated 45° — broadcast standard) ─────────────
        bs = max(7, r // 5)

        def draw_base(pos: QPointF, occupied: bool) -> None:
            p.save()
            p.translate(pos)
            p.rotate(45)
            if occupied:
                p.setBrush(QBrush(self._OCCUPIED))
                p.setPen(QPen(self._OCC_BD, 1.5))
            else:
                p.setBrush(QBrush(self._EMPTY))
                p.setPen(QPen(self._EMPTY_BD, 1.5))
            p.drawRect(QRectF(-bs, -bs, bs * 2, bs * 2))
            p.restore()

        # Draw order: back to front
        draw_base(second, self._second)
        draw_base(third,  self._third)
        draw_base(first,  self._first)

        # ── Home plate — five-sided like the real thing ──────────────────
        hp = max(7, r // 5)
        hp_pts = QPolygonF([
            QPointF(home.x() - hp,  home.y() - hp * 0.55),
            QPointF(home.x() - hp,  home.y() + hp * 0.15),
            QPointF(home.x(),        home.y() + hp * 0.70),
            QPointF(home.x() + hp,  home.y() + hp * 0.15),
            QPointF(home.x() + hp,  home.y() - hp * 0.55),
        ])
        p.setBrush(QBrush(self._EMPTY))
        p.setPen(QPen(self._EMPTY_BD, 1.5))
        p.drawPolygon(hp_pts)

        # ── TV-style count lights near the bottom of the diamond ──────────
        dot_r = max(3, bs // 2)
        dot_gap = max(3, dot_r - 1)
        group_gap = max(8, dot_r * 2 + 2)
        label_gap = max(4, dot_r)
        # Anchor lights just below home plate so they sit under the diamond.
        y = min(h - dot_r - 2, int(home.y() + hp + dot_r + 6))

        groups = [
            ("B", 3, self._balls, self._BALL_ON),
            ("S", 2, self._strikes, self._STRIKE_ON),
            ("O", 2, self._outs, self._OUT_ON),
        ]

        label_font = QFont(p.font())
        label_font.setBold(True)
        label_font.setPointSize(max(8, dot_r + 2))
        p.setFont(label_font)
        label_fm = QFontMetrics(label_font)

        total_width = 0
        for label, total, _, _ in groups:
            dots_width = (total * (dot_r * 2)) + ((total - 1) * dot_gap) if total > 0 else 0
            label_width = label_fm.horizontalAdvance(label)
            total_width += label_width + label_gap + dots_width
        total_width += group_gap * (len(groups) - 1)
        x = cx - (total_width / 2.0)

        for idx, (label, total, active, on_color) in enumerate(groups):
            label_width = label_fm.horizontalAdvance(label)
            dots_width = (total * (dot_r * 2)) + ((total - 1) * dot_gap)
            group_width = label_width + label_gap + dots_width

            label_rect = QRectF(x, y - dot_r - 2, label_width, (dot_r * 2) + 4)
            p.setPen(QPen(self._LABEL, 1))
            p.drawText(label_rect, Qt.AlignVCenter | Qt.AlignLeft, label)

            dots_start = x + label_width + label_gap
            for dot in range(total):
                center_x = dots_start + dot_r + dot * ((dot_r * 2) + dot_gap)
                p.setBrush(QBrush(on_color if dot < active else self._LIGHT_OFF))
                p.setPen(QPen(QColor(20, 24, 30), 1.0))
                p.drawEllipse(QPointF(center_x, y), dot_r, dot_r)

            x += group_width
            if idx < len(groups) - 1:
                sep_x = x + (group_gap / 2.0)
                p.setPen(QPen(self._LABEL, 1))
                p.drawLine(QPointF(sep_x, y - dot_r - 1), QPointF(sep_x, y + dot_r + 1))
                x += group_gap


class TickerLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ticker_text = ""
        self._ticker_pieces: list[tuple[str, Any]] = []
        self._ticker_pieces_width = 0.0
        self._ticker_enabled = False
        self._ticker_offset = 0.0
        self._ticker_speed = TICKER_SPEED_PX
        self._ticker_direction = 1
        self._ticker_key: object | None = None

    def set_ticker_text(self, text: str, *, speed_px: float = TICKER_SPEED_PX, direction: str = "ltr") -> None:
        self.set_ticker_text_with_offset(text, speed_px=speed_px, direction=direction, preserve_offset=False)
        return

    def set_ticker_text_with_offset(
        self,
        text: str,
        *,
        speed_px: float = TICKER_SPEED_PX,
        direction: str = "ltr",
        preserve_offset: bool = False,
    ) -> None:
        prev_offset = self._ticker_offset
        prev_enabled = self.is_ticker_enabled()
        self._ticker_text = text or ""
        self._ticker_pieces = []
        self._ticker_pieces_width = 0.0
        self._ticker_speed = max(1.0, float(speed_px))
        self._ticker_direction = 1 if direction == "ltr" else -1
        self._ticker_enabled = bool(self._ticker_text)
        self._ticker_key = ("text", self._ticker_text)
        if preserve_offset and prev_enabled and self._ticker_enabled:
            self._ticker_offset = prev_offset
            self._wrap_offset()
        else:
            self._reset_offset()
        self.update()

    def set_ticker_pieces(
        self,
        pieces: list[tuple[str, Any]],
        *,
        speed_px: float = TICKER_SPEED_PX,
        direction: str = "ltr",
        key: object | None = None,
    ) -> None:
        self.set_ticker_pieces_with_offset(
            pieces,
            speed_px=speed_px,
            direction=direction,
            key=key,
            preserve_offset=False,
        )
        return

    def set_ticker_pieces_with_offset(
        self,
        pieces: list[tuple[str, Any]],
        *,
        speed_px: float = TICKER_SPEED_PX,
        direction: str = "ltr",
        key: object | None = None,
        preserve_offset: bool = False,
    ) -> None:
        prev_offset = self._ticker_offset
        prev_enabled = self.is_ticker_enabled()
        self._ticker_text = ""
        self._ticker_pieces = list(pieces or [])
        self._ticker_pieces_width = self._calc_pieces_width()
        self._ticker_speed = max(1.0, float(speed_px))
        self._ticker_direction = 1 if direction == "ltr" else -1
        self._ticker_enabled = bool(self._ticker_pieces)
        self._ticker_key = key if key is not None else ("pieces", len(self._ticker_pieces), int(self._ticker_pieces_width))
        if preserve_offset and prev_enabled and self._ticker_enabled:
            self._ticker_offset = prev_offset
            self._wrap_offset()
        else:
            self._reset_offset()
        self.update()

    def stop_ticker(self) -> None:
        self._ticker_enabled = False
        self._ticker_text = ""
        self._ticker_pieces = []
        self._ticker_pieces_width = 0.0
        self._ticker_offset = 0.0
        self._ticker_key = None
        self.update()

    def is_ticker_enabled(self) -> bool:
        return self._ticker_enabled and (bool(self._ticker_text) or bool(self._ticker_pieces))

    def ticker_text(self) -> str:
        return self._ticker_text

    def ticker_key(self) -> object | None:
        return self._ticker_key

    def set_ticker_speed(self, speed_px: float) -> None:
        self._ticker_speed = max(1.0, float(speed_px))

    def setText(self, text: str) -> None:  # type: ignore[override]
        self._ticker_enabled = False
        self._ticker_text = ""
        self._ticker_pieces = []
        self._ticker_pieces_width = 0.0
        self._ticker_offset = 0.0
        self._ticker_key = None
        super().setText(text)

    def _calc_pieces_width(self) -> float:
        if not self._ticker_pieces:
            return 0.0
        fm = self.fontMetrics()
        width = 0.0
        for kind, payload in self._ticker_pieces:
            if kind == "text":
                width += fm.horizontalAdvance(str(payload))
            elif kind == "logo":
                if isinstance(payload, QPixmap) and not payload.isNull():
                    width += min(payload.width(), TICKER_LOGO_SIZE)
            elif kind == "gap":
                try:
                    width += float(payload)
                except Exception:
                    pass
        return width

    def _content_width(self) -> float:
        if self._ticker_pieces:
            return self._ticker_pieces_width
        return float(self.fontMetrics().horizontalAdvance(self._ticker_text))

    def _reset_offset(self) -> None:
        text_width = self._content_width()
        if self._ticker_direction > 0:
            self._ticker_offset = -float(text_width)
        else:
            self._ticker_offset = float(self.width())

    def _wrap_offset(self) -> None:
        text_width = self._content_width()
        if text_width <= 0:
            self._ticker_offset = 0.0
            return
        if self._ticker_direction > 0:
            while self._ticker_offset > self.width():
                self._ticker_offset -= text_width
            while self._ticker_offset < -float(text_width):
                self._ticker_offset += text_width
        else:
            while self._ticker_offset < -float(text_width):
                self._ticker_offset += text_width
            while self._ticker_offset > self.width():
                self._ticker_offset -= text_width
    def advance(self, delta_sec: float) -> None:
        if not self.is_ticker_enabled():
            return
        text_width = self._content_width()
        if text_width <= 0:
            return
        self._ticker_offset += self._ticker_direction * self._ticker_speed * delta_sec
        if self._ticker_direction > 0:
            if self._ticker_offset > self.width():
                self._ticker_offset = -float(text_width)
        else:
            if self._ticker_offset < -float(text_width):
                self._ticker_offset = float(self.width())
        self.update()

    def paintEvent(self, event):
        if not self.is_ticker_enabled():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QPalette.WindowText))
        fm = self.fontMetrics()
        text_width = self._content_width()
        if text_width <= 0:
            return
        text_y = (self.height() + fm.ascent() - fm.descent()) // 2
        logo_size = min(TICKER_LOGO_SIZE, max(0, self.height() - 4))
        logo_y = (self.height() - logo_size) // 2
        x = self._ticker_offset
        if self._ticker_pieces:
            while x < self.width():
                cursor = x
                for kind, payload in self._ticker_pieces:
                    if kind == "text":
                        painter.drawText(int(cursor), int(text_y), str(payload))
                        cursor += fm.horizontalAdvance(str(payload))
                    elif kind == "logo":
                        if isinstance(payload, QPixmap) and not payload.isNull() and logo_size > 0:
                            painter.drawPixmap(QRect(int(cursor), int(logo_y), logo_size, logo_size), payload)
                            cursor += logo_size
                    elif kind == "gap":
                        try:
                            cursor += float(payload)
                        except Exception:
                            pass
                x += text_width
            return
        x = self._ticker_offset
        while x < self.width():
            painter.drawText(int(x), int(text_y), self._ticker_text)
            x += text_width


class ScoreCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background: transparent; border: none;")


class TimeoutBar(QFrame):
    def __init__(self):
        super().__init__()
        self._squares: List[QFrame] = []
        self._remaining = 0
        self._total = 0
        self._active_color = TIMEOUT_ACTIVE
        self._inactive_color = TIMEOUT_INACTIVE
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self._layout = layout
        self.setVisible(False)

    def set_colors(self, active: str, inactive: str | None = None) -> None:
        self._active_color = active or self._active_color
        if inactive:
            self._inactive_color = inactive
        if self._total:
            self._apply_colors()

    def set_timeouts(self, remaining: int | None, total: int | None = None) -> None:
        if remaining is None:
            self.setVisible(False)
            return
        try:
            remaining_val = int(remaining)
        except Exception:
            self.setVisible(False)
            return
        if total is None:
            total_val = self._total or remaining_val
        else:
            try:
                total_val = int(total)
            except Exception:
                total_val = remaining_val
        if total_val <= 0:
            self.setVisible(False)
            return
        total_val = max(total_val, remaining_val)
        self._ensure_squares(total_val)
        self._remaining = max(0, min(remaining_val, total_val))
        self._apply_colors()
        self.setVisible(True)

    def _ensure_squares(self, total: int) -> None:
        if total == self._total:
            return
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._squares = []
        for _ in range(total):
            square = QFrame()
            square.setFixedSize(8, 6)
            square.setStyleSheet(f"background-color: {self._inactive_color}; border-radius: 0px;")
            self._layout.addWidget(square)
            self._squares.append(square)
        self._total = total

    def _apply_colors(self) -> None:
        for idx, square in enumerate(self._squares, start=1):
            color = self._active_color if idx <= self._remaining else self._inactive_color
            square.setStyleSheet(f"background-color: {color}; border-radius: 0px;")


class CenterPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("background: transparent; border: none;")
        self.setFixedWidth(CENTER_PANEL_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.period_badge = QFrame()
        self.period_badge.setFrameShape(QFrame.StyledPanel)
        self.period_badge.setStyleSheet("background: transparent; border: none;")
        badge_layout = QVBoxLayout(self.period_badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setSpacing(0)
        self.league_badge_logo = QLabel()
        self.league_badge_logo.setFixedSize(40, 40)
        self.league_badge_logo.setAlignment(Qt.AlignCenter)
        self.league_badge_logo.setStyleSheet("background: transparent;")
        self.pitch_left_indicator = QLabel()
        self.pitch_left_indicator.setFixedSize(14, 14)
        self.pitch_left_indicator.setAlignment(Qt.AlignCenter)
        self.pitch_left_indicator.setStyleSheet("background: transparent;")
        self.period_label = QLabel("Q-")
        self.period_label.setAlignment(Qt.AlignCenter)
        self.period_label.setStyleSheet("color: #e6edf7; font-weight: 700; font-size: 14px;")
        self.pitch_right_indicator = QLabel()
        self.pitch_right_indicator.setFixedSize(14, 14)
        self.pitch_right_indicator.setAlignment(Qt.AlignCenter)
        self.pitch_right_indicator.setStyleSheet("background: transparent;")
        self._pitch_ball_pixmap = self._build_pitch_ball_pixmap(14)
        self._pitch_blank_pixmap = QPixmap(14, 14)
        self._pitch_blank_pixmap.fill(Qt.transparent)
        period_row = QHBoxLayout()
        period_row.setContentsMargins(0, 0, 0, 0)
        period_row.setSpacing(6)
        period_row.addStretch(1)
        period_row.addWidget(self.pitch_left_indicator)
        period_row.addWidget(self.period_label)
        period_row.addWidget(self.pitch_right_indicator)
        period_row.addStretch(1)
        badge_layout.addWidget(self.league_badge_logo, alignment=Qt.AlignHCenter)
        badge_layout.addLayout(period_row)
        self.set_pitching_side(None)

        self.clock_frame = QFrame()
        self.clock_frame.setFrameShape(QFrame.StyledPanel)
        self.clock_frame.setStyleSheet("background-color: #0b0f16; border: none;")
        clock_layout = QHBoxLayout(self.clock_frame)
        clock_layout.setContentsMargins(0, 6, 0, 6)
        clock_layout.setSpacing(0)
        self.clock_display = QLCDNumber()
        self._clock_display_scale = 1.85
        self._clock_trim_px = 18
        self._clock_trim_px_wide = 8
        self._clock_digit_count = 4
        self.clock_display.setDigitCount(self._clock_digit_count)
        self.clock_display.setSegmentStyle(QLCDNumber.Filled)
        self.clock_display.setFrameShape(QFrame.NoFrame)
        self.clock_display.setStyleSheet("color: #ffd34d; background: transparent; padding: 0px; margin: 0px;")
        clock_glow = QGraphicsDropShadowEffect(self.clock_display)
        clock_glow.setBlurRadius(14)
        clock_glow.setOffset(0, 0)
        clock_glow.setColor(QColor(255, 211, 77, 160))
        self.clock_display.setGraphicsEffect(clock_glow)
        self.clock_display.display("00:00")
        self._update_clock_display_size(self._clock_digit_count)
        clock_layout.addWidget(self.clock_display)

        self.bottom_row = QHBoxLayout()
        self.bottom_row.setContentsMargins(4, 0, 4, 0)
        self.bottom_row.setSpacing(8)
        self.bottom_left = QLabel("")
        self.bottom_left.setAlignment(Qt.AlignCenter)
        self.bottom_left.setStyleSheet(CENTER_BOTTOM_LEFT_STYLE)
        self.bottom_center = QLabel("")
        self.bottom_center.setAlignment(Qt.AlignCenter)
        self.bottom_center.setStyleSheet(CENTER_BOTTOM_CENTER_STYLE)
        self.bottom_right = QLabel("")
        self.bottom_right.setAlignment(Qt.AlignCenter)
        self.bottom_right.setStyleSheet(CENTER_BOTTOM_RIGHT_STYLE)
        self.bottom_row.addWidget(self.bottom_left, stretch=1)
        self.bottom_row.addWidget(self.bottom_center, stretch=1)
        self.bottom_row.addWidget(self.bottom_right, stretch=1)

        self.diamond_widget = _BasesDiamondWidget()
        self.diamond_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.diamond_widget.setMinimumHeight(80)
        self.diamond_widget.setVisible(False)

        layout.addWidget(self.period_badge)
        layout.addWidget(self.clock_frame)
        layout.addWidget(self.diamond_widget)
        layout.addLayout(self.bottom_row)

    def set_state(
        self,
        period_text: str,
        clock_text: str,
        bottom_left: str = "",
        bottom_right: str = "",
        bottom_center: str = "",
    ):
        self.period_label.setText(period_text)
        clock_text = clock_text or ""
        if not re.match(r"^\d{1,2}:\d{2}$", clock_text):
            clock_text = "00:00"
        digit_count = 5 if re.match(r"^\d{2}:\d{2}$", clock_text) else 4
        self._update_clock_display_size(digit_count)
        self.clock_display.display(clock_text)
        self.bottom_left.setText(bottom_left)
        self.bottom_center.setText(bottom_center)
        self.bottom_right.setText(bottom_right)

    def set_bottom_labels(self, bottom_left: str = "", bottom_right: str = "", bottom_center: str = "") -> None:
        self.bottom_left.setText(bottom_left)
        self.bottom_center.setText(bottom_center)
        self.bottom_right.setText(bottom_right)

    def set_league_logo(self, pixmap: QPixmap | None) -> None:
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.league_badge_logo.setPixmap(scaled)
            self.league_badge_logo.setVisible(True)
            return
        self.league_badge_logo.clear()
        self.league_badge_logo.setVisible(False)

    @staticmethod
    def _build_pitch_ball_pixmap(size: int) -> QPixmap:
        size = max(10, int(size))
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(1, 1, size - 2, size - 2)
        p.setBrush(QBrush(QColor(245, 247, 250)))
        p.setPen(QPen(QColor(188, 196, 207), 1.2))
        p.drawEllipse(rect)
        seam_rect = rect.adjusted(size * 0.12, size * 0.06, -size * 0.12, -size * 0.06)
        p.setPen(QPen(QColor(200, 90, 90), 1.0))
        p.drawArc(seam_rect, 36 * 16, 112 * 16)
        p.drawArc(seam_rect, 216 * 16, 112 * 16)
        p.end()
        return pix

    def _update_clock_display_size(self, digit_count: int) -> None:
        digit_count = max(1, int(digit_count))
        if self._clock_digit_count != digit_count:
            self._clock_digit_count = digit_count
            self.clock_display.setDigitCount(digit_count)
        display_hint = self.clock_display.sizeHint()
        trim_px = self._clock_trim_px if digit_count <= 4 else self._clock_trim_px_wide
        width = max(1, int(display_hint.width() * self._clock_display_scale) - trim_px)
        height = max(1, int(display_hint.height() * self._clock_display_scale))
        max_width = CENTER_PANEL_WIDTH - 6
        if width > max_width:
            width = max_width
        self.clock_display.setFixedSize(width, height)

    def show_diamond(self, show: bool) -> None:
        """Toggle between the LCD clock and the bases diamond (MLB mode)."""
        self.clock_frame.setVisible(not show)
        self.diamond_widget.setVisible(show)

    def set_bases(self, first: bool = False, second: bool = False, third: bool = False) -> None:
        """Update which bases are occupied on the diamond."""
        self.diamond_widget.set_bases(first, second, third)

    def set_count(self, balls: Any = None, strikes: Any = None, outs: Any = None) -> None:
        """Update TV-style B/S/O indicator lights on the diamond."""
        self.diamond_widget.set_count(balls, strikes, outs)

    def set_pitching_side(self, side: str | None) -> None:
        """Set pitcher marker next to inning: left (away) or right (home)."""
        normalized = str(side or "").strip().lower()
        left_on = normalized == "left"
        right_on = normalized == "right"
        self.pitch_left_indicator.setPixmap(self._pitch_ball_pixmap if left_on else self._pitch_blank_pixmap)
        self.pitch_right_indicator.setPixmap(self._pitch_ball_pixmap if right_on else self._pitch_blank_pixmap)


class PlayerCardDialog(QDialog):
    STAT_MAX = 16
    GAME_STATS_MAX = 4
    PROFILE_STATS_MAX = 4
    CAREER_STATS_MAX = 5
    PORTRAIT_PANEL_WIDTH = 116
    PORTRAIT_PANEL_HEIGHT = 124
    HERO_HEADSHOT_WIDTH = 108
    HERO_HEADSHOT_HEIGHT = 120
    HERO_TEAM_LOGO_SIZE = 40
    HERO_STAT_MIN_WIDTH = 92
    HERO_STAT_MAX_WIDTH = 118
    HERO_STAT_HEIGHT = 94
    PROFILE_COLUMNS = 4
    GAME_STATS_COLUMNS = 2
    CAREER_STATS_COLUMNS = 5
    HOT_STATE_THRESHOLDS: Dict[str, Dict[str, float]] = {
        "NBA": {"PTS": 20, "REB": 10, "AST": 8, "STL": 3, "BLK": 3, "+/-": 10},
        "NCAA BASKETBALL": {"PTS": 20, "REB": 10, "AST": 8, "STL": 3, "BLK": 3},
        "NFL": {"YDS": 100, "TD": 2, "REC": 8, "CAR": 15, "TKL": 10, "SACK": 2, "INT": 1},
        "NCAA FOOTBALL": {"YDS": 100, "TD": 2, "REC": 8, "CAR": 15, "TKL": 10, "SACK": 2, "INT": 1},
        "NHL": {"PTS": 3, "G": 2, "A": 2, "SOG": 5, "SV": 25},
        "MLB": {"H": 3, "RBI": 3, "HR": 1, "SB": 2, "SO": 7, "SV": 1},
        "MLS": {"G": 1, "A": 2, "SOG": 4, "SV": 6},
    }
    DEFAULT_CARD_LAYOUT: Dict[str, List[str]] = {
        "profile_order": ["Ht", "Wt", "Age", "Exp"],
        "profile_extras": ["DOB"],
        "live_order": ["PTS", "AST", "REB", "MIN"],
        "career_order": ["GP", "PTS", "AST", "REB"],
        "hero_live": ["PTS", "AST", "REB"],
        "hero_snapshot": ["PTS", "AST", "REB"],
    }
    SPORT_CARD_LAYOUTS: Dict[str, Dict[str, List[str]]] = {
        "NBA": {
            "profile_order": ["Ht", "Wt", "Age", "Exp", "College"],
            "profile_extras": [],
            "live_order": ["MIN", "PTS", "REB", "AST", "3PT", "STL", "BLK", "TO", "+/-"],
            "career_order": ["GP", "PTS", "REB", "AST", "STL", "BLK", "FG%", "3P%", "FT%"],
            "hero_live": ["PTS", "REB", "AST", "+/-", "STL", "BLK"],
            "hero_snapshot": ["PTS", "REB", "AST", "FG%", "3P%", "FT%"],
        },
        "NCAA BASKETBALL": {
            "profile_order": ["Ht", "Wt", "Age", "Exp", "College"],
            "profile_extras": [],
            "live_order": ["MIN", "PTS", "REB", "AST", "3PT", "STL", "BLK", "TO", "PF"],
            "career_order": ["GP", "PTS", "REB", "AST", "STL", "BLK", "FG%", "3P%", "FT%"],
            "hero_live": ["PTS", "REB", "AST", "STL", "BLK", "PF"],
            "hero_snapshot": ["PTS", "REB", "AST", "FG%", "3P%", "FT%"],
        },
        "NFL": {
            "profile_order": ["Ht", "Wt", "Age", "Exp", "College"],
            "profile_extras": [],
            "live_order": ["YDS", "TD", "REC", "CAR", "TKL", "AST", "SACK", "INT"],
            "career_order": [
                "GP",
                "PASS YDS",
                "PASS TD",
                "INT",
                "RUSH YDS",
                "RUSH TD",
                "REC",
                "REC YDS",
                "REC TD",
                "TKL",
                "SACK",
            ],
            "hero_live": ["TD", "YDS", "REC", "CAR", "TKL", "SACK", "INT"],
            "hero_snapshot": ["PASS YDS", "PASS TD", "RUSH YDS", "REC YDS", "REC TD", "RUSH TD", "INT"],
        },
        "NCAA FOOTBALL": {
            "profile_order": ["Ht", "Wt", "Age", "Exp", "College"],
            "profile_extras": [],
            "live_order": ["YDS", "TD", "REC", "CAR", "TKL", "AST", "SACK", "INT"],
            "career_order": [
                "GP",
                "PASS YDS",
                "PASS TD",
                "INT",
                "RUSH YDS",
                "RUSH TD",
                "REC",
                "REC YDS",
                "REC TD",
                "TKL",
                "SACK",
            ],
            "hero_live": ["TD", "YDS", "REC", "CAR", "TKL", "SACK", "INT"],
            "hero_snapshot": ["PASS YDS", "PASS TD", "RUSH YDS", "REC YDS", "REC TD", "RUSH TD", "INT"],
        },
        "NHL": {
            "profile_order": ["Ht", "Wt", "Age", "Shoots"],
            "profile_extras": ["DOB"],
            "live_order": ["PTS", "G", "A", "SOG", "TOI", "HITS", "BLK", "+/-", "PIM", "SV", "SV%"],
            "career_order": ["GP", "PTS", "G", "A", "SOG", "+/-", "PIM", "SV%", "GAA", "W", "L", "SO", "TOI/G"],
            "hero_live": ["PTS", "G", "A", "SOG", "SV", "SV%"],
            "hero_snapshot": ["PTS", "G", "A", "SOG", "SV%", "SV"],
        },
        "MLB": {
            "profile_order": ["B/T", "Ht", "Wt", "Age", "BO"],
            "profile_extras": [],
            "live_order": ["AVG", "OBP", "SLG", "OPS", "HR", "RBI", "R", "H", "AB", "BB", "SO", "SB"],
            "career_order": ["GP", "AVG", "HR", "RBI", "H", "OBP", "SLG", "OPS", "SB", "SO", "ERA", "W", "L", "SV"],
            "hero_live": ["RBI", "H", "HR", "R", "SB", "SO", "IP", "SV", "AVG", "OPS"],
            "hero_snapshot": ["OPS", "AVG", "HR", "RBI", "H", "ERA", "SV"],
        },
        "MLS": {
            "profile_order": ["Ht", "Wt", "Age", "Exp"],
            "profile_extras": ["DOB"],
            "live_order": ["G", "A", "SOG", "MIN"],
            "career_order": ["APP", "G", "A", "SOG", "MIN", "YC", "RC", "CS", "SV", "GA"],
            "hero_live": ["G", "A", "SOG", "SV", "MIN"],
            "hero_snapshot": ["G", "A", "SOG", "MIN", "SV"],
        },
    }
    ROLE_CARD_LAYOUTS: Dict[str, Dict[str, Dict[str, List[str]]]] = {
        "NFL": {
            "QB": {
                "live_order": ["YDS", "TD", "INT", "CAR", "REC"],
                "career_order": ["GP", "PASS YDS", "PASS TD", "INT", "RUSH YDS", "RUSH TD"],
                "hero_live": ["YDS", "TD", "INT", "CAR"],
                "hero_snapshot": ["PASS YDS", "PASS TD", "INT", "RUSH YDS", "RUSH TD"],
            },
            "RB": {
                "live_order": ["YDS", "TD", "CAR", "REC"],
                "career_order": ["GP", "RUSH YDS", "RUSH TD", "REC", "REC YDS", "REC TD"],
                "hero_live": ["YDS", "TD", "CAR", "REC"],
                "hero_snapshot": ["RUSH YDS", "RUSH TD", "REC YDS", "REC TD", "REC"],
            },
            "WR": {
                "live_order": ["YDS", "TD", "REC", "CAR"],
                "career_order": ["GP", "REC YDS", "REC TD", "REC", "RUSH YDS", "RUSH TD"],
                "hero_live": ["YDS", "TD", "REC", "CAR"],
                "hero_snapshot": ["REC YDS", "REC TD", "REC", "RUSH YDS", "RUSH TD"],
            },
            "TE": {
                "live_order": ["YDS", "TD", "REC", "CAR"],
                "career_order": ["GP", "REC YDS", "REC TD", "REC", "RUSH YDS", "RUSH TD"],
                "hero_live": ["YDS", "TD", "REC", "CAR"],
                "hero_snapshot": ["REC YDS", "REC TD", "REC", "RUSH YDS", "RUSH TD"],
            },
            "DEF": {
                "live_order": ["TKL", "AST", "SACK", "INT", "PD", "FF"],
                "career_order": ["GP", "TKL", "SACK", "INT"],
                "hero_live": ["TKL", "SACK", "INT", "PD"],
                "hero_snapshot": ["TKL", "SACK", "INT"],
            },
        },
        "NCAA FOOTBALL": {
            "QB": {
                "live_order": ["YDS", "TD", "INT", "CAR", "REC"],
                "career_order": ["GP", "PASS YDS", "PASS TD", "INT", "RUSH YDS", "RUSH TD"],
                "hero_live": ["YDS", "TD", "INT", "CAR"],
                "hero_snapshot": ["PASS YDS", "PASS TD", "INT", "RUSH YDS", "RUSH TD"],
            },
            "RB": {
                "live_order": ["YDS", "TD", "CAR", "REC"],
                "career_order": ["GP", "RUSH YDS", "RUSH TD", "REC", "REC YDS", "REC TD"],
                "hero_live": ["YDS", "TD", "CAR", "REC"],
                "hero_snapshot": ["RUSH YDS", "RUSH TD", "REC YDS", "REC TD", "REC"],
            },
            "WR": {
                "live_order": ["YDS", "TD", "REC", "CAR"],
                "career_order": ["GP", "REC YDS", "REC TD", "REC", "RUSH YDS", "RUSH TD"],
                "hero_live": ["YDS", "TD", "REC", "CAR"],
                "hero_snapshot": ["REC YDS", "REC TD", "REC", "RUSH YDS", "RUSH TD"],
            },
            "TE": {
                "live_order": ["YDS", "TD", "REC", "CAR"],
                "career_order": ["GP", "REC YDS", "REC TD", "REC", "RUSH YDS", "RUSH TD"],
                "hero_live": ["YDS", "TD", "REC", "CAR"],
                "hero_snapshot": ["REC YDS", "REC TD", "REC", "RUSH YDS", "RUSH TD"],
            },
            "DEF": {
                "live_order": ["TKL", "AST", "SACK", "INT", "PD", "FF"],
                "career_order": ["GP", "TKL", "SACK", "INT"],
                "hero_live": ["TKL", "SACK", "INT", "PD"],
                "hero_snapshot": ["TKL", "SACK", "INT"],
            },
        },
        "NHL": {
            "G": {
                "live_order": ["SV", "SV%", "SA", "GA", "SO", "GAA", "PIM"],
                "career_order": ["GP", "W", "SV%", "GAA", "SO", "L", "SV"],
                "hero_live": ["SV", "SV%", "SO", "GAA"],
                "hero_snapshot": ["SV", "SV%", "SO", "GAA", "W"],
            },
        },
        "MLB": {
            "P": {
                "live_order": ["IP", "SO", "ERA", "W", "SV", "H", "BB"],
                "career_order": ["GP", "ERA", "SO", "W", "L", "SV", "IP", "WHIP"],
                "hero_live": ["SO", "IP", "ERA", "SV", "W"],
                "hero_snapshot": ["ERA", "SO", "SV", "W", "L"],
            },
        },
        "MLS": {
            "GK": {
                "live_order": ["SV", "CS", "GA", "MIN"],
                "career_order": ["APP", "SV", "CS", "GA", "MIN"],
                "hero_live": ["SV", "CS", "GA", "MIN"],
                "hero_snapshot": ["SV", "CS", "GA", "MIN"],
            },
        },
    }

    def __init__(self, context: Dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self._context = dict(context or {})
        accent = str(self._context.get("teamColor") or ACCENT)
        self._profile: Dict[str, Any] = {}
        self._row_stats = dict(self._context.get("rowStats") or {})
        self._supplement_row_stats_from_context()
        self._stat_source_mode = "game"
        self._primary_stat_keys: set[str] = set()
        self._palette = self._resolve_palette(accent)
        self.setWindowTitle("Player Card")
        self.setModal(False)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.Tool, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFixedSize(560, 336)
        self.setStyleSheet(self._build_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 6, 6, 6)
        root.setSpacing(0)

        self.headshot_label = QLabel()
        self.headshot_label.setObjectName("headshot")
        self.headshot_label.setFixedSize(self.HERO_HEADSHOT_WIDTH, self.HERO_HEADSHOT_HEIGHT)
        self.headshot_label.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        self._headshot_loaded = False

        self.jersey_badge = QLabel("")
        self.jersey_badge.setObjectName("jerseyBadge")
        self.jersey_badge.setAlignment(Qt.AlignCenter)

        self.team_logo_label = QLabel()
        self.team_logo_label.setObjectName("teamLogo")
        self.team_logo_label.setFixedSize(self.HERO_TEAM_LOGO_SIZE, self.HERO_TEAM_LOGO_SIZE)
        self.team_logo_label.setAlignment(Qt.AlignCenter)

        self.name_label = QLabel("")
        self.name_label.setObjectName("playerName")
        self.name_label.setWordWrap(False)
        self.name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("playerMeta")
        self.meta_label.setWordWrap(False)
        self.meta_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.status_badge = QLabel("")
        self.status_badge.setObjectName("statusBadge")
        self.status_badge.setVisible(False)
        self.status_badge.setAlignment(Qt.AlignCenter)

        self.hero_stat_value = QLabel("--")
        self.hero_stat_value.setObjectName("heroStatValue")
        self.hero_stat_value.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        self.hero_stat_label = QLabel("STAT")
        self.hero_stat_label.setObjectName("heroStatLabel")
        self.hero_stat_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        close_button = QToolButton()
        close_button.setObjectName("cardClose")
        close_button.setText("x")
        close_button.setAutoRaise(True)
        close_button.clicked.connect(self.close)

        self.hero_stat_wrap = QFrame()
        self.hero_stat_wrap.setObjectName("heroStatWrap")
        self.hero_stat_wrap.setProperty("cardState", "default")
        self.hero_stat_wrap.setMinimumWidth(self.HERO_STAT_MIN_WIDTH)
        self.hero_stat_wrap.setFixedHeight(self.HERO_STAT_HEIGHT)
        self.hero_stat_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        hero_stat_layout = QVBoxLayout(self.hero_stat_wrap)
        hero_stat_layout.setContentsMargins(12, 10, 12, 10)
        hero_stat_layout.setSpacing(0)
        hero_stat_layout.addStretch(1)
        hero_stat_layout.addWidget(self.hero_stat_value, 0, Qt.AlignLeft | Qt.AlignBottom)
        hero_stat_layout.addWidget(self.hero_stat_label, 0, Qt.AlignLeft | Qt.AlignTop)

        self.surface = QFrame()
        self.surface.setObjectName("cardSurface")
        self.surface.setProperty("cardState", "default")
        root.addWidget(self.surface, 1)

        shadow = QGraphicsDropShadowEffect(self.surface)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 130))
        self.surface.setGraphicsEffect(shadow)

        body_layout = QVBoxLayout(self.surface)
        body_layout.setContentsMargins(16, 12, 16, 12)
        body_layout.setSpacing(8)

        self.header_panel = QFrame()
        self.header_panel.setObjectName("cardHeader")
        header_layout = QVBoxLayout(self.header_panel)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(self.jersey_badge, 0, Qt.AlignVCenter)
        title_row.addWidget(self.name_label, 1, Qt.AlignVCenter)
        title_row.addStretch(1)
        title_row.addWidget(self.team_logo_label, 0, Qt.AlignTop | Qt.AlignRight)
        title_row.addWidget(close_button, 0, Qt.AlignTop | Qt.AlignRight)
        header_layout.addLayout(title_row)

        subheader_row = QHBoxLayout()
        subheader_row.setContentsMargins(0, 0, 0, 0)
        subheader_row.setSpacing(5)
        subheader_row.addWidget(self.meta_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        subheader_row.addStretch(1)
        header_layout.addLayout(subheader_row)

        self.bio_grid = QGridLayout()
        self.bio_grid.setContentsMargins(0, 0, 0, 0)
        self.bio_grid.setHorizontalSpacing(5)
        self.bio_grid.setVerticalSpacing(4)
        self.bio_grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        header_layout.addLayout(self.bio_grid)
        body_layout.addWidget(self.header_panel)

        self.main_band = QFrame()
        self.main_band.setObjectName("mainBand")
        main_row = QHBoxLayout(self.main_band)
        main_row.setContentsMargins(8, 8, 10, 8)
        main_row.setSpacing(10)

        self.identity_wrap = QFrame()
        self.identity_wrap.setObjectName("portraitPanel")
        self.identity_wrap.setFixedSize(self.PORTRAIT_PANEL_WIDTH, self.PORTRAIT_PANEL_HEIGHT)
        portrait_layout = QVBoxLayout(self.identity_wrap)
        portrait_layout.setContentsMargins(4, 4, 4, 4)
        portrait_layout.setSpacing(0)
        portrait_layout.addStretch(1)
        portrait_layout.addWidget(self.headshot_label, 0, Qt.AlignHCenter | Qt.AlignBottom)
        main_row.addWidget(self.identity_wrap, 0, Qt.AlignTop)

        self.stats_panel = QFrame()
        self.stats_panel.setObjectName("statsGroup")
        self.stats_panel.setFixedHeight(self.PORTRAIT_PANEL_HEIGHT)
        stats_layout = QHBoxLayout(self.stats_panel)
        stats_layout.setContentsMargins(0, 2, 0, 2)
        stats_layout.setSpacing(8)
        self.stat_grid = QGridLayout()
        self.stat_grid.setHorizontalSpacing(8)
        self.stat_grid.setVerticalSpacing(8)
        stats_layout.addWidget(self.hero_stat_wrap, 0, Qt.AlignVCenter)
        stats_layout.addLayout(self.stat_grid, 1)
        main_row.addWidget(self.stats_panel, 1)
        body_layout.addWidget(self.main_band, 1)

        self.career_panel = QFrame()
        self.career_panel.setObjectName("careerBand")
        career_layout = QVBoxLayout(self.career_panel)
        career_layout.setContentsMargins(2, 0, 2, 0)
        career_layout.setSpacing(5)
        career_divider = QFrame()
        career_divider.setObjectName("cardDivider")
        career_divider.setFixedHeight(1)
        career_layout.addWidget(career_divider)

        career_title = QLabel("CAREER")
        career_title.setObjectName("sectionTitle")
        career_layout.addWidget(career_title)
        self.career_grid = QGridLayout()
        self.career_grid.setHorizontalSpacing(8)
        self.career_grid.setVerticalSpacing(6)
        career_layout.addLayout(self.career_grid)
        body_layout.addWidget(self.career_panel)

        self._set_name_text(str(self._context.get("playerName") or "Player"))
        self.set_headshot(None)
        self.set_team_logo(None)
        self._refresh_meta()
        self._render_bio({})
        self._render_stats(self._row_stats)
        self._render_career_stats({})
        self._apply_card_state()

    @classmethod
    def _as_color(cls, raw: Any, fallback: str) -> QColor:
        color = QColor(str(raw or ""))
        if color.isValid():
            return color
        return QColor(fallback)

    @classmethod
    def _blend(cls, color_hex: Any, base_hex: Any, factor: float) -> str:
        factor = max(0.0, min(1.0, float(factor)))
        color = cls._as_color(color_hex, ACCENT)
        base = cls._as_color(base_hex, BG)
        red = round(base.red() + ((color.red() - base.red()) * factor))
        green = round(base.green() + ((color.green() - base.green()) * factor))
        blue = round(base.blue() + ((color.blue() - base.blue()) * factor))
        return QColor(red, green, blue).name()

    @classmethod
    def _rgba(cls, color_hex: Any, alpha: float) -> str:
        color = cls._as_color(color_hex, ACCENT)
        alpha_value = max(0.0, min(1.0, float(alpha)))
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha_value:.3f})"

    @classmethod
    def _color_luminance(cls, color_hex: Any) -> float:
        color = cls._as_color(color_hex, BG)

        def _channel(value: int) -> float:
            srgb = value / 255.0
            if srgb <= 0.03928:
                return srgb / 12.92
            return ((srgb + 0.055) / 1.055) ** 2.4

        return (
            (0.2126 * _channel(color.red()))
            + (0.7152 * _channel(color.green()))
            + (0.0722 * _channel(color.blue()))
        )

    def _resolve_palette(self, accent: str) -> Dict[str, str]:
        accent_color = self._as_color(accent, ACCENT).name()
        accent_soft = self._blend(accent_color, "#edf5ff", 0.40)
        return {
            "accent": accent_color,
            "accent_soft": accent_soft,
            "surface_top": self._blend(accent_color, "#101929", 0.18),
            "surface_mid": self._blend(accent_color, "#0b1320", 0.08),
            "surface_deep": "#07111a",
            "surface_bench": self._blend(accent_color, "#0a111b", 0.05),
            "surface_hot": self._blend(accent_color, "#132137", 0.24),
            "border": self._blend(accent_color, "#4a5e79", 0.28),
            "border_soft": self._blend(accent_color, "#6c84a2", 0.20),
            "chip": self._blend(accent_color, "#101927", 0.10),
            "chip_alt": self._blend(accent_color, "#0d1624", 0.07),
            "hero": self._blend(accent_color, "#152337", 0.30),
            "hero_hot": self._blend(accent_color, "#1a2c45", 0.42),
            "text": "#f3f8ff",
            "muted": "#9db1c9",
            "muted_soft": "#7f95af",
            "success": "#47d1a0",
            "warning": "#f2b651",
            "danger": "#ff7474",
        }

    def _build_style(self) -> str:
        palette = self._palette
        return f"""
        QDialog {{
            background: transparent;
        }}
        QFrame#cardSurface {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {self._rgba(palette["accent"], 0.10)},
                stop:0.16 {palette["surface_top"]},
                stop:0.58 {palette["surface_mid"]},
                stop:1 {palette["surface_deep"]}
            );
            border: 1px solid {self._rgba(palette["border"], 0.72)};
            border-radius: 18px;
        }}
        QFrame#cardSurface[cardState="active"] {{
            border: 1px solid {self._rgba(palette["accent_soft"], 0.50)};
        }}
        QFrame#cardSurface[cardState="hot"] {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {self._rgba(palette["accent"], 0.16)},
                stop:0.18 {palette["surface_hot"]},
                stop:0.62 {palette["surface_mid"]},
                stop:1 {palette["surface_deep"]}
            );
            border: 1px solid {self._rgba(palette["accent_soft"], 0.60)};
        }}
        QFrame#cardSurface[cardState="alert"] {{
            border: 1px solid {self._rgba(palette["warning"], 0.70)};
        }}
        QFrame#cardSurface[cardState="bench"] {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {self._rgba(palette["accent"], 0.06)},
                stop:0.20 {palette["surface_bench"]},
                stop:1 {palette["surface_deep"]}
            );
            border: 1px solid {self._rgba(palette["border_soft"], 0.50)};
        }}
        QFrame#cardHeader {{
            background: transparent;
            border-radius: 0px;
        }}
        QFrame#mainBand {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {self._rgba(palette["chip_alt"], 0.30)},
                stop:1 {self._rgba(palette["surface_mid"], 0.42)}
            );
            border: 1px solid {self._rgba(palette["border_soft"], 0.12)};
            border-radius: 18px;
        }}
        QFrame#careerBand {{
            background: transparent;
            border: none;
        }}
        QFrame#portraitPanel {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {self._rgba(palette["accent"], 0.16)},
                stop:0.40 {self._rgba(palette["surface_mid"], 0.74)},
                stop:1 {self._rgba(palette["surface_deep"], 0.92)}
            );
            border: 1px solid {self._rgba(palette["border_soft"], 0.22)};
            border-radius: 16px;
        }}
        QFrame#statsGroup {{
            background: transparent;
            border: none;
        }}
        QFrame#heroStatWrap {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {self._rgba(palette["accent"], 0.22)},
                stop:1 {self._rgba(palette["hero"], 0.82)}
            );
            border: 1px solid {self._rgba(palette["accent_soft"], 0.18)};
            border-radius: 16px;
        }}
        QFrame#heroStatWrap[cardState="hot"] {{
            background-color: {self._rgba(palette["hero_hot"], 0.92)};
            border: 1px solid {self._rgba(palette["accent_soft"], 0.34)};
        }}
        QFrame#heroStatWrap[cardState="alert"] {{
            background-color: {self._rgba(palette["warning"], 0.10)};
            border: 1px solid {self._rgba(palette["warning"], 0.34)};
        }}
        QFrame#heroStatWrap[cardState="bench"] {{
            background-color: {self._rgba(palette["chip_alt"], 0.76)};
        }}
        QLabel#playerName {{
            color: {palette["text"]};
            font-weight: 800;
            letter-spacing: 0.1px;
        }}
        QLabel#playerMeta {{
            color: {self._rgba(palette["text"], 0.82)};
            font-size: 11px;
            font-weight: 700;
        }}
        QLabel#statusBadge {{
            color: {palette["text"]};
            font-size: 9px;
            font-weight: 800;
            border-radius: 9px;
            padding: 2px 7px;
            background-color: {self._rgba(palette["border"], 0.30)};
            border: 1px solid {self._rgba(palette["border_soft"], 0.45)};
        }}
        QLabel#playerStatus {{
            color: {palette["muted_soft"]};
            font-size: 9px;
            font-weight: 600;
        }}
        QLabel#headshot {{
            background-color: {self._rgba(palette["surface_top"], 0.16)};
            border: 1px solid {self._rgba(palette["border_soft"], 0.10)};
            border-radius: 14px;
            color: {self._rgba(palette["text"], 0.90)};
            font-size: 34px;
            font-weight: 800;
        }}
        QLabel#teamLogo {{
            background: transparent;
            border: none;
            color: {palette["text"]};
            font-size: 10px;
            font-weight: 800;
            padding: 0px;
        }}
        QLabel#jerseyBadge {{
            color: {palette["text"]};
            background-color: {self._rgba(palette["accent"], 0.18)};
            border: 1px solid {self._rgba(palette["accent_soft"], 0.26)};
            border-radius: 12px;
            font-size: 13px;
            font-weight: 900;
            padding: 3px 9px;
            min-width: 34px;
        }}
        QLabel#heroStatValue {{
            color: {palette["text"]};
            font-size: 32px;
            font-weight: 900;
            letter-spacing: 0.2px;
        }}
        QLabel#heroStatLabel {{
            color: {palette["muted"]};
            font-size: 9px;
            font-weight: 800;
            letter-spacing: 0.7px;
        }}
        QToolButton#cardClose {{
            color: {self._rgba(palette["muted"], 0.88)};
            font-size: 12px;
            font-weight: 900;
            border: none;
            border-radius: 8px;
            background: transparent;
            min-width: 16px;
            min-height: 16px;
            max-width: 16px;
            max-height: 16px;
        }}
        QLabel#sectionTitle {{
            color: {palette["muted_soft"]};
            font-size: 8px;
            font-weight: 700;
            letter-spacing: 1.2px;
        }}
        QFrame#cardDivider {{
            background-color: {self._rgba(palette["border_soft"], 0.12)};
        }}
        QFrame#statChip {{
            background-color: {self._rgba(palette["chip_alt"], 0.20)};
            border-radius: 12px;
        }}
        QFrame#infoChip {{
            background-color: {self._rgba(palette["chip_alt"], 0.24)};
            border-radius: 10px;
        }}
        QFrame#careerChip {{
            background: transparent;
            border: none;
        }}
        QLabel#chipKey {{
            color: {palette["muted"]};
            font-size: 8px;
            font-weight: 700;
            letter-spacing: 0.5px;
        }}
        QLabel#chipValue {{
            color: {palette["text"]};
            font-size: 18px;
            font-weight: 900;
        }}
        QLabel#careerChipValue {{
            color: {self._rgba(palette["text"], 0.88)};
            font-size: 12px;
            font-weight: 700;
        }}
        QLabel#infoKey {{
            color: {self._rgba(palette["muted"], 0.94)};
            font-size: 8px;
            font-weight: 800;
            letter-spacing: 0.4px;
        }}
        QLabel#infoValue {{
            color: {self._rgba(palette["text"], 0.95)};
            font-size: 11px;
            font-weight: 700;
        }}
        """

    def _sport_code(self) -> str:
        return str(self._context.get("sport") or "").strip().upper()

    def _player_position_code(self) -> str:
        raw = str(self._profile.get("position") or self._context.get("position") or "").strip().upper()
        if not raw:
            return ""
        raw = raw.split("/")[0].strip()
        return raw.split("-")[0].strip()

    def _role_layout_key(self) -> str:
        sport = self._sport_code()
        position = self._player_position_code()
        if not sport or not position:
            return ""
        if sport in {"NFL", "NCAA FOOTBALL"}:
            if position in {"QB"}:
                return "QB"
            if position in {"RB", "HB", "FB"}:
                return "RB"
            if position in {"WR", "TE"}:
                return position
            if position in {
                "LB",
                "ILB",
                "OLB",
                "CB",
                "DB",
                "S",
                "FS",
                "SS",
                "DL",
                "DE",
                "DT",
                "NT",
                "EDGE",
            }:
                return "DEF"
            return ""
        if sport == "NHL" and position in {"G", "GK", "GOALIE"}:
            return "G"
        if sport == "MLB" and position in {"P", "SP", "RP", "CL"}:
            return "P"
        if sport == "MLS" and position in {"GK"}:
            return "GK"
        return ""

    @staticmethod
    def _format_card_minutes(value: Any) -> str:
        if value in (None, "", 0):
            return ""
        if isinstance(value, (int, float)):
            total = float(value)
            minutes = int(total)
            seconds = int(round((total - minutes) * 60))
            return f"{minutes}:{seconds:02d}"
        text = str(value).strip()
        if not text:
            return ""
        if ":" in text:
            return text
        match = re.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", text)
        if not match:
            return text
        minutes = int(match.group(1) or 0)
        seconds = int(float(match.group(2) or 0))
        return f"{minutes}:{seconds:02d}"

    def _supplement_row_stats_from_context(self) -> None:
        player = self._context.get("playerData")
        if not isinstance(player, dict):
            return
        stats = player.get("statistics") or {}
        if not isinstance(stats, dict):
            return

        def _merge_stat(label: str, value: Any) -> None:
            if value in (None, ""):
                return
            if str(self._row_stats.get(label) or "").strip():
                return
            self._row_stats[label] = str(value)

        sport = self._sport_code()
        if sport in {"NBA", "NCAA BASKETBALL"}:
            player_position = str(self._context.get("position") or player.get("position") or "").strip()
            if player_position and not str(self._context.get("position") or "").strip():
                self._context["position"] = player_position
            _merge_stat("Pos", player_position)
            _merge_stat("MIN", self._format_card_minutes(stats.get("minutes") or stats.get("minutesCalculated")))
            _merge_stat("PTS", stats.get("points"))
            _merge_stat("REB", stats.get("reboundsTotal", stats.get("rebounds")))
            _merge_stat("AST", stats.get("assists"))
            _merge_stat("3PT", extract_three_point_made(stats))
            _merge_stat("STL", stats.get("steals", stats.get("stealsTotal")))
            _merge_stat("BLK", stats.get("blocks", stats.get("blockedShots")))
            _merge_stat("TO", stats.get("turnovers", stats.get("turnoversTotal", stats.get("turnover"))))
            _merge_stat("+/-", stats.get("plusMinus", stats.get("plusMinusPoints")))
            return

        if sport != "NHL":
            return

        role = self._role_layout_key()
        if role == "G" or "saves" in stats or "savePct" in stats:
            saves = stats.get("saves")
            shots_against = stats.get("shotsAgainst")
            goals_against = None
            try:
                if shots_against not in (None, "") and saves not in (None, ""):
                    goals_against = int(shots_against) - int(saves)
            except Exception:
                goals_against = None
            _merge_stat("SV", saves)
            _merge_stat("SV%", stats.get("savePct"))
            _merge_stat("SA", shots_against)
            _merge_stat("GA", goals_against)
            _merge_stat("PIM", stats.get("pim"))
            return

        _merge_stat("G", stats.get("goals"))
        _merge_stat("A", stats.get("assists"))
        _merge_stat("PTS", stats.get("points"))
        _merge_stat("SOG", stats.get("shotsOnGoal"))
        _merge_stat("PIM", stats.get("pim"))
        _merge_stat("+/-", stats.get("plusMinus"))
        _merge_stat("TOI", stats.get("toi") or stats.get("timeOnIce"))
        _merge_stat("HITS", stats.get("hits"))
        _merge_stat("BLK", stats.get("blockedShots"))

    def _card_layout(self) -> Dict[str, List[str]]:
        layout = dict(self.SPORT_CARD_LAYOUTS.get(self._sport_code(), self.DEFAULT_CARD_LAYOUT))
        role_key = self._role_layout_key()
        if not role_key:
            return layout
        overrides = self.ROLE_CARD_LAYOUTS.get(self._sport_code(), {}).get(role_key, {})
        for key, value in overrides.items():
            layout[key] = list(value)
        return layout

    def _set_name_text(self, raw_name: str) -> None:
        text = str(raw_name or "Player").strip() or "Player"
        self.name_label.setText(text)
        font = QFont(self.name_label.font())
        font.setBold(True)
        if len(text) > 20:
            font.setPointSize(16)
        elif len(text) > 14:
            font.setPointSize(17)
        else:
            font.setPointSize(19)
        while font.pointSize() > 14 and QFontMetrics(font).horizontalAdvance(text) > 272:
            font.setPointSize(font.pointSize() - 1)
        self.name_label.setFont(font)

    def _fit_label_font(
        self,
        widget: QLabel,
        text: str,
        *,
        max_width: int,
        max_size: int,
        min_size: int,
        bold: bool = True,
    ) -> None:
        font = QFont(widget.font())
        font.setBold(bold)
        font.setPointSize(max_size)
        while font.pointSize() > min_size and QFontMetrics(font).horizontalAdvance(text) > max_width:
            font.setPointSize(font.pointSize() - 1)
        widget.setFont(font)

    def _refresh_hero_stat_wrap(self) -> None:
        value_text = str(self.hero_stat_value.text() or "--").strip() or "--"
        label_text = str(self.hero_stat_label.text() or "STAT").strip() or "STAT"
        value_width = QFontMetrics(self.hero_stat_value.font()).horizontalAdvance(value_text)
        label_width = QFontMetrics(self.hero_stat_label.font()).horizontalAdvance(label_text)
        target = max(
            self.HERO_STAT_MIN_WIDTH,
            min(self.HERO_STAT_MAX_WIDTH, max(value_width, label_width) + 32),
        )
        self.hero_stat_wrap.setFixedWidth(int(target))
        available_width = max(48, int(target) - 24)
        self._fit_label_font(
            self.hero_stat_value,
            value_text,
            max_width=available_width,
            max_size=32,
            min_size=18,
        )
        self._fit_label_font(
            self.hero_stat_label,
            label_text,
            max_width=available_width,
            max_size=9,
            min_size=8,
        )

    def _refresh_widget_style(self, widget: QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    def _set_opacity(self, widget: QWidget, value: float) -> None:
        effect = widget.graphicsEffect()
        target = max(0.0, min(1.0, float(value)))
        if target >= 0.999:
            if isinstance(effect, QGraphicsOpacityEffect):
                widget.setGraphicsEffect(None)
            return
        if effect is not None and not isinstance(effect, QGraphicsOpacityEffect):
            return
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
        effect.setOpacity(target)

    def _truthy_flag(self, raw: Any) -> bool:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return raw != 0
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "y", "active", "starter"}
        return False

    def _stat_text(self, *labels: str) -> str:
        for label in labels:
            value = str(self._row_stats.get(label) or "").strip()
            if value:
                return value
        return ""

    def _parse_stat_number(self, raw: Any) -> float | None:
        text = str(raw or "").strip()
        if not text:
            return None
        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if not match:
            return None
        try:
            return float(match.group(0))
        except Exception:
            return None

    def _current_status_text(self) -> str:
        for source in (self._profile, self._context.get("playerData") or {}, self._context):
            if not isinstance(source, dict):
                continue
            status = str(source.get("status") or "").strip()
            if status:
                return status
        return ""

    def _is_player_active(self) -> bool:
        player = self._context.get("playerData")
        if not isinstance(player, dict):
            return False
        stats = player.get("statistics") or {}
        for key in ("isOnCourt", "onCourt", "oncourt"):
            if key in stats and stats.get(key) not in (None, ""):
                return self._truthy_flag(stats.get(key))
        for key in ("active", "starter", "onCourt", "oncourt", "isOnCourt"):
            if key in player and player.get(key) not in (None, ""):
                return self._truthy_flag(player.get(key))
        return False

    def _is_player_bench_or_inactive(self) -> bool:
        status_text = self._current_status_text().lower()
        if any(token in status_text for token in ("bench", "inactive", "out", "dnp", "scratch", "inj")):
            return True
        player = self._context.get("playerData")
        if not isinstance(player, dict):
            return False
        stats = player.get("statistics") or {}
        for key in ("isOnCourt", "onCourt", "oncourt"):
            if key in stats and stats.get(key) not in (None, ""):
                return not self._truthy_flag(stats.get(key))
        if "active" in player and player.get("active") not in (None, ""):
            return not self._truthy_flag(player.get("active"))
        return False

    def _foul_trouble_text(self) -> str:
        sport = self._sport_code()
        if sport not in {"NBA", "NCAA BASKETBALL"}:
            return ""
        foul_text = self._stat_text("PF", "FOULS")
        foul_count = self._parse_stat_number(foul_text)
        if foul_count is None:
            return ""
        threshold = 4 if sport == "NCAA BASKETBALL" else 5
        if foul_count >= threshold:
            return f"FOUL {int(foul_count)}"
        return ""

    def _hero_pair(self, ordered_stats: List[tuple[str, str]]) -> tuple[str, str]:
        if not ordered_stats:
            return "STAT", "--"
        by_norm = {self._normalize_stat_key(label): (str(label).upper(), value) for label, value in ordered_stats}
        for label in self._card_layout().get("hero_live", []):
            pair = by_norm.get(self._normalize_stat_key(label))
            if pair:
                return pair
        label, value = ordered_stats[0]
        return str(label).upper(), value

    def _snapshot_hero_pair(self, ordered_stats: List[tuple[str, str]]) -> tuple[str, str]:
        if not ordered_stats:
            return "STAT", "--"
        by_norm = {self._normalize_stat_key(label): (str(label).upper(), value) for label, value in ordered_stats}
        for label in self._card_layout().get("hero_snapshot", []):
            pair = by_norm.get(self._normalize_stat_key(label))
            if pair:
                return pair
        label, value = ordered_stats[0]
        return str(label).upper(), value

    def _is_hot_player(self, hero_label: str, hero_value: str) -> bool:
        if self._stat_source_mode != "game":
            return False
        thresholds = self.HOT_STATE_THRESHOLDS.get(self._sport_code(), {})
        norm = self._normalize_stat_key(hero_label)
        for label, threshold in thresholds.items():
            if self._normalize_stat_key(label) != norm:
                continue
            value = self._parse_stat_number(hero_value)
            if value is not None and value >= threshold:
                return True
        return False

    def _state_payload(self) -> tuple[str, str, str]:
        status_text = self._current_status_text().strip()
        status_lower = status_text.lower()
        if status_text and any(token in status_lower for token in ("out", "doubt", "question", "inj", "inactive", "suspend")):
            return "alert", status_text.upper(), "danger"
        foul_text = self._foul_trouble_text()
        if foul_text:
            return "alert", foul_text, "warning"
        hero_label = self.hero_stat_label.text().strip()
        hero_value = self.hero_stat_value.text().strip()
        if hero_value and hero_value != "--" and self._is_hot_player(hero_label, hero_value):
            return "hot", "HOT", "hot"
        if self._is_player_active():
            label = "ON FLOOR" if self._sport_code() in {"NBA", "NCAA BASKETBALL"} else "ACTIVE"
            return "active", label, "success"
        if self._is_player_bench_or_inactive():
            return "bench", "BENCH", "muted"
        return "default", "", "muted"

    def _set_status_badge(self, text: str, tone: str) -> None:
        self.status_badge.clear()
        self.status_badge.setVisible(False)
        self.status_badge.setStyleSheet("")

    def _apply_card_state(self) -> None:
        state, badge_text, badge_tone = self._state_payload()
        self.surface.setProperty("cardState", state)
        self.hero_stat_wrap.setProperty("cardState", state)
        self._refresh_widget_style(self.surface)
        self._refresh_widget_style(self.hero_stat_wrap)
        self._set_status_badge(badge_text, badge_tone)

        bench_opacity = 0.82 if state == "bench" else 1.0
        self._set_opacity(self.identity_wrap, bench_opacity)
        self._set_opacity(self.team_logo_label, 0.80 if state == "bench" else 1.0)
        self._set_opacity(self.hero_stat_wrap, 0.88 if state == "bench" else 1.0)

        glow = self.hero_stat_value.graphicsEffect()
        if not isinstance(glow, QGraphicsDropShadowEffect):
            glow = QGraphicsDropShadowEffect(self.hero_stat_value)
            glow.setOffset(0, 0)
            self.hero_stat_value.setGraphicsEffect(glow)
        color = QColor(self._palette["accent_soft"])
        if state == "hot":
            color.setAlpha(210)
            glow.setColor(color)
            glow.setBlurRadius(24)
        elif state == "active":
            color.setAlpha(120)
            glow.setColor(color)
            glow.setBlurRadius(14)
        elif state == "alert":
            color = QColor(self._palette["warning"])
            color.setAlpha(140)
            glow.setColor(color)
            glow.setBlurRadius(16)
        else:
            color = QColor(0, 0, 0, 0)
            glow.setColor(color)
            glow.setBlurRadius(0)

    def _refresh_meta(self) -> None:
        sport = self._sport_code()
        jersey = str(self._profile.get("jersey") or self._context.get("jersey") or "").strip()
        lineup_order = str(self._context.get("lineupOrder") or "").strip()
        position = str(self._profile.get("position") or self._context.get("position") or "").strip()
        team = str(self._context.get("teamTricode") or self._context.get("teamName") or "").strip()
        self.jersey_badge.setText(f"#{jersey}" if jersey else (position or sport[:3] or "PLY")[:4].upper())
        parts = []
        if position:
            parts.append(position)
        minutes = ""
        if sport in {"NBA", "NCAA BASKETBALL", "MLS"}:
            min_val = self._stat_text("MIN", "TIME")
            if min_val:
                minutes = f"{min_val} MIN"
        elif sport == "NHL":
            toi_val = self._stat_text("TOI", "MIN")
            if toi_val:
                minutes = f"{toi_val} TOI"
        elif sport == "MLB":
            ip_val = self._stat_text("IP")
            if ip_val:
                minutes = f"{ip_val} IP"
            elif lineup_order and lineup_order != jersey:
                parts.append(f"BO {lineup_order}")
        if minutes:
            parts.append(minutes)
        if team:
            parts.append(team)
        if sport and not parts:
            parts.append(sport)
        self.meta_label.setText(" · ".join(parts) if parts else "Live game data")

    def _first_text(self, payload: Dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = str(payload.get(key) or "").strip()
            if value:
                return value
        return ""

    def _format_date(self, raw: Any) -> str:
        text = str(raw or "").strip()
        if not text:
            return ""
        for fmt in ("%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).strftime("%b %d, %Y")
            except Exception:
                continue
        return text

    def _bio_pairs_for_sport(self, payload: Dict[str, Any]) -> List[tuple[str, str]]:
        sport = self._sport_code()
        bats = self._first_text(payload, "bats")
        throws = self._first_text(payload, "throws")
        shoots = self._first_text(payload, "shootsCatches")
        bats_throws = ""
        if bats or throws:
            bats_throws = f"{bats or '-'} / {throws or '-'}"
        elif shoots:
            bats_throws = shoots
        base = {
            "No.": self._first_text(payload, "jersey"),
            "BO": self._first_text(payload, "lineupOrder"),
            "Pos": self._first_text(payload, "position"),
            "Team": self._first_text(payload, "team"),
            "Status": self._first_text(payload, "status"),
            "Ht": self._first_text(payload, "height"),
            "Wt": self._first_text(payload, "weight"),
            "Age": self._first_text(payload, "age"),
            "DOB": self._format_date(payload.get("dateOfBirth")),
            "Born": self._first_text(payload, "birthPlace"),
            "Exp": self._first_text(payload, "experience"),
            "College": self._first_text(payload, "college"),
            "B/T": bats_throws,
            "Shoots": shoots,
        }
        layout = self._card_layout()
        order = layout.get("profile_order", self.DEFAULT_CARD_LAYOUT["profile_order"])
        extras = layout.get("profile_extras", self.DEFAULT_CARD_LAYOUT["profile_extras"])
        pairs: List[tuple[str, str]] = []
        used: set[str] = set()
        for label in order:
            val = str(base.get(label) or "").strip()
            if not val:
                continue
            pairs.append((label, val))
            used.add(label)
        for label in extras:
            if label in used:
                continue
            val = str(base.get(label) or "").strip()
            if not val:
                continue
            pairs.append((label, val))
            used.add(label)
        return pairs

    def _truncate_profile_value(self, value: str) -> str:
        text = str(value or "").strip()
        if len(text) <= 18:
            return text
        return text[:17].rstrip() + "…"

    def _render_bio(self, payload: Dict[str, Any]) -> None:
        merged = dict(payload or {})
        merged.setdefault(
            "team",
            str(self._context.get("teamTricode") or self._context.get("teamName") or "").strip(),
        )
        merged.setdefault("jersey", str(self._context.get("jersey") or "").strip())
        merged.setdefault("lineupOrder", str(self._context.get("lineupOrder") or "").strip())
        merged.setdefault("position", str(self._context.get("position") or "").strip())
        skip = {"No.", "Pos", "Team"}
        pairs = [
            (label, self._truncate_profile_value(value))
            for label, value in self._bio_pairs_for_sport(merged)
            if label not in skip
        ]
        pairs = pairs[: self.PROFILE_STATS_MAX]
        self._render_pairs_grid(
            self.bio_grid,
            pairs,
            empty_text="No profile details available yet.",
            columns=self.PROFILE_COLUMNS,
            variant="info",
        )

    def _normalize_stat_key(self, raw: str) -> str:
        text = str(raw or "").strip().upper()
        special = {
            "SV%": "svpct",
            "FG%": "fgpct",
            "3P%": "3ppct",
            "FT%": "ftpct",
            "+/-": "plusminus",
        }
        if text in special:
            return special[text]
        return re.sub(r"[^a-z0-9]+", "", text.lower())

    def _is_zeroish_stat(self, value: Any) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        normalized = text.replace("+", "").replace(",", "")
        return normalized in {"0", "0.0", "0.00", "0.000", ".000", "-0", "-0.0", "-0.00", "-0.000"}

    def _should_skip_display_stat(self, label: str, value: Any) -> bool:
        sport = self._sport_code()
        role = self._role_layout_key()
        norm = self._normalize_stat_key(label)
        if sport == "NHL":
            if norm == "pim" and self._is_zeroish_stat(value):
                return True
            if role == "G" and norm in {"g", "a", "pts", "sog"}:
                return True
            if role != "G" and norm in {"sv", "svpct", "gaa", "w", "l", "so"}:
                return True
        return False

    def _display_stat_label(self, label: str, *, hero: bool = False) -> str:
        text = str(label or "").strip().upper()
        if not text:
            return text
        if self._sport_code() == "NHL":
            mapping = {
                "G": "GOALS",
                "A": "ASSISTS",
                "PTS": "POINTS",
                "SOG": "SOG",
                "TOI": "TOI",
                "HITS": "HITS",
                "BLK": "BLOCKS",
                "SV": "SAVES",
                "SV%": "SAVE %",
                "SA": "SHOTS AG",
                "GA": "GOALS AG",
                "SO": "SHUTOUTS",
            }
            return mapping.get(text, text)
        return text

    def _game_stats_limit(self) -> int:
        if self._sport_code() == "NHL" and self._role_layout_key() != "G":
            return 5
        return self.GAME_STATS_MAX

    def _ordered_stats(self, stats: Dict[str, Any]) -> List[tuple[str, str]]:
        raw_pairs: List[tuple[str, str]] = []
        for key, raw_val in stats.items():
            label = str(key or "").strip()
            if not label:
                continue
            value = str(raw_val or "").strip()
            if not value:
                continue
            raw_pairs.append((label, value))

        skip = {
            self._normalize_stat_key("#"),
            self._normalize_stat_key("player"),
            self._normalize_stat_key("pos"),
            self._normalize_stat_key("position"),
        }
        filtered = [(k, v) for k, v in raw_pairs if self._normalize_stat_key(k) not in skip]
        if not filtered:
            return []

        preferred = self._card_layout().get("live_order", self.DEFAULT_CARD_LAYOUT["live_order"])

        by_norm: Dict[str, tuple[str, str]] = {}
        for pair in filtered:
            norm = self._normalize_stat_key(pair[0])
            by_norm.setdefault(norm, pair)
        ordered: List[tuple[str, str]] = []
        used: set[str] = set()
        for label in preferred:
            norm = self._normalize_stat_key(label)
            pair = by_norm.get(norm)
            if pair and norm not in used:
                ordered.append(pair)
                used.add(norm)
        for pair in filtered:
            norm = self._normalize_stat_key(pair[0])
            if norm in used:
                continue
            ordered.append(pair)
            used.add(norm)
        return ordered[: self.STAT_MAX]

    def _render_stats(self, stats: Dict[str, Any]) -> None:
        filtered = self._ordered_stats(stats)
        if filtered:
            self._stat_source_mode = "game"
            source_pairs = filtered
        else:
            self._stat_source_mode = "snapshot"
            source_pairs = self._snapshot_stat_pairs()
        if self._stat_source_mode == "snapshot":
            hero_label, hero_value = self._snapshot_hero_pair(source_pairs)
        else:
            hero_label, hero_value = self._hero_pair(source_pairs)
        self.hero_stat_value.setText(hero_value or "--")
        self.hero_stat_label.setText(self._display_stat_label(hero_label or "STAT", hero=True))
        self._refresh_hero_stat_wrap()
        hero_norm = self._normalize_stat_key(hero_label)
        self._primary_stat_keys = {hero_norm} if hero_norm else set()
        trimmed: List[tuple[str, str]] = []
        skipped_hero = False
        for key, value in source_pairs:
            norm = self._normalize_stat_key(key)
            if not skipped_hero and norm == hero_norm and str(value).strip() == str(hero_value).strip():
                skipped_hero = True
                continue
            if self._should_skip_display_stat(key, value):
                continue
            trimmed.append((key, value))
        trimmed = trimmed[: self._game_stats_limit()]
        self._primary_stat_keys.update(self._normalize_stat_key(key) for key, _value in trimmed)
        self._render_pairs_grid(
            self.stat_grid,
            [(self._display_stat_label(key), value) for key, value in trimmed],
            empty_text="No player snapshot available yet.",
            columns=self.GAME_STATS_COLUMNS,
            variant="stat",
        )
        self._refresh_meta()
        self._apply_card_state()

    def _ordered_career_stats(self, stats: Dict[str, Any]) -> List[tuple[str, str]]:
        raw_pairs: List[tuple[str, str]] = []
        for key, raw_val in stats.items():
            label = str(key or "").strip()
            if not label:
                continue
            value = str(raw_val or "").strip()
            if not value:
                continue
            raw_pairs.append((label, value))
        if not raw_pairs:
            return []

        preferred = self._card_layout().get("career_order", self.DEFAULT_CARD_LAYOUT["career_order"])

        by_norm: Dict[str, tuple[str, str]] = {}
        for pair in raw_pairs:
            norm = self._normalize_stat_key(pair[0])
            by_norm.setdefault(norm, pair)
        ordered: List[tuple[str, str]] = []
        used: set[str] = set()
        for label in preferred:
            norm = self._normalize_stat_key(label)
            pair = by_norm.get(norm)
            if pair and norm not in used:
                ordered.append(pair)
                used.add(norm)
        for pair in raw_pairs:
            norm = self._normalize_stat_key(pair[0])
            if norm in used:
                continue
            ordered.append(pair)
            used.add(norm)
        return ordered[: self.STAT_MAX]

    def _snapshot_stat_pairs(self) -> List[tuple[str, str]]:
        career_stats = self._profile.get("careerStats")
        if not isinstance(career_stats, dict):
            return []
        skip = {
            self._normalize_stat_key("GP"),
            self._normalize_stat_key("APP"),
            self._normalize_stat_key("W"),
            self._normalize_stat_key("L"),
        }
        pairs: List[tuple[str, str]] = []
        for label, value in self._ordered_career_stats(career_stats):
            if self._normalize_stat_key(label) in skip:
                continue
            pairs.append((label, value))
        return pairs

    def _render_career_stats(self, stats: Dict[str, Any]) -> None:
        filtered = self._ordered_career_stats(stats)
        if self._stat_source_mode == "snapshot" and self._primary_stat_keys:
            deduped = [
                (key, value)
                for key, value in filtered
                if self._normalize_stat_key(key) not in self._primary_stat_keys
            ]
            if len(deduped) >= 2:
                filtered = deduped
        filtered = filtered[: self.CAREER_STATS_MAX]
        self._render_pairs_grid(
            self.career_grid,
            [(self._display_stat_label(str(key)), value) for key, value in filtered],
            empty_text="No career stats available yet.",
            columns=self.CAREER_STATS_COLUMNS,
            variant="career",
        )

    def _clear_grid(self, layout: QGridLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
                continue
            child_layout = item.layout()
            if child_layout is not None:
                while child_layout.count():
                    child = child_layout.takeAt(0)
                    child_widget = child.widget()
                    if child_widget is not None:
                        child_widget.hide()
                        child_widget.setParent(None)
                        child_widget.deleteLater()

    def apply_profile(self, profile: Dict[str, Any]) -> None:
        payload = dict(profile or {})
        self._profile = payload
        resolved_name = (
            payload.get("displayName")
            or payload.get("fullName")
            or self._context.get("playerName")
            or "Player"
        )
        self._set_name_text(str(resolved_name))
        if not self._headshot_loaded:
            self.set_headshot(None)

        if payload.get("jersey"):
            self._context["jersey"] = str(payload.get("jersey") or "")
        if payload.get("position"):
            self._context["position"] = str(payload.get("position") or "")
        self._refresh_meta()
        self._render_stats(self._row_stats)
        self._render_bio(payload)
        career_stats = payload.get("careerStats")
        if isinstance(career_stats, dict):
            self._render_career_stats(career_stats)
        else:
            self._render_career_stats({})
        self._apply_card_state()

    def _render_pairs_grid(
        self,
        layout: QGridLayout,
        pairs: List[tuple[str, str]],
        *,
        empty_text: str,
        columns: int = 2,
        variant: str = "info",
    ) -> None:
        self._clear_grid(layout)
        rows: List[tuple[str, str]] = []
        for key, value in pairs:
            label = str(key or "").strip()
            val = str(value or "").strip()
            if not label or not val:
                continue
            rows.append((label, val))

        if not rows:
            placeholder = QLabel(empty_text)
            placeholder.setObjectName("playerStatus")
            placeholder.setWordWrap(True)
            layout.addWidget(placeholder, 0, 0, 1, max(1, columns))
            return

        columns = max(1, int(columns))
        for idx in range(8):
            layout.setColumnStretch(idx, 0)
        if variant != "info":
            for idx in range(columns):
                layout.setColumnStretch(idx, 1)
        for idx, (label, val) in enumerate(rows):
            row = idx // columns
            col = idx % columns
            chip = QFrame()
            if variant == "stat":
                chip.setObjectName("statChip")
                chip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                chip.setMinimumHeight(46)
                chip_layout = QVBoxLayout(chip)
                chip_layout.setContentsMargins(12, 8, 12, 7)
                chip_layout.setSpacing(0)
                value_label = QLabel(val)
                value_label.setObjectName("chipValue")
                key_label = QLabel(label)
                key_label.setObjectName("chipKey")
                value_label.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
                key_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                chip_layout.addWidget(value_label, 0, Qt.AlignLeft | Qt.AlignBottom)
                chip_layout.addWidget(key_label, 0, Qt.AlignLeft | Qt.AlignTop)
            elif variant == "career":
                chip.setObjectName("careerChip")
                chip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                chip.setMinimumHeight(24)
                chip_layout = QHBoxLayout(chip)
                chip_layout.setContentsMargins(2, 2, 4, 2)
                chip_layout.setSpacing(5)
                value_label = QLabel(val)
                value_label.setObjectName("careerChipValue")
                key_label = QLabel(label)
                key_label.setObjectName("chipKey")
                value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                key_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                chip_layout.addWidget(value_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
                chip_layout.addWidget(key_label, 1, Qt.AlignLeft | Qt.AlignVCenter)
            else:
                chip.setObjectName("infoChip")
                chip.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
                chip.setMinimumHeight(28)
                chip_layout = QHBoxLayout(chip)
                chip_layout.setContentsMargins(8, 4, 8, 4)
                chip_layout.setSpacing(4)
                key_label = QLabel(label)
                key_label.setObjectName("infoKey")
                key_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                value_label = QLabel(val)
                value_label.setObjectName("infoValue")
                value_label.setWordWrap(False)
                value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                chip_layout.addWidget(key_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
                chip_layout.addWidget(value_label, 1, Qt.AlignLeft | Qt.AlignVCenter)
            layout.addWidget(chip, row, col)

    def set_headshot(self, pixmap: QPixmap | None) -> None:
        if pixmap and not pixmap.isNull():
            self.headshot_label.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            scaled = pixmap.scaled(
                self.headshot_label.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            self.headshot_label.setPixmap(scaled)
            self.headshot_label.setText("")
            self._headshot_loaded = True
            return
        self.headshot_label.setPixmap(QPixmap())
        self.headshot_label.setAlignment(Qt.AlignCenter)
        initials = self._initials(self.name_label.text() or self._context.get("playerName") or "")
        self.headshot_label.setText(initials or "?")
        self._headshot_loaded = False

    def set_team_logo(self, pixmap: QPixmap | None) -> None:
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                self.team_logo_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.team_logo_label.setPixmap(scaled)
            self.team_logo_label.setText("")
            return
        self.team_logo_label.setPixmap(QPixmap())
        fallback = str(self._context.get("teamTricode") or self._context.get("teamName") or "").strip()
        self.team_logo_label.setText(fallback[:4].upper() if fallback else "")

    def _initials(self, raw_name: Any) -> str:
        parts = [part for part in str(raw_name or "").strip().split() if part]
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class ScoreSourceWindow(QMainWindow):
    scores_ready = Signal(dict)
    boxscore_ready = Signal(dict)
    logo_ready = Signal(str, object)
    combo_logo_ready = Signal(object, object)
    pbp_ready = Signal(str, object)
    scores_fetched = Signal(dict)  # cross-thread handoff before delay
    boxscore_fetched = Signal(str, object)
    realtime_ready = Signal(object)
    player_profile_ready = Signal(object, object)

    def __init__(
        self,
        logic: ScoreSourceLogic | None = None,
        *,
        switch_sport: Callable[[str, "ScoreSourceWindow"], None] | None = None,
        sport_options: list[str] | None = None,
        backend_module=None,
        sport_name: str = "NBA",
        sport_logo_path: str | None = None,
        sport_icon_map: dict[str, str] | None = None,
    ):
        super().__init__()
        self.sport_name = sport_name
        self._sport_key = canonicalize_sport_name(sport_name)
        self.setWindowTitle(f"ScoreSource – {self.sport_name}")
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setAutoFillBackground(True)
        self._default_icon = QIcon(self._make_default_icon())
        self.setWindowIcon(self._default_icon)

        self.backend = backend_module or default_backend
        self.display_tz = os.environ.get("SCORESOURCE_TZ", "America/Chicago")
        if logic is not None:
            self.logic = logic
        else:
            self.logic = ScoreSourceLogic(default_sport=self._sport_key)
        self._switch_sport = switch_sport
        self._sport_options = sport_options or ["NBA"]
        self._sport_icon_map = sport_icon_map or {}
        self._sport_logo_path = sport_logo_path
        self.games: List[Dict[str, Any]] = []
        self.lines: List[str] = []
        self.selected_game_id: str | None = None
        self._pending_selection_id: str | None = None
        self._table_headers = self._resolve_headers(getattr(self.backend, "sport_table_headers", None))
        self.display_delay_ms = 200  # minimal delay to show scores quickly

        delay_sec = os.environ.get("SCORESOURCE_FEED_DELAY_SEC", "0")
        try:
            self.feed_delay_ms = max(0, int(float(delay_sec)) * 1000)
        except Exception:
            self.feed_delay_ms = 60_000
        self._delay_is_default = "SCORESOURCE_FEED_DELAY_SEC" not in os.environ
        if self._delay_is_default and self._sport_key != "NBA":
            self.feed_delay_ms = 0
        try:
            self.boxscore_poll_default_ms = max(
                1000, int(float(os.environ.get("SCORESOURCE_BOXSCORE_POLL_MS", "2000")))
            )
        except Exception:
            self.boxscore_poll_default_ms = 2000
        try:
            self.boxscore_poll_live_ms = max(
                self.boxscore_poll_default_ms,
                int(float(os.environ.get("SCORESOURCE_BOXSCORE_POLL_LIVE_MS", "3000"))),
            )
        except Exception:
            self.boxscore_poll_live_ms = max(self.boxscore_poll_default_ms, 3000)
        try:
            self.scores_poll_live_ms = max(
                2000, int(float(os.environ.get("SCORESOURCE_SCORES_POLL_LIVE_MS", "5000")))
            )
        except Exception:
            self.scores_poll_live_ms = 5000
        try:
            self.scores_poll_upcoming_ms = max(
                self.scores_poll_live_ms,
                int(float(os.environ.get("SCORESOURCE_SCORES_POLL_UPCOMING_MS", "15000"))),
            )
        except Exception:
            self.scores_poll_upcoming_ms = max(self.scores_poll_live_ms, 15000)
        try:
            self.scores_poll_idle_ms = max(
                self.scores_poll_upcoming_ms,
                int(float(os.environ.get("SCORESOURCE_SCORES_POLL_IDLE_MS", "30000"))),
            )
        except Exception:
            self.scores_poll_idle_ms = max(self.scores_poll_upcoming_ms, 30000)
        try:
            self.ticker_speed_px = max(
                TICKER_SPEED_PX,
                float(os.environ.get("SCORESOURCE_TICKER_SPEED_PX", TICKER_SPEED_PX)),
            )
        except Exception:
            self.ticker_speed_px = TICKER_SPEED_PX
        self._next_display_at: float | None = None
        self._cached_state = self._load_cached_state()
        self._state_dirty = False
        self._last_state_save_ts = 0.0
        self._state_save_interval_sec = 3.0
        self._state_save_timer = QTimer(self)
        self._state_save_timer.setSingleShot(True)
        self._state_save_timer.timeout.connect(self._flush_cached_state)
        self._last_boxscore_data: Dict[str, Any] | None = None
        self._clock_state: Dict[str, Any] | None = None
        self._penalty_state: Dict[str, Any] | None = None
        self._instant_boxscore_apply = False
        self.clock_buffer_sec = 0.5  # small buffer to reduce jitter
        self._rss_enabled = False
        self._rss_headlines: List[str] = []
        self._rss_index = 0
        self._rss_last_fetch = 0.0
        self._rss_fetch_ttl = 180.0
        self._rss_future = None
        self._nba_scroll_tables: set[QTableWidget] = set()
        self._player_click_tables: set[QTableWidget] = set()
        self._active_player_card: PlayerCardDialog | None = None
        self._nfl_scroll_views: dict[QWidget, QTableWidget] = {}
        self._nfl_table_team: dict[QTableWidget, Dict[str, Any]] = {}
        self._nfl_table_side: dict[QTableWidget, str] = {}
        self._nfl_manual_mode: dict[str, str] = {}
        self._nfl_last_possession: str | None = None
        self._nfl_toggle_ts = 0.0

        self._apply_palette()
        self._build_layout()
        self.update_league_logo(self._sport_logo_path)
        self._setup_timers()
        self._update_rss_mode(force=True)

        self.scores_fetched.connect(self._schedule_scores_emit)
        self.boxscore_fetched.connect(self._schedule_boxscore_emit)
        self.scores_ready.connect(self._apply_scores)
        self.boxscore_ready.connect(self.apply_boxscore)
        self.logo_ready.connect(self._apply_logo_bytes)
        self.combo_logo_ready.connect(self._apply_combo_logo_bytes)
        self.pbp_ready.connect(self._apply_pbp)
        self.realtime_ready.connect(self._apply_realtime_state)
        self.player_profile_ready.connect(self._apply_player_profile_ready)

        self._shortcut_up = QShortcut(Qt.Key_Up, self)
        self._shortcut_up.activated.connect(lambda: self._step_game_selection(-1))
        self._shortcut_down = QShortcut(Qt.Key_Down, self)
        self._shortcut_down.activated.connect(lambda: self._step_game_selection(1))

        try:
            data_workers = max(2, min(12, int(os.environ.get("SCORESOURCE_DATA_WORKERS", "4"))))
        except Exception:
            data_workers = 4
        try:
            logo_workers = max(1, min(8, int(os.environ.get("SCORESOURCE_LOGO_WORKERS", "2"))))
        except Exception:
            logo_workers = 2
        self._executor = ThreadPoolExecutor(max_workers=data_workers)
        self._logo_executor = ThreadPoolExecutor(max_workers=logo_workers)
        self._scores_future = None
        self._scores_future_sport = None
        self._boxscore_future = None
        self._boxscore_future_key = None
        self._sport_token = 0
        self._sport_token_name = self.sport_name
        self._has_displayed_scores = False
        self._has_displayed_boxscore = False
        self._score_history: deque[tuple[float, Dict[str, Any]]] = deque(maxlen=120)
        self._boxscore_history: Dict[str, deque[tuple[float, Dict[str, Any]]]] = {}
        self._pbp_history: Dict[str, deque[tuple[float, list[dict[str, Any]]]]] = {}
        self._runtime_scores_cache: Dict[str, Dict[str, Any]] = {}
        self._runtime_boxscore_cache: Dict[tuple[str, str], Dict[str, Any]] = {}
        self._boxscore_prefetch_inflight: set[tuple[str, str]] = set()
        self._score_prefetch_inflight: set[str] = set()
        self._last_cross_sport_prefetch_ts = 0.0
        self._cross_sport_prefetch_interval_sec = 20.0
        try:
            self._cross_sport_prefetch_batch = max(
                1, min(6, int(os.environ.get("SCORESOURCE_CROSS_SPORT_PREFETCH_BATCH", "2")))
            )
        except Exception:
            self._cross_sport_prefetch_batch = 2
        try:
            self._prefetch_game_limit = max(0, min(6, int(os.environ.get("SCORESOURCE_PREFETCH_GAME_COUNT", "3"))))
        except Exception:
            self._prefetch_game_limit = 3
        self._displayed_boxscore_key: tuple[str, str] | None = None
        self._last_logo_keys: Dict[str, tuple[str, str, str]] = {"home": ("", "", ""), "away": ("", "", "")}
        self._combo_logo_cache: Dict[tuple[str, str, str], QPixmap] = {}
        self._combo_logo_pending: set[tuple[str, str, str]] = set()
        self._combo_game_row_by_id: Dict[str, int] = {}
        self._pbp_future = None
        self._pbp_future_game_id: str | None = None
        self._last_pbp_key: object | None = None
        self._pbp_lines: list[str] = []
        self._fade_anims: Dict[object, QPropertyAnimation] = {}
        self._score_flash_tokens: Dict[QLabel, object] = {}
        self._alive = True

        self.refresh_scores()  # initial fetch
        self._apply_cached_state_if_available()

    def _resolve_headers(self, headers: list[str] | None = None) -> List[str]:
        if self.sport_name.upper() == "NBA":
            return list(NBA_SCROLL_HEADERS)
        resolved = headers or getattr(self.backend, "sport_table_headers", None) or DEFAULT_TABLE_HEADERS
        return list(resolved)

    def _make_default_icon(self) -> QPixmap:
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
        if icon_path.exists():
            pix = QPixmap(str(icon_path))
            if not pix.isNull():
                return pix
        pm = QPixmap(128, 128)
        pm.fill(QColor(ACCENT))
        return pm

    # --------------- palette ---------------
    def _apply_palette(self):
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(BG))
        pal.setColor(QPalette.WindowText, QColor(TEXT))
        pal.setColor(QPalette.Base, QColor(PANEL))
        pal.setColor(QPalette.Button, QColor(PANEL))
        pal.setColor(QPalette.Text, QColor(TEXT))
        self.setPalette(pal)

    # --------------- layout ---------------
    def _build_layout(self):
        root = QWidget()
        root.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        control_frame = QFrame()
        control_frame.setFixedHeight(CONTROL_BAR_HEIGHT)
        control_frame.setStyleSheet("background: transparent;")
        control_bar = QHBoxLayout(control_frame)
        control_bar.setContentsMargins(TOP_H_MARGIN, 0, TOP_H_MARGIN, 0)
        control_bar.setSpacing(8)

        self.sport_combo = QComboBox()
        for name in self._sport_options:
            icon = QIcon(self._sport_icon_map.get(name, "")) if name in self._sport_icon_map else QIcon()
            self.sport_combo.addItem(icon, name)
        try:
            idx = self._sport_options.index(self.sport_name)
            self.sport_combo.setCurrentIndex(idx)
        except Exception:
            pass
        self.sport_combo.setFixedHeight(CONTROL_BAR_HEIGHT)
        self.sport_combo.setMinimumWidth(84)
        self.sport_combo.currentTextChanged.connect(self._on_sport_change)

        self.game_combo = QComboBox()
        self.game_combo.setObjectName("game_combo")
        self.game_combo.setPlaceholderText("Select game")
        self.game_combo.setItemDelegate(GameLineDelegate(self.game_combo))
        self.game_combo.setFixedHeight(CONTROL_BAR_HEIGHT)
        self.game_combo.setMinimumWidth(240)
        self.game_combo.currentIndexChanged.connect(self.on_game_selected)

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(CONTROL_BAR_HEIGHT, CONTROL_BAR_HEIGHT)
        self.close_btn.clicked.connect(self.close)

        self.league_logo = QLabel()
        self.league_logo.setFixedSize(CONTROL_BAR_HEIGHT, CONTROL_BAR_HEIGHT)
        if self._sport_logo_path and Path(self._sport_logo_path).exists():
            pix = QPixmap(self._sport_logo_path).scaled(
                CONTROL_BAR_HEIGHT, CONTROL_BAR_HEIGHT, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.league_logo.setPixmap(pix)

        self.settings_menu = QMenu(self)
        self.timezone_actions: list[QAction] = []
        self.delay_actions: list[QAction] = []
        self.ticker_speed_actions: list[QAction] = []
        self.timezone_options = [
            ("Eastern", "America/New_York"),
            ("Central", "America/Chicago"),
            ("Mountain", "America/Denver"),
            ("Pacific", "America/Los_Angeles"),
            ("Alaska", "America/Anchorage"),
            ("Hawaii", "Pacific/Honolulu"),
        ]
        for label, tz in self.timezone_options:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setData(tz)
            act.triggered.connect(lambda checked, a=act: self._on_timezone_selected(a))
            self.settings_menu.addAction(act)
            self.timezone_actions.append(act)
        self.settings_menu.addSeparator()
        delay_group = QActionGroup(self)
        delay_group.setExclusive(True)
        for label, sec in (
            ("Live", 0),
            ("Delay 30s", 30),
            ("Delay 1:00", 60),
            ("Delay 1:15", 75),
            ("Delay 2:00", 120),
            ("Delay 2:30", 150),
            ("Delay 3:00", 180),
            ("Delay 5:00", 300),
        ):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setData(sec)
            act.triggered.connect(lambda checked, a=act: self._on_delay_selected(a))
            delay_group.addAction(act)
            self.settings_menu.addAction(act)
            self.delay_actions.append(act)
        self.settings_menu.addSeparator()
        speed_group = QActionGroup(self)
        speed_group.setExclusive(True)
        for label, speed in (
            ("Ticker Slow", 8.0),
            ("Ticker Normal", 16.0),
            ("Ticker Fast", 24.0),
            ("Ticker Turbo", 36.0),
        ):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setData(speed)
            act.triggered.connect(lambda checked, a=act: self._on_ticker_speed_selected(a))
            speed_group.addAction(act)
            self.settings_menu.addAction(act)
            self.ticker_speed_actions.append(act)
        self._sync_timezone_actions()
        self._sync_delay_actions()
        self._sync_ticker_speed_actions()
        self.settings_btn = QToolButton()
        self.settings_btn.setText("⚙")
        self.settings_btn.setFixedSize(CONTROL_BAR_HEIGHT, CONTROL_BAR_HEIGHT)
        self.settings_btn.setPopupMode(QToolButton.InstantPopup)
        self.settings_btn.setMenu(self.settings_menu)
        left_controls = QFrame()
        left_controls.setFixedHeight(CONTROL_BAR_HEIGHT)
        left_controls.setFixedWidth(SIDE_SECTION_WIDTH - (TOP_H_MARGIN * 2))
        left_controls_layout = QHBoxLayout(left_controls)
        left_controls_layout.setContentsMargins(0, 0, 0, 0)
        left_controls_layout.setSpacing(8)
        left_controls_layout.addWidget(self.settings_btn, alignment=Qt.AlignLeft)
        left_controls_layout.addStretch(1)
        left_controls_layout.addWidget(self.sport_combo, alignment=Qt.AlignRight)
        self.drag_bar = DragBar(self)
        self.drag_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        control_bar.addWidget(left_controls, alignment=Qt.AlignLeft)
        control_bar.addWidget(self.league_logo, alignment=Qt.AlignLeft)
        control_bar.addWidget(self.game_combo, alignment=Qt.AlignLeft)
        control_bar.addWidget(self.drag_bar, stretch=1)
        control_bar.addWidget(self.close_btn, alignment=Qt.AlignRight)

        self.top_frame = QFrame()
        self.top_frame.setFixedSize(WINDOW_WIDTH, TOP_SECTION_HEIGHT)
        self.top_frame.setStyleSheet("background: transparent;")
        self.top_bg = QFrame(self.top_frame)
        self.top_bg.setFixedSize(WINDOW_WIDTH, TOP_SECTION_HEIGHT)
        self.top_bg.setStyleSheet("background: transparent;")
        self.top_bg.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        top_bg_layout = QHBoxLayout(self.top_bg)
        top_bg_layout.setContentsMargins(0, 0, 0, 0)
        top_bg_layout.setSpacing(0)
        self.left_bg = QFrame()
        self.right_bg = QFrame()
        self.left_bg.setStyleSheet("background: transparent;")
        self.right_bg.setStyleSheet("background: transparent;")
        top_bg_layout.addWidget(self.left_bg)
        top_bg_layout.addWidget(self.right_bg)
        self.nfl_bow_left = QFrame(self.left_bg)
        self.nfl_bow_left.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.nfl_bow_left.setStyleSheet("background: transparent; border: none;")
        self.nfl_bow_left.lower()
        self.nfl_bow_right = QFrame(self.right_bg)
        self.nfl_bow_right.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.nfl_bow_right.setStyleSheet("background: transparent; border: none;")
        self.nfl_bow_right.lower()
        self.seam_shadow = QFrame(self.top_bg)
        self.seam_shadow.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.seam_shadow.setGeometry(
            (WINDOW_WIDTH - CENTER_SEAM_WIDTH) // 2,
            0,
            CENTER_SEAM_WIDTH,
            TOP_SECTION_HEIGHT,
        )
        self.seam_shadow.setStyleSheet("background: transparent; border: none;")
        self.seam_shadow.raise_()

        top_layout = QHBoxLayout(self.top_frame)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        left_frame = QFrame()
        left_frame.setFixedSize(SIDE_SECTION_WIDTH, TOP_SECTION_HEIGHT)
        left_frame.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(TOP_H_MARGIN, TOP_V_MARGIN, TOP_H_MARGIN, TOP_BOTTOM_MARGIN)
        left_layout.setSpacing(2)

        self.away_city = QLabel("", left_frame)
        self.away_city.setVisible(True)
        self.away_city.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.away_city.setStyleSheet(f"font-size: {CITY_FONT_SIZE}px; font-weight: 800; letter-spacing: 0.6px;")
        self.away_name = QLabel("AWAY TEAM")
        self.away_name.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.away_name.setStyleSheet("font-size: 22px; font-weight: 900; color: #f7f7f7; letter-spacing: 1px;")
        left_layout.addWidget(self.away_city)

        left_mid = QHBoxLayout()
        left_mid.setContentsMargins(0, 0, 0, 0)
        left_mid.setSpacing(12)
        self.away_logo_box = CircularLogoGlow()
        left_mid.addStretch(1)

        self.away_score_card = ScoreCard()
        self.away_score_card.setFixedSize(SCORE_CARD_WIDTH, SCORE_CARD_HEIGHT)
        away_score_layout = QVBoxLayout(self.away_score_card)
        away_score_layout.setContentsMargins(0, 0, 0, 0)
        away_score_layout.setSpacing(4)
        self.away_score = QLabel("0")
        self.away_score.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.away_score.setStyleSheet("font-size: 58px; font-weight: 900; color: #f7f7f7;")
        away_score_layout.addWidget(self.away_score, alignment=Qt.AlignRight)
        self.away_timeouts = TimeoutBar()
        self.away_penalties = QLabel("PIM --")
        self.away_penalties.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.away_penalties.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 12px; font-weight: 800;")
        self.away_penalty_clock = QLabel("PEN --")
        self.away_penalty_clock.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.away_penalty_clock.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 11px; font-weight: 800;")
        self._away_penalty_meta = QFrame()
        self._away_penalty_meta.setStyleSheet("background: transparent; border: none;")
        away_penalty_layout = QVBoxLayout(self._away_penalty_meta)
        away_penalty_layout.setContentsMargins(0, 0, 0, 0)
        away_penalty_layout.setSpacing(2)
        away_penalty_layout.addWidget(self.away_penalties, alignment=Qt.AlignRight)
        away_penalty_layout.addWidget(self.away_penalty_clock, alignment=Qt.AlignRight)
        self._away_meta_stack = QStackedLayout()
        self._away_meta_stack.setContentsMargins(0, 0, 0, 0)
        self._away_meta_stack.addWidget(self.away_timeouts)
        self._away_meta_stack.addWidget(self._away_penalty_meta)
        self._away_meta_stack.setCurrentWidget(self.away_timeouts)
        away_meta = QFrame()
        away_meta.setStyleSheet("background: transparent; border: none;")
        away_meta.setLayout(self._away_meta_stack)
        away_score_layout.addWidget(away_meta, alignment=Qt.AlignRight)
        left_mid.addWidget(self.away_score_card, alignment=Qt.AlignRight | Qt.AlignVCenter)

        left_layout.addLayout(left_mid)
        left_layout.addWidget(self.away_name)
        self.away_record = QLabel("--")
        self.away_record.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.away_record.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 12px; font-weight: 700;")
        left_layout.addWidget(self.away_record)

        center_frame = QFrame()
        center_frame.setFixedSize(CENTER_PANEL_WIDTH, TOP_SECTION_HEIGHT)
        center_frame.setStyleSheet("background: transparent;")
        center_layout = QVBoxLayout(center_frame)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        self.center_panel = CenterPanel()
        center_layout.addWidget(self.center_panel, alignment=Qt.AlignCenter)

        right_frame = QFrame()
        right_frame.setFixedSize(SIDE_SECTION_WIDTH, TOP_SECTION_HEIGHT)
        right_frame.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(TOP_H_MARGIN, TOP_V_MARGIN, TOP_H_MARGIN, TOP_BOTTOM_MARGIN)
        right_layout.setSpacing(2)

        self.home_city = QLabel("", right_frame)
        self.home_city.setVisible(True)
        self.home_city.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.home_city.setStyleSheet(f"font-size: {CITY_FONT_SIZE}px; font-weight: 800; letter-spacing: 0.6px;")
        self.home_name = QLabel("HOME TEAM")
        self.home_name.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.home_name.setStyleSheet("font-size: 22px; font-weight: 900; color: #f7f7f7; letter-spacing: 1px;")
        right_layout.addWidget(self.home_city)

        right_mid = QHBoxLayout()
        right_mid.setContentsMargins(0, 0, 0, 0)
        right_mid.setSpacing(12)
        self.home_score_card = ScoreCard()
        self.home_score_card.setFixedSize(SCORE_CARD_WIDTH, SCORE_CARD_HEIGHT)
        home_score_layout = QVBoxLayout(self.home_score_card)
        home_score_layout.setContentsMargins(0, 0, 0, 0)
        home_score_layout.setSpacing(4)
        self.home_score = QLabel("0")
        self.home_score.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.home_score.setStyleSheet("font-size: 58px; font-weight: 900; color: #f7f7f7;")
        home_score_layout.addWidget(self.home_score, alignment=Qt.AlignLeft)
        self.home_timeouts = TimeoutBar()
        self.home_penalties = QLabel("PIM --")
        self.home_penalties.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.home_penalties.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 12px; font-weight: 800;")
        self.home_penalty_clock = QLabel("PEN --")
        self.home_penalty_clock.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.home_penalty_clock.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 11px; font-weight: 800;")
        self._home_penalty_meta = QFrame()
        self._home_penalty_meta.setStyleSheet("background: transparent; border: none;")
        home_penalty_layout = QVBoxLayout(self._home_penalty_meta)
        home_penalty_layout.setContentsMargins(0, 0, 0, 0)
        home_penalty_layout.setSpacing(2)
        home_penalty_layout.addWidget(self.home_penalties, alignment=Qt.AlignLeft)
        home_penalty_layout.addWidget(self.home_penalty_clock, alignment=Qt.AlignLeft)
        self._home_meta_stack = QStackedLayout()
        self._home_meta_stack.setContentsMargins(0, 0, 0, 0)
        self._home_meta_stack.addWidget(self.home_timeouts)
        self._home_meta_stack.addWidget(self._home_penalty_meta)
        self._home_meta_stack.setCurrentWidget(self.home_timeouts)
        home_meta = QFrame()
        home_meta.setStyleSheet("background: transparent; border: none;")
        home_meta.setLayout(self._home_meta_stack)
        home_score_layout.addWidget(home_meta, alignment=Qt.AlignLeft)
        right_mid.addWidget(self.home_score_card, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        right_mid.addStretch(1)
        self.home_logo_box = CircularLogoGlow()
        right_mid.addStretch(1)

        right_layout.addLayout(right_mid)
        right_layout.addWidget(self.home_name)
        self.home_record = QLabel("--")
        self.home_record.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.home_record.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 12px; font-weight: 700;")
        right_layout.addWidget(self.home_record)

        left_logo_layout = QVBoxLayout(self.left_bg)
        left_logo_layout.setContentsMargins(0, CONTROL_BAR_HEIGHT, CENTER_PANEL_WIDTH // 2, 0)
        left_logo_layout.setSpacing(0)
        left_logo_layout.addStretch(1)
        left_logo_layout.addWidget(self.away_logo_box, alignment=Qt.AlignCenter)
        left_logo_layout.addStretch(1)
        right_logo_layout = QVBoxLayout(self.right_bg)
        right_logo_layout.setContentsMargins(CENTER_PANEL_WIDTH // 2, CONTROL_BAR_HEIGHT, 0, 0)
        right_logo_layout.setSpacing(0)
        right_logo_layout.addStretch(1)
        right_logo_layout.addWidget(self.home_logo_box, alignment=Qt.AlignCenter)
        right_logo_layout.addStretch(1)

        top_layout.addWidget(left_frame)
        top_layout.addWidget(center_frame)
        top_layout.addWidget(right_frame)
        control_frame.setParent(self.top_frame)
        control_frame.setGeometry(0, 2, WINDOW_WIDTH, CONTROL_BAR_HEIGHT)
        control_frame.raise_()
        self.top_bg.lower()
        layout.addWidget(self.top_frame)

        bottom_frame = QFrame()
        bottom_frame.setFixedSize(WINDOW_WIDTH, BOTTOM_SECTION_HEIGHT)
        bottom_frame.setStyleSheet("background: transparent;")
        bottom_layout = QVBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(BOTTOM_H_MARGIN, BOTTOM_V_MARGIN, BOTTOM_H_MARGIN, BOTTOM_V_MARGIN)
        bottom_layout.setSpacing(BOTTOM_SECTION_SPACING)

        self.tables_frame = QFrame()
        self.tables_frame.setFixedHeight(TABLES_HEIGHT)
        self.tables_frame.setStyleSheet("background: transparent;")
        tables_layout = QHBoxLayout(self.tables_frame)
        tables_layout.setContentsMargins(0, 0, 0, 0)
        tables_layout.setSpacing(TABLE_GAP)

        (
            self.away_table_frame,
            self.away_table,
            self.away_table_title,
        ) = self._make_table("STATS", self._table_headers)
        (
            self.home_table_frame,
            self.home_table,
            self.home_table_title,
        ) = self._make_table("STATS", self._table_headers)

        table_width = (WINDOW_WIDTH - (BOTTOM_H_MARGIN * 2) - TABLE_GAP) // 2
        self.away_table_frame.setFixedSize(table_width, TABLES_HEIGHT)
        self.home_table_frame.setFixedSize(table_width, TABLES_HEIGHT)
        tables_layout.addWidget(self.away_table_frame)
        tables_layout.addWidget(self.home_table_frame)
        bottom_layout.addWidget(self.tables_frame)

        self.pbp_bar = QFrame()
        self.pbp_bar.setFrameShape(QFrame.StyledPanel)
        self.pbp_bar.setFixedHeight(PBP_BAR_HEIGHT)
        self.pbp_bar.setStyleSheet("background-color: #0b101a; border: none;")
        pbp_layout = QHBoxLayout(self.pbp_bar)
        pbp_layout.setContentsMargins(8, 2, 8, 2)
        pbp_layout.setSpacing(8)
        self.pbp_ticker_label = TickerLabel("Play-by-play loading...")
        self.pbp_ticker_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.pbp_ticker_label.setStyleSheet(f"color: {TEXT}; font-weight: 600; font-size: 11px;")
        pbp_layout.addWidget(self.pbp_ticker_label, stretch=1)
        self.pbp_bar.setVisible(False)
        bottom_layout.addWidget(self.pbp_bar)

        self.bottom_bar = QFrame()
        self.bottom_bar.setFrameShape(QFrame.StyledPanel)
        self.bottom_bar.setFixedHeight(BOTTOM_BAR_HEIGHT)
        self.bottom_bar.setStyleSheet("background-color: #0c121d; border: none;")
        bar_layout = QHBoxLayout(self.bottom_bar)
        bar_layout.setContentsMargins(8, 2, 8, 2)
        bar_layout.setSpacing(8)

        self.bottom_left_label = QLabel("AWY (--)")
        self.bottom_left_label.setAlignment(Qt.AlignCenter)
        self.bottom_left_label.setStyleSheet(f"color: {TEXT}; font-weight: 700; font-size: 12px;")
        self.bottom_center_label = TickerLabel("BONUS")
        self.bottom_center_label.setAlignment(Qt.AlignCenter)
        self.bottom_center_label.setStyleSheet(f"color: {ACCENT}; font-weight: 800; font-size: 12px;")
        self.bottom_right_label = QLabel("HME (--)")
        self.bottom_right_label.setAlignment(Qt.AlignCenter)
        self.bottom_right_label.setStyleSheet(f"color: {TEXT}; font-weight: 700; font-size: 12px;")

        bar_layout.addWidget(self.bottom_left_label, stretch=1)
        bar_layout.addWidget(self.bottom_center_label, stretch=1)
        bar_layout.addWidget(self.bottom_right_label, stretch=1)
        bottom_layout.addWidget(self.bottom_bar)

        layout.addWidget(bottom_frame)
        self.setCentralWidget(root)
        self._set_top_background(ACCENT, ACCENT_SOFT, ACCENT_SOFT, ACCENT)
        self._apply_control_colors("#f7f7f7")

    def _make_table(self, title: str, headers: list[str]):
        frame = QFrame()
        frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: {PANEL};
                border-radius: 12px;
                border: 1px solid #1c2b3c;
            }}
            """
        )
        if self.sport_name.upper() == "NBA":
            frame.setStyleSheet(
                f"""
                QFrame {{
                    background-color: {PANEL};
                    border: none;
                    border-radius: 0px;
                }}
                """
            )
        vbox = QVBoxLayout(frame)
        vbox.setContentsMargins(6, 2, 6, 2)
        vbox.setSpacing(2)
        label = QLabel(title)
        label.setObjectName("table_title")
        label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {ACCENT};")
        label.setVisible(False)
        label.setFixedHeight(0)
        vbox.addWidget(label)

        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setShowGrid(False)
        self._apply_table_column_layout(table)
        if not hasattr(self, "_player_row_delegate"):
            self._player_row_delegate = PlayerRowDelegate(self)
        table.setItemDelegate(self._player_row_delegate)
        table.verticalHeader().setVisible(False)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        if self.sport_name.upper() == "NBA":
            self._configure_nba_table(table)
        else:
            QScroller.grabGesture(table.viewport(), QScroller.LeftMouseButtonGesture)
            QScroller.grabGesture(table.viewport(), QScroller.TouchGesture)
            self._configure_player_table(table)
        if not hasattr(self, "_nfl_scroll_views"):
            self._nfl_scroll_views = {}
        self._nfl_scroll_views[table.viewport()] = table
        table.viewport().installEventFilter(self)
        table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {PANEL};
                gridline-color: #2b3e55;
                color: {TEXT};
                alternate-background-color: #0d1523;
            }}
            QHeaderView::section {{
                background-color: #1c2a3e;
                color: {TEXT};
                font-weight: bold;
                border: 0px;
                padding: 4px;
            }}
            QTableWidget::item {{
                padding: 2px 4px 2px 10px;
            }}
            """
        )
        vbox.addWidget(table)
        return frame, table, label

    def _apply_table_column_layout(self, table: QTableWidget) -> None:
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Fixed)
        count = table.columnCount()
        if count == 0:
            return
        if self.sport_name.upper() == "NBA":
            table.setColumnWidth(0, 42)
            if count > 1:
                table.setColumnWidth(1, NBA_PLAYER_COL_WIDTH)
            for idx in range(2, count):
                header_item = table.horizontalHeaderItem(idx)
                label = header_item.text().upper() if header_item else ""
                if label == "POS":
                    width = NBA_POS_COL_WIDTH
                elif label in ("MIN", "TIME"):
                    width = NBA_MIN_COL_WIDTH
                elif label in ("3PT", "3P", "3PM"):
                    width = NBA_THREE_COL_WIDTH
                else:
                    width = NBA_STAT_COL_WIDTH
                table.setColumnWidth(idx, width)
            return
        # Keep stat columns compact so the player name column gets more room.
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

    def update_table_headers(self, headers: list[str] | None = None) -> None:
        resolved = self._resolve_headers(headers)
        self._update_mlb_diamond_visibility()
        if getattr(self, "_table_headers", None) == resolved:
            return
        self._table_headers = resolved
        for table in (getattr(self, "away_table", None), getattr(self, "home_table", None)):
            if table is None:
                continue
            table.setColumnCount(len(resolved))
            table.setHorizontalHeaderLabels(resolved)
            self._apply_table_column_layout(table)
            self._configure_player_table(table)
            if self.sport_name.upper() == "NBA":
                self._configure_nba_table(table)
            table.setRowCount(0)

    def _update_mlb_diamond_visibility(self) -> None:
        """Show the bases diamond in the center panel for MLB; clock for all other sports."""
        is_mlb = self.sport_name.upper() == "MLB"
        self.center_panel.show_diamond(is_mlb)

    def update_league_logo(self, logo_path: str | None) -> None:
        self._sport_logo_path = logo_path
        if not hasattr(self, "league_logo"):
            return
        fallback_path = None
        if not logo_path:
            fallback_path = (self._sport_icon_map or {}).get(self.sport_name)
        use_path = logo_path or fallback_path
        if use_path and Path(use_path).exists():
            pix = QPixmap(use_path).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.league_logo.clear()
            self.league_logo.setVisible(False)
            self.center_panel.set_league_logo(pix)
        else:
            self.league_logo.clear()
            self.league_logo.setVisible(False)
            self.center_panel.set_league_logo(None)

    def _configure_nba_table(self, table: QTableWidget) -> None:
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerItem)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setFocusPolicy(Qt.ClickFocus)
        table.setShowGrid(False)
        table.horizontalScrollBar().setSingleStep(60)
        table.viewport().setCursor(Qt.ArrowCursor)
        if table not in self._nba_scroll_tables:
            table.installEventFilter(self)
            self._nba_scroll_tables.add(table)
        self._configure_player_table(table)

    def _configure_player_table(self, table: QTableWidget) -> None:
        if table in self._player_click_tables:
            return
        table.cellClicked.connect(lambda row, col, t=table: self._on_player_cell_clicked(t, row, col))
        self._player_click_tables.add(table)

    def _on_player_cell_clicked(self, table: QTableWidget, row: int, col: int) -> None:
        if col != 1:
            return
        name_item = table.item(row, 1)
        if name_item is None:
            return
        player_name = str(name_item.text() or "").strip()
        if player_name.lower() in {"", "no stats available", "lineups tbd"}:
            return

        context = name_item.data(PLAYER_CONTEXT_ROLE)
        if not isinstance(context, dict):
            context = self._fallback_player_context(table, row, player_name)
        if not context:
            return
        context["playerName"] = context.get("playerName") or player_name
        context["rowStats"] = context.get("rowStats") or self._table_row_stats(table, row)
        self._open_player_card(context, table=table, row=row)

    def _fallback_player_context(self, table: QTableWidget, row: int, player_name: str) -> Dict[str, Any]:
        side = "away" if table is getattr(self, "away_table", None) else "home"
        box = self._last_boxscore_data or {}
        team = box.get(side) if isinstance(box, dict) else {}
        if not isinstance(team, dict):
            team = {}
        row_stats = self._table_row_stats(table, row)
        jersey = str(table.item(row, 0).text() if table.item(row, 0) else "")
        pos = str(row_stats.get("Pos") or row_stats.get("Position") or "")
        matched = self._match_team_player_for_row(team, [jersey, player_name, pos], set())
        team_tri = str(team.get("teamTricode") or team.get("tricode") or "").upper()
        team_color = self._team_color(team_tri)
        context = {
            "sport": self.sport_name.upper(),
            "teamId": str(team.get("teamId") or team.get("id") or ""),
            "teamTricode": team_tri,
            "teamName": team.get("teamName") or team.get("displayName") or "",
            "teamColor": team_color,
            "playerName": player_name,
            "jersey": jersey,
            "position": pos,
            "rowStats": row_stats,
        }
        if isinstance(matched, dict):
            context["playerId"] = self._player_id_from_entry(matched)
            context["playerData"] = dict(matched)
            context["playerName"] = self._player_full_name(matched) or context["playerName"]
            context["jersey"] = context["jersey"] or self._player_jersey(matched)
            context["position"] = context["position"] or self._player_position(matched)
        return context

    def _table_row_stats(self, table: QTableWidget, row: int) -> Dict[str, str]:
        stats: Dict[str, str] = {}
        for col in range(table.columnCount()):
            header_item = table.horizontalHeaderItem(col)
            key = str(header_item.text() if header_item else f"Stat {col + 1}").strip()
            if not key:
                continue
            cell = table.item(row, col)
            val = str(cell.text() if cell else "").strip()
            if col != 1 and not val:
                continue
            stats[key] = val
        return stats

    def _open_player_card(
        self,
        context: Dict[str, Any],
        *,
        table: QTableWidget | None = None,
        row: int | None = None,
    ) -> None:
        if self._active_player_card is not None:
            try:
                self._active_player_card.close()
            except Exception:
                pass
        dialog = PlayerCardDialog(context, self)
        self._active_player_card = dialog
        self._position_player_card(dialog, table=table, row=row)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._fetch_player_profile_async(dialog, context)

    def _position_player_card(
        self,
        dialog: PlayerCardDialog,
        *,
        table: QTableWidget | None = None,
        row: int | None = None,
    ) -> None:
        max_width = max(300, self.width() - 12)
        max_height = max(220, self.height() - 12)
        width = min(dialog.width(), max_width)
        height = min(dialog.height(), max_height)
        dialog.resize(width, height)

        anchor = None
        if table is not None and isinstance(row, int) and row >= 0:
            item = table.item(row, 1)
            if item is not None:
                item_rect = table.visualItemRect(item)
                if item_rect.isValid():
                    anchor = table.viewport().mapToGlobal(item_rect.center())
        if anchor is None:
            anchor = self.mapToGlobal(self.rect().center())

        parent_top_left = self.mapToGlobal(QPoint(0, 0))
        bounds = QRect(parent_top_left, self.size())
        margin = 6
        x = int(anchor.x() - (width / 2))
        y = int(anchor.y() - (height / 2))
        min_x = bounds.left() + margin
        max_x = bounds.right() - width - margin + 1
        min_y = bounds.top() + margin
        max_y = bounds.bottom() - height - margin + 1
        if max_x < min_x:
            max_x = min_x
        if max_y < min_y:
            max_y = min_y
        x = max(min_x, min(x, max_x))
        y = max(min_y, min(y, max_y))
        dialog.move(x, y)

    def _fetch_player_profile_async(self, dialog: PlayerCardDialog, context: Dict[str, Any]) -> None:
        if not self.logic or not hasattr(self.logic, "fetch_player_profile"):
            dialog.apply_profile({})
            return
        team_id = str(context.get("teamId") or "").strip()
        team_tricode = str(context.get("teamTricode") or "").strip().upper()
        player_id = str(context.get("playerId") or "").strip()
        if not team_id and not player_id and not team_tricode:
            dialog.apply_profile({})
            return
        try:
            future = self._executor.submit(self._fetch_player_card_payload, dict(context))
        except Exception:
            dialog.apply_profile({})
            return
        future.add_done_callback(
            lambda fut, d=dialog, ctx=dict(context): self._on_player_profile_ready(fut, d, ctx)
        )

    def _fetch_player_card_payload(self, context: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"context": dict(context), "profile": {}, "headshotBytes": None, "teamLogoBytes": None}
        if not self.logic:
            return payload
        sport = str(context.get("sport") or self.sport_name).upper()
        team_id = str(context.get("teamId") or "").strip()
        team_tricode = str(context.get("teamTricode") or "").strip().upper()
        player_id = str(context.get("playerId") or "").strip()
        player_name = str(context.get("playerName") or "").strip()
        player_jersey = str(context.get("jersey") or "").strip()
        profile: Dict[str, Any] = {}
        if hasattr(self.logic, "fetch_player_profile"):
            try:
                raw_profile = self.logic.fetch_player_profile(
                    sport,
                    team_id,
                    player_id=player_id,
                    player_name=player_name,
                    player_jersey=player_jersey,
                    team_tricode=team_tricode,
                )
                if isinstance(raw_profile, dict):
                    profile = dict(raw_profile)
            except Exception:
                profile = {}

        headshot_bytes: bytes | None = None
        headshot_url = str(profile.get("headshotUrl") or "").strip()
        if headshot_url and hasattr(self.logic, "fetch_remote_bytes"):
            try:
                raw_bytes = self.logic.fetch_remote_bytes(headshot_url)
                if isinstance(raw_bytes, (bytes, bytearray)):
                    headshot_bytes = bytes(raw_bytes)
            except Exception:
                headshot_bytes = None

        team_logo_bytes: bytes | None = None
        if hasattr(self.logic, "load_logo") and team_tricode:
            try:
                raw_logo = self.logic.load_logo(sport, team_id, team_tricode)
                if isinstance(raw_logo, (bytes, bytearray)):
                    team_logo_bytes = bytes(raw_logo)
            except Exception:
                team_logo_bytes = None
        if team_logo_bytes is None and team_tricode and hasattr(self.logic, "fetch_remote_bytes"):
            fallback_logo_url = self._player_card_team_logo_url(sport, team_id, team_tricode)
            if fallback_logo_url:
                try:
                    raw_logo = self.logic.fetch_remote_bytes(fallback_logo_url)
                    if isinstance(raw_logo, (bytes, bytearray)):
                        team_logo_bytes = bytes(raw_logo)
                except Exception:
                    team_logo_bytes = None

        payload["profile"] = profile
        payload["headshotBytes"] = headshot_bytes
        payload["teamLogoBytes"] = team_logo_bytes
        return payload

    def _player_card_team_logo_url(self, sport: str, team_id: str, team_tricode: str) -> str:
        sp = str(sport or "").strip().upper()
        tid = str(team_id or "").strip()
        tri = str(team_tricode or "").strip().upper()
        if not tri and not tid:
            return ""
        if sp == "NBA":
            code = {
                "GSW": "gs",
                "NOP": "no",
                "NYK": "ny",
                "SAS": "sa",
                "WAS": "wsh",
                "UTA": "uta",
            }.get(tri, tri.lower())
            return f"https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/{code}.png"
        if sp == "NFL" and tri:
            return f"https://a.espncdn.com/i/teamlogos/nfl/500/{tri.lower()}.png"
        if sp == "NHL" and tri:
            code = {
                "LAK": "la",
                "NJD": "nj",
                "SJS": "sj",
                "TBL": "tb",
                "UTAH": "utah",
            }.get(tri, tri.lower())
            return f"https://a.espncdn.com/i/teamlogos/nhl/500/{code}.png"
        if sp == "MLB" and tri:
            return f"https://a.espncdn.com/i/teamlogos/mlb/500/{tri.lower()}.png"
        if sp == "MLS" and tid and tid not in {"0", "AWY", "HOM"}:
            return f"https://a.espncdn.com/i/teamlogos/soccer/500/{tid}.png"
        if sp == "NCAA BASKETBALL" and tid and tid not in {"0", "AWY", "HOM"}:
            return f"https://a.espncdn.com/i/teamlogos/ncaa/500/{tid}.png"
        if sp == "NCAA FOOTBALL" and tid and tid not in {"0", "AWY", "HOM"}:
            return f"https://a.espncdn.com/i/teamlogos/ncaa/500/{tid}.png"
        return ""

    def _on_player_profile_ready(self, future, dialog: PlayerCardDialog, context: Dict[str, Any]) -> None:
        if not self._alive:
            return
        try:
            payload = future.result()
        except Exception:
            payload = {"context": dict(context), "profile": {}, "headshotBytes": None, "teamLogoBytes": None}
        if not isinstance(payload, dict):
            payload = {"context": dict(context), "profile": {}, "headshotBytes": None, "teamLogoBytes": None}
        payload.setdefault("context", dict(context))
        self.player_profile_ready.emit(dialog, payload)

    def _apply_player_profile_ready(self, dialog_obj: object, payload_obj: object) -> None:
        if not self._alive:
            return
        if not isinstance(dialog_obj, PlayerCardDialog):
            return
        if not dialog_obj.isVisible():
            return
        payload = payload_obj if isinstance(payload_obj, dict) else {}
        profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
        dialog_obj.apply_profile(profile)
        raw_headshot = payload.get("headshotBytes")
        pixmap = None
        if isinstance(raw_headshot, (bytes, bytearray)):
            pm = QPixmap()
            if pm.loadFromData(bytes(raw_headshot)):
                pixmap = pm
        dialog_obj.set_headshot(pixmap)
        raw_team_logo = payload.get("teamLogoBytes")
        logo_pixmap = None
        if isinstance(raw_team_logo, (bytes, bytearray)):
            pm = QPixmap()
            if pm.loadFromData(bytes(raw_team_logo)):
                logo_pixmap = pm
        dialog_obj.set_team_logo(logo_pixmap)

    # --------------- timers ---------------
    def _setup_timers(self):
        self.scores_timer = QTimer(self)
        self.scores_timer.timeout.connect(self.refresh_scores)
        self._update_scores_poll_timer(restart=True)

        self.boxscore_timer = QTimer(self)
        self.boxscore_timer.timeout.connect(self.refresh_boxscore)
        self._update_boxscore_poll_timer(restart=True)

        self.clock_tick_timer = QTimer(self)
        self.clock_tick_timer.timeout.connect(self._tick_clock)
        self.clock_tick_timer.start(500)
        self.clock_feed_stale_sec = 30.0  # allow a longer live-delay window for smoother seconds
        self.clock_feed_interval_avg = None
        self._nfl_possession_tricode = None
        self.ticker_timer = QTimer(self)
        self.ticker_timer.setTimerType(Qt.PreciseTimer)
        self.ticker_timer.timeout.connect(self._tick_ticker)
        self.ticker_timer.start(16)
        self._ticker_last_ts = time.monotonic()
        self.pbp_timer = QTimer(self)
        self.pbp_timer.timeout.connect(self.refresh_pbp)
        self.pbp_timer.start(7_000)
        self.rss_timer = QTimer(self)
        self.rss_timer.timeout.connect(self._rotate_rss_headline)

    # --------------- settings ---------------
    def _on_timezone_selected(self, action: QAction):
        tz = action.data()
        if tz:
            self._set_timezone(str(tz))

    def _set_timezone(self, tz: str, persist: bool = True):
        self.display_tz = tz
        os.environ["SCORESOURCE_TZ"] = tz
        self._sync_timezone_actions()
        self.refresh_scores()
        self.refresh_boxscore()
        if persist:
            try:
                if self._cached_state is not None:
                    self._cached_state["timezone"] = tz
                    self._schedule_state_save()
            except Exception:
                pass

    def _sync_timezone_actions(self):
        for act in getattr(self, "timezone_actions", []):
            act.setChecked(str(act.data()) == self.display_tz)

    def _sync_delay_actions(self):
        current_sec = int(self.feed_delay_ms / 1000) if hasattr(self, "feed_delay_ms") else 0
        for act in getattr(self, "delay_actions", []):
            try:
                act.setChecked(int(act.data() or 0) == current_sec)
            except Exception:
                act.setChecked(False)

    def _selected_game_live(self) -> bool:
        game_id = str(self.selected_game_id or self._pending_selection_id or "")
        if not game_id:
            return False
        for game in self.games:
            if str(game.get("gameId") or "") != game_id:
                continue
            status = str(game.get("status") or "").lower().strip()
            if status in {"live", "inprogress", "in progress", "ongoing"}:
                return True
            if status in {"upcoming", "scheduled", "pre", "final", "post"}:
                return False
            status_val = game.get("gameStatus") or game.get("status")
            if isinstance(status_val, int):
                return status_val == 2
            status_text = str(game.get("gameStatusText") or game.get("statusText") or "").lower()
            if any(token in status_text for token in ("final", "scheduled", "pregame", "pre-game", "tba", "starts")):
                return False
            return bool(re.search(r"\bq[1-4]\b|\bot\b|\blive\b", status_text))
        return False

    def _scores_poll_interval_ms(self) -> int:
        if any(self._normalize_status(g.get("status") or g.get("gameStatus"), g.get("gameStatusText")) == "live" for g in self.games):
            return self.scores_poll_live_ms
        if any(
            self._normalize_status(g.get("status") or g.get("gameStatus"), g.get("gameStatusText")) == "upcoming"
            for g in self.games
        ):
            return self.scores_poll_upcoming_ms
        return self.scores_poll_idle_ms

    def _update_scores_poll_timer(self, *, restart: bool = False) -> None:
        timer = getattr(self, "scores_timer", None)
        if timer is None:
            return
        interval_ms = self._scores_poll_interval_ms()
        if timer.interval() != interval_ms:
            timer.setInterval(interval_ms)
            restart = True
        if restart or not timer.isActive():
            timer.start(interval_ms)

    def _boxscore_poll_interval_ms(self) -> int:
        sport = self.sport_name.upper()
        if sport != "NBA":
            return self.boxscore_poll_default_ms
        if self.feed_delay_ms <= 0 and self._selected_game_live():
            # In live mode realtime already streams clocks/scores, so poll boxscore less frequently.
            return self.boxscore_poll_live_ms
        return self.boxscore_poll_default_ms

    def _update_boxscore_poll_timer(self, *, restart: bool = False) -> None:
        timer = getattr(self, "boxscore_timer", None)
        if timer is None:
            return
        interval_ms = self._boxscore_poll_interval_ms()
        if timer.interval() != interval_ms:
            timer.setInterval(interval_ms)
            restart = True
        if restart or not timer.isActive():
            timer.start(interval_ms)

    def _apply_default_delay_for_sport(self) -> None:
        if not getattr(self, "_delay_is_default", False):
            return
        desired_sec = 0
        desired_ms = desired_sec * 1000
        if self.feed_delay_ms != desired_ms:
            self.feed_delay_ms = desired_ms
            self._sync_delay_actions()
            self._clock_state = None
            self._update_boxscore_poll_timer(restart=True)

    def _sync_ticker_speed_actions(self):
        current_speed = float(getattr(self, "ticker_speed_px", TICKER_SPEED_PX))
        for act in getattr(self, "ticker_speed_actions", []):
            try:
                act.setChecked(abs(float(act.data() or 0) - current_speed) < 0.25)
            except Exception:
                act.setChecked(False)

    def _tick_ticker(self):
        now = time.monotonic()
        delta = now - getattr(self, "_ticker_last_ts", now)
        self._ticker_last_ts = now
        for label in (
            getattr(self, "bottom_center_label", None),
            getattr(self, "pbp_ticker_label", None),
        ):
            if isinstance(label, TickerLabel) and label.is_ticker_enabled():
                label.advance(delta)

    def _on_ticker_speed_selected(self, action: QAction):
        try:
            speed = float(action.data())
        except Exception:
            return
        self.ticker_speed_px = max(4.0, min(60.0, speed))
        os.environ["SCORESOURCE_TICKER_SPEED_PX"] = str(self.ticker_speed_px)
        self._sync_ticker_speed_actions()
        label = getattr(self, "bottom_center_label", None)
        if isinstance(label, TickerLabel) and label.is_ticker_enabled():
            label.set_ticker_speed(self.ticker_speed_px)
            label.update()
            self._ticker_last_ts = time.monotonic()
        pbp_label = getattr(self, "pbp_ticker_label", None)
        if isinstance(pbp_label, TickerLabel) and pbp_label.is_ticker_enabled():
            pbp_label.set_ticker_speed(self._pbp_speed_px())
            pbp_label.update()
            self._ticker_last_ts = time.monotonic()
        self._refresh_nba_merged_ticker(force=True)
        if self.sport_name.upper() != "NBA" and isinstance(pbp_label, TickerLabel) and pbp_label.is_ticker_enabled():
            pbp_label.stop_ticker()
        if self._cached_state is not None:
            try:
                settings = self._cached_state.get("settings") or {}
                settings["ticker_speed_px"] = self.ticker_speed_px
                self._cached_state["settings"] = settings
                self._schedule_state_save()
            except Exception:
                pass

    def _on_delay_selected(self, action: QAction):
        try:
            delay_sec = int(action.data())
        except Exception:
            return
        prev_delay = self.feed_delay_ms
        self.feed_delay_ms = max(0, delay_sec * 1000)
        self._delay_is_default = False
        os.environ["SCORESOURCE_FEED_DELAY_SEC"] = str(delay_sec)
        self._sync_delay_actions()
        self._clock_state = None
        if prev_delay <= 0 and self.feed_delay_ms > 0:
            try:
                if self.logic:
                    self.logic.stop_realtime()
            except Exception:
                pass
        if prev_delay > 0 and self.feed_delay_ms <= 0 and self.selected_game_id:
            self._start_realtime_for_game(self.selected_game_id)
        self._update_boxscore_poll_timer(restart=True)
        self._next_display_at = None
        self.refresh_scores()
        self.refresh_boxscore()
        self._apply_delay_snapshot()
        try:
            if self._cached_state is not None:
                settings = self._cached_state.get("settings") or {}
                settings["feed_delay_sec"] = delay_sec
                self._cached_state["settings"] = settings
                self._schedule_state_save()
        except Exception:
            pass

    # --------------- data refresh ---------------
    def _cache_runtime_scores(
        self,
        sport_name: str,
        games: List[Dict[str, Any]],
        lines: List[str] | None = None,
        *,
        selected_game_id: str | None = None,
    ) -> None:
        if not sport_name:
            return
        self._runtime_scores_cache[sport_name] = {
            "games": games or [],
            "lines": lines or [],
            "selected_game_id": selected_game_id if selected_game_id is not None else self.selected_game_id,
            "ts": time.monotonic(),
        }

    def _runtime_scores_snapshot(self, sport_name: str) -> Dict[str, Any] | None:
        snapshot = self._runtime_scores_cache.get(sport_name)
        if not isinstance(snapshot, dict):
            return None
        games = snapshot.get("games") or []
        if not isinstance(games, list) or not games:
            return None
        selected_game_id = snapshot.get("selected_game_id")
        if selected_game_id:
            self._pending_selection_id = str(selected_game_id)
        return {
            "games": games,
            "lines": snapshot.get("lines") or [],
            "_sport_name": sport_name,
            "_sport_token": self._sport_token,
        }

    def _cache_runtime_boxscore(self, sport_name: str, game_id: str | None, data: Dict[str, Any] | None) -> None:
        if not sport_name or not game_id or not isinstance(data, dict):
            return
        key = (sport_name, str(game_id))
        payload = dict(data)
        payload.pop("_sport_name", None)
        payload.pop("_sport_token", None)
        self._runtime_boxscore_cache[key] = payload
        if len(self._runtime_boxscore_cache) > 320:
            for stale_key in list(self._runtime_boxscore_cache.keys())[:80]:
                if stale_key != key:
                    self._runtime_boxscore_cache.pop(stale_key, None)

    def _runtime_boxscore(self, sport_name: str, game_id: str | None) -> Dict[str, Any] | None:
        if not sport_name or not game_id:
            return None
        cached = self._runtime_boxscore_cache.get((sport_name, str(game_id)))
        return cached if isinstance(cached, dict) else None

    def _prioritized_prefetch_game_ids(self, games: List[Dict[str, Any]]) -> List[str]:
        current_game_id = str(self.selected_game_id or "")
        current_idx = -1
        for idx, game in enumerate(games):
            if str(game.get("gameId") or "") == current_game_id:
                current_idx = idx
                break

        ranked: list[tuple[tuple[int, int, int], str]] = []
        for idx, game in enumerate(games):
            game_id = str(game.get("gameId") or "")
            if not game_id or game_id == current_game_id:
                continue
            status_raw = game.get("status")
            if status_raw is None:
                status_raw = game.get("gameStatus")
            status_text = game.get("gameStatusText") or game.get("statusText") or game.get("header")
            normalized = self._normalize_status(status_raw, status_text)
            is_live = normalized in {"live", "in", "inprogress", "in progress", "ongoing"}
            distance = abs(idx - current_idx) if current_idx >= 0 else idx
            ranked.append(((0 if is_live else 1, distance, idx), game_id))
        ranked.sort(key=lambda item: item[0])
        return [game_id for _, game_id in ranked]

    def _prefetch_boxscores_for_games(self, games: List[Dict[str, Any]]) -> None:
        limit = int(getattr(self, "_prefetch_game_limit", 0) or 0)
        if limit <= 0:
            return
        sport_name = self.sport_name
        queued = 0
        for game_id in self._prioritized_prefetch_game_ids(games):
            if queued >= limit:
                break
            key = (sport_name, game_id)
            if key in self._runtime_boxscore_cache or key in self._boxscore_prefetch_inflight:
                continue
            try:
                if self.logic is not None:
                    future = self._executor.submit(self.logic.get_boxscore, game_id)
                else:
                    future = self._executor.submit(self.backend.fetch_boxscore, game_id)
            except Exception:
                continue
            self._boxscore_prefetch_inflight.add(key)
            future.add_done_callback(
                lambda fut, k=key, gid=game_id, s=sport_name: self._on_prefetch_boxscore_ready(fut, k, gid, s)
            )
            queued += 1

    def _on_prefetch_boxscore_ready(self, future, key: tuple[str, str], game_id: str, sport_name: str) -> None:
        self._boxscore_prefetch_inflight.discard(key)
        if not self._alive:
            return
        try:
            data = future.result()
        except Exception:
            return
        if not isinstance(data, dict):
            return
        self._cache_runtime_boxscore(sport_name, game_id, data)
        if sport_name != self.sport_name:
            return
        tagged = dict(data)
        tagged["_sport_name"] = sport_name
        tagged["_sport_token"] = self._sport_token
        self._append_boxscore_history(game_id, tagged)

    def _prefetch_other_sports_scoreboards(self) -> None:
        if self.logic is None:
            return
        now = time.monotonic()
        if now - self._last_cross_sport_prefetch_ts < self._cross_sport_prefetch_interval_sec:
            return
        self._last_cross_sport_prefetch_ts = now
        queued = 0
        for sport_name in self._sport_options:
            if sport_name == self.sport_name:
                continue
            if sport_name in self._score_prefetch_inflight:
                continue
            cached = self._runtime_scores_cache.get(sport_name) or {}
            cached_ts = cached.get("ts")
            if isinstance(cached_ts, (int, float)) and now - cached_ts < 30.0:
                continue
            try:
                future = self._executor.submit(self.logic.fetch_scores, sport_name)
            except Exception:
                continue
            self._score_prefetch_inflight.add(sport_name)
            future.add_done_callback(lambda fut, s=sport_name: self._on_prefetch_scores_ready(fut, s))
            queued += 1
            if queued >= self._cross_sport_prefetch_batch:
                break

    def _on_prefetch_scores_ready(self, future, sport_name: str) -> None:
        self._score_prefetch_inflight.discard(sport_name)
        if not self._alive:
            return
        try:
            data = future.result()
        except Exception:
            return
        if not isinstance(data, dict):
            return
        games = data.get("games") or []
        if not isinstance(games, list):
            return
        selected = None
        cached = self._runtime_scores_cache.get(sport_name)
        if isinstance(cached, dict):
            selected = cached.get("selected_game_id")
        self._cache_runtime_scores(sport_name, games, data.get("lines") or [], selected_game_id=selected)

    def refresh_scores(self):
        self.update_table_headers(getattr(self.backend, "sport_table_headers", None))
        self._apply_default_delay_for_sport()
        if self.sport_name != self._sport_token_name:
            previous_sport = self._sport_token_name
            self._cache_runtime_scores(previous_sport, self.games, self.lines, selected_game_id=self.selected_game_id)
            if self.selected_game_id and isinstance(self._last_boxscore_data, dict):
                self._cache_runtime_boxscore(previous_sport, str(self.selected_game_id), self._last_boxscore_data)
            self._sport_token += 1
            self._sport_token_name = self.sport_name
            self._has_displayed_scores = False
            self._has_displayed_boxscore = False
            self._next_display_at = None
            self._score_history.clear()
            self._boxscore_history.clear()
            self._pbp_history.clear()
            self._pbp_lines = []
            self._last_pbp_key = None
            self._displayed_boxscore_key = None
            self._clock_state = None
            self.clock_feed_interval_avg = None
            self._last_cross_sport_prefetch_ts = 0.0
        if not self._has_displayed_scores:
            runtime_scores = self._runtime_scores_snapshot(self.sport_name)
            if runtime_scores:
                self._emit_scores_if_current(runtime_scores)
        if self._scores_future and not self._scores_future.done() and self._scores_future_sport == self.sport_name:
            return
        sport_name = self.sport_name
        sport_token = self._sport_token
        if self.logic is not None:
            self._scores_future = self._executor.submit(self.logic.get_scoreboard)
        else:
            self._scores_future = self._executor.submit(self.backend.fetch_scoreboard)
        self._scores_future_sport = self.sport_name
        self._scores_future.add_done_callback(lambda fut, s=sport_name, t=sport_token: self._on_scores_ready(fut, s, t))

    def _on_scores_ready(self, future, sport_name: str, sport_token: int):
        if not self._alive:
            return
        try:
            data = future.result()
        except Exception:
            return
        data["_sport_name"] = sport_name
        data["_sport_token"] = sport_token
        self._cache_runtime_scores(sport_name, data.get("games") or [], data.get("lines") or [])
        self._append_score_history(data)
        self.scores_fetched.emit(data)

    def _schedule_scores_emit(self, data: Dict[str, Any]):
        if data.get("_sport_name") != self.sport_name or data.get("_sport_token") != self._sport_token:
            return
        now = time.monotonic()
        # anchor both score and boxscore display to the same target
        delay_ms = self._delay_ms_for_scores(data)
        self._next_display_at = now + (delay_ms / 1000.0)
        target_id, _ = self._preferred_game_id(data.get("games", []) or [])
        self._pending_selection_id = target_id
        if target_id:
            self._start_boxscore_prefetch(target_id)
        delayed = self._select_delayed_scores(data)
        QTimer.singleShot(self._remaining_delay_ms(), lambda d=delayed: self._emit_scores_if_current(d))

    def _emit_scores_if_current(self, data: Dict[str, Any]):
        if not self._alive:
            return
        if data.get("_sport_name") != self.sport_name or data.get("_sport_token") != self._sport_token:
            return
        self.scores_ready.emit(data)

    def _preferred_game_id(self, games: List[Dict[str, Any]]) -> tuple[str | None, int]:
        if not games:
            return None, 0
        for gid in (self.selected_game_id, self._pending_selection_id):
            if gid:
                for i, g in enumerate(games):
                    if g.get("gameId") == gid:
                        return gid, i
        if self.sport_name.upper() == "NHL":
            # Prefer a live game when no prior selection exists.
            for i, g in enumerate(games):
                status_raw = g.get("status")
                if status_raw is None:
                    status_raw = g.get("gameStatus")
                status_text = g.get("gameStatusText") or g.get("statusText") or g.get("header")
                normalized = self._normalize_status(status_raw, status_text)
                if normalized in ("live", "in", "inprogress", "in progress", "ongoing"):
                    return g.get("gameId"), i
        return games[0].get("gameId"), 0

    def _group_games_for_combo(self, games: List[Dict[str, Any]]) -> list[tuple[str | None, List[Dict[str, Any]]]]:
        sport = self.sport_name.upper()
        if sport == "NCAA FOOTBALL":
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for g in games:
                label = g.get("division") or "Other"
                grouped.setdefault(str(label), []).append(g)
            if not grouped:
                return [(None, games)]
            ordered: list[tuple[str | None, List[Dict[str, Any]]]] = []
            for label in ("FBS", "FCS", "Other"):
                if label in grouped:
                    ordered.append((label, grouped.pop(label)))
            for label in sorted(grouped):
                ordered.append((label, grouped[label]))
            return ordered
        if sport == "NCAA BASKETBALL":
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for g in games:
                label = (
                    g.get("eventBucket")
                    or g.get("groupShortName")
                    or g.get("groupName")
                    or ("March Madness" if g.get("isMarchMadness") else "NCAA Basketball")
                )
                grouped.setdefault(str(label), []).append(g)
            if len(grouped) <= 1:
                return [(None, games)]
            ordered: list[tuple[str | None, List[Dict[str, Any]]]] = []
            if "March Madness" in grouped:
                ordered.append(("March Madness", grouped.pop("March Madness")))
            for label in sorted(grouped):
                ordered.append((label, grouped[label]))
            return ordered
        return [(None, games)]

    def _add_combo_header(self, label: str) -> None:
        if not label:
            return
        row = self.game_combo.count()
        self.game_combo.addItem(label)
        model = self.game_combo.model()
        if hasattr(model, "item"):
            item = model.item(row)
            if item:
                item.setEnabled(False)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setForeground(QColor(TEXT_MUTED))

    def _start_boxscore_prefetch(self, game_id: str):
        if self._boxscore_future and not self._boxscore_future.done():
            return
        sport_name = self.sport_name
        sport_token = self._sport_token
        if self.logic is not None:
            self._boxscore_future = self._executor.submit(self.logic.get_boxscore, game_id)
        else:
            self._boxscore_future = self._executor.submit(self.backend.fetch_boxscore, game_id)
        self._boxscore_future.add_done_callback(
            lambda fut, gid=game_id, s=sport_name, t=sport_token: self._on_boxscore_ready(gid, fut, s, t)
        )

    def _start_realtime_for_game(self, game_id: str):
        if not self.logic:
            return
        if self.feed_delay_ms > 0:
            try:
                self.logic.stop_realtime()
            except Exception:
                pass
            self._update_boxscore_poll_timer()
            return
        if not self._selected_game_live():
            try:
                self.logic.stop_realtime()
            except Exception:
                pass
            self._update_boxscore_poll_timer()
            return
        try:
            self.logic.start_realtime(game_id, self._on_realtime_update)
        except Exception:
            pass
        self._update_boxscore_poll_timer()

    def _apply_scores(self, data: Dict[str, Any]):
        self.games = data.get("games", []) or []
        self.lines = []
        self._has_displayed_scores = True
        self._update_scores_poll_timer(restart=True)

        self.game_combo.blockSignals(True)
        self.game_combo.clear()
        self.game_combo.addItem("Select game")
        self._combo_game_row_by_id = {}
        for group_label, group_games in self._group_games_for_combo(self.games):
            if group_label:
                self._add_combo_header(group_label)
            for g in group_games:
                away_team = g.get("awayTeam") or {}
                home_team = g.get("homeTeam") or {}
                away_name = away_team.get("teamName", "Away")
                home_name = home_team.get("teamName", "Home")
                away_score = int(away_team.get("score") or 0)
                home_score = int(home_team.get("score") or 0)
                status_text = g.get("gameStatusText", "Scheduled")
                if self.sport_name.upper() == "MLB":
                    status_text = self._mlb_arrow_status_text(status_text)
                status_state = (g.get("status") or "").lower()
                if status_state not in ("live", "upcoming", "final"):
                    lowered = str(status_text or "").lower()
                    if any(key in lowered for key in ("final", "end", "ended")):
                        status_state = "final"
                    elif any(key in lowered for key in ("am", "pm", "scheduled", "tba", "starts")):
                        status_state = "upcoming"
                    else:
                        status_state = "live" if lowered else "upcoming"
                start_time = g.get("startTime") or g.get("gameTimeUTC") or g.get("gameTime")
                start_time_local = g.get("startTimeLocal")
                if start_time:
                    formatted_start = iso_to_local(start_time)
                    if formatted_start != "--:--":
                        start_time_local = formatted_start
                        if status_state == "upcoming":
                            status_text = formatted_start
                away_tricode = (away_team.get("teamTricode") or away_team.get("tricode") or "").upper()
                home_tricode = (home_team.get("teamTricode") or home_team.get("tricode") or "").upper()
                line_text = f"{away_name} {away_score} @ {home_name} {home_score}"
                self.lines.append(f"{line_text} ({status_text})")
                row = self.game_combo.count()
                self.game_combo.addItem(
                    line_text,
                    {
                        "gameId": g.get("gameId"),
                        "away_name": away_name,
                        "home_name": home_name,
                        "away_score": away_score,
                        "home_score": home_score,
                        "status_text": status_text,
                        "status_state": status_state,
                        "startTime": start_time,
                        "startTimeLocal": start_time_local,
                        "away_tricode": away_tricode,
                        "home_tricode": home_tricode,
                    },
                )
                game_id = str(g.get("gameId") or "")
                if game_id:
                    self._combo_game_row_by_id[game_id] = row
                away_logo_key = self._team_logo_key(away_team)
                if away_logo_key:
                    self.game_combo.setItemData(row, away_logo_key, GAME_LOGO_AWAY_KEY_ROLE)
                    away_pix = self._combo_logo_cache.get(away_logo_key)
                    if away_pix:
                        self.game_combo.setItemData(row, away_pix, GAME_LOGO_AWAY_ROLE)
                    else:
                        self._queue_combo_logo(away_logo_key)
                home_logo_key = self._team_logo_key(home_team)
                if home_logo_key:
                    self.game_combo.setItemData(row, home_logo_key, GAME_LOGO_HOME_KEY_ROLE)
                    home_pix = self._combo_logo_cache.get(home_logo_key)
                    if home_pix:
                        self.game_combo.setItemData(row, home_pix, GAME_LOGO_HOME_ROLE)
                    else:
                        self._queue_combo_logo(home_logo_key)
        self.game_combo.blockSignals(False)

        if not self.games:
            self.selected_game_id = None
            message = (data.get("lines") or ["No games today."])[0]
            self._clear_ui_for_no_games(message)
            return
        sport = self.sport_name.upper()
        if sport == "NBA":
            if hasattr(self, "pbp_bar"):
                self.pbp_bar.setVisible(False)
            self._refresh_nba_merged_ticker()
        elif sport in ("NFL", "NHL"):
            if hasattr(self, "pbp_bar"):
                self.pbp_bar.setVisible(False)
            pbp_label = getattr(self, "pbp_ticker_label", None)
            if isinstance(pbp_label, TickerLabel):
                pbp_label.stop_ticker()
            self._pbp_lines = []
            self._refresh_nba_merged_ticker()
        else:
            if hasattr(self, "pbp_bar"):
                self.pbp_bar.setVisible(False)
            pbp_label = getattr(self, "pbp_ticker_label", None)
            if isinstance(pbp_label, TickerLabel):
                pbp_label.stop_ticker()

        # keep previous selection if still present, otherwise pick first
        target_id, idx = self._preferred_game_id(self.games)
        self.selected_game_id = target_id
        self._cache_runtime_scores(self.sport_name, self.games, self.lines, selected_game_id=self.selected_game_id)
        self._prefetch_boxscores_for_games(self.games)
        self._prefetch_other_sports_scoreboards()

        self.game_combo.blockSignals(True)
        self._show_placeholder()
        self.game_combo.blockSignals(False)
        self._pending_selection_id = None
        if self.selected_game_id:
            self._start_realtime_for_game(self.selected_game_id)
        else:
            self._update_boxscore_poll_timer()
        self.refresh_boxscore()
        self.refresh_pbp()

    def refresh_boxscore(self):
        game_id = self.selected_game_id or self._pending_selection_id
        if not game_id:
            return
        key = (self.sport_name, str(game_id))
        if self._displayed_boxscore_key != key:
            self._clock_state = None
            self.clock_feed_interval_avg = None
            cached_runtime = self._runtime_boxscore(*key)
            if isinstance(cached_runtime, dict):
                try:
                    self.apply_boxscore(cached_runtime)
                except Exception:
                    pass
        if self._boxscore_future and not self._boxscore_future.done() and self._boxscore_future_key == key:
            return
        sport_name = self.sport_name
        sport_token = self._sport_token
        if self.logic is not None:
            self._boxscore_future = self._executor.submit(self.logic.get_boxscore, game_id)
        else:
            self._boxscore_future = self._executor.submit(self.backend.fetch_boxscore, game_id)
        self._boxscore_future_key = key
        self._boxscore_future.add_done_callback(
            lambda fut, gid=game_id, s=sport_name, t=sport_token: self._on_boxscore_ready(gid, fut, s, t)
        )

    def refresh_pbp(self):
        if self.sport_name.upper() != "NBA":
            if hasattr(self, "pbp_bar"):
                self.pbp_bar.setVisible(False)
            pbp_label = getattr(self, "pbp_ticker_label", None)
            if isinstance(pbp_label, TickerLabel):
                pbp_label.stop_ticker()
            return
        if hasattr(self, "pbp_bar"):
            self.pbp_bar.setVisible(False)
        game_id = self.selected_game_id or self._pending_selection_id
        if not game_id:
            self._pbp_lines = []
            self._refresh_nba_merged_ticker(force=True)
            return
        fetcher = getattr(self.backend, "fetch_play_by_play", None)
        if not callable(fetcher):
            self._pbp_lines = []
            self._refresh_nba_merged_ticker(force=True)
            return
        if self._pbp_future_game_id != str(game_id):
            self._pbp_lines = []
            self._refresh_nba_merged_ticker(force=True)
        if self._pbp_future and not self._pbp_future.done() and self._pbp_future_game_id == str(game_id):
            return
        self._pbp_future_game_id = str(game_id)
        self._pbp_future = self._executor.submit(fetcher, game_id, 18)
        self._pbp_future.add_done_callback(lambda fut, gid=str(game_id): self._on_pbp_ready(gid, fut))

    def _on_pbp_ready(self, game_id: str, future):
        if not self._alive:
            return
        try:
            items = future.result()
        except Exception:
            items = []
        self.pbp_ready.emit(game_id, items)

    def _apply_pbp(self, game_id: str, items: object):
        if not self._alive:
            return
        if self.sport_name.upper() != "NBA":
            return
        current_ids = {str(gid) for gid in (self.selected_game_id, self._pending_selection_id) if gid}
        if str(game_id) not in current_ids:
            return
        if hasattr(self, "pbp_bar"):
            self.pbp_bar.setVisible(False)
        pbp_items = items if isinstance(items, list) else []
        self._append_pbp_history(game_id, pbp_items)
        delayed = self._select_delayed_pbp(game_id, pbp_items)
        self._apply_pbp_items(game_id, delayed)

    def _apply_pbp_items(self, game_id: str, items: list[dict[str, Any]]) -> None:
        if self.sport_name.upper() != "NBA":
            return
        if not isinstance(getattr(self, "pbp_ticker_label", None), QLabel):
            return
        if hasattr(self, "pbp_bar"):
            self.pbp_bar.setVisible(False)
        if not items:
            self._pbp_lines = []
            self._refresh_nba_merged_ticker(force=True)
            return
        lines = self._pbp_lines_from_items(game_id, items)
        if not lines:
            self._pbp_lines = []
            self._refresh_nba_merged_ticker(force=True)
            return
        self._pbp_lines = lines
        self._refresh_nba_merged_ticker(force=True)

    def _on_boxscore_ready(self, game_id: str, future, sport_name: str, sport_token: int):
        if not self._alive:
            return
        try:
            data = future.result()
        except Exception:
            data = None
        if data is None:
            data = self._build_boxscore_stub(game_id)
        data["_sport_name"] = sport_name
        data["_sport_token"] = sport_token
        self._cache_runtime_boxscore(sport_name, str(game_id), data)
        self._append_boxscore_history(game_id, data)
        if game_id not in (self.selected_game_id, self._pending_selection_id):
            return
        self.boxscore_fetched.emit(game_id, data)

    def _schedule_boxscore_emit(self, game_id: str, data: Dict[str, Any]):
        if data.get("_sport_name") != self.sport_name or data.get("_sport_token") != self._sport_token:
            return
        if self._instant_boxscore_apply:
            delay = self.display_delay_ms
        else:
            delay = self._remaining_delay_ms()
        delayed = self._select_delayed_boxscore(game_id, data)
        QTimer.singleShot(delay, lambda gid=game_id, d=delayed: self._emit_boxscore_if_current(gid, d))
        self._instant_boxscore_apply = False

    def _delay_ms_for_scores(self, data: Dict[str, Any]) -> int:
        return self.display_delay_ms

    def _append_score_history(self, data: Dict[str, Any]) -> None:
        self._score_history.append((time.monotonic(), data))

    def _append_boxscore_history(self, game_id: str, data: Dict[str, Any]) -> None:
        key = str(game_id)
        history = self._boxscore_history.get(key)
        if history is None:
            history = deque(maxlen=600)
            self._boxscore_history[key] = history
        history.append((time.monotonic(), data))

    def _append_pbp_history(self, game_id: str, items: list[dict[str, Any]]) -> None:
        key = str(game_id)
        history = self._pbp_history.get(key)
        if history is None:
            history = deque(maxlen=180)
            self._pbp_history[key] = history
        history.append((time.monotonic(), items))

    def _history_snapshot(self, history: deque[tuple[float, Dict[str, Any]]], target_ts: float) -> Dict[str, Any] | None:
        for ts, payload in reversed(history):
            if ts <= target_ts:
                return payload
        if history:
            return history[0][1]
        return None

    def _select_delayed_scores(self, data: Dict[str, Any]) -> Dict[str, Any]:
        delay_sec = self.feed_delay_ms / 1000.0
        if delay_sec <= 0 or not self._score_history:
            return data
        target_ts = time.monotonic() - delay_sec
        snapshot = self._history_snapshot(self._score_history, target_ts)
        return snapshot or data

    def _select_delayed_boxscore(self, game_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        delay_sec = self.feed_delay_ms / 1000.0
        if delay_sec <= 0:
            return data
        history = self._boxscore_history.get(str(game_id))
        if not history:
            return data
        target_ts = time.monotonic() - delay_sec
        snapshot = self._history_snapshot(history, target_ts)
        return snapshot or data

    def _select_delayed_pbp(self, game_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        delay_sec = self.feed_delay_ms / 1000.0
        if delay_sec <= 0:
            return items
        history = self._pbp_history.get(str(game_id))
        if not history:
            return items
        target_ts = time.monotonic() - delay_sec
        snapshot = None
        for ts, payload in reversed(history):
            if ts <= target_ts:
                snapshot = payload
                break
        if snapshot is None:
            snapshot = history[0][1] if history else items
        return snapshot or items

    def _apply_delay_snapshot(self) -> None:
        if not self._score_history:
            return
        delay_sec = self.feed_delay_ms / 1000.0
        target_ts = time.monotonic() - delay_sec if delay_sec > 0 else time.monotonic()
        score_snapshot = self._history_snapshot(self._score_history, target_ts) or self._score_history[-1][1]
        if score_snapshot:
            self._emit_scores_if_current(score_snapshot)
        game_id = self.selected_game_id or self._pending_selection_id
        if not game_id:
            games = (score_snapshot or {}).get("games") or []
            if games:
                game_id = games[0].get("gameId")
        if not game_id:
            return
        history = self._boxscore_history.get(str(game_id))
        if history:
            box_snapshot = self._history_snapshot(history, target_ts) or history[-1][1]
            if box_snapshot:
                self._emit_boxscore_if_current(str(game_id), box_snapshot)
        pbp_history = self._pbp_history.get(str(game_id))
        if pbp_history:
            pbp_snapshot = None
            for ts, payload in reversed(pbp_history):
                if ts <= target_ts:
                    pbp_snapshot = payload
                    break
            if pbp_snapshot is None:
                pbp_snapshot = pbp_history[0][1] if pbp_history else None
            if pbp_snapshot is not None:
                self._apply_pbp_items(str(game_id), pbp_snapshot)

    def _is_game_live(self, game: Dict[str, Any]) -> bool:
        status = game.get("status")
        if isinstance(status, str):
            status = status.lower()
            if status in ("live", "in", "inprogress", "in progress"):
                return True
            if status in ("final", "upcoming", "pre", "post"):
                return False
        status_val = game.get("gameStatus")
        if isinstance(status_val, int):
            return status_val == 2
        status_text = str(game.get("gameStatusText") or game.get("header") or "").lower()
        if any(token in status_text for token in ("final", "postponed", "canceled", "cancelled")):
            return False
        if any(token in status_text for token in ("scheduled", "starts", "tba")):
            return False
        return bool(status_text)

    def _emit_boxscore_if_current(self, game_id: str, data: Dict[str, Any]):
        if not self._alive:
            return
        if data.get("_sport_name") != self.sport_name or data.get("_sport_token") != self._sport_token:
            return
        if game_id not in (self.selected_game_id, self._pending_selection_id):
            return
        if self.selected_game_id is None:
            self.selected_game_id = game_id
        self.boxscore_ready.emit(data)

    def _build_boxscore_stub(self, game_id: str) -> Dict[str, Any]:
        """Fallback boxscore when backend fails; uses game list to populate."""
        game_entry = next((g for g in self.games if g.get("gameId") == game_id), None)
        home = (game_entry or {}).get("homeTeam") or {"teamName": "HOME", "teamTricode": "HME", "score": 0}
        away = (game_entry or {}).get("awayTeam") or {"teamName": "AWAY", "teamTricode": "AWY", "score": 0}
        header = (game_entry or {}).get("gameStatusText") or "No Data"
        game = {
            "gameClock": None,
            "shotClock": None,
            "period": {"current": None},
            "gameStatusText": header,
        }
        return {"game": game, "home": home, "away": away, "header": header, "shotclock": None}

    # --------------- apply boxscore to UI ---------------
    def apply_boxscore(self, data: Dict[str, Any]):
        prev_data = self._last_boxscore_data
        game = data["game"]
        home = data["home"]
        away = data["away"]
        current_game_id = str(self.selected_game_id or self._pending_selection_id or "")
        if current_game_id:
            self._displayed_boxscore_key = (self.sport_name, current_game_id)
            self._cache_runtime_boxscore(self.sport_name, current_game_id, data)
        self._has_displayed_boxscore = True
        self._last_boxscore_data = data
        if current_game_id:
            self._merge_live_game_state(
                current_game_id,
                away_score=(away or {}).get("score"),
                home_score=(home or {}).get("score"),
                status_text=str(data.get("header") or (game or {}).get("gameStatusText") or ""),
                game_clock=(game or {}).get("gameClock"),
                period=(game or {}).get("period"),
                status=(game or {}).get("gameStatus") if (game or {}).get("gameStatus") is not None else (game or {}).get("status"),
            )

        # quarter + clock
        self._apply_clock(data)
        self.center_panel.set_pitching_side(None)

        # Default: away on left, home on right
        left_team = away
        right_team = home
        left_side = "away"
        right_side = "home"
        if self.sport_name.upper() in ("NBA", "NCAA BASKETBALL"):
            left_fouls = "BONUS" if self._team_in_bonus(left_team) else self._team_fouls_text(left_team)
            right_fouls = "BONUS" if self._team_in_bonus(right_team) else self._team_fouls_text(right_team)
            self.center_panel.set_bottom_labels(str(left_fouls), str(right_fouls), "FOULS")
        elif self.sport_name.upper() == "MLB":
            situation = game.get("situation") or {}
            on1 = bool(situation.get("onFirst"))
            on2 = bool(situation.get("onSecond"))
            on3 = bool(situation.get("onThird"))
            self.center_panel.set_bases(on1, on2, on3)
            balls = situation.get("balls")
            strikes = situation.get("strikes")
            outs = situation.get("outs")
            self.center_panel.set_count(balls, strikes, outs)
            half = str(situation.get("inningHalf") or "").strip().upper()
            pitching_side: str | None = None
            if half.startswith("TOP") or half == "T" or half.startswith("▲"):
                pitching_side = "right"  # home team fields in top half
            elif half.startswith("BOT") or half.startswith("BOTTOM") or half == "B" or half.startswith("▼"):
                pitching_side = "left"   # away team fields in bottom half
            self.center_panel.set_pitching_side(pitching_side)
            count_text = ""
            if on1 and on2 and on3:
                count_text = "BASES LOADED"
            batter = situation.get("batter") or ""
            pitcher = situation.get("pitcher") or ""
            self.center_panel.set_bottom_labels(batter, pitcher, count_text)
        elif self.sport_name.upper() == "NHL":
            is_shootout = (
                self.center_panel.period_label.text().upper() == "SO"
                or self._is_shootout_status(game, data.get("header"))
            )
            if is_shootout:
                left_so = self._team_shootout_score_text(left_team)
                right_so = self._team_shootout_score_text(right_team)
                self.center_panel.set_bottom_labels(left_so, right_so, "SO")
            else:
                left_shots = self._team_shots_text(left_team)
                right_shots = self._team_shots_text(right_team)
                left_pim = self._team_penalties_text(left_team)
                right_pim = self._team_penalties_text(right_team)
                self.center_panel.set_bottom_labels(
                    f"{left_shots}\n{left_pim}", f"{right_shots}\n{right_pim}", "SHOTS\nPIM"
                )
        elif self.sport_name.upper() == "MLS":
            left_shots = self._team_shots_text(left_team)
            right_shots = self._team_shots_text(right_team)
            left_poss = self._team_stat_text(left_team, ("possessionPct",), suffix="%")
            right_poss = self._team_stat_text(right_team, ("possessionPct",), suffix="%")
            self.center_panel.set_bottom_labels(
                f"{left_shots}\n{left_poss}",
                f"{right_shots}\n{right_poss}",
                "SOG\nPOSS",
            )
        elif self.sport_name.upper() == "NFL":
            current_possession = (self._nfl_possession_tricode or "").upper()
            if current_possession != self._nfl_last_possession:
                self._nfl_manual_mode.clear()
                self._nfl_last_possession = current_possession
            self._nfl_table_team[self.away_table] = left_team
            self._nfl_table_team[self.home_table] = right_team
            self._nfl_table_side[self.away_table] = left_side
            self._nfl_table_side[self.home_table] = right_side

        # team names & tricodes
        left_city, left_name = self._team_city_and_name(left_team)
        right_city, right_name = self._team_city_and_name(right_team)
        if not left_name:
            left_name = "LEFT"
        if not right_name:
            right_name = "RIGHT"
        if not left_city:
            left_city = left_name
        if not right_city:
            right_city = right_name
        left_tri = self._display_tricode(left_team, "AWY")
        right_tri = self._display_tricode(right_team, "HME")
        left_record = self._team_record_text(left_team, left_side)
        right_record = self._team_record_text(right_team, right_side)

        self._set_label_text(self.away_name, left_name.upper(), animate=True)
        self._set_label_text(self.home_name, right_name.upper(), animate=True)
        self._set_label_text(self.away_city, left_city, animate=True)
        self._set_label_text(self.home_city, right_city, animate=True)
        self._set_label_text(self.away_record, left_record, animate=True)
        self._set_label_text(self.home_record, right_record, animate=True)

        left_color = self._team_color(left_tri)
        right_color = self._team_color(right_tri)
        left_alt = self._team_alt_color(left_tri)
        right_alt = self._team_alt_color(right_tri)
        left_secondary = self._team_secondary_color(left_tri)
        right_secondary = self._team_secondary_color(right_tri)
        if self.sport_name.upper() == "NHL":
            left_secondary = left_alt
            right_secondary = right_alt
        left_color, left_secondary, left_alt = self._resolve_team_theme_colors(left_tri, left_color, left_secondary, left_alt)
        right_color, right_secondary, right_alt = self._resolve_team_theme_colors(
            right_tri, right_color, right_secondary, right_alt
        )
        left_text = self._top_text_color(left_color)
        right_text = self._top_text_color(right_color)
        left_name_text = "#f7f7f7" if left_tri == "SAS" else left_text
        right_name_text = "#f7f7f7" if right_tri == "SAS" else right_text
        left_record_color = "#f7f7f7" if left_tri == "SAS" else self._with_alpha(left_text, 0.85)
        right_record_color = "#f7f7f7" if right_tri == "SAS" else self._with_alpha(right_text, 0.85)
        left_score_text = "#f7f7f7" if left_tri == "SAS" else left_text
        right_score_text = "#f7f7f7" if right_tri == "SAS" else right_text
        self._set_top_background(left_color, left_secondary, right_color, right_secondary)
        self.apply_team_logo_style(self.away_logo_box, left_tri, left_color, left_alt)
        self.apply_team_logo_style(self.home_logo_box, right_tri, right_color, right_alt)
        city_size = CITY_FONT_SIZE
        self.away_city.setStyleSheet(
            f"font-size: {city_size}px; font-weight: 800; color: {self._with_alpha(left_text, 0.9)}; letter-spacing: 0.6px;"
        )
        self.home_city.setStyleSheet(
            f"font-size: {city_size}px; font-weight: 800; color: {self._with_alpha(right_text, 0.9)}; letter-spacing: 0.6px;"
        )
        self.away_name.setStyleSheet(
            f"font-size: 20px; font-weight: 900; color: {left_name_text}; letter-spacing: 0.8px;"
        )
        self.home_name.setStyleSheet(
            f"font-size: 20px; font-weight: 900; color: {right_name_text}; letter-spacing: 0.8px;"
        )
        self.away_record.setStyleSheet(f"color: {left_record_color}; font-size: 12px; font-weight: 700;")
        self.home_record.setStyleSheet(f"color: {right_record_color}; font-size: 12px; font-weight: 700;")
        self._set_score_style(self.away_score, left_score_text)
        self._set_score_style(self.home_score, right_score_text)
        self._apply_control_colors(left_text, right_text)
        self._set_score_card_color(self.away_score_card, left_color)
        self._set_score_card_color(self.home_score_card, right_color)
        self._set_table_color(self.away_table_frame, self.away_table, left_color)
        self._set_table_color(self.home_table_frame, self.home_table, right_color)
        self._apply_timeouts(left_team, right_team, left_color, right_color)

        # logos fetched off the UI thread
        self._request_logo("away", left_team)
        self._request_logo("home", right_team)

        # scores
        left_score = self.backend.safe_score(left_team)
        right_score = self.backend.safe_score(right_team)

        prev_left_delta = None
        prev_right_delta = None
        if self.sport_name.upper() == "NBA" and isinstance(prev_data, dict):
            prev_left_delta = self._score_delta(prev_data.get("away"), left_team)
            prev_right_delta = self._score_delta(prev_data.get("home"), right_team)

        score_fade_away = None if self.sport_name.upper() == "NBA" else self.away_score_card
        score_fade_home = None if self.sport_name.upper() == "NBA" else self.home_score_card
        self._set_label_text(self.away_score, str(left_score), animate=True, fade_widget=score_fade_away, duration_ms=220)
        self._set_label_text(self.home_score, str(right_score), animate=True, fade_widget=score_fade_home, duration_ms=220)
        if self.sport_name.upper() == "NBA":
            if prev_left_delta == 3:
                self._flash_score_label(self.away_score, base_color=left_score_text)
            if prev_right_delta == 3:
                self._flash_score_label(self.home_score, base_color=right_score_text)

        # tables
        show_lineups = self._should_show_lineups()
        self._set_table_titles(show_lineups)
        self.fill_team_table(self.away_table, left_team, show_lineups=show_lineups)
        self.fill_team_table(self.home_table, right_team, show_lineups=show_lineups)
        # For bottom bar, always pass away first, then home
        self._update_bottom_bar(left_team, right_team)  # away, home
        self._save_cached_state(data)

    def _row_stats_from_values(self, table: QTableWidget, values: List[Any]) -> Dict[str, str]:
        stats: Dict[str, str] = {}
        limit = min(table.columnCount(), len(values))
        for col in range(limit):
            header_item = table.horizontalHeaderItem(col)
            key = str(header_item.text() if header_item else f"Stat {col + 1}").strip()
            if not key:
                continue
            val = str(values[col] if col < len(values) else "").strip()
            if col != 1 and not val:
                continue
            stats[key] = val
        return stats

    def _set_player_context_on_row(self, table: QTableWidget, row: int, context: Dict[str, Any]) -> None:
        name_item = table.item(row, 1)
        if name_item is None:
            name_item = QTableWidgetItem(str(context.get("playerName") or ""))
            table.setItem(row, 1, name_item)
        name_item.setData(PLAYER_CONTEXT_ROLE, context)

    def _player_id_from_entry(self, player: Dict[str, Any]) -> str:
        if not isinstance(player, dict):
            return ""
        for key in ("id", "personId", "playerId", "athleteId", "alternateId"):
            val = player.get(key)
            if val not in (None, ""):
                return str(val)
        athlete = player.get("athlete")
        if isinstance(athlete, dict):
            for key in ("id", "alternateId"):
                val = athlete.get(key)
                if val not in (None, ""):
                    return str(val)
            alt_ids = athlete.get("alternateIds")
            if isinstance(alt_ids, dict):
                for val in alt_ids.values():
                    if val not in (None, ""):
                        return str(val)
        return ""

    def _player_name_candidates(self, player: Dict[str, Any]) -> List[str]:
        athlete = player.get("athlete") if isinstance(player.get("athlete"), dict) else {}
        names = [
            self._player_full_name(player),
            player.get("fullName"),
            player.get("displayName"),
            player.get("name"),
            athlete.get("fullName"),
            athlete.get("displayName"),
            athlete.get("name"),
            athlete.get("shortName"),
        ]
        first = str(player.get("firstName") or athlete.get("firstName") or "").strip()
        last = str(player.get("familyName") or athlete.get("lastName") or athlete.get("familyName") or "").strip()
        if first or last:
            names.append(f"{first} {last}".strip())
        out: List[str] = []
        seen: set[str] = set()
        for raw in names:
            token = str(raw or "").strip()
            if not token:
                continue
            lowered = token.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            out.append(token)
        return out

    def _normalize_player_token(self, value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

    def _match_team_player_for_row(
        self,
        team: Dict[str, Any],
        values: List[Any],
        used_indices: set[int],
    ) -> Dict[str, Any] | None:
        players = team.get("players") or []
        if not isinstance(players, list) or not players:
            return None
        row_name = str(values[1] if len(values) > 1 else "").strip()
        row_jersey = str(values[0] if values else "").strip()
        row_name_token = self._normalize_player_token(row_name)
        candidates: list[tuple[int, int, Dict[str, Any]]] = []
        for idx, player in enumerate(players):
            if idx in used_indices or not isinstance(player, dict):
                continue
            p_jersey = self._player_jersey(player).strip()
            score = 0
            if row_jersey and p_jersey and row_jersey == p_jersey:
                score += 4
            p_names = self._player_name_candidates(player)
            if row_name_token:
                p_tokens = [self._normalize_player_token(name) for name in p_names]
                if row_name_token in p_tokens:
                    score += 5
                else:
                    row_parts = [p for p in re.split(r"[^a-z0-9]+", row_name.lower()) if p]
                    if row_parts:
                        row_last = row_parts[-1]
                        row_initial = row_parts[0][:1]
                        for name in p_names:
                            parts = [p for p in re.split(r"[^a-z0-9]+", str(name).lower()) if p]
                            if not parts:
                                continue
                            if parts[-1] == row_last:
                                score += 2
                                if row_initial and parts[0].startswith(row_initial):
                                    score += 1
                                break
            if score > 0:
                candidates.append((score, idx, player))
                if score >= 9:
                    break
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        _, chosen_idx, chosen = candidates[0]
        used_indices.add(chosen_idx)
        return chosen

    def _build_player_context(
        self,
        team: Dict[str, Any],
        player: Dict[str, Any] | None,
        *,
        row_stats: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        tri = str(team.get("teamTricode") or team.get("tricode") or "").upper()
        context: Dict[str, Any] = {
            "sport": self.sport_name.upper(),
            "teamId": str(team.get("teamId") or team.get("id") or ""),
            "teamTricode": tri,
            "teamName": str(team.get("teamName") or team.get("displayName") or team.get("name") or ""),
            "teamColor": self._team_color(tri),
            "rowStats": dict(row_stats or {}),
        }
        if isinstance(player, dict):
            context["playerData"] = dict(player)
            context["playerId"] = self._player_id_from_entry(player)
            context["playerName"] = self._player_full_name(player)
            context["jersey"] = self._player_jersey(player)
            row_position = ""
            if isinstance(row_stats, dict):
                row_position = str(row_stats.get("Pos") or row_stats.get("Position") or "").strip()
            context["position"] = self._player_position(player) or row_position
            if self.sport_name.upper() == "MLB":
                lineup_order = self._mlb_lineup_order(player)
                if lineup_order:
                    context["lineupOrder"] = str(lineup_order)
        return context

    def fill_team_table(self, table: QTableWidget, team: Dict[str, Any], *, show_lineups: bool = False):
        if show_lineups:
            self._fill_lineup_table(table, team)
            return
        if self.sport_name.upper() == "NFL":
            self._fill_nfl_table(table, team)
            return
        if self.sport_name.upper() == "NHL":
            self._fill_nhl_table(table, team)
            return
        if self.sport_name.upper() == "NBA":
            self._fill_nba_scroll_table(table, team)
            return
        rows: List[List[str]] | None = None
        builder = getattr(self.backend, "build_player_rows", None)
        if callable(builder):
            try:
                rows = builder(team) or []
            except Exception:
                rows = []
        if rows:
            table.setRowCount(0)
            headers_count = table.columnCount()
            used_player_indices: set[int] = set()
            for values in rows:
                row = table.rowCount()
                table.insertRow(row)
                for col, val in enumerate(values[:headers_count]):
                    item = QTableWidgetItem(str(val))
                    if col == 1:
                        item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                    elif col in (0, 2, 4, 5, 6, 7):
                        item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, col, item)
                row_stats = self._row_stats_from_values(table, values)
                matched = self._match_team_player_for_row(team, values, used_player_indices)
                context = self._build_player_context(team, matched, row_stats=row_stats)
                if len(values) > 1 and not context.get("playerName"):
                    context["playerName"] = str(values[1] or "")
                if values and not context.get("jersey"):
                    context["jersey"] = str(values[0] or "")
                if len(values) > 2 and not context.get("position"):
                    context["position"] = str(values[2] or "")
                self._set_player_context_on_row(table, row, context)
            return

        table.setRowCount(0)
        headers_count = table.columnCount()

        # NFL uses different stat mapping than NBA
        is_nfl = self.sport_name.upper() == "NFL"
        is_nba = self.sport_name.upper() == "NBA"
        players = team.get("players", []) or []
        divider_row = None
        if is_nba:
            def _order(p: Dict[str, Any]) -> Any:
                return p.get("order", 9999)

            def _truthy_flag(val: Any) -> bool:
                if isinstance(val, str):
                    return val.strip().lower() in ("1", "true", "yes", "y")
                return bool(val)

            def _is_on_court(p: Dict[str, Any]) -> bool:
                stats = p.get("statistics", {}) or {}
                for key in ("isOnCourt", "onCourt", "oncourt"):
                    if key in stats and stats.get(key) not in (None, ""):
                        return _truthy_flag(stats.get(key))
                for key in ("onCourt", "oncourt", "isOnCourt"):
                    if key in p and p.get(key) not in (None, ""):
                        return _truthy_flag(p.get(key))
                return False

            on_court = [p for p in players if _is_on_court(p)]
            off_court = [p for p in players if not _is_on_court(p)]
            on_court.sort(key=_order)
            off_court.sort(key=_order)
            if on_court:
                divider_row = min(len(on_court), 5) - 1
                players = on_court[:5] + off_court + on_court[5:]
            else:
                players = sorted(players, key=_order)
        else:
            players = sorted(
                players,
                key=lambda p: (
                    0 if (p.get("statistics", {}) or {}).get("isOnCourt") else 1,
                    p.get("order", 9999),
                ),
            )

        for p in players:
            stats = p.get("statistics", {}) or {}
            jersey = p.get("jerseyNum") or ""
            first = (p.get("firstName") or "").strip()
            last = (p.get("familyName") or "").strip()
            name = format_player_initial_name(first, last)
            pos = p.get("position") or ""

            if is_nfl:
                # NFL headers: ["#", "Player", "Pos", "Yds", "TD", "Tkl", "Ast", "Pen"]
                # Backend maps: points=TD*6, reboundsTotal=tackles, assists=yards/10, personalFouls=penalties
                # So we need to reverse-map for display
                touchdowns = int(stats.get("points", 0) // 6)  # points = TD * 6
                tackles = stats.get("reboundsTotal", stats.get("rebounds", 0))
                yards = int(stats.get("assists", 0) * 10)  # assists = yards / 10
                penalties = stats.get("personalFouls", 0)
                values = [jersey, name, pos, str(yards), str(touchdowns), str(tackles), "", str(penalties)]
            else:
                # NBA headers: ["#", "Player", "Min", "Pos", "Pts", "Reb", "Ast", "3pt"]
                minutes = self.backend.format_time_played(stats.get("minutes") or stats.get("minutesCalculated"))
                pts = str(stats.get("points", 0))
                reb = str(stats.get("reboundsTotal", stats.get("rebounds", 0)))
                ast = str(stats.get("assists", 0))
                pf_value = extract_three_point_made(stats) if is_nba else stats.get("personalFouls", 0)
                pf = str(pf_value)
                values = [jersey, name, minutes, pos, pts, reb, ast, pf]

            row = table.rowCount()
            table.insertRow(row)
            alignment_cols = (0, 3, 4, 5, 6, 7) if is_nfl else (0, 4, 5, 6, 7)
            for col, val in enumerate(values[:headers_count]):
                item = QTableWidgetItem(val)
                if divider_row is not None and row == divider_row:
                    item.setData(PLAYER_DIVIDER_ROLE, True)
                if col == 1:
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                elif col in alignment_cols:
                    item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)
            row_stats = self._row_stats_from_values(table, values)
            context = self._build_player_context(team, p, row_stats=row_stats)
            if not context.get("playerName"):
                context["playerName"] = name
            self._set_player_context_on_row(table, row, context)

    def _fill_nfl_table(self, table: QTableWidget, team: Dict[str, Any]) -> None:
        players = team.get("players", []) or []
        table.setRowCount(0)
        headers_count = table.columnCount()
        if not players:
            self._set_nfl_table_mode(table, "offense")
            row = table.rowCount()
            table.insertRow(row)
            values = ["", "No stats available", ""] + [""] * max(0, headers_count - 3)
            for col, val in enumerate(values[:headers_count]):
                item = QTableWidgetItem(str(val))
                if col == 1:
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                else:
                    item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)
            return

        offense: list[dict[str, Any]] = []
        defense: list[dict[str, Any]] = []
        for p in players:
            group = self._nfl_player_group(p)
            if group == "defense":
                defense.append(p)
            else:
                offense.append(p)

        offense.sort(key=self._nfl_offense_sort, reverse=True)
        defense.sort(key=self._nfl_defense_sort, reverse=True)
        offense = offense[:11]
        defense = defense[:11]

        mode = self._nfl_resolve_mode(table, team, offense, defense)

        self._set_nfl_table_mode(table, mode)
        active_players = offense if mode == "offense" else defense

        for p in active_players:
            row = table.rowCount()
            table.insertRow(row)
            values = self._nfl_player_values(p, offense=(mode == "offense"))
            for col, val in enumerate(values[:headers_count]):
                item = QTableWidgetItem(str(val))
                if col == 1:
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                elif col in (0, 2, 3, 4, 5, 6, 7):
                    item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)
            row_stats = self._row_stats_from_values(table, values)
            context = self._build_player_context(team, p, row_stats=row_stats)
            self._set_player_context_on_row(table, row, context)

    def _set_nfl_table_mode(self, table: QTableWidget, mode: str) -> None:
        headers = NFL_OFFENSE_HEADERS if mode == "offense" else NFL_DEFENSE_HEADERS
        if table.columnCount() == len(headers):
            table.setHorizontalHeaderLabels(headers)
            self._apply_table_column_layout(table)
        for idx in range(table.columnCount()):
            table.setColumnHidden(idx, False)

    def _nfl_resolve_mode(
        self,
        table: QTableWidget,
        team: Dict[str, Any],
        offense: list[dict[str, Any]],
        defense: list[dict[str, Any]],
    ) -> str:
        side = self._nfl_table_side.get(table)
        override = self._nfl_manual_mode.get(side) if side else None
        if override in ("offense", "defense"):
            return override
        team_tri = (team.get("teamTricode") or "").upper()
        possession_tri = (self._nfl_possession_tricode or "").upper()
        if team_tri and possession_tri:
            return "offense" if team_tri == possession_tri else "defense"
        if offense:
            return "offense"
        if defense:
            return "defense"
        return "offense"

    def _toggle_nfl_table_mode(self, table: QTableWidget) -> None:
        team = self._nfl_table_team.get(table)
        if not team:
            return
        side = self._nfl_table_side.get(table)
        offense: list[dict[str, Any]] = []
        defense: list[dict[str, Any]] = []
        for p in team.get("players", []) or []:
            group = self._nfl_player_group(p)
            if group == "defense":
                defense.append(p)
            else:
                offense.append(p)
        offense.sort(key=self._nfl_offense_sort, reverse=True)
        defense.sort(key=self._nfl_defense_sort, reverse=True)
        offense = offense[:11]
        defense = defense[:11]
        current = self._nfl_resolve_mode(table, team, offense, defense)
        next_mode = "defense" if current == "offense" else "offense"
        if side:
            self._nfl_manual_mode[side] = next_mode
        self._fill_nfl_table(table, team)

    def _fill_nhl_table(self, table: QTableWidget, team: Dict[str, Any]) -> None:
        players = team.get("players", []) or []
        table.setRowCount(0)
        headers_count = table.columnCount()
        if not players:
            row = table.rowCount()
            table.insertRow(row)
            values = ["", "No stats available", ""] + [""] * max(0, headers_count - 3)
            for col, val in enumerate(values[:headers_count]):
                item = QTableWidgetItem(str(val))
                if col == 1:
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                else:
                    item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)
            return

        def _order(p: Dict[str, Any]) -> Any:
            stats = p.get("statistics", {}) or {}
            on_ice_order = stats.get("onIceOrder")
            if isinstance(on_ice_order, int):
                return on_ice_order
            if isinstance(on_ice_order, str) and on_ice_order.isdigit():
                return int(on_ice_order)
            for key in ("lineupOrder", "order", "starterOrder"):
                val = p.get(key, stats.get(key))
                if isinstance(val, int):
                    return val
                if isinstance(val, str) and val.isdigit():
                    return int(val)
            return 9999

        def _truthy_flag(val: Any) -> bool:
            if isinstance(val, str):
                return val.strip().lower() in ("1", "true", "yes", "y")
            return bool(val)

        def _is_goalie(p: Dict[str, Any]) -> bool:
            stats = p.get("statistics", {}) or {}
            pos = p.get("position") or ""
            return (str(pos).upper() == "G") or ("saves" in stats) or ("savePct" in stats)

        def _is_on_ice(p: Dict[str, Any]) -> bool:
            stats = p.get("statistics", {}) or {}
            for key in ("onIce", "on_ice", "isOnIce", "is_on_ice", "onIceNow", "onIceFlag", "onIceStatus"):
                if key in stats and stats.get(key) not in (None, ""):
                    return _truthy_flag(stats.get(key))
                if key in p and p.get(key) not in (None, ""):
                    return _truthy_flag(p.get(key))
            return False

        active = [p for p in players if _is_on_ice(p)]
        inactive = [p for p in players if not _is_on_ice(p)]
        active_size = self._lineup_size()
        if active:
            active.sort(key=_order)
            inactive.sort(key=_order)
            active_skaters = [p for p in active if not _is_goalie(p)]
            active_goalies = [p for p in active if _is_goalie(p)]
            goalie = active_goalies[:1]
            if active_size:
                skater_count = max(0, active_size - (1 if goalie else 0))
                active = active_skaters[:skater_count] + goalie
                leftover = active_skaters[skater_count:] + active_goalies[1:]
                inactive = leftover + inactive
            else:
                active = active_skaters + goalie
                inactive = active_goalies[1:] + inactive
        else:
            ordered = sorted(players, key=_order)
            if active_size and len(ordered) > active_size:
                active = ordered[:active_size]
                inactive = ordered[active_size:]
            else:
                active = ordered
                inactive = []

        ordered = active + inactive
        divider_row = len(active) - 1 if active and inactive else None

        for p in ordered:
            stats = p.get("statistics", {}) or {}
            jersey = p.get("jerseyNum") or ""
            name = format_player_initial_name(p.get("firstName"), p.get("familyName"))
            pos = p.get("position") or ""
            is_goalie = (pos or "").upper() == "G" or "saves" in stats or "savePct" in stats
            if is_goalie:
                saves = self._nfl_stat_int(stats.get("saves"))
                save_pct = stats.get("savePct") or ""
                pim = self._nfl_stat_int(stats.get("pim"))
                values = [jersey, name, pos, "", "", "", "", str(pim), str(saves), str(save_pct)]
            else:
                goals = self._nfl_stat_int(stats.get("goals"))
                assists = self._nfl_stat_int(stats.get("assists"))
                points = self._nfl_stat_int(stats.get("points") or (goals + assists))
                sog = self._nfl_stat_int(stats.get("shotsOnGoal"))
                pim = self._nfl_stat_int(stats.get("pim"))
                values = [jersey, name, pos, str(goals), str(assists), str(points), str(sog), str(pim), "", ""]

            row = table.rowCount()
            table.insertRow(row)
            for col, val in enumerate(values[:headers_count]):
                item = QTableWidgetItem(str(val))
                if divider_row is not None and row == divider_row:
                    item.setData(PLAYER_DIVIDER_ROLE, True)
                if col == 1:
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                else:
                    item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)
            row_stats = self._row_stats_from_values(table, values)
            context = self._build_player_context(team, p, row_stats=row_stats)
            if not context.get("playerName"):
                context["playerName"] = name
            self._set_player_context_on_row(table, row, context)

    def _fill_nba_scroll_table(self, table: QTableWidget, team: Dict[str, Any]) -> None:
        self._configure_nba_table(table)
        table.clearContents()
        players = team.get("players", []) or []
        headers_count = table.columnCount()
        if not players:
            table.setRowCount(1)
            values = ["", "No stats available", ""] + [""] * max(0, headers_count - 3)
            for col, val in enumerate(values[:headers_count]):
                item = QTableWidgetItem(str(val))
                if col == 1:
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                else:
                    item.setTextAlignment(Qt.AlignCenter)
                table.setItem(0, col, item)
            return

        def _order(p: Dict[str, Any]) -> Any:
            return p.get("order", 9999)

        def _truthy_flag(val: Any) -> bool:
            if isinstance(val, str):
                return val.strip().lower() in ("1", "true", "yes", "y")
            return bool(val)

        def _is_on_court(p: Dict[str, Any]) -> bool:
            stats = p.get("statistics", {}) or {}
            for key in ("isOnCourt", "onCourt", "oncourt"):
                if key in stats and stats.get(key) not in (None, ""):
                    return _truthy_flag(stats.get(key))
            for key in ("onCourt", "oncourt", "isOnCourt"):
                if key in p and p.get(key) not in (None, ""):
                    return _truthy_flag(p.get(key))
            return False

        on_court = [p for p in players if _is_on_court(p)]
        off_court = [p for p in players if not _is_on_court(p)]
        on_court.sort(key=_order)
        off_court.sort(key=_order)
        if len(on_court) > 5:
            off_court = on_court[5:] + off_court
            on_court = on_court[:5]
        ordered = on_court + off_court if on_court else sorted(players, key=_order)
        divider_row = None
        if on_court and off_court:
            divider_row = len(on_court) - 1

        table.setRowCount(len(ordered))
        for row, p in enumerate(ordered):
            stats = p.get("statistics", {}) or {}
            jersey = p.get("jerseyNum") or ""
            first = (p.get("firstName") or "").strip()
            last = (p.get("familyName") or "").strip()
            name = format_player_initial_name(first, last)
            pos = self._player_position(p).strip()
            minutes = self.backend.format_time_played(stats.get("minutes") or stats.get("minutesCalculated"))
            pts = stats.get("points", 0)
            reb = stats.get("reboundsTotal", stats.get("rebounds", 0))
            ast = stats.get("assists", 0)
            stl = stats.get("steals", stats.get("stealsTotal", 0))
            blk = stats.get("blocks", stats.get("blockedShots", 0))
            tov = stats.get("turnovers", stats.get("turnoversTotal", stats.get("turnover", 0)))
            plus_minus = stats.get("plusMinus", stats.get("plusMinusPoints", ""))
            three_pt = extract_three_point_made(stats)
            values = [
                str(jersey),
                str(name),
                str(pos),
                str(minutes),
                str(pts),
                str(reb),
                str(ast),
                str(three_pt),
                str(stl),
                str(blk),
                str(tov),
                str(plus_minus),
            ]
            for col, val in enumerate(values[:headers_count]):
                item = QTableWidgetItem(str(val))
                if divider_row is not None and row == divider_row:
                    item.setData(PLAYER_DIVIDER_ROLE, True)
                if col == 1:
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                else:
                    item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)
            row_stats = self._row_stats_from_values(table, values)
            context = self._build_player_context(team, p, row_stats=row_stats)
            if not context.get("playerName"):
                context["playerName"] = name
            self._set_player_context_on_row(table, row, context)

    def _nfl_section_values(self, label: str) -> list[str]:
        return ["", label, "", "", "", "", "", ""]

    def _nfl_player_values(self, p: Dict[str, Any], *, offense: bool) -> list[str]:
        stats = p.get("statistics", {}) or {}
        jersey = p.get("jerseyNum") or ""
        first = (p.get("firstName") or "").strip()
        last = (p.get("familyName") or "").strip()
        name = format_player_initial_name(first, last)
        pos = p.get("position") or ""
        yards = self._nfl_stat_int(stats.get("yardsTotal") or stats.get("assists"))
        touchdowns = self._nfl_stat_int(stats.get("touchdowns") or (stats.get("points") or 0) // 6)
        receptions = self._nfl_stat_int(stats.get("receptions"))
        carries = self._nfl_stat_int(stats.get("carries"))
        interceptions = self._nfl_stat_int(stats.get("interceptions"))
        tackles = self._nfl_stat_int(stats.get("tacklesTotal") or stats.get("reboundsTotal"))
        assists = self._nfl_stat_int(stats.get("tacklesAssist") or stats.get("assists"))
        sacks = self._nfl_stat_int(stats.get("sacks"))
        passes_defended = self._nfl_stat_int(stats.get("passesDefended"))
        if offense:
            return [
                jersey,
                name,
                pos,
                str(yards),
                str(touchdowns),
                str(receptions),
                str(carries),
                str(interceptions),
            ]
        return [
            jersey,
            name,
            pos,
            str(tackles),
            str(assists),
            str(sacks),
            str(interceptions),
            str(passes_defended),
        ]

    def _nfl_stat_int(self, val: Any) -> int:
        try:
            return int(float(val))
        except Exception:
            return 0

    def _nfl_player_group(self, p: Dict[str, Any]) -> str:
        stats = p.get("statistics", {}) or {}
        pos = (p.get("position") or "").upper()
        offense_pos = {
            "QB", "RB", "FB", "WR", "TE", "OT", "OG", "C", "OL", "LT", "LG", "RT", "RG", "HB",
        }
        defense_pos = {
            "DL", "DE", "DT", "NT", "LB", "OLB", "MLB", "ILB", "DB", "CB", "S", "FS", "SS", "NB",
        }
        if pos in offense_pos:
            return "offense"
        if pos in defense_pos:
            return "defense"
        yards = self._nfl_stat_int(stats.get("yardsTotal"))
        touchdowns = self._nfl_stat_int(stats.get("touchdowns"))
        tackles = self._nfl_stat_int(stats.get("tacklesTotal") or stats.get("reboundsTotal"))
        if yards or touchdowns:
            return "offense"
        if tackles:
            return "defense"
        return "offense"

    def _nfl_offense_sort(self, p: Dict[str, Any]) -> tuple[int, int]:
        stats = p.get("statistics", {}) or {}
        yards = self._nfl_stat_int(stats.get("yardsTotal") or stats.get("assists"))
        touchdowns = self._nfl_stat_int(stats.get("touchdowns") or (stats.get("points") or 0) // 6)
        return (yards, touchdowns)

    def _nfl_defense_sort(self, p: Dict[str, Any]) -> tuple[int, int]:
        stats = p.get("statistics", {}) or {}
        tackles = self._nfl_stat_int(stats.get("tacklesTotal") or stats.get("reboundsTotal"))
        assists = self._nfl_stat_int(stats.get("tacklesAssist") or stats.get("assists"))
        return (tackles, assists)

    def _fill_lineup_table(self, table: QTableWidget, team: Dict[str, Any]) -> None:
        lineup_players = self._lineup_players(team)
        rows = self._lineup_rows(team)
        table.setRowCount(0)
        headers_count = table.columnCount()
        if not rows:
            rows = [["", "Lineups TBD", ""]]
        for idx, values in enumerate(rows):
            padded = list(values) + [""] * max(0, headers_count - len(values))
            row = table.rowCount()
            table.insertRow(row)
            for col, val in enumerate(padded[:headers_count]):
                item = QTableWidgetItem(str(val))
                if col == 1:
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                elif col in (0, 2, 4, 5, 6, 7):
                    item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)
            if str(values[1] if len(values) > 1 else "").strip().lower() == "lineups tbd":
                continue
            player = lineup_players[idx] if idx < len(lineup_players) else None
            row_stats = self._row_stats_from_values(table, padded)
            context = self._build_player_context(team, player, row_stats=row_stats)
            if len(values) > 1 and not context.get("playerName"):
                context["playerName"] = str(values[1] or "")
            if values and not context.get("jersey"):
                context["jersey"] = str(values[0] or "")
            if len(values) > 2 and not context.get("position"):
                context["position"] = str(values[2] or "")
            self._set_player_context_on_row(table, row, context)

    def _lineup_rows(self, team: Dict[str, Any]) -> List[List[str]]:
        players = self._lineup_players(team)
        if not players:
            return []
        rows: List[List[str]] = []
        for p in players:
            jersey = self._player_jersey(p)
            name = self._player_name(p)
            pos = self._player_position(p)
            rows.append([jersey, name, pos])
        return rows

    def _lineup_players(self, team: Dict[str, Any]) -> List[Dict[str, Any]]:
        for key in ("startingLineup", "lineup", "starters", "startingPlayers"):
            val = team.get(key)
            if isinstance(val, list) and val:
                return [self._normalize_player_entry(p) for p in val]

        players = team.get("players", []) or []
        if not players:
            return []
        starters = [p for p in players if self._is_starter_player(p)]
        if starters:
            return starters

        size = self._lineup_size()
        if size and len(players) >= size:
            ordered = sorted(players, key=self._lineup_order)
            trimmed = [p for p in ordered if self._player_name(p)]
            return trimmed[:size]
        return []

    def _normalize_player_entry(self, entry: Any) -> Dict[str, Any]:
        if isinstance(entry, dict):
            return entry
        if isinstance(entry, str):
            return {"fullName": entry}
        return {}

    def _lineup_order(self, player: Dict[str, Any]) -> int:
        stats = player.get("statistics", {}) or {}
        for key in ("lineupOrder", "order", "starterOrder"):
            val = player.get(key, stats.get(key))
            if isinstance(val, int):
                return val
            if isinstance(val, str) and val.isdigit():
                return int(val)
        return 9999

    def _is_starter_player(self, player: Dict[str, Any]) -> bool:
        stats = player.get("statistics", {}) or {}
        for key in ("isStarter", "starter", "starting", "starterFlag", "isStarting"):
            val = player.get(key, stats.get(key))
            if isinstance(val, str):
                if val.strip().lower() in ("1", "true", "yes", "y"):
                    return True
            elif val:
                return True
        return False

    def _player_name(self, player: Dict[str, Any]) -> str:
        athlete = player.get("athlete") or {}
        first = (player.get("firstName") or athlete.get("firstName") or "").strip()
        last = (player.get("familyName") or athlete.get("lastName") or athlete.get("familyName") or "").strip()
        if first or last:
            return format_player_initial_name(first, last)
        name = player.get("fullName") or player.get("displayName") or player.get("name")
        if not name and isinstance(athlete, dict):
            name = athlete.get("fullName") or athlete.get("displayName") or athlete.get("name")
        return str(name or "")

    def _player_full_name(self, player: Dict[str, Any]) -> str:
        athlete = player.get("athlete") or {}
        first = (player.get("firstName") or athlete.get("firstName") or "").strip()
        last = (player.get("familyName") or athlete.get("lastName") or athlete.get("familyName") or "").strip()
        if first or last:
            return f"{first} {last}".strip()
        name = player.get("fullName") or player.get("displayName") or player.get("name")
        if not name and isinstance(athlete, dict):
            name = athlete.get("fullName") or athlete.get("displayName") or athlete.get("name")
        return str(name or "")

    def _player_position(self, player: Dict[str, Any]) -> str:
        athlete = player.get("athlete") or {}
        pos = player.get("position") or athlete.get("position")
        if isinstance(pos, dict):
            pos = pos.get("abbreviation") or pos.get("shortName") or pos.get("displayName")
        return str(pos or "")

    def _player_jersey(self, player: Dict[str, Any]) -> str:
        athlete = player.get("athlete") or {}
        jersey = (
            player.get("jerseyNum")
            or player.get("jersey")
            or player.get("jerseyNumber")
            or athlete.get("jersey")
        )
        return str(jersey or "")

    def _mlb_lineup_order(self, player: Dict[str, Any]) -> int | None:
        stats = player.get("statistics") if isinstance(player.get("statistics"), dict) else {}
        for key in ("order", "batOrder", "lineupOrder", "battingOrder"):
            raw = player.get(key)
            if raw in (None, ""):
                raw = stats.get(key)
            if raw in (None, ""):
                continue
            try:
                order = int(str(raw).strip())
            except Exception:
                continue
            if order > 9 and order % 100 == 0:
                order = order // 100
            if order > 0:
                return order
        return None

    def _lineup_size(self) -> int:
        sport = self.sport_name.upper()
        return {
            "NBA": 5,
            "NCAA BASKETBALL": 5,
            "WNBA": 5,
            "NHL": 6,
            "MLB": 9,
            "NFL": 11,
            "NCAA FOOTBALL": 11,
            "MLS": 11,
        }.get(sport, 5)

    def _should_show_lineups(self) -> bool:
        return self._selected_game_status() == "upcoming"

    def _selected_game_status(self) -> str:
        game_id = self.selected_game_id or self._pending_selection_id
        if not game_id:
            return ""
        entry = next((g for g in self.games if g.get("gameId") == game_id), None)
        if not entry:
            return ""
        status = entry.get("status") or entry.get("gameStatus") or entry.get("state")
        text = entry.get("gameStatusText") or entry.get("header")
        return self._normalize_status(status, text)

    def _normalize_status(self, raw: Any, text: Any = None) -> str:
        if isinstance(raw, str):
            normalized = raw.lower()
            if normalized in {"pre", "pre-game", "pre game", "preview", "scheduled", "upcoming"}:
                return "upcoming"
            if normalized in {"post", "final"}:
                return "final"
            if normalized in {"live", "inprogress", "in progress", "ongoing"}:
                return "live"
            return normalized
        if isinstance(raw, int):
            if raw == 3:
                return "final"
            if raw in (0, 1):
                return "upcoming"
            return "live"
        lowered = str(text or "").lower()
        if any(key in lowered for key in ("final", "end", "ended")):
            return "final"
        if any(key in lowered for key in ("am", "pm", "scheduled", "tba", "starts")):
            return "upcoming"
        return ""

    def _game_status_payload(self, game: Dict[str, Any]) -> tuple[str, str, str | None]:
        status_text = str(game.get("gameStatusText") or game.get("statusText") or "Scheduled")
        if self.sport_name.upper() == "MLB":
            status_text = self._mlb_arrow_status_text(status_text)
        status_state = self._normalize_status(game.get("status") or game.get("gameStatus"), status_text)
        start_time = game.get("startTime") or game.get("gameTimeUTC") or game.get("gameTime")
        start_time_local = game.get("startTimeLocal")
        if start_time:
            formatted_start = iso_to_local(start_time)
            if formatted_start != "--:--":
                start_time_local = formatted_start
                if status_state == "upcoming":
                    status_text = formatted_start
        if status_state not in ("live", "upcoming", "final"):
            status_state = "live" if status_text else "upcoming"
        return status_text, status_state, start_time_local

    def _sync_combo_entry_from_game(self, game: Dict[str, Any]) -> None:
        game_id = str(game.get("gameId") or "")
        row = self._combo_game_row_by_id.get(game_id)
        if not row:
            return
        away_team = game.get("awayTeam") or {}
        home_team = game.get("homeTeam") or {}
        away_name = away_team.get("teamName", "Away")
        home_name = home_team.get("teamName", "Home")
        away_score = int(away_team.get("score") or 0)
        home_score = int(home_team.get("score") or 0)
        status_text, status_state, start_time_local = self._game_status_payload(game)
        line_text = f"{away_name} {away_score} @ {home_name} {home_score}"
        self.game_combo.blockSignals(True)
        self.game_combo.setItemText(row, line_text)
        self.game_combo.setItemData(
            row,
            {
                "gameId": game.get("gameId"),
                "away_name": away_name,
                "home_name": home_name,
                "away_score": away_score,
                "home_score": home_score,
                "status_text": status_text,
                "status_state": status_state,
                "startTime": game.get("startTime") or game.get("gameTimeUTC") or game.get("gameTime"),
                "startTimeLocal": start_time_local,
                "away_tricode": (away_team.get("teamTricode") or away_team.get("tricode") or "").upper(),
                "home_tricode": (home_team.get("teamTricode") or home_team.get("tricode") or "").upper(),
            },
            GAME_DATA_ROLE,
        )
        self.game_combo.blockSignals(False)

    def _rebuild_score_lines(self) -> None:
        lines: list[str] = []
        for game in self.games:
            away_team = game.get("awayTeam") or {}
            home_team = game.get("homeTeam") or {}
            away_name = away_team.get("teamName", "Away")
            home_name = home_team.get("teamName", "Home")
            away_score = int(away_team.get("score") or 0)
            home_score = int(home_team.get("score") or 0)
            status_text, _, _ = self._game_status_payload(game)
            lines.append(f"{away_name} {away_score} @ {home_name} {home_score} ({status_text})")
        self.lines = lines

    def _merge_live_game_state(
        self,
        game_id: str,
        *,
        away_score: Any = None,
        home_score: Any = None,
        status_text: str | None = None,
        game_clock: Any = None,
        period: Any = None,
        status: Any = None,
    ) -> None:
        if not game_id:
            return
        updated_game: Dict[str, Any] | None = None
        for idx, game in enumerate(self.games):
            if str(game.get("gameId") or "") != str(game_id):
                continue
            merged = dict(game)
            away_team = dict(merged.get("awayTeam") or {})
            home_team = dict(merged.get("homeTeam") or {})
            if away_score not in (None, ""):
                try:
                    away_team["score"] = int(away_score)
                except Exception:
                    pass
            if home_score not in (None, ""):
                try:
                    home_team["score"] = int(home_score)
                except Exception:
                    pass
            if away_team:
                merged["awayTeam"] = away_team
            if home_team:
                merged["homeTeam"] = home_team
            if status not in (None, ""):
                normalized_status = self._normalize_status(status, status_text)
                if isinstance(status, int):
                    merged["gameStatus"] = status
                    if normalized_status:
                        merged["status"] = normalized_status
                else:
                    merged["status"] = normalized_status or str(status).lower()
                    if merged["status"] == "final":
                        merged["gameStatus"] = 3
                    elif merged["status"] == "upcoming":
                        merged["gameStatus"] = 1
                    elif merged["status"]:
                        merged["gameStatus"] = 2
            if game_clock not in (None, ""):
                merged["gameClock"] = game_clock
            if period not in (None, ""):
                merged["period"] = period if isinstance(period, dict) else {"current": period}
            if status_text:
                merged["gameStatusText"] = status_text
                merged["header"] = status_text
            updated_game = merged
            self.games[idx] = merged
            break
        if updated_game is None:
            return
        self._sync_combo_entry_from_game(updated_game)
        self._rebuild_score_lines()
        self._cache_runtime_scores(self.sport_name, self.games, self.lines, selected_game_id=self.selected_game_id)
        self._update_scores_poll_timer(restart=True)
        self._refresh_nba_merged_ticker(force=True)

    def _set_table_titles(self, show_lineups: bool) -> None:
        left = "LINEUP" if show_lineups else "STATS"
        right = "LINEUP" if show_lineups else "STATS"
        if getattr(self, "away_table_title", None) is not None:
            self.away_table_title.setText(left)
        if getattr(self, "home_table_title", None) is not None:
            self.home_table_title.setText(right)

    def on_game_selected(self, index: int):
        if index <= 0:
            return
        data = self.game_combo.itemData(index, GAME_DATA_ROLE)
        if not isinstance(data, dict):
            return
        game_id = data.get("gameId")
        if not game_id:
            return
        game = next((g for g in self.games if str(g.get("gameId")) == str(game_id)), None)
        if not game:
            return
        if str(self.selected_game_id or "") != str(game.get("gameId") or ""):
            self._clock_state = None
            self.clock_feed_interval_avg = None
        self.selected_game_id = game.get("gameId")
        self._pending_selection_id = None
        self._instant_boxscore_apply = True
        if self.selected_game_id:
            self._start_realtime_for_game(self.selected_game_id)
            self._cache_runtime_scores(self.sport_name, self.games, self.lines, selected_game_id=self.selected_game_id)
            cached = self._runtime_boxscore(self.sport_name, str(self.selected_game_id))
            if cached is None:
                history = self._boxscore_history.get(str(self.selected_game_id))
                if history:
                    cached = history[-1][1]
            if cached is None:
                cached = self._build_boxscore_stub(self.selected_game_id)
            if isinstance(cached, dict):
                try:
                    self.apply_boxscore(cached)
                except Exception:
                    pass
        self.refresh_boxscore()
        self.refresh_pbp()
        self._show_placeholder()

    def _request_logo(self, side: str, team: Dict[str, Any]):
        box = self.away_logo_box if side == "away" else self.home_logo_box
        team_id = team.get("teamId")
        tri = (team.get("teamTricode") or team.get("tricode") or "").upper()
        logo_url = None
        if self.sport_name.upper() == "NBA":
            logo_url = self._team_logo_url(team)
        logo_token = logo_url or tri

        if not (team_id or logo_token):
            self._last_logo_keys[side] = ("", "", "")
            box.set_logo(None)
            if side == "home":
                self.setWindowIcon(self._default_icon)
            return

        key = self._scoped_logo_key(team_id, logo_token)
        if self._last_logo_keys.get(side) == key:
            return
        self._last_logo_keys[side] = key

        future = self._logo_executor.submit(self.backend.load_logo, team_id, logo_token)
        future.add_done_callback(lambda fut, s=side, k=key: self._on_logo_ready(s, k, fut))

    def _scoped_logo_key(self, team_id: Any, logo_token: Any) -> tuple[str, str, str]:
        return (self.sport_name.upper(), str(team_id or ""), str(logo_token or ""))

    def _team_logo_key(self, team: Dict[str, Any]) -> tuple[str, str, str] | None:
        team_id = team.get("teamId") or team.get("id")
        tri = (team.get("teamTricode") or team.get("tricode") or "").upper()
        logo_url = self._team_logo_url(team) if self.sport_name.upper() == "NBA" else None
        logo_token = logo_url or tri
        if not (team_id or logo_token):
            return None
        return self._scoped_logo_key(team_id, logo_token)

    def _queue_combo_logo(self, key: tuple[str, str, str]) -> None:
        if key in self._combo_logo_cache or key in self._combo_logo_pending:
            return
        if not hasattr(self, "_logo_executor") or self._logo_executor is None:
            return
        self._combo_logo_pending.add(key)
        team_id = key[1] or None
        logo_token = key[2] or ""
        future = self._logo_executor.submit(self.backend.load_logo, team_id, logo_token)
        future.add_done_callback(lambda fut, k=key: self._on_combo_logo_ready(k, fut))

    def _team_logo_url(self, team: Dict[str, Any]) -> str | None:
        url = team.get("logoUrl") or team.get("logo")
        if not url:
            logos = team.get("logos") or []
            if logos:
                url = logos[0].get("href") or logos[0].get("url")
        if isinstance(url, str):
            if url.startswith("http"):
                return url
            if Path(url).exists():
                return url
        return None

    def _on_logo_ready(self, side: str, key: tuple[str, str, str], future):
        if not self._alive:
            return
        try:
            data = future.result()
        except Exception:
            data = None
        if self._last_logo_keys.get(side) != key:
            return
        self.logo_ready.emit(side, data)

    def _on_combo_logo_ready(self, key: tuple[str, str, str], future):
        if not self._alive:
            return
        try:
            data = future.result()
        except Exception:
            data = None
        self.combo_logo_ready.emit(key, data)

    def _apply_logo_bytes(self, side: str, data: bytes | None):
        box = self.away_logo_box if side == "away" else self.home_logo_box
        if data:
            pix = self._load_logo_pixmap(data, box.width())
            if pix:
                box.set_logo(pix)
                if side == "home":
                    self.setWindowIcon(QIcon(pix))
                return
        # Keep current logo/icon on transient fetch failures to avoid flicker.

    def _apply_combo_logo_bytes(self, key: tuple[str, str, str], data: bytes | None) -> None:
        self._combo_logo_pending.discard(key)
        if not data:
            return
        pix = self._load_logo_pixmap(data, GAME_LOGO_SIZE)
        if not pix:
            return
        pix = pix.scaled(GAME_LOGO_SIZE, GAME_LOGO_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._combo_logo_cache[key] = pix
        if not hasattr(self, "game_combo"):
            return
        for row in range(1, self.game_combo.count()):
            if self.game_combo.itemData(row, GAME_LOGO_AWAY_KEY_ROLE) == key:
                self.game_combo.setItemData(row, pix, GAME_LOGO_AWAY_ROLE)
            if self.game_combo.itemData(row, GAME_LOGO_HOME_KEY_ROLE) == key:
                self.game_combo.setItemData(row, pix, GAME_LOGO_HOME_ROLE)
        self.game_combo.view().viewport().update()
        if self.sport_name.upper() == "NBA":
            self._refresh_nba_merged_ticker(force=True)

    def _load_logo_pixmap(self, data: bytes, target_size: int) -> QPixmap | None:
        if not data:
            return None
        lower = data[:200].lower()
        is_svg = lower.strip().startswith(b"<svg") or b"<svg" in lower
        if is_svg:
            try:
                from PySide6.QtSvg import QSvgRenderer  # type: ignore

                renderer = QSvgRenderer(data)
                dim = max(target_size, renderer.defaultSize().width(), renderer.defaultSize().height(), 220)
                dim = min(dim, 512)
                pm = QPixmap(dim, dim)
                pm.fill(Qt.transparent)
                painter = QPainter(pm)
                painter.setRenderHint(QPainter.Antialiasing, True)
                renderer.render(painter, QRectF(0, 0, dim, dim))
                painter.end()
                return pm
            except Exception:
                pass

        pix = QPixmap()
        if pix.loadFromData(data):
            return pix
        return None

    def _clear_ui_for_no_games(self, message: str = "No games today."):
        self.center_panel.set_state("Q-", "00:00", "", "--")
        self.away_name.setText("AWAY TEAM")
        self.home_name.setText("HOME TEAM")
        self.away_city.setText("")
        self.home_city.setText("")
        self.away_record.setText("--")
        self.home_record.setText("--")
        self.away_logo_box.set_logo(None)
        self.home_logo_box.set_logo(None)
        self.apply_team_logo_style(self.away_logo_box, "AWY", ACCENT, ACCENT_SOFT)
        self.apply_team_logo_style(self.home_logo_box, "HME", ACCENT_SOFT, ACCENT)
        self._set_top_background(ACCENT, ACCENT_SOFT, ACCENT_SOFT, ACCENT)
        left_text = self._top_text_color(ACCENT)
        right_text = self._top_text_color(ACCENT_SOFT)
        self.away_name.setStyleSheet(
            f"font-size: 20px; font-weight: 900; color: {left_text}; letter-spacing: 0.8px;"
        )
        self.home_name.setStyleSheet(
            f"font-size: 20px; font-weight: 900; color: {right_text}; letter-spacing: 0.8px;"
        )
        city_size = CITY_FONT_SIZE
        self.away_city.setStyleSheet(
            f"font-size: {city_size}px; font-weight: 800; color: {self._with_alpha(left_text, 0.9)}; letter-spacing: 0.6px;"
        )
        self.home_city.setStyleSheet(
            f"font-size: {city_size}px; font-weight: 800; color: {self._with_alpha(right_text, 0.9)}; letter-spacing: 0.6px;"
        )
        self.away_record.setStyleSheet(f"color: {self._with_alpha(left_text, 0.85)}; font-size: 12px; font-weight: 700;")
        self.home_record.setStyleSheet(f"color: {self._with_alpha(right_text, 0.85)}; font-size: 12px; font-weight: 700;")
        self._set_score_style(self.away_score, left_text)
        self._set_score_style(self.home_score, right_text)
        self._apply_control_colors(left_text, right_text)
        self.away_score.setText("0")
        self.home_score.setText("0")
        self.away_timeouts.set_timeouts(None)
        self.home_timeouts.set_timeouts(None)
        if self.sport_name.upper() == "NHL":
            self.away_penalties.setText("PIM --")
            self.home_penalties.setText("PIM --")
            self.away_penalty_clock.setText("PEN --")
            self.home_penalty_clock.setText("PEN --")
            self.away_penalties.setVisible(False)
            self.home_penalties.setVisible(False)
            self.away_penalty_clock.setVisible(True)
            self.home_penalty_clock.setVisible(True)
            self._away_meta_stack.setCurrentWidget(self._away_penalty_meta)
            self._home_meta_stack.setCurrentWidget(self._home_penalty_meta)
        else:
            self._away_meta_stack.setCurrentWidget(self.away_timeouts)
            self._home_meta_stack.setCurrentWidget(self.home_timeouts)
        self.away_table.setRowCount(0)
        self.home_table.setRowCount(0)
        self.setWindowIcon(self._default_icon)
        self._pending_selection_id = None
        self._displayed_boxscore_key = None
        self._next_display_at = None
        self.lines = []
        self.games = []
        self._clock_state = None
        self.center_panel.set_state("Q-", "00:00", "", "--")
        if hasattr(self, "pbp_bar"):
            self.pbp_bar.setVisible(False)
        self._pbp_lines = []
        self._refresh_nba_merged_ticker(force=True, fallback=message or "No games today.")
        pbp_label = getattr(self, "pbp_ticker_label", None)
        if isinstance(pbp_label, TickerLabel):
            pbp_label.stop_ticker()
        if hasattr(self, "game_combo"):
            self.game_combo.blockSignals(True)
            try:
                self.game_combo.setItemText(0, message or "No games today.")
            except Exception:
                pass
            self.game_combo.blockSignals(False)
        self._show_placeholder()
        try:
            if self.logic:
                self.logic.stop_realtime()
        except Exception:
            pass
        self._update_boxscore_poll_timer()

    def closeEvent(self, event):
        self._alive = False
        self._flush_cached_state()
        if self._active_player_card is not None:
            try:
                self._active_player_card.close()
            except Exception:
                pass
        try:
            if self.logic:
                self.logic.stop_realtime()
        except Exception:
            pass
        self._executor.shutdown(wait=False)
        if getattr(self, "_logo_executor", None) is not None:
            self._logo_executor.shutdown(wait=False)
        super().closeEvent(event)

    def _remaining_delay_ms(self) -> int:
        if self._next_display_at is None:
            return self.display_delay_ms
        remaining = int(max(0.0, (self._next_display_at - time.monotonic()) * 1000))
        return remaining or 1

    def _compute_clock_state(
        self,
        period_text: str,
        raw_secs: float | None,
        shot_val: Any,
        fallback_clock_text: str,
        *,
        force_live: bool = False,
        buffer_sec: float | None = None,
        stale_window_sec: float | None = None,
        source: str = "boxscore",
    ) -> tuple[str, str, Dict[str, Any]]:
        """
        Normalize incoming clock + shot clock into display text and tick state.
        Keeps the display from bouncing up a second when the official clock is stopped.
        """
        prev = self._clock_state or {}
        sport = self.sport_name.upper()
        count_up = sport == "MLS"
        prev_raw = prev.get("raw_secs")
        period_changed = prev.get("period") not in (None, period_text)
        buffer = self.clock_buffer_sec if buffer_sec is None else buffer_sec
        stale_window_default = self.clock_feed_stale_sec if stale_window_sec is None else stale_window_sec

        # Count-down sports decrease the raw clock; MLS increases elapsed time.
        raw_running = False
        clock_running = False
        synthetic_window_sec = None
        now = time.monotonic()
        last_feed_ts = prev.get("last_feed_ts", now)
        feed_interval_avg = prev.get("feed_interval_avg", self.clock_feed_interval_avg)
        feed_advanced = prev_raw is None or (raw_secs is not None and raw_secs != prev_raw)
        if raw_secs is None:
            raw_running = False
        elif period_changed or prev_raw is None:
            raw_running = True
        else:
            delta_raw = (raw_secs - prev_raw) if count_up else (prev_raw - raw_secs)
            if delta_raw > 0.05:
                raw_running = True
            elif ((prev_raw - raw_secs) if count_up else (raw_secs - prev_raw)) > 30:
                raw_running = True
            else:
                raw_running = False
        clock_running = raw_running
        if force_live and raw_secs is not None:
            if feed_advanced:
                interval = max(0.0, now - last_feed_ts)
                if interval > 0:
                    if feed_interval_avg is None:
                        feed_interval_avg = interval
                    else:
                        feed_interval_avg = (feed_interval_avg * 0.7) + (interval * 0.3)
                last_feed_ts = now
            else:
                stale_window = stale_window_default
                if feed_interval_avg is not None:
                    stale_window = max(stale_window, min(60.0, feed_interval_avg * 1.5))
                if sport == "NBA":
                    synthetic_window = min(stale_window, 2.0)
                elif sport == "NHL":
                    synthetic_window = min(stale_window, 3.0)
                elif sport == "MLS":
                    synthetic_window = min(stale_window, 8.0)
                else:
                    synthetic_window = min(stale_window, 4.0)
                synthetic_window_sec = synthetic_window
                if (prev.get("running") or prev.get("raw_running")) and (now - last_feed_ts) <= synthetic_window:
                    clock_running = True
            if synthetic_window_sec is None and sport != "MLS":
                synthetic_window_sec = 2.0 if sport == "NBA" else (3.0 if sport == "NHL" else 4.0)
            if sport == "NHL" and raw_secs <= 0.1:
                clock_running = False
            elif sport == "MLS":
                # Soccer clocks count up continuously while the period is active even
                # if ESPN leaves the raw clock unchanged for long stretches.
                clock_running = True

        clock_secs = None
        snap_to_official_stop = False
        if (
            sport == "NBA"
            and raw_secs is not None
            and prev_raw is not None
            and abs(float(raw_secs) - float(prev_raw)) <= 0.05
            and prev.get("clock_secs") is not None
            and float(raw_secs) > (float(prev.get("clock_secs")) + 0.75)
            and not raw_running
        ):
            # If the official clock is unchanged but our synthetic timer ran low,
            # snap back to the feed instead of preserving the drifted local value.
            snap_to_official_stop = True

        if raw_secs is not None:
            clock_secs = max(0.0, raw_secs + buffer) if count_up else max(0.0, raw_secs - buffer)
            # If the feed isn't moving, hold at the lowest seen value to avoid flicker
            if not clock_running and prev.get("clock_secs") is not None and not period_changed and not snap_to_official_stop:
                if count_up:
                    clock_secs = max(prev["clock_secs"], clock_secs)
                else:
                    clock_secs = min(prev["clock_secs"], clock_secs)
            # Prevent small upward jumps that cause the display to bounce (ex: 5:59 -> 6:00 -> 5:59).
            prev_clock_secs = prev.get("clock_secs")
            if prev_clock_secs is not None and not period_changed:
                raw_jump = False
                if prev_raw is not None and raw_secs is not None and (
                    ((prev_raw - raw_secs) if count_up else (raw_secs - prev_raw)) > 30
                ):
                    raw_jump = True
                if count_up and not raw_jump and clock_secs < (prev_clock_secs - 0.05):
                    clock_secs = prev_clock_secs
                elif not count_up and not raw_jump and clock_secs > (prev_clock_secs + 0.05):
                    if not snap_to_official_stop and sport == "NBA":
                        # Prevent same-period clock regressions caused by stale/out-of-order packets.
                        clock_secs = prev_clock_secs
                    elif not snap_to_official_stop and sport == "NHL":
                        clock_secs = prev_clock_secs
                    elif not snap_to_official_stop:
                        if (clock_secs - prev_clock_secs) <= 0.5:
                            clock_secs = prev_clock_secs

        clock_text = self._format_clock(clock_secs) if clock_secs is not None else (fallback_clock_text or "")
        shot_secs = self._shot_to_seconds(shot_val)
        shot_text = self.backend.format_shotclock(shot_val) if shot_val not in (None, "", "--") else "--"

        state = {
            "period": period_text,
            "clock_secs": clock_secs,
            "shot_secs": shot_secs,
            "raw_secs": raw_secs,
            "running": clock_running,
            "raw_running": raw_running,
            "last_ts": now,
            "last_feed_ts": last_feed_ts,
            "feed_interval_avg": feed_interval_avg,
            "source": source,
            "count_up": count_up,
            "synthetic_window_sec": synthetic_window_sec,
        }
        self.clock_feed_interval_avg = feed_interval_avg
        return clock_text, shot_text, state

    def _preserve_bottom_labels_for_clock(self, sport: str) -> bool:
        return sport in {"NBA", "MLB", "NHL", "MLS"}

    def _apply_clock(self, data: Dict[str, Any]):
        sport = self.sport_name.upper()
        # Avoid live NBA clock oscillation from racing boxscore vs realtime updates.
        if sport == "NBA" and self.feed_delay_ms <= 0 and self._selected_game_live():
            prev = self._clock_state or {}
            prev_source = prev.get("source")
            prev_feed_ts = prev.get("last_feed_ts") or prev.get("last_ts")
            if prev_source == "realtime" and prev_feed_ts:
                try:
                    if (time.monotonic() - float(prev_feed_ts)) <= 4.0:
                        return
                except Exception:
                    pass

        game = data.get("game") or {}
        shot_val = data.get("shotclock")
        period_text = self._format_period_badge({**game, "_header": data.get("header")})
        raw_clock = game.get("gameClock") or game.get("gameClockText") or ""
        if not raw_clock:
            raw_clock = self._extract_clock_text(game.get("gameStatusText") or data.get("header"))
        raw_secs = self._clock_to_seconds(raw_clock)
        force_live, buffer_sec, stale_window_sec = self._clock_sync_settings(sport, period_text, data.get("header"))
        fallback_clock = self._extract_clock_text(raw_clock)
        if raw_secs is None and force_live:
            header_clock = self._extract_clock_text(game.get("gameStatusText") or data.get("header"))
            raw_secs = self._clock_to_seconds(header_clock)
            if header_clock:
                fallback_clock = header_clock
        clock_text, shot_display, clock_state = self._compute_clock_state(
            period_text,
            raw_secs,
            shot_val,
            fallback_clock or data.get("header", ""),
            force_live=force_live,
            buffer_sec=buffer_sec,
            stale_window_sec=stale_window_sec,
            source="boxscore",
        )
        if sport == "NHL":
            clock_text = self._clean_nhl_clock_text(clock_text)
        is_active = self._is_game_active(game, period_text, data.get("header"))
        if not is_active:
            clock_text = "00:00"
            clock_state["clock_secs"] = 0.0
            clock_state["running"] = False
        self._apply_period_label_style(sport)
        bottom_left = ""
        bottom_center = ""
        bottom_right = shot_display
        away_tri = None
        home_tri = None
        if self._preserve_bottom_labels_for_clock(sport):
            bottom_left = self.center_panel.bottom_left.text()
            bottom_center = self.center_panel.bottom_center.text()
            bottom_right = self.center_panel.bottom_right.text()
        elif sport == "NCAA BASKETBALL":
            bottom_left = "BONUS" if self._team_in_bonus(data.get("away") or {}) else self._team_fouls_text(data.get("away") or {})
            bottom_center = "FOULS"
            bottom_right = "BONUS" if self._team_in_bonus(data.get("home") or {}) else self._team_fouls_text(data.get("home") or {})
        elif sport == "NFL":
            away = data.get("away") or {}
            home = data.get("home") or {}
            away_tri = (away.get("teamTricode") or "AWY")[:3].upper()
            home_tri = (home.get("teamTricode") or "HME")[:3].upper()
            bottom_left = away_tri
            bottom_center = self._down_text_from_game(game)
            bottom_right = home_tri
        self.center_panel.set_state(period_text, clock_text, bottom_left, bottom_right, bottom_center)
        if sport == "NFL":
            self._apply_nfl_possession_highlight(game, away_tri, home_tri)
        else:
            self._reset_center_bottom_styles()
        self._clock_state = clock_state

    def _down_text_from_game(self, game: Dict[str, Any]) -> str:
        situation = game.get("situation") or {}
        for key in ("shortDownDistanceText", "downDistanceText"):
            val = game.get(key) or situation.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return ""

    def _is_live_clock(self, period_text: str, header: Any) -> bool:
        status = str(header or "").lower()
        if any(tag in status for tag in ("final", "postponed", "canceled", "cancelled", "tba", "scheduled")):
            return False
        if "intermission" in status:
            return False
        if re.search(r"\bht\b", status):
            return False
        if any(tag in status for tag in ("am", "pm", "starts", "start")):
            return False
        if period_text in ("FINAL", "HALF TIME", "HT", "PK", "Q-", "H-"):
            return False
        return True

    def _is_shootout_status(self, game: Dict[str, Any], header: Any) -> bool:
        text = f"{game.get('gameStatusText') or ''} {game.get('statusText') or ''} {header or ''}"
        upper = text.upper()
        return "SHOOTOUT" in upper or re.search(r"\bSO\b", upper) is not None

    def _clock_sync_settings(self, sport: str, period_text: str, header: Any) -> tuple[bool, float, float]:
        if not self._is_game_active({}, period_text, header):
            return False, self.clock_buffer_sec, self.clock_feed_stale_sec
        sport_upper = (sport or "").upper()
        buffer_sec = 0.0
        if sport_upper == "NBA":
            return True, buffer_sec, 2.0
        if sport_upper == "NCAA BASKETBALL":
            return True, buffer_sec, 2.5
        if sport_upper == "NHL":
            return True, buffer_sec, 3.0
        if sport_upper in ("NFL", "NCAA FOOTBALL"):
            return True, buffer_sec, 4.0
        if sport_upper == "MLS":
            return True, buffer_sec, 8.0
        return False, buffer_sec, self.clock_feed_stale_sec

    def _is_game_active(self, game: Dict[str, Any], period_text: str, header: Any) -> bool:
        period_upper = (period_text or "").upper()
        if period_upper in ("FINAL", "HALF TIME", "HT", "PK", "INTERMISSION", "INT", "Q-", "H-", "P-"):
            return False
        if period_upper.startswith("INTERMISSION"):
            return False
        if period_upper.startswith("INT"):
            return False
        if period_upper.startswith("END OF"):
            return False
        status_val = game.get("gameStatus") or game.get("status")
        if isinstance(status_val, int):
            if status_val == 2:
                return True
            if status_val in (0, 1) or status_val >= 3:
                return False
        return self._is_live_clock(period_text, header)

    def _reset_center_bottom_styles(self) -> None:
        if self.sport_name.upper() == "NBA":
            self.center_panel.bottom_left.setStyleSheet(NBA_CENTER_BOTTOM_LEFT_STYLE)
            self.center_panel.bottom_center.setStyleSheet(NBA_CENTER_BOTTOM_CENTER_STYLE)
            self.center_panel.bottom_right.setStyleSheet(NBA_CENTER_BOTTOM_RIGHT_STYLE)
            return
        self.center_panel.bottom_left.setStyleSheet(CENTER_BOTTOM_LEFT_STYLE)
        self.center_panel.bottom_center.setStyleSheet(CENTER_BOTTOM_CENTER_STYLE)
        self.center_panel.bottom_right.setStyleSheet(CENTER_BOTTOM_RIGHT_STYLE)

    def _nfl_possession_label_style(self, active: bool, base_style: str) -> str:
        if not active:
            return base_style
        return (
            f"color: {POSSESSION_HIGHLIGHT_TEXT}; font-size: 11px; font-weight: 700; "
            f"background-color: {POSSESSION_HIGHLIGHT}; border: 1px solid {POSSESSION_HIGHLIGHT_BORDER}; "
            "border-radius: 4px; padding: 2px 4px;"
        )

    def _possession_tricode_from_text(self, text: Any, away_tri: str, home_tri: str) -> str | None:
        if not text:
            return None
        upper = str(text).upper()
        for tri in (away_tri, home_tri):
            if tri and re.search(rf"\b{re.escape(tri)}\b", upper):
                return tri
        tokens = re.findall(r"\b[A-Z]{2,4}\b", upper)
        for token in tokens:
            if token in (away_tri, home_tri):
                return token
        return None

    def _apply_nfl_possession_highlight(self, game: Dict[str, Any], away_tri: str | None, home_tri: str | None) -> None:
        away_tri = (away_tri or "AWY").upper()
        home_tri = (home_tri or "HME").upper()
        possession_tri = self._possession_tricode_from_text(game.get("possessionText"), away_tri, home_tri)
        self._nfl_possession_tricode = possession_tri
        self.center_panel.bottom_left.setStyleSheet(
            self._nfl_possession_label_style(possession_tri == away_tri, CENTER_BOTTOM_LEFT_STYLE)
        )
        self.center_panel.bottom_right.setStyleSheet(
            self._nfl_possession_label_style(possession_tri == home_tri, CENTER_BOTTOM_RIGHT_STYLE)
        )
        self.center_panel.bottom_center.setStyleSheet(CENTER_BOTTOM_CENTER_STYLE)

    def _has_live_game(self) -> bool:
        for g in self.games:
            status = str(g.get("status") or "").lower()
            if status == "live":
                return True
            status_val = g.get("gameStatus") or g.get("status")
            if isinstance(status_val, int) and status_val == 2:
                return True
            status_text = str(g.get("gameStatusText") or g.get("statusText") or "").lower()
            if "q" in status_text or "period" in status_text or "ot" in status_text:
                return True
        return False

    def _game_start_time_label(self, game: Dict[str, Any]) -> str:
        for key in ("gameTimeLocal", "gameTimeUTC", "gameEt", "startTime", "gameTime"):
            val = game.get(key)
            if isinstance(val, str) and val:
                if "T" in val:
                    label = iso_to_local(val)
                    if label != "--:--":
                        return label
                else:
                    return val
        header = str(game.get("_header") or game.get("gameStatusText") or "")
        if re.search(r"\d{1,2}:\d{2}", header):
            return header.strip()
        return ""

    @staticmethod
    def _mlb_arrow_status_text(text: Any) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        if raw.startswith(("▲", "▼")):
            return raw
        if raw.startswith(("↑", "↓")):
            return raw.replace("↑", "▲", 1).replace("↓", "▼", 1)
        if re.match(r"^(top|t)\b", raw, re.IGNORECASE):
            return re.sub(r"^(top|t)\b\.?\s*", "▲ ", raw, flags=re.IGNORECASE)
        if re.match(r"^(bottom|bot|b)\b", raw, re.IGNORECASE):
            return re.sub(r"^(bottom|bot|b)\b\.?\s*", "▼ ", raw, flags=re.IGNORECASE)
        return raw

    def _format_period_badge(self, game: Dict[str, Any]) -> str:
        status_val = game.get("status") or game.get("gameStatus")
        raw_status = str(game.get("gameStatusText") or game.get("statusText") or game.get("_header") or "")
        raw_clock = str(game.get("gameClockText") or game.get("gameClock") or "")
        status_text = raw_status.lower()
        clock_text = raw_clock.lower()
        sport = self.sport_name.upper()
        if (
            "halftime" in status_text
            or "half time" in status_text
            or "halftime" in clock_text
            or "half time" in clock_text
        ):
            return "HALF TIME"
        if isinstance(status_val, int) and status_val >= 3:
            if sport in ("NBA", "NCAA BASKETBALL"):
                return "FINAL"
            if not self._has_live_game():
                time_label = self._game_start_time_label(game)
                if time_label:
                    return time_label
            return "FINAL"
        if any(k in status_text for k in ("final", "endgame", "ended")):
            if sport in ("NBA", "NCAA BASKETBALL"):
                return "FINAL"
            if not self._has_live_game():
                time_label = self._game_start_time_label(game)
                if time_label:
                    return time_label
            return "FINAL"
        period_field = game.get("period")
        current_period = None
        if isinstance(period_field, dict):
            current_period = period_field.get("current")
        elif isinstance(period_field, int):
            current_period = period_field
        if not isinstance(current_period, int):
            header_text = str(game.get("_header") or "")
            combined = f"{raw_status} {raw_clock} {header_text}".upper()
            if sport == "MLS":
                if any(tag in combined for tag in ("HALF TIME", "HALFTIME")) or re.search(r"\bHT\b", combined):
                    return "HT"
                if any(tag in combined for tag in ("PEN", "SHOOTOUT", "SHOOT OUT")) or re.search(r"\bPK\b", combined):
                    return "PK"
                if any(tag in combined for tag in ("AET", "EXTRA")):
                    return "ET"
                soccer_clock = self._extract_clock_text(raw_clock or raw_status or header_text)
                minute_match = re.match(r"(\d{1,3})'", soccer_clock)
                if minute_match:
                    try:
                        minute = int(minute_match.group(1))
                    except Exception:
                        minute = 0
                    return "2H" if minute >= 46 else "1H"
            time_label = raw_status.strip()
            if time_label and time_label.upper() not in ("SCHEDULED", "TBA"):
                return time_label
            if sport in ("NBA", "NFL", "NCAA FOOTBALL"):
                match = re.search(r"\bQ([1-4])\b", combined) or re.search(r"\b([1-4])(ST|ND|RD|TH)\b", combined)
                if match:
                    try:
                        current_period = int(match.group(1))
                    except Exception:
                        current_period = None
            elif sport == "NCAA BASKETBALL":
                match = re.search(r"\b([12])(ST|ND)\s+HALF\b", combined)
                if match:
                    try:
                        current_period = int(match.group(1))
                    except Exception:
                        current_period = None
                elif "OT" in combined:
                    current_period = 3
            elif sport == "NHL":
                match = re.search(r"\bPERIOD\s*([1-3])\b", combined) or re.search(
                    r"\b([1-3])(ST|ND|RD|TH)\b", combined
                )
                if match:
                    try:
                        current_period = int(match.group(1))
                    except Exception:
                        current_period = None
                elif "SO" in combined or "SHOOTOUT" in combined:
                    return "SO"
                elif "OT" in combined:
                    return "OT"
            if not isinstance(current_period, int):
                if sport == "NHL":
                    return "P-"
                if sport == "NCAA BASKETBALL":
                    return "H-"
                return "Q-"
        if sport == "NCAA BASKETBALL":
            clock_secs = self._clock_to_seconds(game.get("gameClock"))
            if current_period == 1 and clock_secs is not None and clock_secs <= 0.1:
                return "HALF TIME"
            if current_period == 1:
                return "1ST HALF"
            if current_period == 2:
                return "2ND HALF"
            if current_period == 3:
                return "OT"
            if current_period > 3:
                return f"OT{current_period - 2}"
            return "H-"
        if sport in ("NBA", "NFL", "NCAA FOOTBALL"):
            clock_secs = self._clock_to_seconds(game.get("gameClock"))
            if current_period == 2 and clock_secs is not None and clock_secs <= 0.1:
                return "HALF TIME"
            if current_period in (1, 3) and clock_secs is not None and clock_secs <= 0.1:
                return f"END OF {self._ordinal_period_label(current_period)}"
        if sport == "NHL":
            clock_source = game.get("gameClock") or raw_clock or raw_status
            clock_secs = self._clock_to_seconds(clock_source)
            intermission_label = "INT"
            if isinstance(current_period, int) and current_period in (1, 2):
                intermission_label = f"INT {current_period}"
            combined_status = f"{raw_status} {game.get('_header') or ''} {raw_clock}".lower()
            if "intermission" in status_text or "intermission" in clock_text:
                return intermission_label
            if current_period in (1, 2):
                if clock_secs is not None and clock_secs <= 0.1:
                    return intermission_label
                if "end of" in status_text:
                    return intermission_label
            if "shootout" in combined_status or re.search(r"\bso\b", combined_status):
                return "SO"
            if current_period in (1, 2, 3):
                return f"P {current_period}"
            if current_period == 4:
                return "OT"
            if current_period > 4:
                return f"OT {current_period - 3}"
            return "P-"
        if sport == "MLS":
            combined_status = f"{raw_status} {game.get('_header') or ''} {raw_clock}".upper()
            if any(tag in combined_status for tag in ("HALF TIME", "HALFTIME")) or re.search(r"\bHT\b", combined_status):
                return "HT"
            if any(tag in combined_status for tag in ("PEN", "SHOOTOUT", "SHOOT OUT")) or re.search(r"\bPK\b", combined_status):
                return "PK"
            if any(tag in combined_status for tag in ("AET", "EXTRA")):
                return "ET"
            if isinstance(current_period, int):
                if current_period == 1:
                    return "1H"
                if current_period == 2:
                    return "2H"
                if current_period >= 3:
                    return "ET"
            if any(tag in combined_status for tag in ("1ST HALF", "FIRST HALF")):
                return "1H"
            if any(tag in combined_status for tag in ("2ND HALF", "SECOND HALF")):
                return "2H"
            return "1H" if self._is_live_clock("1H", raw_status or raw_clock or game.get("_header")) else "Q-"
        if sport == "MLB":
            # For live games use ESPN inning text, but render half-inning with arrows.
            if raw_status.strip():
                return self._mlb_arrow_status_text(raw_status)
            if isinstance(current_period, int):
                return f"Inn {current_period}"
            return "MLB"
        mapping = {1: "1ST", 2: "2ND", 3: "3RD", 4: "4TH"}
        return mapping.get(current_period, f"OT{current_period - 4}" if current_period > 4 else f"Q{current_period}")

    @staticmethod
    def _ordinal_period_label(period: int) -> str:
        mapping = {1: "1ST", 2: "2ND", 3: "3RD", 4: "4TH"}
        return mapping.get(period, str(period))

    def _clock_to_seconds(self, clock_raw: Any) -> float | None:
        if not clock_raw:
            return None
        if isinstance(clock_raw, (int, float)):
            return float(clock_raw)
        if isinstance(clock_raw, str):
            text = clock_raw.strip()
            if not text:
                return None
            if re.search(r"\b(am|pm)\b", text.lower()):
                return None
            if text.startswith("PT"):
                try:
                    match = re.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", text)
                    if not match:
                        return None
                    mins = float(match.group(1) or 0)
                    secs = float(match.group(2) or 0)
                    return mins * 60 + secs
                except Exception:
                    return None
            match = re.search(r"(\d{1,2})\s*:\s*(\d{2})(?:\.(\d+))?", text)
            if match:
                try:
                    mins = int(match.group(1))
                    secs = int(match.group(2))
                    frac = float(f"0.{match.group(3)}") if match.group(3) else 0.0
                    return (mins * 60) + secs + frac
                except Exception:
                    return None
            match = re.search(r":(\d{2})(?:\.(\d+))?", text)
            if match:
                try:
                    secs = int(match.group(1))
                    frac = float(f"0.{match.group(2)}") if match.group(2) else 0.0
                    return secs + frac
                except Exception:
                    return None
            if re.fullmatch(r"\d+(?:\.\d+)?", text):
                try:
                    return float(text)
                except Exception:
                    return None
        return None

    def _shot_to_seconds(self, val: Any) -> float | None:
        if val in (None, "", "--"):
            return None
        try:
            return float(val)
        except Exception:
            return None

    def _format_clock(self, seconds: float) -> str:
        minutes = int(max(0, seconds) // 60)
        secs = int(max(0, seconds) % 60)
        return f"{minutes}:{secs:02d}"

    def _tick_clock(self):
        if not self._clock_state:
            return
        now = time.monotonic()
        state = self._clock_state
        last = state.get("last_ts", now)
        delta = now - last
        clock_secs = state.get("clock_secs")
        shot_secs = state.get("shot_secs")
        updated = False
        count_up = bool(state.get("count_up"))
        synthetic_window = state.get("synthetic_window_sec")
        source = str(state.get("source") or "")
        last_feed_ts = state.get("last_feed_ts")
        if (
            self.sport_name.upper() == "NBA"
            and source == "realtime"
            and not count_up
            and synthetic_window not in (None, "")
            and last_feed_ts is not None
            and (now - float(last_feed_ts)) > float(synthetic_window)
        ):
            state["running"] = False
        if clock_secs is not None and state.get("running", True):
            if count_up:
                clock_secs = max(0.0, clock_secs + delta)
            else:
                clock_secs = max(0.0, clock_secs - delta)
            updated = True
        if not updated:
            state["last_ts"] = now
            return
        state["clock_secs"] = clock_secs
        state["shot_secs"] = shot_secs
        state["last_ts"] = now
        period = state.get("period", "")
        current_left_text = self.center_panel.bottom_left.text()
        current_center_text = self.center_panel.bottom_center.text()
        current_right_text = self.center_panel.bottom_right.text()
        if clock_secs is not None:
            self.center_panel.set_state(period, self._format_clock(clock_secs), current_left_text, current_right_text, current_center_text)
        penalty_running = bool(state.get("running", True))
        self._tick_penalty_state(now, penalty_running)

    def _tick_penalty_state(self, now: float, running: bool) -> None:
        if self.sport_name.upper() != "NHL":
            return
        if not self._penalty_state:
            return
        state = self._penalty_state
        last_ts = state.get("last_ts", now)
        delta = now - last_ts
        state["last_ts"] = now
        if not running or delta <= 0:
            return
        updated = False
        for side in ("left", "right"):
            values = state.get(side) or []
            if not values:
                continue
            new_values = [max(0.0, val - delta) for val in values]
            new_values = [val for val in new_values if val > 0.2]
            if new_values != values:
                state[side] = new_values
                updated = True
        if not updated:
            return
        left_label, left_text = self._nhl_penalty_clock_text(state.get("left") or [], state.get("right") or [], {})
        right_label, right_text = self._nhl_penalty_clock_text(state.get("right") or [], state.get("left") or [], {})
        self.away_penalty_clock.setText(f"{left_label} {left_text}")
        self.home_penalty_clock.setText(f"{right_label} {right_text}")

    def _update_bottom_bar(self, away: Dict[str, Any], home: Dict[str, Any]):
        sport = self.sport_name.upper()
        if sport != "NBA":
            self._pbp_lines = []
        self._refresh_nba_merged_ticker()

    def _elide_label_text(self, label: QLabel, text: str) -> str:
        width = max(0, label.width() - 12)
        if width <= 0:
            return text
        metrics = QFontMetrics(label.font())
        return metrics.elidedText(text, Qt.ElideRight, width)

    def _begin_fade(self, widget: QWidget, *, duration_ms: int = FADE_DURATION_MS) -> QPropertyAnimation | None:
        effect = widget.graphicsEffect()
        if effect is not None and not isinstance(effect, QGraphicsOpacityEffect):
            return None
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        prev = self._fade_anims.pop(widget, None)
        if prev:
            try:
                prev.stop()
            except RuntimeError:
                pass
            try:
                prev.deleteLater()
            except RuntimeError:
                pass
        anim = QPropertyAnimation(effect, b"opacity", widget)
        anim.setDuration(duration_ms)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def _clear_fade_anim() -> None:
            current = self._fade_anims.get(widget)
            if current is anim:
                self._fade_anims.pop(widget, None)
            try:
                anim.deleteLater()
            except RuntimeError:
                pass

        anim.finished.connect(_clear_fade_anim)
        self._fade_anims[widget] = anim
        return anim

    def _set_label_text(
        self,
        label: QLabel,
        text: str,
        *,
        animate: bool = False,
        fade_widget: QWidget | None = None,
        duration_ms: int = FADE_DURATION_MS,
    ) -> None:
        if label.text() == text:
            return
        anim = None
        if animate:
            target = fade_widget or label
            anim = self._begin_fade(target, duration_ms=duration_ms)
        label.setText(text)
        if anim:
            try:
                anim.start()
            except RuntimeError:
                pass

    def _score_style(self, color: str) -> str:
        return f"font-size: 58px; font-weight: 900; color: {color};"

    def _set_score_style(self, label: QLabel, color: str) -> None:
        label.setStyleSheet(self._score_style(color))
        self._score_flash_tokens[label] = object()

    def _flash_score_label(
        self,
        label: QLabel,
        *,
        base_color: str,
        flash_color: str = THREE_POINT_FLASH,
        duration_ms: int = 260,
    ) -> None:
        token = object()
        self._score_flash_tokens[label] = token
        label.setStyleSheet(self._score_style(flash_color))

        def _restore() -> None:
            if self._score_flash_tokens.get(label) is not token:
                return
            label.setStyleSheet(self._score_style(base_color))

        QTimer.singleShot(duration_ms, _restore)

    def _score_delta(self, prev_team: Dict[str, Any] | None, team: Dict[str, Any]) -> int | None:
        if not prev_team:
            return None
        prev_id = str(prev_team.get("teamId") or prev_team.get("id") or "")
        team_id = str(team.get("teamId") or team.get("id") or "")
        prev_tri = (prev_team.get("teamTricode") or prev_team.get("tricode") or "").upper()
        team_tri = (team.get("teamTricode") or team.get("tricode") or "").upper()
        if (prev_id and team_id and prev_id != team_id) or (prev_tri and team_tri and prev_tri != team_tri):
            return None
        return self.backend.safe_score(team) - self.backend.safe_score(prev_team)

    def _refresh_rss_headlines(self, force: bool = False) -> None:
        if not self._rss_enabled:
            return
        now = time.monotonic()
        if not force and self._rss_headlines and now - self._rss_last_fetch < self._rss_fetch_ttl:
            return
        if self._rss_future and not self._rss_future.done():
            return
        if not hasattr(self, "_executor") or self._executor is None:
            return
        self._rss_future = self._executor.submit(self.backend.get_rss_headlines, 20)
        self._rss_future.add_done_callback(self._on_rss_ready)

    def _current_rss_headline(self) -> str | None:
        if not self._rss_headlines:
            return None
        idx = max(0, min(self._rss_index, len(self._rss_headlines) - 1))
        return self._rss_headlines[idx]

    def _nba_ticker_text(self, fallback: str | None = None) -> str:
        return self._score_ticker_text(fallback)

    def _nba_merged_ticker_text(self, fallback: str | None = None) -> str:
        return self._score_ticker_text(fallback)

    def _nba_merged_ticker_key(self) -> tuple[Any, ...]:
        return self._score_ticker_key()

    def _nba_ticker_key(self) -> tuple[tuple[Any, ...], ...]:
        return self._score_ticker_games_key()

    def _ticker_boxscore_data(self) -> Dict[str, Any]:
        game_id = str(self.selected_game_id or self._pending_selection_id or "")
        if not game_id:
            return {}
        expected_key = (self.sport_name, game_id)
        if self._displayed_boxscore_key == expected_key and isinstance(self._last_boxscore_data, dict):
            return self._last_boxscore_data
        cached = self._runtime_boxscore(self.sport_name, game_id)
        return cached if isinstance(cached, dict) else {}

    def _ticker_games(self) -> list[Dict[str, Any]]:
        ordered: list[Dict[str, Any]] = []
        selected_id = str(self.selected_game_id or self._pending_selection_id or "")
        if selected_id:
            selected = next((g for g in self.games if str(g.get("gameId") or "") == selected_id), None)
            if isinstance(selected, dict):
                ordered.append(selected)
        for game in self.games:
            if not isinstance(game, dict):
                continue
            if selected_id and str(game.get("gameId") or "") == selected_id:
                continue
            ordered.append(game)
        return ordered

    def _score_ticker_games_key(self) -> tuple[tuple[Any, ...], ...]:
        key_parts: list[tuple[Any, ...]] = []
        for g in self._ticker_games():
            away = g.get("awayTeam") or {}
            home = g.get("homeTeam") or {}
            status_text, _, _ = self._game_status_payload(g)
            key_parts.append(
                (
                    g.get("gameId") or "",
                    self.backend.safe_score(away),
                    self.backend.safe_score(home),
                    str(status_text),
                )
            )
        return tuple(key_parts)

    def _score_ticker_status_text(self, game: Dict[str, Any]) -> str:
        status_text, status_state, _ = self._game_status_payload(game)
        if status_state == "final" and not status_text:
            return "Final"
        return status_text

    def _score_ticker_game_segment_text(self, game: Dict[str, Any]) -> str:
        away = game.get("awayTeam") or {}
        home = game.get("homeTeam") or {}
        away_tri = (away.get("teamTricode") or away.get("tricode") or "").upper()
        home_tri = (home.get("teamTricode") or home.get("tricode") or "").upper()
        away_score = self.backend.safe_score(away)
        home_score = self.backend.safe_score(home)
        status_text = self._score_ticker_status_text(game)
        segment = f"{away_tri} {away_score} @ {home_tri} {home_score}"
        if status_text:
            segment += f" [{status_text}]"
        return segment

    def _selected_ticker_detail_lines(self) -> list[str]:
        sport = self.sport_name.upper()
        data = self._ticker_boxscore_data()
        lines: list[str] = []
        primary = self._format_selected_info_line(data)
        if primary:
            lines.append(primary)
        if sport == "NBA":
            for line in self._pbp_lines[:3]:
                cleaned = str(line or "").strip()
                if cleaned:
                    lines.append(f"PLAY {cleaned}")
        return lines

    def _ticker_info_lines(self) -> list[str]:
        return self._selected_ticker_detail_lines()

    def _format_selected_info_line(self, data: Dict[str, Any]) -> str:
        sport = self.sport_name.upper()
        if not isinstance(data, dict) or not data:
            return ""
        if sport == "NBA":
            return self._format_nba_info_line(data)
        if sport == "NCAA BASKETBALL":
            return self._format_ncaa_basketball_info_line(data)
        if sport in ("NFL", "NCAA FOOTBALL"):
            return self._format_nfl_info_line(data)
        if sport == "NHL":
            return self._format_nhl_info_line(data)
        if sport == "MLB":
            return self._format_mlb_info_line(data)
        if sport == "MLS":
            return self._format_mls_info_line(data)
        return self._format_generic_info_line(data)

    def _ncaa_basketball_event_label(self, game: Dict[str, Any]) -> str:
        if not isinstance(game, dict):
            return ""
        note = str(game.get("eventNote") or "").strip()
        if note:
            return note.upper()
        bucket = str(game.get("eventBucket") or game.get("groupShortName") or game.get("groupName") or "").strip()
        if bucket:
            return bucket.upper()
        return "MARCH MADNESS" if game.get("isMarchMadness") else ""

    def _ncaa_basketball_theme_active(self) -> bool:
        payload = self._ticker_boxscore_data()
        game = payload.get("game") if isinstance(payload, dict) else {}
        if not isinstance(game, dict):
            return False
        return bool(game.get("isMarchMadness") or game.get("isTournament"))

    def _format_ncaa_basketball_info_line(self, data: Dict[str, Any]) -> str:
        game = data.get("game") or {}
        away = data.get("away") or {}
        home = data.get("home") or {}
        away_tri = (away.get("teamTricode") or "AWAY").upper()
        home_tri = (home.get("teamTricode") or "HOME").upper()
        away_score = self.backend.safe_score(away)
        home_score = self.backend.safe_score(home)
        period_text = self._format_period_badge({**game, "_header": data.get("header")})
        clock_text = (
            self._normalize_pbp_clock(game.get("gameClock"))
            or self._normalize_pbp_clock(game.get("gameStatusText"))
            or self._normalize_pbp_clock(data.get("header"))
        )
        extras = []
        event_label = self._ncaa_basketball_event_label(game)
        if event_label:
            extras.append(event_label)
        time_part = " ".join(
            part
            for part in (period_text, clock_text)
            if part and part not in ("Q-", "FINAL", "HALF TIME")
        )
        if period_text == "HALF TIME":
            extras.append(period_text)
        elif time_part:
            extras.append(time_part)
        line = f"{away_tri} {away_score} @ {home_tri} {home_score}"
        if extras:
            line = f"{line} | {' | '.join(extras)}"
        return line.strip()

    def _format_nba_info_line(self, data: Dict[str, Any]) -> str:
        game = data.get("game") or {}
        away = data.get("away") or {}
        home = data.get("home") or {}
        away_tri = (away.get("teamTricode") or "AWY")[:3].upper()
        home_tri = (home.get("teamTricode") or "HME")[:3].upper()
        away_score = self.backend.safe_score(away)
        home_score = self.backend.safe_score(home)
        period_text = self._format_period_badge({**game, "_header": data.get("header")})
        clock_text = (
            self._normalize_pbp_clock(game.get("gameClock"))
            or self._normalize_pbp_clock(game.get("gameStatusText"))
            or self._normalize_pbp_clock(data.get("header"))
        )
        time_parts = [part for part in (period_text, clock_text) if part and part not in ("Q-", "FINAL")]
        shot_text = str(data.get("shotclock") or "").strip()
        extras = []
        if time_parts:
            extras.append(" ".join(time_parts))
        if shot_text and shot_text != "--":
            extras.append(f"SHOT {shot_text}")
        line = f"{away_tri} {away_score} @ {home_tri} {home_score}"
        if extras:
            line = f"{line} | {' | '.join(extras)}"
        return line.strip()

    def _format_nfl_info_line(self, data: Dict[str, Any]) -> str:
        game = data.get("game") or {}
        away = data.get("away") or {}
        home = data.get("home") or {}
        away_tri = (away.get("teamTricode") or "AWY")[:3].upper()
        home_tri = (home.get("teamTricode") or "HME")[:3].upper()
        away_score = self.backend.safe_score(away)
        home_score = self.backend.safe_score(home)
        period_text = self._format_period_badge({**game, "_header": data.get("header")})
        if period_text in ("Q-", "FINAL"):
            period_text = ""
        clock_text = (
            self._normalize_pbp_clock(game.get("gameClock"))
            or self._normalize_pbp_clock(game.get("gameStatusText"))
            or self._normalize_pbp_clock(data.get("header"))
        )
        time_part = " ".join(part for part in (period_text, clock_text) if part)
        down_text = (
            game.get("shortDownDistanceText")
            or game.get("downDistanceText")
            or ""
        )
        line = f"{away_tri} {away_score} @ {home_tri} {home_score}"
        if time_part:
            line = f"{line} {time_part}"
        if down_text:
            line = f"{line} | {down_text}"
        return line.strip()

    def _format_nhl_info_line(self, data: Dict[str, Any]) -> str:
        game = data.get("game") or {}
        away = data.get("away") or {}
        home = data.get("home") or {}
        away_tri = (away.get("teamTricode") or "AWY")[:3].upper()
        home_tri = (home.get("teamTricode") or "HME")[:3].upper()
        away_score = self.backend.safe_score(away)
        home_score = self.backend.safe_score(home)
        period_text = self._format_period_badge({**game, "_header": data.get("header")})
        if period_text in ("P-", "FINAL"):
            period_text = ""
        clock_text = (
            self._normalize_pbp_clock(game.get("gameClock"))
            or self._normalize_pbp_clock(game.get("gameStatusText"))
            or self._normalize_pbp_clock(data.get("header"))
        )
        time_part = " ".join(part for part in (period_text, clock_text) if part)
        away_shots = self._team_shots_text(away)
        home_shots = self._team_shots_text(home)
        shots_part = ""
        if away_shots not in ("", "--") and home_shots not in ("", "--"):
            shots_part = f"SOG {away_shots}-{home_shots}"
        line = f"{away_tri} {away_score} @ {home_tri} {home_score}"
        if time_part:
            line = f"{line} {time_part}"
        if shots_part:
            line = f"{line} | {shots_part}"
        return line.strip()

    def _format_mlb_info_line(self, data: Dict[str, Any]) -> str:
        game = data.get("game") or {}
        away = data.get("away") or {}
        home = data.get("home") or {}
        away_tri = (away.get("teamTricode") or "AWY")[:3].upper()
        home_tri = (home.get("teamTricode") or "HME")[:3].upper()
        away_score = self.backend.safe_score(away)
        home_score = self.backend.safe_score(home)
        period_text = self._format_period_badge({**game, "_header": data.get("header")})
        situation = game.get("situation") or {}
        extras: list[str] = []
        if period_text and period_text not in ("Q-", "FINAL"):
            extras.append(period_text)
        balls = situation.get("balls")
        strikes = situation.get("strikes")
        outs = situation.get("outs")
        try:
            if balls is not None and strikes is not None:
                extras.append(f"COUNT {int(balls)}-{int(strikes)}")
        except Exception:
            pass
        try:
            if outs is not None:
                out_count = int(outs)
                extras.append(f"{out_count} OUT" if out_count == 1 else f"{out_count} OUTS")
        except Exception:
            pass
        line = f"{away_tri} {away_score} @ {home_tri} {home_score}"
        if extras:
            line = f"{line} | {' | '.join(extras)}"
        return line.strip()

    def _format_mls_info_line(self, data: Dict[str, Any]) -> str:
        game = data.get("game") or {}
        away = data.get("away") or {}
        home = data.get("home") or {}
        away_tri = (away.get("teamTricode") or "AWY").upper()
        home_tri = (home.get("teamTricode") or "HME").upper()
        away_score = self.backend.safe_score(away)
        home_score = self.backend.safe_score(home)
        period_text = self._format_period_badge({**game, "_header": data.get("header")})
        clock_text = (
            self._extract_clock_text(game.get("gameClock"))
            or self._extract_clock_text(game.get("gameStatusText"))
            or self._extract_clock_text(data.get("header"))
        )
        extras: list[str] = []
        if period_text == "FINAL":
            extras.append("FT")
        elif period_text == "HT":
            extras.append("HT")
        elif period_text not in ("FINAL", "Q-", "H-", "P-", "PK"):
            time_parts = [part for part in (period_text, clock_text) if part]
            if time_parts:
                extras.append(" ".join(time_parts))
        elif period_text == "PK":
            extras.append("PK")

        away_shots = self._team_stat_text(away, ("shotsOnGoal", "shotsOnTarget"), default="")
        home_shots = self._team_stat_text(home, ("shotsOnGoal", "shotsOnTarget"), default="")
        if away_shots and home_shots:
            extras.append(f"SOG {away_shots}-{home_shots}")

        away_poss = self._team_stat_text(away, ("possessionPct",), default="", suffix="%")
        home_poss = self._team_stat_text(home, ("possessionPct",), default="", suffix="%")
        if away_poss and home_poss:
            extras.append(f"POSS {away_poss}-{home_poss}")

        away_yc = self._team_stat_text(away, ("yellowCards",), default="")
        home_yc = self._team_stat_text(home, ("yellowCards",), default="")
        if away_yc and home_yc and any(val not in ("0", "0%", "0.0%") for val in (away_yc, home_yc)):
            extras.append(f"YC {away_yc}-{home_yc}")

        away_rc = self._team_stat_text(away, ("redCards",), default="")
        home_rc = self._team_stat_text(home, ("redCards",), default="")
        if away_rc and home_rc and any(val not in ("0", "0%", "0.0%") for val in (away_rc, home_rc)):
            extras.append(f"RC {away_rc}-{home_rc}")

        line = f"{away_tri} {away_score} @ {home_tri} {home_score}"
        if extras:
            line = f"{line} | {' | '.join(extras)}"
        return line.strip()

    def _format_generic_info_line(self, data: Dict[str, Any]) -> str:
        game = data.get("game") or {}
        away = data.get("away") or {}
        home = data.get("home") or {}
        away_tri = (away.get("teamTricode") or "AWY")[:3].upper()
        home_tri = (home.get("teamTricode") or "HME")[:3].upper()
        away_score = self.backend.safe_score(away)
        home_score = self.backend.safe_score(home)
        period_text = self._format_period_badge({**game, "_header": data.get("header")})
        clock_text = (
            self._normalize_pbp_clock(game.get("gameClock"))
            or self._normalize_pbp_clock(game.get("gameStatusText"))
            or self._normalize_pbp_clock(data.get("header"))
        )
        extras = [part for part in (period_text, clock_text) if part and part not in ("Q-", "P-")]
        line = f"{away_tri} {away_score} @ {home_tri} {home_score}"
        if extras:
            line = f"{line} | {' | '.join(extras)}"
        return line.strip()

    def _score_ticker_game_segment_pieces(self, game: Dict[str, Any]) -> list[tuple[str, Any]]:
        pieces: list[tuple[str, Any]] = []
        away = game.get("awayTeam") or {}
        home = game.get("homeTeam") or {}
        away_tri = (away.get("teamTricode") or away.get("tricode") or "").upper()
        home_tri = (home.get("teamTricode") or home.get("tricode") or "").upper()
        away_score = self.backend.safe_score(away)
        home_score = self.backend.safe_score(home)
        status_text = self._score_ticker_status_text(game)

        away_logo_key = self._team_logo_key(away)
        away_pix = None
        if away_logo_key:
            away_pix = self._combo_logo_cache.get(away_logo_key)
            if away_pix is None:
                self._queue_combo_logo(away_logo_key)
        home_logo_key = self._team_logo_key(home)
        home_pix = None
        if home_logo_key:
            home_pix = self._combo_logo_cache.get(home_logo_key)
            if home_pix is None:
                self._queue_combo_logo(home_logo_key)

        if away_pix:
            pieces.append(("logo", away_pix))
            pieces.append(("gap", TICKER_LOGO_GAP))
        pieces.append(("text", f"{away_tri} {away_score}"))
        pieces.append(("gap", TICKER_TEXT_GAP))
        pieces.append(("text", "@"))
        pieces.append(("gap", TICKER_TEXT_GAP))
        if home_pix:
            pieces.append(("logo", home_pix))
            pieces.append(("gap", TICKER_LOGO_GAP))
        pieces.append(("text", f"{home_tri} {home_score}"))
        if status_text:
            pieces.append(("gap", TICKER_TEXT_GAP))
            pieces.append(("text", f"[{status_text}]"))
        return pieces

    def _nba_ticker_pieces(self) -> list[tuple[str, Any]]:
        return self._score_ticker_pieces()

    def _nba_merged_ticker_pieces(self) -> list[tuple[str, Any]]:
        return self._score_ticker_pieces()

    def _score_ticker_pieces(self) -> list[tuple[str, Any]]:
        pieces: list[tuple[str, Any]] = []
        for line in self._selected_ticker_detail_lines():
            pieces.append(("text", line))
            pieces.append(("gap", TICKER_SEGMENT_GAP))
        for game in self._ticker_games():
            pieces.extend(self._score_ticker_game_segment_pieces(game))
            pieces.append(("gap", TICKER_SEGMENT_GAP))
        return pieces

    def _score_ticker_text(self, fallback: str | None = None) -> str:
        segments = [line for line in self._selected_ticker_detail_lines() if line]
        segments.extend(self._score_ticker_game_segment_text(game) for game in self._ticker_games())
        segments = [segment for segment in segments if segment]
        if segments:
            sep = "   |   "
            return f"{sep.join(segments)}{sep}"
        return fallback or "No games today."

    def _score_ticker_key(self) -> tuple[Any, ...]:
        return ("score_ticker", tuple(self._selected_ticker_detail_lines()), self._score_ticker_games_key())

    def _nba_game_segment_text(self, game: Dict[str, Any]) -> str:
        return self._score_ticker_game_segment_text(game)

    def _nba_game_segment_pieces(self, game: Dict[str, Any]) -> list[tuple[str, Any]]:
        return self._score_ticker_game_segment_pieces(game)

    def _refresh_nba_merged_ticker(self, *, force: bool = False, fallback: str | None = None) -> None:
        self._set_bottom_bar_ticker(
            self._score_ticker_text(fallback),
            pieces=self._score_ticker_pieces(),
            key=self._score_ticker_key(),
            force=force,
        )

    def _pbp_team_tricodes(self, game_id: str) -> tuple[str, str]:
        away_tri = ""
        home_tri = ""
        for g in self.games:
            if str(g.get("gameId")) == str(game_id):
                away = g.get("awayTeam") or {}
                home = g.get("homeTeam") or {}
                away_tri = (away.get("teamTricode") or away.get("tricode") or "").upper()
                home_tri = (home.get("teamTricode") or home.get("tricode") or "").upper()
                break
        return away_tri, home_tri

    def _format_pbp_period(self, period: Any) -> str:
        try:
            value = int(period)
        except Exception:
            return ""
        if value <= 0:
            return ""
        if value <= 4:
            return f"Q{value}"
        extra = value - 4
        return "OT" if extra == 1 else f"OT{extra}"

    def _format_pbp_timestamp(self, item: Dict[str, Any]) -> str:
        for key in (
            "clock",
            "clockDisplayValue",
            "clockValue",
            "timeRemaining",
            "time",
            "remainingTime",
            "playClock",
        ):
            raw = item.get(key)
            stamp = self._normalize_pbp_clock(raw)
            if stamp:
                return stamp
        return ""

    def _normalize_pbp_clock(self, raw: Any) -> str:
        if raw in (None, ""):
            return ""
        if isinstance(raw, (int, float)):
            total = int(float(raw))
            if total < 0:
                return ""
            minutes = total // 60
            seconds = total % 60
            return f"{minutes}:{seconds:02d}"
        text = str(raw).strip()
        match = re.search(r"(\d{1,2}:\d{2})", text)
        if match:
            return match.group(1)
        match = re.search(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", text)
        if match:
            minutes = int(match.group(1) or 0)
            seconds = int(float(match.group(2) or 0))
            return f"{minutes}:{seconds:02d}"
        return ""

    def _format_pbp_line(self, item: Dict[str, Any], away_tri: str, home_tri: str) -> str:
        desc = str(item.get("description") or "").strip()
        if not desc:
            return ""
        timestamp = self._format_pbp_timestamp(item)
        if timestamp:
            return f"{timestamp} {desc}".strip()
        return desc.strip()

    def _pbp_lines_from_items(self, game_id: str, items: list[dict[str, Any]]) -> list[str]:
        away_tri, home_tri = self._pbp_team_tricodes(game_id)
        lines: list[str] = []
        for item in reversed(items):
            line = self._format_pbp_line(item, away_tri, home_tri)
            if line:
                lines.append(line)
            if len(lines) >= PBP_TICKER_MAX:
                break
        return lines

    def _pbp_ticker_text(self, lines: list[str]) -> str:
        if not lines:
            return "Play-by-play unavailable"
        sep = PBP_TICKER_SEPARATOR
        return f"{sep.join(lines)}{sep}"

    def _pbp_speed_px(self) -> float:
        base = float(getattr(self, "ticker_speed_px", TICKER_SPEED_PX))
        return max(4.0, min(80.0, base * PBP_TICKER_SPEED_MULTIPLIER))

    def _set_pbp_ticker(self, text: str, *, key: object | None = None, force: bool = False) -> None:
        label = getattr(self, "pbp_ticker_label", None)
        if label is None:
            return
        if isinstance(label, TickerLabel):
            effective_key = key if key is not None else ("pbp", text)
            if not force and label.is_ticker_enabled() and self._last_pbp_key == effective_key:
                return
            self._last_pbp_key = effective_key
            anim = self._begin_fade(label, duration_ms=220)
            label.set_ticker_text(text, speed_px=self._pbp_speed_px(), direction="ltr")
            if anim:
                try:
                    anim.start()
                except RuntimeError:
                    pass
        else:
            label.setText(self._elide_label_text(label, text))

    def _set_bottom_bar_ticker(
        self,
        text: str,
        *,
        pieces: list[tuple[str, Any]] | None = None,
        key: object | None = None,
        force: bool = False,
    ) -> None:
        self.bottom_left_label.setVisible(False)
        self.bottom_right_label.setVisible(False)
        self.bottom_center_label.setVisible(True)
        self.bottom_center_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.bottom_center_label.setStyleSheet(f"color: {TEXT}; font-weight: 700; font-size: 13px;")
        label = self.bottom_center_label
        if isinstance(label, TickerLabel):
            if not force and label.is_ticker_enabled() and label.ticker_key() == key:
                return
            if pieces:
                label.set_ticker_pieces_with_offset(
                    pieces,
                    speed_px=self.ticker_speed_px,
                    direction="ltr",
                    key=key,
                    preserve_offset=label.is_ticker_enabled(),
                )
            else:
                label.set_ticker_text_with_offset(
                    text,
                    speed_px=self.ticker_speed_px,
                    direction="ltr",
                    preserve_offset=label.is_ticker_enabled(),
                )
        else:
            label.setText(self._elide_label_text(label, text))

    def _set_bottom_bar_rss(self, headline: str) -> None:
        self.bottom_left_label.setVisible(False)
        self.bottom_right_label.setVisible(False)
        self.bottom_center_label.setVisible(True)
        self.bottom_center_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.bottom_center_label.setStyleSheet(f"color: {TEXT}; font-weight: 700; font-size: 13px;")
        text = f"NBA NEWS - {headline}"
        self.bottom_center_label.setText(self._elide_label_text(self.bottom_center_label, text))

    def _on_rss_ready(self, future):
        if not self._alive:
            return
        try:
            items = future.result()
        except Exception:
            items = []
        QTimer.singleShot(0, lambda i=items: self._apply_rss_items(i))

    def _apply_rss_items(self, items: List[str]) -> None:
        if not self._rss_enabled or self.sport_name.upper() != "NBA":
            return
        if not items:
            if not self._rss_headlines:
                self._set_bottom_bar_rss("Headlines unavailable")
            return
        self._rss_headlines = items
        self._rss_last_fetch = time.monotonic()
        if self._rss_index >= len(items):
            self._rss_index = 0
        self._set_bottom_bar_rss(self._rss_headlines[self._rss_index])

    def _rotate_rss_headline(self):
        if not self._rss_enabled or self.sport_name.upper() != "NBA":
            return
        self._refresh_rss_headlines()
        if not self._rss_headlines:
            return
        self._rss_index = (self._rss_index + 1) % len(self._rss_headlines)
        self._set_bottom_bar_rss(self._rss_headlines[self._rss_index])

    def _update_rss_mode(self, force: bool = False) -> None:
        enabled = False
        self._rss_enabled = enabled
        if enabled:
            if not self.rss_timer.isActive():
                self.rss_timer.start(10_000)
            self._refresh_rss_headlines(force=force)
        else:
            if self.rss_timer.isActive():
                self.rss_timer.stop()
            self._rss_headlines = []
            self._rss_index = 0
            self.bottom_left_label.setVisible(True)
            self.bottom_right_label.setVisible(True)
            self.bottom_center_label.setVisible(True)

    def _on_realtime_update(self, state: RealTimeGameState):
        if not self._alive:
            return
        self.realtime_ready.emit(state)

    def _apply_realtime_state(self, state: RealTimeGameState):
        if not self._alive:
            return
        if self.feed_delay_ms > 0:
            return
        if self.selected_game_id and state.game_id != self.selected_game_id:
            return
        period = state.period or "-"
        period_text = self._format_period_badge(
            {
                "period": {"current": period},
                "gameClockText": state.game_clock_text,
                "gameClock": state.game_clock_raw,
                "gameStatus": 2,
                "status": "live",
                "gameStatusText": "Live",
            }
        )
        raw_clock = state.game_clock_raw or state.game_clock_text or ""
        raw_secs = self._clock_to_seconds(raw_clock)
        sport = self.sport_name.upper()
        force_live, buffer_sec, stale_window_sec = self._clock_sync_settings(
            sport, period_text, state.game_clock_text
        )
        fallback_clock = self._extract_clock_text(raw_clock)
        clock_text, shot_text, clock_state = self._compute_clock_state(
            period_text,
            raw_secs,
            state.shot_clock,
            fallback_clock or state.game_clock_text or state.game_clock_raw or "",
            force_live=force_live,
            buffer_sec=buffer_sec,
            stale_window_sec=stale_window_sec,
            source="realtime",
        )
        if sport == "NHL":
            clock_text = self._clean_nhl_clock_text(clock_text)
        if not self._is_game_active({}, period_text, state.game_clock_text or ""):
            clock_text = "00:00"
            clock_state["clock_secs"] = 0.0
            clock_state["running"] = False
        self._apply_period_label_style(sport)
        if self._preserve_bottom_labels_for_clock(sport):
            left_text = self.center_panel.bottom_left.text()
            center_text = self.center_panel.bottom_center.text()
            right_text = self.center_panel.bottom_right.text()
        else:
            left_text = ""
            center_text = ""
            right_text = shot_text
        self.center_panel.set_state(period_text, clock_text, left_text, right_text, center_text)
        self._clock_state = clock_state
        live_status_text = " ".join(
            part for part in (period_text if period_text not in ("Q-", "P-", "FINAL") else "", clock_text) if part
        ).strip() or "Live"
        self._merge_live_game_state(
            state.game_id,
            away_score=state.away_score,
            home_score=state.home_score,
            status_text=live_status_text,
            game_clock=state.game_clock_raw or state.game_clock_text,
            period={"current": state.period} if state.period else {},
            status="live",
        )
        if state.home_score is not None:
            self.home_score.setText(str(state.home_score))
        if state.away_score is not None:
            self.away_score.setText(str(state.away_score))

    def _load_cached_state(self) -> Dict[str, Any] | None:
        try:
            if STATE_PATH.exists():
                return json.loads(STATE_PATH.read_text())
        except Exception:
            return None
        return None

    def _should_apply_cached_live_state(self, cached: Dict[str, Any]) -> bool:
        if not isinstance(cached, dict):
            return False
        scores = cached.get("scores") or {}
        games = scores.get("games") or []
        if not isinstance(games, list) or not games:
            return True
        selected_id = str(cached.get("selected_game_id") or "")
        target_game = None
        if selected_id:
            target_game = next((g for g in games if str((g or {}).get("gameId") or "") == selected_id), None)
        if target_game is None:
            target_game = next((g for g in games if isinstance(g, dict) and self._is_game_live(g)), None)
        if not isinstance(target_game, dict) or not self._is_game_live(target_game):
            return True
        try:
            cached_ts = float(cached.get("ts") or 0.0)
        except Exception:
            cached_ts = 0.0
        if cached_ts <= 0:
            return False
        age_sec = max(0.0, time.time() - cached_ts)
        if self.sport_name.upper() == "NHL":
            return age_sec <= 12.0
        return age_sec <= 30.0

    def _apply_cached_state_if_available(self):
        if not self._cached_state:
            return
        cached = None
        if isinstance(self._cached_state.get("sports"), dict):
            cached = self._cached_state.get("sports", {}).get(self.sport_name)
        if cached is None and self._cached_state.get("scores"):
            cached = self._cached_state
        if not cached:
            return
        scores = cached.get("scores") or {}
        boxscore = cached.get("boxscore")
        self.selected_game_id = cached.get("selected_game_id")
        cached_tz = self._cached_state.get("timezone") or (self._cached_state.get("settings") or {}).get("timezone")
        if cached_tz:
            self._set_timezone(cached_tz, persist=False)
        cached_delay = (self._cached_state.get("settings") or {}).get("feed_delay_sec")
        if cached_delay is not None:
            try:
                self.feed_delay_ms = max(0, int(float(cached_delay)) * 1000)
                os.environ["SCORESOURCE_FEED_DELAY_SEC"] = str(int(self.feed_delay_ms / 1000))
            except Exception:
                pass
            self._sync_delay_actions()
        cached_speed = (self._cached_state.get("settings") or {}).get("ticker_speed_px")
        if cached_speed is not None:
            try:
                self.ticker_speed_px = float(cached_speed)
                os.environ["SCORESOURCE_TICKER_SPEED_PX"] = str(self.ticker_speed_px)
            except Exception:
                pass
            self._sync_ticker_speed_actions()
        self.ticker_speed_px = max(self.ticker_speed_px, TICKER_SPEED_PX)
        if not self._should_apply_cached_live_state(cached):
            return
        self._pending_selection_id = None
        self.lines = scores.get("lines", []) or []
        self.games = scores.get("games", []) or []
        if scores:
            self._cache_runtime_scores(self.sport_name, self.games, self.lines, selected_game_id=self.selected_game_id)
            self._apply_scores({"games": self.games, "lines": self.lines})
        if boxscore:
            self._cache_runtime_boxscore(self.sport_name, self.selected_game_id, boxscore)
            self.apply_boxscore(boxscore)

    def _schedule_state_save(self, *, immediate: bool = False) -> None:
        self._state_dirty = True
        if immediate:
            self._flush_cached_state()
            return
        now = time.monotonic()
        elapsed = now - self._last_state_save_ts
        if elapsed >= self._state_save_interval_sec:
            self._flush_cached_state()
            return
        delay_ms = int(max(250, (self._state_save_interval_sec - elapsed) * 1000))
        self._state_save_timer.start(delay_ms)

    def _flush_cached_state(self) -> None:
        if not self._state_dirty:
            return
        if not isinstance(self._cached_state, dict):
            return
        try:
            STATE_PATH.write_text(json.dumps(self._cached_state))
            self._state_dirty = False
            self._last_state_save_ts = time.monotonic()
        except Exception:
            pass

    def _save_cached_state(self, boxscore: Dict[str, Any]):
        settings = {
            "timezone": self.display_tz,
            "feed_delay_sec": int(self.feed_delay_ms / 1000),
            "ticker_speed_px": float(self.ticker_speed_px),
        }
        payload = {
            "scores": {"games": self.games, "lines": self.lines},
            "boxscore": boxscore,
            "selected_game_id": self.selected_game_id,
            "ts": time.time(),
        }
        state = self._cached_state if isinstance(self._cached_state, dict) else {}
        sports = state.get("sports")
        if not isinstance(sports, dict):
            sports = {}
        sports[self.sport_name] = payload
        state["sports"] = sports
        state["timezone"] = self.display_tz
        state["settings"] = settings
        self._cached_state = state
        self._schedule_state_save()

    def _team_color(self, tri: str | None) -> str:
        return getattr(self.backend, "TEAM_COLORS", getattr(self.backend, "TEAM_PRIMARY_COLORS", {})).get(
            (tri or "").upper(), ACCENT
        )

    def _display_tricode(self, team: Dict[str, Any], fallback: str = "") -> str:
        tri = (team.get("teamTricode") or team.get("tricode") or fallback or "").upper()
        if self.sport_name.upper() in ("NCAA FOOTBALL", "NCAA BASKETBALL", "MLS"):
            return tri
        return tri[:3]

    def _team_secondary_color(self, tri: str | None) -> str:
        secondary = getattr(self.backend, "TEAM_SECONDARY_COLORS", {}).get((tri or "").upper())
        if secondary:
            return secondary
        return self._mix_color(self._team_color(tri), BG, 0.35)

    def _team_alt_color(self, tri: str | None) -> str:
        tri_key = (tri or "").upper()
        alt = getattr(self.backend, "TEAM_ALT_COLORS", {}).get(tri_key)
        if alt:
            return alt
        accents = getattr(self.backend, "TEAM_ACCENT_COLORS", {})
        return accents.get(tri_key, self._team_color(tri))

    def _extract_clock_text(self, raw: Any) -> str:
        if not raw:
            return ""
        raw_text = str(raw)
        if re.search(r"\b(am|pm)\b", raw_text.lower()):
            return ""
        soccer_match = re.search(r"(\d{1,3}'(?:\+\d{1,2}')?)", raw_text)
        if soccer_match:
            return soccer_match.group(1)
        secs = self._clock_to_seconds(raw)
        if secs is not None:
            return self._format_clock(secs)
        match = re.search(r"(\d{1,2}:\d{2})", raw_text)
        return match.group(1) if match else ""

    def _split_full_team_name(self, full_name: str) -> tuple[str, str]:
        name = str(full_name or "").strip()
        if not name:
            return "", ""
        parts = name.split()
        if len(parts) <= 1:
            return "", name
        if len(parts) >= 2:
            last_two = " ".join(parts[-2:])
            if last_two.upper() in MULTIWORD_NICKNAMES:
                return " ".join(parts[:-2]).strip(), last_two
        return " ".join(parts[:-1]).strip(), parts[-1]

    def _team_city_and_name(self, team: Dict[str, Any]) -> tuple[str, str]:
        raw_name = str(team.get("teamName") or team.get("displayName") or team.get("name") or "").strip()
        city = str(
            team.get("teamCity")
            or team.get("city")
            or team.get("location")
            or team.get("teamLocation")
            or ""
        ).strip()
        nickname = str(team.get("nickname") or team.get("shortName") or "").strip()
        if nickname and not city and raw_name and raw_name.lower().endswith(nickname.lower()):
            city = raw_name[: -len(nickname)].strip()
        if not city and raw_name:
            split_city, split_nick = self._split_full_team_name(raw_name)
            if split_nick:
                nickname = nickname or split_nick
            city = city or split_city
        if not nickname:
            nickname = raw_name
        if not city:
            city = raw_name
        return city.upper(), nickname.upper()

    def _team_record_text(self, team: Dict[str, Any], side: str | None = None) -> str:
        rec = self._record_from_dict(team)
        if not rec and side and self.selected_game_id:
            for g in self.games:
                if g.get("gameId") == self.selected_game_id:
                    side_team = g.get(f"{side}Team") or {}
                    rec = self._record_from_dict(side_team)
                    if rec:
                        break
        if not rec:
            return "--"
        try:
            wins = int(rec[0])
            losses = int(rec[1])
            ties = None
            if len(rec) > 2 and rec[2] is not None:
                ties = int(rec[2])
            if ties is not None:
                return f"{wins}-{losses}-{ties}"
            return f"{wins}-{losses}"
        except Exception:
            return "--"

    def _default_timeouts(self) -> int | None:
        defaults = {"NBA": 7, "NFL": 3, "NCAA FOOTBALL": 3, "NHL": 1}
        return defaults.get(self.sport_name.upper())

    def _extract_timeouts(self, team: Dict[str, Any]) -> tuple[int | None, int | None]:
        stats = team.get("statistics") or {}

        def _coerce(val: Any) -> int | None:
            if val in (None, ""):
                return None
            try:
                return int(float(val))
            except Exception:
                return None

        def _first(keys: list[str]) -> int | None:
            for key in keys:
                val = _coerce(team.get(key))
                if val is None:
                    val = _coerce(stats.get(key))
                if val is not None:
                    return val
            return None

        remaining = _first(["timeoutsRemaining", "timeoutsLeft", "remainingTimeouts", "timeoutsRemainingTotal"])
        total = _first(["timeoutsTotal", "timeoutsMax", "totalTimeouts"])
        used = _first(["timeoutsUsed", "timeoutsTaken"])

        default_total = self._default_timeouts()
        if remaining is None:
            if default_total:
                return default_total, default_total
            return None, None
        if total is None and used is not None:
            total = remaining + used
        if total is None:
            total = max(remaining, default_total or remaining)
        return remaining, total

    def _apply_timeouts(
        self, left_team: Dict[str, Any], right_team: Dict[str, Any], left_color: str, right_color: str
    ) -> None:
        if self.sport_name.upper() == "NHL":
            prev_penalty_state = self._penalty_state or {}
            left_text = self._top_text_color(left_color)
            right_text = self._top_text_color(right_color)
            left_penalties = self._team_penalties_text(left_team)
            right_penalties = self._team_penalties_text(right_team)
            left_seconds = self._team_penalty_seconds_list(left_team)
            right_seconds = self._team_penalty_seconds_list(right_team)
            if left_seconds and prev_penalty_state:
                left_seconds = self._smooth_penalty_seconds(left_seconds, prev_penalty_state.get("left"))
            if right_seconds and prev_penalty_state:
                right_seconds = self._smooth_penalty_seconds(right_seconds, prev_penalty_state.get("right"))
            left_label, left_clock = self._nhl_penalty_clock_text(left_seconds, right_seconds, left_team)
            right_label, right_clock = self._nhl_penalty_clock_text(right_seconds, left_seconds, right_team)
            self._penalty_state = {
                "last_ts": time.monotonic(),
                "left": left_seconds,
                "right": right_seconds,
            }
            self.away_timeouts.set_timeouts(None)
            self.home_timeouts.set_timeouts(None)
            self.away_penalties.setText(f"PIM {left_penalties}")
            self.home_penalties.setText(f"PIM {right_penalties}")
            self.away_penalty_clock.setText(f"{left_label} {left_clock}")
            self.home_penalty_clock.setText(f"{right_label} {right_clock}")
            self.away_penalties.setVisible(False)
            self.home_penalties.setVisible(False)
            self.away_penalty_clock.setVisible(True)
            self.home_penalty_clock.setVisible(True)
            self.away_penalties.setStyleSheet(
                f"color: {self._with_alpha(left_text, 0.9)}; font-size: 12px; font-weight: 800; letter-spacing: 0.4px;"
            )
            self.home_penalties.setStyleSheet(
                f"color: {self._with_alpha(right_text, 0.9)}; font-size: 12px; font-weight: 800; letter-spacing: 0.4px;"
            )
            self.away_penalty_clock.setStyleSheet(
                f"color: {self._with_alpha(left_text, 0.7)}; font-size: 11px; font-weight: 800; letter-spacing: 0.4px;"
            )
            self.home_penalty_clock.setStyleSheet(
                f"color: {self._with_alpha(right_text, 0.7)}; font-size: 11px; font-weight: 800; letter-spacing: 0.4px;"
            )
            self._away_meta_stack.setCurrentWidget(self._away_penalty_meta)
            self._home_meta_stack.setCurrentWidget(self._home_penalty_meta)
            return
        self._penalty_state = None
        self._away_meta_stack.setCurrentWidget(self.away_timeouts)
        self._home_meta_stack.setCurrentWidget(self.home_timeouts)
        left_remaining, left_total = self._extract_timeouts(left_team)
        right_remaining, right_total = self._extract_timeouts(right_team)
        self.away_timeouts.set_colors(TIMEOUT_ACTIVE, TIMEOUT_INACTIVE)
        self.home_timeouts.set_colors(TIMEOUT_ACTIVE, TIMEOUT_INACTIVE)
        self.away_timeouts.set_timeouts(left_remaining, left_total)
        self.home_timeouts.set_timeouts(right_remaining, right_total)

    def _team_fouls_text(self, team: Dict[str, Any]) -> str:
        val = team.get("foulsPeriod")
        if val not in (None, ""):
            try:
                return str(int(float(val)))
            except Exception:
                return str(val)
        stats = team.get("statistics") or {}
        for key in ("foulsTeam", "foulsPersonal", "personalFouls", "teamFouls"):
            val = stats.get(key)
            if val not in (None, ""):
                try:
                    return str(int(float(val)))
                except Exception:
                    return str(val)
        return "--"

    def _team_in_bonus(self, team: Dict[str, Any]) -> bool:
        def _is_true(val: Any) -> bool:
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return val > 0
            if isinstance(val, str):
                return val.strip().lower() in ("1", "true", "yes", "y", "bonus")
            return False

        for key in ("inBonus", "bonus", "isBonus"):
            if _is_true(team.get(key)):
                return True
        stats = team.get("statistics") or {}
        for key in ("inBonus", "bonus", "isBonus"):
            if _is_true(stats.get(key)):
                return True
        return False

    def _team_shots_text(self, team: Dict[str, Any]) -> str:
        for key in ("shotsOnGoal", "shotsTotal", "shots", "sog"):
            val = team.get(key)
            if val not in (None, ""):
                try:
                    return str(int(float(val)))
                except Exception:
                    return str(val)
        stats = team.get("statistics") or {}
        for key in ("shotsOnGoal", "shotsTotal", "shots", "sog"):
            val = stats.get(key)
            if val not in (None, ""):
                try:
                    return str(int(float(val)))
                except Exception:
                    return str(val)
        return "--"

    def _team_stat_text(
        self,
        team: Dict[str, Any],
        keys: tuple[str, ...],
        *,
        default: str = "--",
        suffix: str = "",
    ) -> str:
        def _format_value(raw: Any) -> str:
            if raw in (None, ""):
                return ""
            try:
                number = float(raw)
            except Exception:
                text = str(raw).strip()
                return f"{text}{suffix}" if text else ""
            if suffix == "%" and not number.is_integer():
                return f"{number:.1f}{suffix}"
            if number.is_integer():
                return f"{int(number)}{suffix}"
            return f"{number:.1f}{suffix}"

        stats = team.get("statistics") or {}
        for key in keys:
            value = team.get(key)
            if value in (None, ""):
                value = stats.get(key)
            text = _format_value(value)
            if text:
                return text
        return default

    def _team_shootout_score_text(self, team: Dict[str, Any]) -> str:
        def _coerce(val: Any) -> int | None:
            if val in (None, ""):
                return None
            try:
                return int(float(val))
            except Exception:
                return None

        for key in ("shootoutScore", "shootoutGoals", "soScore"):
            val = _coerce(team.get(key))
            if val is not None:
                return str(val)
        stats = team.get("statistics") or {}
        for key in ("shootoutScore", "shootoutGoals", "soScore"):
            val = _coerce(stats.get(key))
            if val is not None:
                return str(val)
        return "--"

    def _team_penalties_text(self, team: Dict[str, Any]) -> str:
        def _coerce(val: Any) -> int | None:
            if val in (None, ""):
                return None
            try:
                return int(float(val))
            except Exception:
                return None

        stats = team.get("statistics") or {}
        for key in ("pim", "penaltyMinutes"):
            val = _coerce(team.get(key))
            if val is None:
                val = _coerce(stats.get(key))
            if val is not None:
                return str(val)

        total = 0
        found = False
        for player in team.get("players") or []:
            pstats = player.get("statistics") or {}
            val = _coerce(pstats.get("pim"))
            if val is None:
                val = _coerce(pstats.get("penaltyMinutes"))
            if val is not None:
                total += val
                found = True
        if found:
            return str(total)
        return "--"

    def _smooth_penalty_seconds(self, values: list[int], previous: list[float] | None) -> list[float]:
        if not values:
            return []
        next_vals = [float(val) for val in values if val and float(val) > 0]
        next_vals.sort()
        prev_vals = [float(val) for val in (previous or []) if val and float(val) > 0]
        prev_vals.sort()
        if not prev_vals:
            return next_vals
        smoothed: list[float] = []
        for idx, val in enumerate(next_vals):
            if idx < len(prev_vals):
                prev_val = prev_vals[idx]
                # Clamp small upward bumps from feed jitter.
                if val > prev_val and (val - prev_val) <= 2.0:
                    smoothed.append(prev_val)
                    continue
            smoothed.append(val)
        return smoothed

    def _team_penalty_seconds_list(self, team: Dict[str, Any]) -> list[int]:
        def _coerce_number(val: Any) -> int | None:
            if val in (None, ""):
                return None
            try:
                return int(float(val))
            except Exception:
                return None

        def _parse_clock_text(text: str) -> list[int]:
            clocks: list[int] = []
            for part in re.split(r"\s*/\s*", text.strip()):
                if not part:
                    continue
                match = re.match(r"^(\d+):(\d{2})$", part)
                if match:
                    clocks.append(int(match.group(1)) * 60 + int(match.group(2)))
                else:
                    val = _coerce_number(part)
                    if val is not None:
                        clocks.append(val)
            return clocks

        def _parse_value(val: Any) -> list[int]:
            if val in (None, ""):
                return []
            if isinstance(val, (int, float)):
                num = _coerce_number(val)
                return [num] if num is not None else []
            if isinstance(val, str):
                text = val.strip()
                if not text:
                    return []
                return _parse_clock_text(text)
            if isinstance(val, (list, tuple)):
                values: list[int] = []
                for entry in val:
                    values.extend(_parse_value(entry))
                return values
            return []

        keys = (
            "penaltySecondsList",
            "penaltySeconds",
            "penaltyClocks",
            "penaltyClockList",
            "penaltyClockText",
            "penaltyClock",
            "penaltyTimeRemaining",
            "penaltyTimes",
        )
        for key in keys:
            values = _parse_value(team.get(key))
            if values:
                return [val for val in values if val is not None and val > 0]
        stats = team.get("statistics") or {}
        for key in keys:
            values = _parse_value(stats.get(key))
            if values:
                return [val for val in values if val is not None and val > 0]
        return []

    def _format_penalty_clock_list(self, seconds_list: list[int | float]) -> str:
        cleaned: list[int] = []
        for val in seconds_list:
            try:
                secs = int(float(val))
            except Exception:
                continue
            if secs > 0:
                cleaned.append(secs)
        if not cleaned:
            return "--"
        cleaned.sort()
        display = cleaned[:2]
        return " / ".join(self._format_clock(secs) for secs in display)

    def _format_powerplay_clock(self, seconds_list: list[int | float]) -> str:
        cleaned: list[int] = []
        for val in seconds_list:
            try:
                secs = int(float(val))
            except Exception:
                continue
            if secs > 0:
                cleaned.append(secs)
        if not cleaned:
            return "--"
        return self._format_clock(min(cleaned))

    def _nhl_penalty_clock_text(
        self,
        own_seconds: list[int | float],
        opp_seconds: list[int | float],
        team: Dict[str, Any],
    ) -> tuple[str, str]:
        if own_seconds:
            return "PEN", self._format_penalty_clock_list(own_seconds)
        if opp_seconds:
            return "PP", self._format_powerplay_clock(opp_seconds)
        fallback = self._team_penalty_clock_text(team) if team else "--"
        return "PEN", fallback or "--"

    def _team_penalty_clock_text(self, team: Dict[str, Any]) -> str:
        def _format_seconds(val: Any) -> str | None:
            try:
                seconds = int(float(val))
            except Exception:
                return None
            if seconds <= 0:
                return None
            minutes, secs = divmod(seconds, 60)
            return f"{minutes}:{secs:02d}"

        def _normalize_clocks(values: list[Any]) -> list[str]:
            clocks: list[str] = []
            for val in values:
                if val in (None, ""):
                    continue
                if isinstance(val, str):
                    text = val.strip()
                    if not text:
                        continue
                    if ":" in text:
                        clocks.append(text)
                        continue
                    formatted = _format_seconds(text)
                    if formatted:
                        clocks.append(formatted)
                    else:
                        clocks.append(text)
                    continue
                formatted = _format_seconds(val)
                if formatted:
                    clocks.append(formatted)
            return clocks

        def _join_clocks(values: list[str]) -> str | None:
            if not values:
                return None
            if len(values) == 1:
                return values[0]
            return " / ".join(values[:2])

        for key in ("penaltyClocks", "penaltyClockList", "penaltySecondsList", "penaltyTimes"):
            val = team.get(key)
            if isinstance(val, (list, tuple)):
                joined = _join_clocks(_normalize_clocks(list(val)))
                if joined:
                    return joined

        for key in ("penaltyClock", "penaltyClockText", "penaltyTimeRemaining"):
            val = team.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            formatted = _format_seconds(val)
            if formatted:
                return formatted
        stats = team.get("statistics") or {}
        for key in ("penaltyClocks", "penaltyClockList", "penaltySecondsList", "penaltyTimes"):
            val = stats.get(key)
            if isinstance(val, (list, tuple)):
                joined = _join_clocks(_normalize_clocks(list(val)))
                if joined:
                    return joined
        for key in ("penaltyClock", "penaltyClockText", "penaltyTimeRemaining", "penaltySeconds"):
            val = stats.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            formatted = _format_seconds(val)
            if formatted:
                return formatted
        formatted = _format_seconds(team.get("penaltySeconds"))
        if formatted:
            return formatted
        return "--"

    def _record_from_dict(self, team: Dict[str, Any]) -> tuple[Any, ...] | None:
        def _parse_record(value: Any) -> tuple[int, int, int | None] | None:
            if not value:
                return None
            nums = re.findall(r"\d+", str(value))
            if len(nums) < 2:
                return None
            wins = int(nums[0])
            losses = int(nums[1])
            ties = int(nums[2]) if len(nums) >= 3 else None
            return wins, losses, ties

        for key in ("record", "recordSummary", "recordDisplay", "summary"):
            parsed = _parse_record(team.get(key))
            if parsed:
                return (parsed[0], parsed[1], parsed[2]) if parsed[2] is not None else (parsed[0], parsed[1])

        records = team.get("records")
        if isinstance(records, list):
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                parsed = _parse_record(rec.get("summary") or rec.get("displayValue") or rec.get("shortDisplayName"))
                if parsed:
                    return (parsed[0], parsed[1], parsed[2]) if parsed[2] is not None else (parsed[0], parsed[1])

        keys = [("wins", "losses"), ("win", "loss"), ("teamWins", "teamLosses"), ("winsTotal", "lossesTotal")]
        tie_keys = ("ties", "tie", "draws", "draw", "gamesTied", "tied", "overtimeLosses", "otLosses", "otl")
        for w_key, l_key in keys:
            w = team.get(w_key)
            l = team.get(l_key)
            if w is None or l is None:
                continue
            tie = None
            for t_key in tie_keys:
                tie = team.get(t_key)
                if tie is not None:
                    break
            if tie is not None:
                return w, l, tie
            return w, l
        return None

    def _show_placeholder(self):
        self.game_combo.blockSignals(True)
        self.game_combo.setCurrentIndex(0)
        self.game_combo.blockSignals(False)

    def _on_sport_change(self, name: str):
        if not self._switch_sport or name == self.sport_name:
            return
        try:
            self._switch_sport(name, self)
        except Exception:
            pass

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Up, Qt.Key_Down):
            delta = -1 if key == Qt.Key_Up else 1
            self._step_game_selection(delta)
            event.accept()
            return
        super().keyPressEvent(event)

    def _step_game_selection(self, delta: int):
        if not self.games:
            return
        current_idx = self._current_game_index()
        if current_idx is None:
            current_idx = 0
        new_idx = max(0, min(len(self.games) - 1, current_idx + delta))
        if new_idx == current_idx:
            return
        game_id = str(self.games[new_idx].get("gameId") or "")
        row = self._combo_game_row_by_id.get(game_id)
        if row is None:
            return
        self.game_combo.setCurrentIndex(row)

    def eventFilter(self, obj, event):
        if obj in getattr(self, "_nba_scroll_tables", set()):
            if event.type() == QEvent.KeyPress:
                if event.key() in (Qt.Key_Left, Qt.Key_Right):
                    bar = obj.horizontalScrollBar()
                    step = bar.singleStep() or 60
                    delta = step if event.key() == Qt.Key_Right else -step
                    bar.setValue(bar.value() + delta)
                    return True
        if self.sport_name.upper() == "NFL":
            nfl_views = getattr(self, "_nfl_scroll_views", {})
            if obj in nfl_views and event.type() == QEvent.Wheel:
                now = time.monotonic()
                if now - getattr(self, "_nfl_toggle_ts", 0.0) < 0.2:
                    return True
                self._nfl_toggle_ts = now
                self._toggle_nfl_table_mode(nfl_views[obj])
                return True
        return super().eventFilter(obj, event)

    def _current_game_index(self) -> int | None:
        if not self.selected_game_id:
            return None
        for i, g in enumerate(self.games):
            if g.get("gameId") == self.selected_game_id:
                return i
        return None

    def _set_top_background(
        self, away_primary: str, away_secondary: str, home_primary: str, home_secondary: str
    ) -> None:
        if getattr(self, "left_bg", None) is None or getattr(self, "right_bg", None) is None:
            return
        away_mid = self._mix_color(away_primary, away_secondary, 0.55)
        home_mid = self._mix_color(home_primary, home_secondary, 0.55)
        away_blend = self._mix_color(away_secondary, "#000000", 0.65)
        home_blend = self._mix_color(home_secondary, "#000000", 0.65)
        self.left_bg.setStyleSheet(
            f"""
            QFrame {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {away_primary},
                    stop:0.45 {away_primary},
                    stop:0.62 {away_mid},
                    stop:0.78 {away_secondary},
                    stop:0.9 {away_blend},
                    stop:1 #000000
                );
            }}
            """
        )
        if getattr(self, "seam_shadow", None) is not None:
            if self.sport_name.upper() == "NCAA BASKETBALL" and self._ncaa_basketball_theme_active():
                self.seam_shadow.setStyleSheet(
                    """
                    QFrame {
                        background: qlineargradient(
                            x1:0, y1:0, x2:1, y2:0,
                            stop:0 rgba(0, 0, 0, 0),
                            stop:0.18 rgba(0, 0, 0, 0.38),
                            stop:0.5 rgba(255, 170, 56, 0.72),
                            stop:0.82 rgba(0, 0, 0, 0.38),
                            stop:1 rgba(0, 0, 0, 0)
                        );
                    }
                    """
                )
            else:
                self.seam_shadow.setStyleSheet(
                    """
                    QFrame {
                        background: qlineargradient(
                            x1:0, y1:0, x2:1, y2:0,
                            stop:0 rgba(0, 0, 0, 0),
                            stop:0.25 rgba(0, 0, 0, 0.45),
                            stop:0.5 rgba(0, 0, 0, 0.85),
                            stop:0.75 rgba(0, 0, 0, 0.45),
                            stop:1 rgba(0, 0, 0, 0)
                        );
                    }
                    """
                )
            self.seam_shadow.show()
        if getattr(self, "nfl_bow_left", None) is not None:
            self.nfl_bow_left.hide()
        if getattr(self, "nfl_bow_right", None) is not None:
            self.nfl_bow_right.hide()
        self.right_bg.setStyleSheet(
            f"""
            QFrame {{
                background: qlineargradient(
                    x1:1, y1:0, x2:0, y2:1,
                    stop:0 {home_primary},
                    stop:0.45 {home_primary},
                    stop:0.62 {home_mid},
                    stop:0.78 {home_secondary},
                    stop:0.9 {home_blend},
                    stop:1 #000000
                );
            }}
            """
        )

    def _top_text_color(self, color_hex: str) -> str:
        luminance = self._color_luminance(color_hex)
        return "#0b0f16" if luminance > 0.6 else "#f7f7f7"

    def _hex_to_rgb(self, color_hex: str) -> tuple[int, int, int]:
        hex_value = (color_hex or "").lstrip("#")
        if len(hex_value) != 6:
            return (0, 0, 0)
        try:
            return tuple(int(hex_value[i : i + 2], 16) for i in (0, 2, 4))
        except Exception:
            return (0, 0, 0)

    def _rgb_to_hex(self, rgb: tuple[int, int, int]) -> str:
        r, g, b = [max(0, min(255, int(val))) for val in rgb]
        return f"#{r:02x}{g:02x}{b:02x}"

    def _color_luminance(self, color_hex: str) -> float:
        def _channel(val: int) -> float:
            srgb = val / 255.0
            if srgb <= 0.03928:
                return srgb / 12.92
            return ((srgb + 0.055) / 1.055) ** 2.4

        r, g, b = self._hex_to_rgb(color_hex)
        return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)

    def _color_contrast_ratio(self, color_a: str, color_b: str) -> float:
        lum_a = self._color_luminance(color_a)
        lum_b = self._color_luminance(color_b)
        hi = max(lum_a, lum_b)
        lo = min(lum_a, lum_b)
        return (hi + 0.05) / (lo + 0.05)

    def _color_hue_distance(self, color_a: str, color_b: str) -> float:
        ra, ga, ba = [channel / 255.0 for channel in self._hex_to_rgb(color_a)]
        rb, gb, bb = [channel / 255.0 for channel in self._hex_to_rgb(color_b)]
        hue_a = rgb_to_hls(ra, ga, ba)[0]
        hue_b = rgb_to_hls(rb, gb, bb)[0]
        distance = abs(hue_a - hue_b)
        return min(distance, 1.0 - distance)

    def _tone_variant(
        self,
        color_hex: str,
        *,
        target_lightness: float | None = None,
        lightness_delta: float = 0.0,
        saturation_scale: float = 1.0,
    ) -> str:
        r, g, b = [channel / 255.0 for channel in self._hex_to_rgb(color_hex)]
        hue, lightness, saturation = rgb_to_hls(r, g, b)
        if target_lightness is None:
            lightness = max(0.0, min(1.0, lightness + lightness_delta))
        else:
            lightness = max(0.0, min(1.0, target_lightness))
        saturation = max(0.0, min(1.0, saturation * saturation_scale))
        rr, gg, bb = hls_to_rgb(hue, lightness, saturation)
        return self._rgb_to_hex((round(rr * 255), round(gg * 255), round(bb * 255)))

    def _derive_panel_secondary(self, primary: str) -> str:
        lum = self._color_luminance(primary)
        _, lightness, saturation = rgb_to_hls(*[channel / 255.0 for channel in self._hex_to_rgb(primary)])
        if lum < 0.18:
            target_lightness = max(0.34, lightness + 0.22)
            saturation_scale = 0.48
        elif lum < 0.32:
            target_lightness = max(0.30, lightness + 0.16)
            saturation_scale = 0.55
        else:
            target_lightness = max(0.14, lightness - 0.18)
            saturation_scale = 0.68
        candidate = self._tone_variant(primary, target_lightness=target_lightness, saturation_scale=saturation_scale)
        if self._color_contrast_ratio(primary, candidate) < 1.6:
            if lum < 0.32:
                candidate = self._mix_color(primary, "#dbe5f2", 0.58)
            else:
                candidate = self._mix_color(primary, PANEL, 0.28)
        return candidate

    def _derive_panel_accent(self, primary: str) -> str:
        lum = self._color_luminance(primary)
        _, lightness, saturation = rgb_to_hls(*[channel / 255.0 for channel in self._hex_to_rgb(primary)])
        if lum < 0.28:
            target_lightness = max(0.58, lightness + 0.28)
            saturation_scale = max(0.5, min(0.9, saturation * 0.7))
        else:
            target_lightness = max(0.24, lightness - 0.16)
            saturation_scale = min(1.0, max(0.45, saturation * 0.75))
        return self._tone_variant(primary, target_lightness=target_lightness, saturation_scale=saturation_scale)

    def _resolve_team_theme_colors(
        self,
        tri: str | None,
        primary: str,
        secondary: str | None,
        accent: str | None,
    ) -> tuple[str, str, str]:
        sport = self.sport_name.upper()
        tri_key = (tri or "").upper()
        resolved_primary = primary or ACCENT
        resolved_secondary = secondary or self._mix_color(resolved_primary, PANEL, 0.3)
        resolved_accent = accent or resolved_secondary
        locked_secondary = False

        if sport == "MLB":
            override = MLB_BG_COLOR_OVERRIDES.get(tri_key)
            if override:
                resolved_primary, resolved_secondary = override
                locked_secondary = True
        elif sport == "NHL":
            override = NHL_BG_COLOR_OVERRIDES.get(tri_key)
            if override:
                resolved_primary, resolved_secondary = override
                locked_secondary = True

        contrast = self._color_contrast_ratio(resolved_primary, resolved_secondary)
        lum_gap = abs(self._color_luminance(resolved_primary) - self._color_luminance(resolved_secondary))
        hue_gap = self._color_hue_distance(resolved_primary, resolved_secondary)
        if not locked_secondary and (contrast < 1.55 or lum_gap < 0.055 or (hue_gap < 0.05 and contrast < 1.9)):
            resolved_secondary = self._derive_panel_secondary(resolved_primary)

        accent_contrast = self._color_contrast_ratio(resolved_primary, resolved_accent)
        accent_lum_gap = abs(self._color_luminance(resolved_primary) - self._color_luminance(resolved_accent))
        accent_hue_gap = self._color_hue_distance(resolved_primary, resolved_accent)
        if accent_contrast < 1.25 or (accent_hue_gap < 0.04 and accent_lum_gap < 0.09):
            resolved_accent = self._derive_panel_accent(resolved_primary)

        return resolved_primary, resolved_secondary, resolved_accent

    def _with_alpha(self, color_hex: str, alpha: float) -> str:
        try:
            hex_value = (color_hex or "").lstrip("#")
            if len(hex_value) != 6:
                return color_hex
            r = int(hex_value[0:2], 16)
            g = int(hex_value[2:4], 16)
            b = int(hex_value[4:6], 16)
        except Exception:
            return color_hex
        return f"rgba({r}, {g}, {b}, {alpha})"

    def _clean_nhl_clock_text(self, text: str) -> str:
        if not text:
            return text
        match = re.search(r"(\d{1,2}:\d{2})", str(text))
        if match:
            return match.group(1)
        return ""

    def _apply_period_label_style(self, sport: str) -> None:
        if not getattr(self, "center_panel", None):
            return
        if sport == "NHL":
            self.center_panel.period_label.setStyleSheet("color: #e6edf7; font-weight: 800; font-size: 16px;")
        elif sport == "NCAA BASKETBALL" and self._ncaa_basketball_theme_active():
            self.center_panel.period_label.setStyleSheet(
                "color: #ffd36e; font-weight: 900; font-size: 15px; letter-spacing: 0.8px;"
            )
        else:
            self.center_panel.period_label.setStyleSheet("color: #e6edf7; font-weight: 700; font-size: 14px;")

    def _apply_control_colors(self, left_text: str, right_text: str | None = None) -> None:
        right_color = right_text or left_text
        menu_bg = PANEL
        menu_text = self._top_text_color(menu_bg)
        menu_selected_text = self._top_text_color(ACCENT)
        menu_border = self._mix_color(menu_bg, menu_text, 0.18)

        def _combo_style(text_color: str) -> str:
            return f"""
            QComboBox {{
                background: transparent;
                border: none;
                padding: 0 6px;
                color: {text_color};
                font-weight: 700;
                font-size: 11px;
                letter-spacing: 0.5px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 0px;
            }}
            QComboBox::down-arrow {{
                image: none;
            }}
            QComboBox QAbstractItemView {{
                background: {menu_bg};
                border: 1px solid {menu_border};
                selection-background-color: {ACCENT};
                selection-color: {menu_selected_text};
                color: {menu_text};
            }}
        """

        sport_combo = getattr(self, "sport_combo", None)
        if sport_combo is not None:
            sport_combo.setStyleSheet(_combo_style(left_text))
        game_combo = getattr(self, "game_combo", None)
        if game_combo is not None:
            game_combo.setStyleSheet(_combo_style(left_text))
        if getattr(self, "settings_btn", None) is not None:
            self.settings_btn.setStyleSheet(
                f"""
                QToolButton {{
                    background: transparent;
                    border: none;
                    color: {left_text};
                    font-weight: 800;
                    font-size: 12px;
                }}
                QToolButton::menu-indicator {{ image: none; }}
                QToolButton:hover {{
                    color: {ACCENT};
                }}
                """
            )
        if getattr(self, "settings_menu", None) is not None:
            self.settings_menu.setStyleSheet(
                f"""
                QMenu {{
                    background-color: {menu_bg};
                    color: {menu_text};
                    border: 1px solid {menu_border};
                }}
                QMenu::item {{
                    padding: 6px 12px;
                    background: transparent;
                    color: {menu_text};
                }}
                QMenu::item:selected {{
                    background-color: {ACCENT};
                    color: {menu_selected_text};
                }}
                QMenu::separator {{
                    height: 1px;
                    margin: 4px 8px;
                    background: {menu_border};
                }}
                """
            )
        if getattr(self, "close_btn", None) is not None:
            self.close_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    color: {right_color};
                    font-weight: 800;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    color: {ACCENT};
                }}
                """
            )

    def _set_score_card_color(self, card: QFrame, color: str):
        card.setStyleSheet("background: transparent; border: none;")

    def _set_table_color(self, frame: QFrame, table: QTableWidget, color: str):
        frame_bg = self._mix_color(color, PANEL, 0.18)
        header_bg = self._mix_color(color, BG, 0.25)
        row_line = "rgba(255,255,255,0.08)"
        frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: {frame_bg};
                border: none;
                border-radius: 0px;
            }}
            """
        )
        table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {frame_bg};
                color: {TEXT};
                border: none;
                alternate-background-color: {self._mix_color(color, BG, 0.28)};
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {TEXT};
                font-weight: 800;
                border: none;
                padding: 4px;
            }}
            QTableWidget::item {{
                padding: 2px 3px 2px 6px;
                font-weight: 700;
                border-bottom: 1px solid {row_line};
            }}
            """
        )
        return

        # table tint
        table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {frame_bg};
                gridline-color: #2b3e55;
                color: {TEXT};
                alternate-background-color: {self._mix_color(color, BG, 0.32)};
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {TEXT};
                font-weight: bold;
                border: 0px;
                padding: 6px;
            }}
            QTableWidget::item {{
                padding: 4px;
            }}
            """
        )

    def apply_team_logo_style(self, box: CircularLogoGlow, tri: str, primary: str, accent: str):
        tri_key = (tri or "").upper()
        secondary = getattr(self.backend, "TEAM_SECONDARY_COLORS", {}).get(tri_key, self._mix_color(primary, BG, 0.4))
        if self.sport_name.upper() == "NHL":
            secondary = getattr(self.backend, "TEAM_ALT_COLORS", {}).get(tri_key, secondary)
        resolved_primary, resolved_secondary, resolved_accent = self._resolve_team_theme_colors(
            tri_key, primary, secondary, accent
        )
        box.set_colors(resolved_primary, resolved_secondary, resolved_accent)
        scale = LOGO_SCALE_OVERRIDES.get(tri, DEFAULT_LOGO_SCALE)
        box.set_logo_scale(scale)
        box.set_logo_y_offset(LOGO_Y_OFFSET_OVERRIDES.get(tri, 0))
        shadow = LOGO_SHADOW_OVERRIDES.get(tri)
        if shadow:
            box.set_logo_shadow(
                shadow.get("dx", 0),
                shadow.get("dy", 0),
                shadow.get("alpha", 0),
                shadow.get("scale", 1.0),
            )
        else:
            box.set_logo_shadow(0, 0, 0)

    def _mix_color(self, color_hex: str, base_hex: str, factor: float) -> str:
        def _to_rgb(h: str):
            h = h.lstrip("#")
            if len(h) != 6:
                return (0, 0, 0)
            return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))

        def _to_hex(rgb):
            return "#%02x%02x%02x" % rgb

        c = _to_rgb(color_hex)
        b = _to_rgb(base_hex)
        mix = tuple(int(c[i] * factor + b[i] * (1 - factor)) for i in range(3))
        return _to_hex(mix)
