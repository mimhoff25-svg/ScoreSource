"""
PySide6 UI for ScoreSource.
Layout: neon night 1280x480 scoreboard with team panels, center clock/shot clock,
and player stat tables. Periodically polls the data layer in nba.py.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Callable

from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QPoint, QRect
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
)
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QLabel,
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
    QScroller,
    QSizePolicy,
    QApplication,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QToolButton,
    QMenu,
)

import nba  # local module
from logic import ScoreSourceLogic
from realtime import RealTimeGameState

# Palette
BG = "#050b16"
PANEL = "#0b1220"
CARD = "#111b2a"
ACCENT = "#45e0ff"
ACCENT_SOFT = "#7cf3c8"
TEXT = "#eaf4ff"
TEXT_MUTED = "#6d88ab"
STATE_PATH = Path.home() / ".cache" / "scoresource" / "state.json"
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


class CircularLogoGlow(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(230, 190)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background-color: transparent;")
        self._primary = QColor(ACCENT)
        self._secondary = QColor(ACCENT)
        self._accent = QColor(ACCENT)
        self._pixmap: QPixmap | None = None
        self._radius = 24

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 210))
        self.setGraphicsEffect(shadow)

    def set_colors(self, primary: str, secondary: str, accent: str):
        self._primary = QColor(primary)
        self._secondary = QColor(secondary)
        self._accent = QColor(accent)
        self.update()

    def set_logo(self, pixmap: QPixmap | None):
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        full_rect = self.rect()
        painter.fillRect(full_rect, Qt.transparent)

        panel_rect = full_rect.adjusted(8, 10, -8, -10)
        radius = min(self._radius, min(panel_rect.width(), panel_rect.height()) / 2 - 2)

        # Soft outer glow in team primary (radial gradient fading to background)
        painter.setPen(Qt.NoPen)
        glow_rect = panel_rect.adjusted(-12, -12, 12, 12)
        glow_radius = radius + 12
        glow_grad = QRadialGradient(glow_rect.center(), max(glow_rect.width(), glow_rect.height()) * 0.55)
        c0 = QColor(self._primary)
        c0.setAlpha(160)
        c1 = QColor(self._primary)
        c1.setAlpha(90)
        c2 = QColor(self._primary)
        c2.setAlpha(0)
        glow_grad.setColorAt(0.0, c0)
        glow_grad.setColorAt(0.5, c1)
        glow_grad.setColorAt(1.0, c2)
        painter.setBrush(glow_grad)
        painter.drawRoundedRect(glow_rect, glow_radius, glow_radius)

        # Gradient fill based on team colors
        base_top = QColor(self._primary).lighter(135)
        mid = QColor(self._secondary)
        base_bottom = QColor(self._primary).darker(145)
        grad = QLinearGradient(panel_rect.topLeft(), panel_rect.bottomLeft())
        grad.setColorAt(0.0, base_top)
        grad.setColorAt(0.55, mid)
        grad.setColorAt(1.0, base_bottom)

        border_color = QColor(self._primary).darker(180)
        painter.setBrush(grad)
        painter.setPen(QPen(border_color, 2))
        painter.drawRoundedRect(panel_rect, radius, radius)

        # Inner plate for the logo (subtle tint + inner stroke)
        plate = panel_rect.adjusted(12, 12, -12, -12)
        plate_radius = max(10, radius - 6)
        plate_grad = QLinearGradient(plate.topLeft(), plate.bottomLeft())
        plate_grad.setColorAt(0.0, QColor(self._secondary).lighter(120))
        plate_grad.setColorAt(1.0, QColor(self._secondary).darker(130))
        painter.setBrush(plate_grad)
        painter.setPen(QPen(QColor(self._primary).darker(200), 1.6))
        painter.drawRoundedRect(plate, plate_radius, plate_radius)

        # Top highlight strip
        highlight_height = int(plate.height() * 0.55)
        highlight = plate.adjusted(4, 4, -4, -highlight_height)
        highlight_grad = QLinearGradient(highlight.topLeft(), highlight.bottomLeft())
        highlight_grad.setColorAt(0.0, QColor(255, 255, 255, 80))
        highlight_grad.setColorAt(1.0, QColor(255, 255, 255, 8))
        painter.setBrush(highlight_grad)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(highlight, plate_radius - 4, plate_radius - 4)

        # Center logo
        if self._pixmap:
            max_size = min(plate.width(), plate.height()) * 0.75
            scaled = self._pixmap.scaled(max_size, max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_rect = QRectF(
                plate.center().x() - scaled.width() / 2,
                plate.center().y() - scaled.height() / 2,
                scaled.width(),
                scaled.height(),
            )
            painter.drawPixmap(logo_rect.topLeft(), scaled)


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

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        data = index.data(Qt.UserRole)
        display = index.data(Qt.DisplayRole) or ""

        painter.save()
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.instance().style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter)

        rect = opt.rect.adjusted(6, 0, -6, 0)
        painter.setFont(opt.font)
        fm = painter.fontMetrics()

        # If no structured data, fall back to default text.
        if not isinstance(data, dict):
            painter.setPen(opt.palette.text().color())
            painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, display)
            painter.restore()
            return

        away_name = data.get("away_name", "")
        home_name = data.get("home_name", "")
        away_score = int(data.get("away_score") or 0)
        home_score = int(data.get("home_score") or 0)
        status = data.get("status", "")

        status_text = f"({status})" if status else ""
        status_w = fm.horizontalAdvance(status_text) + 6
        status_rect = QRect(rect.right() - status_w, rect.top(), status_w, rect.height())
        text_area_right = status_rect.left() - 8

        away_seg = f"{away_name} {away_score}"
        home_seg = f"{home_name} {home_score}"
        at_seg = " @ "

        w_away = fm.horizontalAdvance(away_seg)
        w_home = fm.horizontalAdvance(home_seg)
        w_at = fm.horizontalAdvance(at_seg)

        x = rect.left()
        center_y = rect.center().y()

        leader = "away" if away_score > home_score else ("home" if home_score > away_score else None)
        pad = 6

        # Draw leader highlight
        def _highlight(x_pos: int, width: int):
            box_rect = QRect(x_pos - pad // 2, rect.top() + 4, width + pad, rect.height() - 8)
            grad = QLinearGradient(box_rect.topLeft(), box_rect.bottomLeft())
            grad.setColorAt(0.0, QColor("#3a3f48"))
            grad.setColorAt(1.0, QColor("#2a2f36"))
            painter.setBrush(QBrush(grad))
            painter.setPen(QPen(QColor("#4a505a"), 1.4))
            painter.drawRoundedRect(box_rect, 8, 8)

        # Draw away segment
        if leader == "away":
            _highlight(x, w_away)
        painter.setPen(opt.palette.text().color())
        painter.drawText(QRect(x, rect.top(), w_away, rect.height()), Qt.AlignVCenter | Qt.AlignLeft, away_seg)
        x += w_away

        # Separator
        painter.drawText(QRect(x, rect.top(), w_at, rect.height()), Qt.AlignVCenter | Qt.AlignLeft, at_seg)
        x += w_at

        # Home segment
        if leader == "home":
            _highlight(x, w_home)
        painter.drawText(QRect(x, rect.top(), w_home, rect.height()), Qt.AlignVCenter | Qt.AlignLeft, home_seg)

        # Status aligned right
        painter.setPen(QColor("#9ca9bf"))
        painter.drawText(status_rect, Qt.AlignVCenter | Qt.AlignRight, status_text)
        painter.restore()


class ScoreCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD};
                border-radius: 14px;
                border: 2px solid #26344a;
            }}
            """
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)


class CenterPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(f"background-color: {PANEL}; border-radius: 10px; border: 1px solid #1c2a3a;")
        self.setFixedWidth(220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        self.period_badge = QFrame()
        self.period_badge.setFrameShape(QFrame.StyledPanel)
        self.period_badge.setStyleSheet("background-color: #2a2f38; border-radius: 6px;")
        badge_layout = QHBoxLayout(self.period_badge)
        badge_layout.setContentsMargins(10, 4, 10, 4)
        badge_layout.setSpacing(0)
        self.period_label = QLabel("Q-")
        self.period_label.setAlignment(Qt.AlignCenter)
        self.period_label.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 18px;")
        badge_layout.addWidget(self.period_label)

        self.clock_frame = QFrame()
        self.clock_frame.setFrameShape(QFrame.StyledPanel)
        self.clock_frame.setStyleSheet("background-color: #d0d3d9; border-radius: 8px;")
        clock_layout = QHBoxLayout(self.clock_frame)
        clock_layout.setContentsMargins(12, 8, 12, 8)
        clock_layout.setSpacing(0)
        self.clock_label = QLabel("12:00")
        self.clock_label.setAlignment(Qt.AlignCenter)
        self.clock_label.setStyleSheet("color: #111; font-weight: 800; font-size: 30px;")
        clock_layout.addWidget(self.clock_label)

        self.bottom_row = QHBoxLayout()
        self.bottom_row.setContentsMargins(4, 0, 4, 0)
        self.bottom_row.setSpacing(8)
        self.bottom_left = QLabel("")
        self.bottom_left.setAlignment(Qt.AlignCenter)
        self.bottom_left.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;")
        self.bottom_right = QLabel("")
        self.bottom_right.setAlignment(Qt.AlignCenter)
        self.bottom_right.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;")
        self.bottom_row.addWidget(self.bottom_left, stretch=1)
        self.bottom_row.addWidget(self.bottom_right, stretch=1)

        layout.addWidget(self.period_badge)
        layout.addWidget(self.clock_frame)
        layout.addLayout(self.bottom_row)

    def set_state(self, period_text: str, clock_text: str, bottom_left: str = "", bottom_right: str = ""):
        self.period_label.setText(period_text)
        self.clock_label.setText(clock_text)
        self.bottom_left.setText(bottom_left)
        self.bottom_right.setText(bottom_right)


class ScoreSourceWindow(QMainWindow):
    scores_ready = Signal(dict)
    boxscore_ready = Signal(dict)
    logo_ready = Signal(str, object)
    scores_fetched = Signal(dict)  # cross-thread handoff before delay
    boxscore_fetched = Signal(str, object)
    realtime_ready = Signal(object)

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
        self.setWindowTitle(f"ScoreSource – {self.sport_name}")
        self.resize(1280, 480)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setAutoFillBackground(True)
        self._default_icon = QIcon(self._make_default_icon())
        self.setWindowIcon(self._default_icon)

        self.backend = backend_module or nba
        self.display_tz = os.environ.get("SCORESOURCE_TZ", "America/Chicago")
        if logic is not None:
            self.logic = logic
        else:
            self.logic = ScoreSourceLogic() if self.backend is nba else None
        self._switch_sport = switch_sport
        self._sport_options = sport_options or ["NBA"]
        self._sport_icon_map = sport_icon_map or {}
        self._sport_logo_path = sport_logo_path
        self.games: List[Dict[str, Any]] = []
        self.lines: List[str] = []
        self.selected_game_id: str | None = None
        self._pending_selection_id: str | None = None
        self.display_delay_ms = 500  # minimal delay to show scores quickly
        self._next_display_at: float | None = None
        self._cached_state = self._load_cached_state() if self.sport_name == "NBA" else None
        self._clock_state: Dict[str, Any] | None = None
        self._instant_boxscore_apply = False
        self.clock_buffer_sec = 0.5  # small buffer to reduce jitter

        self._apply_palette()
        self._build_layout()
        self._setup_timers()

        self.scores_fetched.connect(self._schedule_scores_emit)
        self.boxscore_fetched.connect(self._schedule_boxscore_emit)
        self.scores_ready.connect(self._apply_scores)
        self.boxscore_ready.connect(self.apply_boxscore)
        self.logo_ready.connect(self._apply_logo_bytes)
        self.realtime_ready.connect(self._apply_realtime_state)

        self._shortcut_up = QShortcut(Qt.Key_Up, self)
        self._shortcut_up.activated.connect(lambda: self._step_game_selection(-1))
        self._shortcut_down = QShortcut(Qt.Key_Down, self)
        self._shortcut_down.activated.connect(lambda: self._step_game_selection(1))

        self._executor = ThreadPoolExecutor(max_workers=4)
        self._scores_future = None
        self._boxscore_future = None
        self._last_logo_keys: Dict[str, tuple[str, str]] = {"home": ("", ""), "away": ("", "")}
        self._alive = True

        self.refresh_scores()  # initial fetch
        self._apply_cached_state_if_available()

    def _make_default_icon(self) -> QPixmap:
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
        layout = QGridLayout(root)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setVerticalSpacing(14)
        layout.setHorizontalSpacing(0)

        # Row 0: control bar with sport selector, game selector and close button
        control_bar = QHBoxLayout()
        control_bar.setSpacing(10)
        control_bar.addStretch(1)

        self.sport_combo = QComboBox()
        for name in self._sport_options:
            icon = QIcon(self._sport_icon_map.get(name, "")) if name in self._sport_icon_map else QIcon()
            self.sport_combo.addItem(icon, name)
        try:
            idx = self._sport_options.index(self.sport_name)
            self.sport_combo.setCurrentIndex(idx)
        except Exception:
            pass
        self.sport_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: #0f1724;
                padding: 8px 12px;
                border-radius: 8px;
                color: {TEXT};
                border: 2px solid {ACCENT};
                font-weight: 700;
                letter-spacing: 1px;
            }}
            QComboBox QAbstractItemView {{
                background: {PANEL};
                selection-background-color: {ACCENT};
                color: {TEXT};
            }}
            """
        )
        self.sport_combo.currentTextChanged.connect(self._on_sport_change)

        title = QLabel("GAME SELECT")
        title.setStyleSheet(f"color: {ACCENT}; font-size: 16px; font-weight: bold;")
        self.game_combo = QComboBox()
        self.game_combo.setObjectName("game_combo")
        self.game_combo.setPlaceholderText("GAME SELECT")
        self.game_combo.setItemDelegate(GameLineDelegate(self.game_combo))
        self.game_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: #0f1724;
                padding: 8px 12px;
                border-radius: 8px;
                color: {TEXT};
                border: 2px solid {ACCENT};
                font-weight: 700;
                letter-spacing: 1px;
            }}
            QComboBox QAbstractItemView {{
                background: {PANEL};
                selection-background-color: {ACCENT};
                color: {TEXT};
            }}
            """
        )
        self.game_combo.currentIndexChanged.connect(self.on_game_selected)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {CARD};
                color: {TEXT};
                border: 1px solid #1f2a3d;
                border-radius: 6px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {ACCENT};
                color: {BG};
            }}
            """
        )
        close_btn.clicked.connect(self.close)

        # league logo in top-left
        self.league_logo = QLabel()
        self.league_logo.setFixedSize(32, 32)
        if self._sport_logo_path and Path(self._sport_logo_path).exists():
            pix = QPixmap(self._sport_logo_path).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.league_logo.setPixmap(pix)
        control_bar.addWidget(self.league_logo, alignment=Qt.AlignLeft)
        control_bar.addWidget(self.sport_combo, alignment=Qt.AlignLeft)
        control_bar.addWidget(self.game_combo, alignment=Qt.AlignLeft)
        control_bar.addWidget(title, alignment=Qt.AlignLeft)
        # settings (timezone)
        self.settings_menu = QMenu(self)
        self.timezone_actions: list[QAction] = []
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
        self._sync_timezone_actions()
        settings_btn = QToolButton()
        settings_btn.setText("⚙")
        settings_btn.setFixedSize(30, 30)
        settings_btn.setPopupMode(QToolButton.InstantPopup)
        settings_btn.setMenu(self.settings_menu)
        settings_btn.setStyleSheet(
            f"""
            QToolButton {{
                background-color: {CARD};
                color: {TEXT};
                border: 1px solid #1f2a3d;
                border-radius: 6px;
                font-weight: bold;
            }}
            QToolButton::menu-indicator {{ image: none; }}
            QToolButton:hover {{
                background-color: {ACCENT};
                color: {BG};
            }}
            """
        )
        control_bar.addStretch(1)
        # drag handle adjacent to exit for window move
        self.drag_bar = DragBar(self)
        self.drag_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        control_bar.addWidget(settings_btn, alignment=Qt.AlignRight)
        control_bar.addWidget(self.drag_bar, stretch=1)
        control_bar.addWidget(close_btn, alignment=Qt.AlignRight)
        layout.addLayout(control_bar, 0, 0, 1, 3)

        # main scoreboard row (row 1) as a single horizontal strip
        layout.setRowStretch(1, 1)
        layout.setRowStretch(2, 2)

        top_strip = QHBoxLayout()
        top_strip.setSpacing(20)
        top_strip.setContentsMargins(0, 0, 0, 0)

        # ---------- LEFT TEAM ----------
        left_block = QVBoxLayout()
        left_block.setSpacing(6)
        left_block.setAlignment(Qt.AlignCenter)

        self.away_city = QLabel("")
        self.away_city.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.away_logo_box = CircularLogoGlow()
        self.away_name = QLabel("AWAY TEAM")
        self.away_name.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.away_record = QLabel("--")
        self.away_record.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; font-weight: 600;")

        left_block.addWidget(self.away_city, alignment=Qt.AlignCenter)
        left_block.addWidget(self.away_logo_box, alignment=Qt.AlignCenter)
        left_block.addWidget(self.away_name, alignment=Qt.AlignCenter)
        left_block.addWidget(self.away_record, alignment=Qt.AlignCenter)

        # ---------- SCORES + CLOCK CLUSTER ----------
        self.away_score_card = ScoreCard()
        self.away_score_card.setFixedWidth(95)
        self.away_score_card.setFixedHeight(70)
        away_score_layout = QVBoxLayout(self.away_score_card)
        away_score_layout.setContentsMargins(6, 4, 6, 4)
        self.away_score = QLabel("0")
        self.away_score.setAlignment(Qt.AlignCenter)
        self.away_score.setStyleSheet("font-size: 38px; font-weight: 800; color: white;")
        away_score_outline = QGraphicsDropShadowEffect(self.away_score)
        away_score_outline.setBlurRadius(2)
        away_score_outline.setOffset(0, 0)
        away_score_outline.setColor(QColor(0, 0, 0, 230))
        self.away_score.setGraphicsEffect(away_score_outline)
        away_score_layout.addWidget(self.away_score)

        self.center_panel = CenterPanel()

        self.home_score_card = ScoreCard()
        self.home_score_card.setFixedWidth(95)
        self.home_score_card.setFixedHeight(70)
        home_score_layout = QVBoxLayout(self.home_score_card)
        home_score_layout.setContentsMargins(6, 4, 6, 4)
        self.home_score = QLabel("0")
        self.home_score.setAlignment(Qt.AlignCenter)
        self.home_score.setStyleSheet("font-size: 38px; font-weight: 800; color: white;")
        home_score_outline = QGraphicsDropShadowEffect(self.home_score)
        home_score_outline.setBlurRadius(2)
        home_score_outline.setOffset(0, 0)
        home_score_outline.setColor(QColor(0, 0, 0, 230))
        self.home_score.setGraphicsEffect(home_score_outline)
        home_score_layout.addWidget(self.home_score)

        center_row = QHBoxLayout()
        center_row.setSpacing(8)
        center_row.setAlignment(Qt.AlignBottom)
        center_row.addWidget(self.away_score_card, alignment=Qt.AlignBottom)
        center_row.addWidget(self.center_panel, alignment=Qt.AlignBottom)
        center_row.addWidget(self.home_score_card, alignment=Qt.AlignBottom)

        # ---------- RIGHT TEAM ----------
        right_block = QVBoxLayout()
        right_block.setSpacing(6)
        right_block.setAlignment(Qt.AlignCenter)

        self.home_city = QLabel("")
        self.home_city.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.home_logo_box = CircularLogoGlow()
        self.home_name = QLabel("HOME TEAM")
        self.home_name.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.home_record = QLabel("--")
        self.home_record.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; font-weight: 600;")

        right_block.addWidget(self.home_city, alignment=Qt.AlignCenter)
        right_block.addWidget(self.home_logo_box, alignment=Qt.AlignCenter)
        right_block.addWidget(self.home_name, alignment=Qt.AlignCenter)
        right_block.addWidget(self.home_record, alignment=Qt.AlignCenter)

        top_strip.addLayout(left_block, stretch=2)
        top_strip.addLayout(center_row, stretch=3)
        top_strip.addLayout(right_block, stretch=2)
        layout.addLayout(top_strip, 1, 0, 1, 3)

        # ---------- PLAYER TABLES (row 2 in main layout) ----------
        bottom = QGridLayout()
        bottom.setHorizontalSpacing(20)
        headers = getattr(self.backend, "sport_table_headers", ["#", "Player", "Min", "Pos", "Pts", "Reb", "Ast", "PF"])
        self.away_table_frame, self.away_table = self._make_table("STATS", headers)
        self.home_table_frame, self.home_table = self._make_table("STATS", headers)
        self.away_table_frame.setMinimumHeight(260)
        self.home_table_frame.setMinimumHeight(260)
        bottom.addWidget(self.away_table_frame, 0, 0)
        spacer = QWidget()
        bottom.addWidget(spacer, 0, 1)
        bottom.addWidget(self.home_table_frame, 0, 2)
        layout.addLayout(bottom, 2, 0, 1, 3)

        # ---------- BOTTOM INFO BAR (row 3) ----------
        self.bottom_bar = QFrame()
        self.bottom_bar.setFrameShape(QFrame.StyledPanel)
        self.bottom_bar.setStyleSheet("background-color: #0c121d; border: 1px solid #1c2a3a; border-radius: 8px;")
        bar_layout = QHBoxLayout(self.bottom_bar)
        bar_layout.setContentsMargins(12, 6, 12, 6)
        bar_layout.setSpacing(8)

        self.bottom_left_label = QLabel("AWY (--)")
        self.bottom_left_label.setAlignment(Qt.AlignCenter)
        self.bottom_left_label.setStyleSheet(f"color: {TEXT}; font-weight: bold; font-size: 14px;")
        self.bottom_center_label = QLabel("BONUS")
        self.bottom_center_label.setAlignment(Qt.AlignCenter)
        self.bottom_center_label.setStyleSheet(f"color: {ACCENT}; font-weight: 800; font-size: 14px;")
        self.bottom_right_label = QLabel("HME (--)")
        self.bottom_right_label.setAlignment(Qt.AlignCenter)
        self.bottom_right_label.setStyleSheet(f"color: {TEXT}; font-weight: bold; font-size: 14px;")

        bar_layout.addWidget(self.bottom_left_label, stretch=1)
        bar_layout.addWidget(self.bottom_center_label, stretch=1)
        bar_layout.addWidget(self.bottom_right_label, stretch=1)

        layout.addWidget(self.bottom_bar, 3, 0, 1, 3)

        self.setCentralWidget(root)

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
        vbox = QVBoxLayout(frame)
        label = QLabel(title)
        label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {ACCENT};")
        label.setVisible(False)
        label.setFixedHeight(0)
        vbox.addWidget(label)

        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setShowGrid(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        QScroller.grabGesture(table.viewport(), QScroller.LeftMouseButtonGesture)
        QScroller.grabGesture(table.viewport(), QScroller.TouchGesture)
        table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {PANEL};
                gridline-color: #2b3e55;
                color: #ffffff;
                alternate-background-color: #0d1523;
            }}
            QHeaderView::section {{
                background-color: #1c2a3e;
                color: #ffffff;
                font-weight: bold;
                border: 0px;
                padding: 6px;
            }}
            QTableWidget::item {{
                padding: 4px;
            }}
            """
        )
        vbox.addWidget(table)
        return frame, table

    # --------------- timers ---------------
    def _setup_timers(self):
        self.scores_timer = QTimer(self)
        self.scores_timer.timeout.connect(self.refresh_scores)
        self.scores_timer.start(30_000)

        self.boxscore_timer = QTimer(self)
        self.boxscore_timer.timeout.connect(self.refresh_boxscore)
        self.boxscore_timer.start(1_000)

        self.clock_tick_timer = QTimer(self)
        self.clock_tick_timer.timeout.connect(self._tick_clock)
        self.clock_tick_timer.start(500)

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
            # persist alongside cached state for NBA
            try:
                if self._cached_state is not None:
                    self._cached_state["timezone"] = tz
            except Exception:
                pass

    def _sync_timezone_actions(self):
        for act in getattr(self, "timezone_actions", []):
            act.setChecked(str(act.data()) == self.display_tz)

    # --------------- data refresh ---------------
    def refresh_scores(self):
        if self._scores_future and not self._scores_future.done():
            return
        if self.logic is not None:
            self._scores_future = self._executor.submit(self.logic.get_scoreboard)
        else:
            self._scores_future = self._executor.submit(self.backend.fetch_scoreboard)
        self._scores_future.add_done_callback(self._on_scores_ready)

    def _on_scores_ready(self, future):
        if not self._alive:
            return
        try:
            data = future.result()
        except Exception:
            return
        self.scores_fetched.emit(data)

    def _schedule_scores_emit(self, data: Dict[str, Any]):
        now = time.monotonic()
        # anchor both score and boxscore display to the same target
        self._next_display_at = now + (self.display_delay_ms / 1000.0)
        target_id, _ = self._preferred_game_id(data.get("games", []) or [])
        self._pending_selection_id = target_id
        if target_id:
            self._start_boxscore_prefetch(target_id)
        QTimer.singleShot(self._remaining_delay_ms(), lambda d=data: self._emit_scores_if_current(d))

    def _emit_scores_if_current(self, data: Dict[str, Any]):
        if not self._alive:
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
        return games[0].get("gameId"), 0

    def _start_boxscore_prefetch(self, game_id: str):
        if self._boxscore_future and not self._boxscore_future.done():
            return
        self._boxscore_future = self._executor.submit(self.backend.fetch_boxscore, game_id)
        self._boxscore_future.add_done_callback(lambda fut, gid=game_id: self._on_boxscore_ready(gid, fut))

    def _start_realtime_for_game(self, game_id: str):
        if not self.logic:
            return
        try:
            self.logic.start_realtime(game_id, self._on_realtime_update)
        except Exception:
            pass

    def _apply_scores(self, data: Dict[str, Any]):
        self.games = data.get("games", []) or []
        self.lines = []

        self.game_combo.blockSignals(True)
        self.game_combo.clear()
        self.game_combo.addItem("GAME SELECT", None)
        for g in self.games:
            away_team = g.get("awayTeam") or {}
            home_team = g.get("homeTeam") or {}
            away_name = away_team.get("teamName", "Away")
            home_name = home_team.get("teamName", "Home")
            away_score = int(away_team.get("score") or 0)
            home_score = int(home_team.get("score") or 0)
            status = g.get("gameStatusText", "Scheduled")
            line_text = f"{away_name} {away_score} @ {home_name} {home_score}"
            self.lines.append(f"{line_text} ({status})")
            self.game_combo.addItem(
                line_text,
                {
                    "gameId": g.get("gameId"),
                    "away_name": away_name,
                    "home_name": home_name,
                    "away_score": away_score,
                    "home_score": home_score,
                    "status": status,
                },
            )
        self.game_combo.blockSignals(False)

        if not self.games:
            self.selected_game_id = None
            message = (data.get("lines") or ["No games today."])[0]
            self._clear_ui_for_no_games(message)
            return

        # keep previous selection if still present, otherwise pick first
        target_id, idx = self._preferred_game_id(self.games)
        self.selected_game_id = target_id

        self.game_combo.blockSignals(True)
        self._show_placeholder()
        self.game_combo.blockSignals(False)
        self._pending_selection_id = None
        if self.selected_game_id:
            self._start_realtime_for_game(self.selected_game_id)
        self.refresh_boxscore()

    def refresh_boxscore(self):
        game_id = self.selected_game_id or self._pending_selection_id
        if not game_id:
            return
        if self._boxscore_future and not self._boxscore_future.done():
            return
        self._boxscore_future = self._executor.submit(self.backend.fetch_boxscore, game_id)
        self._boxscore_future.add_done_callback(lambda fut, gid=game_id: self._on_boxscore_ready(gid, fut))

    def _on_boxscore_ready(self, game_id: str, future):
        if not self._alive:
            return
        try:
            data = future.result()
        except Exception:
            data = None
        if data is None:
            data = self._build_boxscore_stub(game_id)
        if game_id not in (self.selected_game_id, self._pending_selection_id):
            return
        self.boxscore_fetched.emit(game_id, data)

    def _schedule_boxscore_emit(self, game_id: str, data: Dict[str, Any]):
        delay = 1 if self._instant_boxscore_apply else self._remaining_delay_ms()
        QTimer.singleShot(delay, lambda gid=game_id, d=data: self._emit_boxscore_if_current(gid, d))
        self._instant_boxscore_apply = False

    def _emit_boxscore_if_current(self, game_id: str, data: Dict[str, Any]):
        if not self._alive:
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
        game = data["game"]
        home = data["home"]
        away = data["away"]

        # quarter + clock
        self._apply_clock(data)

        # team names & tricodes
        away_name = away.get("teamName", "Away")
        home_name = home.get("teamName", "Home")
        away_tri = (away.get("teamTricode") or "")[:3].upper()
        home_tri = (home.get("teamTricode") or "")[:3].upper()
        away_city = (away.get("teamCity") or away.get("city") or "").upper()
        home_city = (home.get("teamCity") or home.get("city") or "").upper()
        away_record = self._team_record_text(away, "away")
        home_record = self._team_record_text(home, "home")

        self.away_name.setText(away_name.upper())
        self.home_name.setText(home_name.upper())
        self.away_city.setText(away_city)
        self.home_city.setText(home_city)
        self.away_record.setText(away_record)
        self.home_record.setText(home_record)

        away_color = self._team_color(away_tri)
        home_color = self._team_color(home_tri)
        away_alt = self._team_alt_color(away_tri)
        home_alt = self._team_alt_color(home_tri)
        self.apply_team_logo_style(self.away_logo_box, away_tri, away_color, away_alt)
        self.apply_team_logo_style(self.home_logo_box, home_tri, home_color, home_alt)
        self.away_name.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {away_alt};")
        self.home_name.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {home_alt};")
        self.away_record.setStyleSheet(f"color: {away_alt}; font-size: 13px; font-weight: 600;")
        self.home_record.setStyleSheet(f"color: {home_alt}; font-size: 13px; font-weight: 600;")
        self._set_score_card_color(self.away_score_card, away_color)
        self._set_score_card_color(self.home_score_card, home_color)
        self._set_table_color(self.away_table_frame, self.away_table, away_color)
        self._set_table_color(self.home_table_frame, self.home_table, home_color)

        # logos fetched off the UI thread
        self._request_logo("away", away)
        self._request_logo("home", home)

        # scores
        a_score = self.backend.safe_score(away)
        h_score = self.backend.safe_score(home)

        self.away_score.setText(str(a_score))
        self.home_score.setText(str(h_score))

        # tables
        self.fill_team_table(self.away_table, away)
        self.fill_team_table(self.home_table, home)
        self._update_bottom_bar(away, home)
        self._save_cached_state(data)

    def fill_team_table(self, table: QTableWidget, team: Dict[str, Any]):
        players = team.get("players", []) or []
        players = sorted(
            players,
            key=lambda p: (
                0 if (p.get("statistics", {}) or {}).get("isOnCourt") else 1,
                p.get("order", 9999),
            ),
        )
        table.setRowCount(0)
        headers_count = table.columnCount()
        for p in players:
            stats = p.get("statistics", {}) or {}
            jersey = p.get("jerseyNum") or ""
            first = (p.get("firstName") or "").strip()
            last = (p.get("familyName") or "").strip()
            name = f"{first} {last}".strip() or "Player"
            pos = p.get("position") or ""
            minutes = self.backend.format_time_played(stats.get("minutes") or stats.get("minutesCalculated"))
            pts = str(stats.get("points", 0))
            reb = str(stats.get("reboundsTotal", stats.get("rebounds", 0)))
            ast = str(stats.get("assists", 0))
            pf = str(stats.get("personalFouls", 0))

            row = table.rowCount()
            table.insertRow(row)
            values = [jersey, name, minutes, pos, pts, reb, ast, pf]
            for col, val in enumerate(values[:headers_count]):
                item = QTableWidgetItem(val)
                if col in (0, 4, 5, 6, 7):
                    item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)

    def on_game_selected(self, index: int):
        if index <= 0 or index - 1 >= len(self.games):
            return
        game = self.games[index - 1]
        self.selected_game_id = game.get("gameId")
        self._pending_selection_id = None
        self._instant_boxscore_apply = True
        if self.selected_game_id:
            self._start_realtime_for_game(self.selected_game_id)
        self.refresh_boxscore()
        self._show_placeholder()

    def _request_logo(self, side: str, team: Dict[str, Any]):
        box = self.away_logo_box if side == "away" else self.home_logo_box
        team_id = team.get("teamId")
        tri = (team.get("teamTricode") or "").upper()

        if not (team_id or tri):
            self._last_logo_keys[side] = ("", "")
            box.set_logo(None)
            if side == "home":
                self.setWindowIcon(self._default_icon)
            return

        key = (str(team_id or ""), tri)
        if self._last_logo_keys.get(side) == key:
            return
        box.set_logo(None)
        self._last_logo_keys[side] = key

        future = self._executor.submit(self.backend.load_logo, team_id, tri)
        future.add_done_callback(lambda fut, s=side, k=key: self._on_logo_ready(s, k, fut))

    def _on_logo_ready(self, side: str, key: tuple[str, str], future):
        if not self._alive:
            return
        try:
            data = future.result()
        except Exception:
            data = None
        if self._last_logo_keys.get(side) != key:
            return
        self.logo_ready.emit(side, data)

    def _apply_logo_bytes(self, side: str, data: bytes | None):
        box = self.away_logo_box if side == "away" else self.home_logo_box
        if data:
            pix = self._load_logo_pixmap(data, box.width())
            if pix:
                box.set_logo(pix)
                if side == "home":
                    self.setWindowIcon(QIcon(pix))
                return
        box.set_logo(None)
        if side == "home":
            self.setWindowIcon(self._default_icon)

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
        self.away_name.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {ACCENT};")
        self.home_name.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {ACCENT_SOFT};")
        self.away_record.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; font-weight: 600;")
        self.home_record.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; font-weight: 600;")
        self.away_score.setText("0")
        self.home_score.setText("0")
        self.away_table.setRowCount(0)
        self.home_table.setRowCount(0)
        self.setWindowIcon(self._default_icon)
        self._pending_selection_id = None
        self._next_display_at = None
        self.lines = []
        self.games = []
        self._clock_state = None
        self.center_panel.set_state("Q-", "00:00", "", "--")
        self.bottom_left_label.setText("AWY (--)")
        self.bottom_right_label.setText("HME (--)")
        self.bottom_center_label.setText(message or "No games today.")
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

    def closeEvent(self, event):
        self._alive = False
        try:
            if self.logic:
                self.logic.stop_realtime()
        except Exception:
            pass
        self._executor.shutdown(wait=False)
        super().closeEvent(event)

    def _remaining_delay_ms(self) -> int:
        if self._next_display_at is None:
            return self.display_delay_ms
        remaining = int(max(0.0, (self._next_display_at - time.monotonic()) * 1000))
        return remaining or 1

    def _compute_clock_state(
        self, period_text: str, raw_secs: float | None, shot_val: Any, fallback_clock_text: str
    ) -> tuple[str, str, Dict[str, Any]]:
        """
        Normalize incoming clock + shot clock into display text and tick state.
        Keeps the display from bouncing up a second when the official clock is stopped.
        """
        prev = self._clock_state or {}
        prev_raw = prev.get("raw_secs")
        period_changed = prev.get("period") not in (None, period_text)

        # Consider the clock "running" only when the raw feed is moving downward
        clock_running = False
        if raw_secs is None:
            clock_running = False
        elif period_changed or prev_raw is None:
            clock_running = True
        else:
            delta_raw = prev_raw - raw_secs
            if delta_raw > 0.25:
                clock_running = True
            elif raw_secs - prev_raw > 30:  # large jump (new period / reset)
                clock_running = True
            else:
                clock_running = False

        clock_secs = None
        if raw_secs is not None:
            clock_secs = max(0.0, raw_secs - self.clock_buffer_sec)
            # If the feed isn't moving, hold at the lowest seen value to avoid flicker
            if not clock_running and prev.get("clock_secs") is not None and not period_changed:
                clock_secs = min(prev["clock_secs"], clock_secs)

        clock_text = self._format_clock(clock_secs) if clock_secs is not None else (fallback_clock_text or "")
        shot_secs = self._shot_to_seconds(shot_val)
        shot_text = self.backend.format_shotclock(shot_val) if shot_val not in (None, "", "--") else "--"

        state = {
            "period": period_text,
            "clock_secs": clock_secs,
            "shot_secs": shot_secs,
            "raw_secs": raw_secs,
            "running": clock_running,
            "last_ts": time.monotonic(),
        }
        return clock_text, shot_text, state

    def _apply_clock(self, data: Dict[str, Any]):
        game = data.get("game") or {}
        shot_val = data.get("shotclock")
        period_text = self._format_period_badge({**game, "_header": data.get("header")})
        raw_secs = self._clock_to_seconds(game.get("gameClock"))
        clock_text, shot_display, clock_state = self._compute_clock_state(
            period_text, raw_secs, shot_val, data.get("header", "")
        )
        self.center_panel.set_state(period_text, clock_text, "", shot_display)
        self._clock_state = clock_state

    def _format_period_badge(self, game: Dict[str, Any]) -> str:
        status_val = game.get("status") or game.get("gameStatus")
        status_text = str(game.get("gameStatusText") or game.get("statusText") or game.get("_header") or "").lower()
        clock_text = str(game.get("gameClockText") or game.get("gameClock") or "").lower()
        if "halftime" in status_text or "halftime" in clock_text:
            return "HALF"
        if isinstance(status_val, int) and status_val >= 3:
            return "FINAL"
        if any(k in status_text for k in ("final", "endgame", "ended")):
            return "FINAL"
        period_field = game.get("period")
        current_period = None
        if isinstance(period_field, dict):
            current_period = period_field.get("current")
        elif isinstance(period_field, int):
            current_period = period_field
        if not isinstance(current_period, int):
            return "Q-"
        mapping = {1: "1ST", 2: "2ND", 3: "3RD", 4: "4TH"}
        return mapping.get(current_period, f"OT{current_period - 4}" if current_period > 4 else f"Q{current_period}")

    def _clock_to_seconds(self, clock_raw: Any) -> float | None:
        if not clock_raw:
            return None
        if isinstance(clock_raw, (int, float)):
            return float(clock_raw)
        if isinstance(clock_raw, str) and ":" in clock_raw:
            try:
                mins, secs = clock_raw.split(":")
                return int(mins) * 60 + float(secs)
            except Exception:
                return None
        if isinstance(clock_raw, str) and clock_raw.startswith("PT"):
            try:
                text = clock_raw.replace("PT", "")
                mins = 0.0
                secs = 0.0
                if "M" in text:
                    parts = text.split("M")
                    mins = float(parts[0])
                    text = parts[1]
                if text.endswith("S"):
                    secs = float(text.replace("S", "") or 0)
                return mins * 60 + secs
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
        if clock_secs is not None and state.get("running", True):
            clock_secs = max(0.0, clock_secs - delta)
            updated = True
        if not updated:
            state["last_ts"] = now
            return
        state["clock_secs"] = clock_secs
        state["shot_secs"] = shot_secs
        state["last_ts"] = now
        period = state.get("period", "")
        current_shot_text = self.center_panel.bottom_right.text()
        if clock_secs is not None:
            self.center_panel.set_state(period, self._format_clock(clock_secs), "", current_shot_text)

    def _format_shot_display(self, val: float) -> str:
        if val <= 0.05:
            return "00"
        if val < 1:
            return f"{val:.1f}".rstrip("0").rstrip(".")
        if val.is_integer():
            return str(int(val))
        return f"{val:.1f}".rstrip("0").rstrip(".")

    def _update_bottom_bar(self, away: Dict[str, Any], home: Dict[str, Any]):
        away_tri = (away.get("teamTricode") or "AWY").upper()
        home_tri = (home.get("teamTricode") or "HME").upper()
        away_rec = self._team_record_text(away)
        home_rec = self._team_record_text(home)
        self.bottom_left_label.setText(f"{away_tri} ({away_rec})")
        self.bottom_right_label.setText(f"{home_tri} ({home_rec})")
        bonus_text = ""
        away_bonus = away.get("inBonus")
        home_bonus = home.get("inBonus")
        if away_bonus and home_bonus:
            bonus_text = "BONUS BOTH"
        elif away_bonus:
            bonus_text = f"BONUS {away_tri}"
        elif home_bonus:
            bonus_text = f"BONUS {home_tri}"
        self.bottom_center_label.setText(bonus_text or " ")
        # apply alt accent to labels
        self.bottom_left_label.setStyleSheet(f"color: {self._team_alt_color(away_tri)}; font-weight: bold; font-size: 14px;")
        self.bottom_right_label.setStyleSheet(f"color: {self._team_alt_color(home_tri)}; font-weight: bold; font-size: 14px;")

    def _on_realtime_update(self, state: RealTimeGameState):
        if not self._alive:
            return
        self.realtime_ready.emit(state)

    def _apply_realtime_state(self, state: RealTimeGameState):
        if not self._alive:
            return
        if self.selected_game_id and state.game_id != self.selected_game_id:
            return
        period = state.period or "-"
        period_text = self._format_period_badge(
            {
                "period": {"current": period},
                "gameClockText": state.game_clock_text,
                "gameClock": state.game_clock_raw,
                "gameStatusText": state.game_clock_text,
            }
        )
        raw_secs = self._clock_to_seconds(state.game_clock_raw)
        clock_text, shot_text, clock_state = self._compute_clock_state(
            period_text, raw_secs, state.shot_clock, state.game_clock_text or state.game_clock_raw or ""
        )
        self.center_panel.set_state(period_text, clock_text, "", shot_text)
        self._clock_state = clock_state
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

    def _apply_cached_state_if_available(self):
        if not self._cached_state or self.sport_name != "NBA":
            return
        scores = self._cached_state.get("scores") or {}
        boxscore = self._cached_state.get("boxscore")
        self.selected_game_id = self._cached_state.get("selected_game_id")
        cached_tz = self._cached_state.get("timezone") or (self._cached_state.get("settings") or {}).get("timezone")
        if cached_tz:
            self._set_timezone(cached_tz, persist=False)
        self._pending_selection_id = None
        self.lines = scores.get("lines", []) or []
        self.games = scores.get("games", []) or []
        if scores:
            self._apply_scores({"games": self.games, "lines": self.lines})
        if boxscore:
            self.apply_boxscore(boxscore)

    def _save_cached_state(self, boxscore: Dict[str, Any]):
        if self.sport_name != "NBA":
            return
        state = {
            "scores": {"games": self.games, "lines": self.lines},
            "boxscore": boxscore,
            "selected_game_id": self.selected_game_id,
            "ts": time.time(),
            "timezone": self.display_tz,
        }
        try:
            STATE_PATH.write_text(json.dumps(state))
        except Exception:
            pass

    def _team_color(self, tri: str | None) -> str:
        return getattr(self.backend, "TEAM_COLORS", getattr(self.backend, "TEAM_PRIMARY_COLORS", {})).get(
            (tri or "").upper(), ACCENT
        )

    def _team_alt_color(self, tri: str | None) -> str:
        accents = getattr(self.backend, "TEAM_ACCENT_COLORS", {})
        return accents.get((tri or "").upper(), self._team_color(tri))

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
            wins, losses = rec
            return f"{int(wins)}-{int(losses)}"
        except Exception:
            return "--"

    def _record_from_dict(self, team: Dict[str, Any]) -> tuple[Any, Any] | None:
        keys = [("wins", "losses"), ("win", "loss"), ("teamWins", "teamLosses"), ("winsTotal", "lossesTotal")]
        for w_key, l_key in keys:
            w = team.get(w_key)
            l = team.get(l_key)
            if w is not None and l is not None:
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
        self.game_combo.setCurrentIndex(new_idx + 1)  # offset for placeholder

    def _current_game_index(self) -> int | None:
        if not self.selected_game_id:
            return None
        for i, g in enumerate(self.games):
            if g.get("gameId") == self.selected_game_id:
                return i
        return None

    def _set_score_card_color(self, card: QFrame, color: str):
        bg = color or CARD
        border = color
        card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {bg};
                border-radius: 10px;
                border: 2px solid {border};
            }}
            """
        )

    def _set_table_color(self, frame: QFrame, table: QTableWidget, color: str):
        frame_bg = self._mix_color(color, PANEL, 0.18)
        header_bg = self._mix_color(color, BG, 0.25)
        border = color

        # frame and label tint
        frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: {frame_bg};
                border-radius: 12px;
                border: 1px solid {border};
            }}
            """
        )
        label = frame.findChild(QLabel)
        if label:
            label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color};")

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
        secondary = getattr(self.backend, "TEAM_SECONDARY_COLORS", {}).get(tri, self._mix_color(primary, BG, 0.4))
        box.set_colors(primary, secondary, accent)

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
