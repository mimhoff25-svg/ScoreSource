import base64
import tkinter as tk
from tkinter import ttk
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import json
import math
import os
import re
import requests
import time
from pathlib import Path
import logging
from typing import List

NBA_API_AVAILABLE = True
NBA_API_ERROR = ""
try:
    from nba_api.live.nba.endpoints import boxscore, scoreboard, playbyplay
except Exception as exc:  # ModuleNotFoundError or other import issues
    NBA_API_AVAILABLE = False
    NBA_API_ERROR = str(exc)
    boxscore = scoreboard = playbyplay = None

# Refresh intervals
REFRESH_MS = 30_000       # more frequent scoreboard refresh
BOX_REFRESH_MS = 800      # tighter box/shot clock refresh

# COLORS (rich night theme with teal/neon accents)
BG = "#0b1220"
PANEL_BG = "#111a2b"
BORDER = "#1f2e46"
TEXT = "#eaf4ff"
ACCENT = "#5ee6ff"
ACCENT_2 = "#7cf3c8"

# Basic team primary colors (fallback to neutral when missing).
TEAM_COLORS = {
    "ATL": "#E03A3E", "BOS": "#007A33", "BKN": "#000000", "CHA": "#1D1160",
    "CHI": "#CE1141", "CLE": "#860038", "DAL": "#00538C", "DEN": "#0E2240",
    "DET": "#C8102E", "GSW": "#1D428A", "HOU": "#CE1141", "IND": "#002D62",
    "LAC": "#C8102E", "LAL": "#552583", "MEM": "#5D76A9", "MIA": "#98002E",
    "MIL": "#00471B", "MIN": "#0C2340", "NOP": "#0C2340", "NYK": "#006BB6",
    "OKC": "#007AC1", "ORL": "#0077C0", "PHI": "#006BB6", "PHX": "#1D1160",
    "POR": "#E03A3E", "SAC": "#5A2D81", "SAS": "#C4CED4", "TOR": "#CE1141",
    "UTA": "#002B5C", "WAS": "#002B5C",
}

# --- ROOT WINDOW ---
root = tk.Tk()
root.title("ScoreSource")
root.geometry("1280x480")
root.configure(bg=BG)
PLACEHOLDER_LOGO = tk.PhotoImage(width=64, height=64)
PLACEHOLDER_LOGO.put(PANEL_BG, to=(0, 0, 63, 63))
PLACEHOLDER_LOGO.put(ACCENT, to=(0, 0, 63, 3))
PLACEHOLDER_LOGO.put(ACCENT, to=(0, 60, 63, 63))
PLACEHOLDER_LOGO.put(ACCENT, to=(0, 0, 3, 63))
PLACEHOLDER_LOGO.put(ACCENT, to=(60, 0, 63, 63))

executor = ThreadPoolExecutor(max_workers=6)
prefetch_executor = ThreadPoolExecutor(max_workers=1)
pending_request = False
boxscore_pending = False
selected_game_id = None
games_index = []
logo_cache = {}
logo_session = requests.Session()
shotclock_cache = {}
SHOTCLOCK_TTL = 5  # seconds to avoid hammering play-by-play for shot clock
scoreboard_cache = {"ts": 0.0, "data": None}
SCOREBOARD_TTL = 15  # seconds
boxscore_cache = {}
BOXSCORE_TTL = 12  # seconds
PREFETCH_LIMIT = 1  # fetch one game at a time in background
prefetch_tracker = set()
boxscore_job = None
STATE_PATH = Path.home() / ".local" / "share" / "scoresource" / "state.json"
LOG_PATH = STATE_PATH.parent / "scoreboard.log"
LOGO_DIR = Path.home() / ".cache" / "scoresource" / "logos"
DEMO_MODE = os.environ.get("SCORESOURCE_DEMO") == "1"
DEMO_REASON = ""
if not NBA_API_AVAILABLE:
    DEMO_MODE = True
    DEMO_REASON = f"nba_api missing ({NBA_API_ERROR})"
elif DEMO_MODE:
    DEMO_REASON = "SCORESOURCE_DEMO=1"

# Logging setup
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Grid weights
root.columnconfigure(0, weight=1)
root.columnconfigure(1, weight=4)
root.rowconfigure(2, weight=1)
root.rowconfigure(3, weight=0)

# --- STATUS TEXT ---
status_label = tk.Label(
    root, text="Loading scores...",
    font=("Helvetica", 12, "bold"),
    fg=ACCENT, bg=BG, anchor="w"
)
status_label.grid(row=0, column=0, columnspan=2,
                  sticky="ew", padx=16, pady=(0, 8))

# --- GAME DROPDOWN (bottom-left) ---
dropdown_var = tk.StringVar()
games_dropdown = ttk.Combobox(
    root,
    textvariable=dropdown_var,
    state="readonly",
    font=("Helvetica", 11),
    width=50
)
games_dropdown.grid(row=1, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 8))
games_dropdown.set("")

# --- RIGHT SIDE SCOREBOARD PANEL ---
scoreboard_frame = tk.Frame(root, bg=PANEL_BG,
                            bd=2, relief="groove", highlightthickness=1,
                            highlightbackground=ACCENT, highlightcolor=ACCENT)
scoreboard_frame.grid(row=2, column=0, columnspan=2,
                      sticky="nsew", padx=4, pady=6)

scoreboard_frame.rowconfigure(0, weight=0)
scoreboard_frame.rowconfigure(1, weight=1)
scoreboard_frame.columnconfigure(0, weight=2, minsize=240, uniform="toprow")
scoreboard_frame.columnconfigure(1, weight=1, minsize=240, uniform="toprow")  # center column thinner
scoreboard_frame.columnconfigure(2, weight=2, minsize=240, uniform="toprow")

# --- TOP CLOCK, SCORES, LOGOS ---
clock_frame = tk.Frame(scoreboard_frame, bg=PANEL_BG)
clock_frame.grid(row=0, column=1, sticky="nsew", pady=(8, 4))
clock_frame.columnconfigure(0, weight=1)
clock_frame.rowconfigure(0, weight=1)
clock_frame.rowconfigure(1, weight=1)

quarter_label = tk.Label(
    clock_frame,
    text="Q1 12:00",
    font=("Helvetica", 28, "bold"),
    fg=ACCENT_2, bg=PANEL_BG,
    anchor="center"
)
quarter_label.grid(row=0, column=0, sticky="nsew")

shotclock_label = tk.Label(
    clock_frame,
    text="SC --",
    font=("Helvetica", 18, "bold"),
    fg=ACCENT, bg=PANEL_BG,
    anchor="center"
)
shotclock_label.grid(row=1, column=0, sticky="nsew")

top_left = tk.Frame(scoreboard_frame, bg=PANEL_BG)
top_left.grid(row=0, column=0, sticky="nsew", padx=(4, 4))
top_left.columnconfigure(0, weight=1)
top_left.columnconfigure(1, weight=1)

away_name_label = tk.Label(top_left, font=("Helvetica", 17, "bold"),
                           fg=ACCENT, bg=PANEL_BG, anchor="w")
away_name_label.grid(row=0, column=0, sticky="w", padx=(0, 6))

away_logo_label = tk.Label(top_left, bg=PANEL_BG, fg=TEXT, anchor="center", width=70, height=70)
away_logo_label.grid(row=0, column=1, sticky="nsew")

away_score_label = tk.Label(top_left, font=("Helvetica", 44, "bold"),
                            fg=TEXT, bg=PANEL_BG, bd=3, relief="ridge",
                            width=3, anchor="e")
away_score_label.grid(row=1, column=0, columnspan=2, sticky="e", pady=(4, 0))

top_right = tk.Frame(scoreboard_frame, bg=PANEL_BG)
top_right.grid(row=0, column=2, sticky="nsew", padx=(4, 4))
top_right.columnconfigure(0, weight=1)
top_right.columnconfigure(1, weight=1)

home_logo_label = tk.Label(top_right, bg=PANEL_BG, fg=TEXT, anchor="center", width=70, height=70)
home_logo_label.grid(row=0, column=0, sticky="nsew")

home_name_label = tk.Label(top_right, font=("Helvetica", 17, "bold"),
                           fg=ACCENT, bg=PANEL_BG, anchor="e")
home_name_label.grid(row=0, column=1, sticky="e", padx=(6, 0))

home_score_label = tk.Label(top_right, font=("Helvetica", 44, "bold"),
                            fg=TEXT, bg=PANEL_BG, bd=3, relief="ridge",
                            width=3, anchor="w")
home_score_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

# --- CENTER PANEL (STATUS) ---
center_panel = tk.Frame(scoreboard_frame, bg=PANEL_BG)
center_panel.grid(row=1, column=1,
                  sticky="nsew", padx=0, pady=6)

center_panel.columnconfigure(0, weight=1)

center_status_label = tk.Label(center_panel, text="",
                               font=("Helvetica", 13, "bold"), fg=ACCENT_2, bg=PANEL_BG, anchor="center", justify="center")
center_status_label.grid(row=0, column=0, pady=(12, 0), sticky="n")

# --- PLAYER TABLES LEFT & RIGHT ---
STAT_COLUMNS = ("num", "player", "pts", "reb", "ast", "fg", "tp", "ft", "time")

style = ttk.Style()
style.theme_use("default")
style.configure(
    "Score.Treeview",
    background=PANEL_BG,
    foreground=TEXT,
    fieldbackground=PANEL_BG,
    bordercolor=BORDER,
    borderwidth=1,
    rowheight=22,
)
style.configure(
    "Score.Treeview.Heading",
    background=BORDER,
    foreground=TEXT,
    relief="flat",
    font=("Helvetica", 9, "bold"),
)
style.map("Score.Treeview", background=[("selected", "#1d3557")])
# Match combobox to palette
style.configure(
    "TCombobox",
    fieldbackground=PANEL_BG,
    background=BORDER,
    foreground=TEXT,
    bordercolor=BORDER,
)


def build_player_table(parent):
    tree = ttk.Treeview(
        parent,
        columns=STAT_COLUMNS,
        show="headings",
        selectmode="none",
        style="Score.Treeview",
    )
    headings = {
        "num": "#",
        "player": "Player",
        "pts": "PTS",
        "reb": "REB",
        "ast": "AST",
        "fg": "FG",
        "tp": "3P",
        "ft": "FT",
        "time": "TIME",
    }
    widths = {
        "num": 38,
        "player": 150,
        "pts": 32,
        "reb": 32,
        "ast": 32,
        "fg": 50,
        "tp": 50,
        "ft": 50,
        "time": 54,
    }
    for col in STAT_COLUMNS:
        tree.heading(col, text=headings[col])
        anchor = "center" if col == "num" else ("w" if col == "player" else "center")
        # Let the player column take leftover width; keep stat columns fixed to avoid crowding.
        stretch = col == "player"
        tree.column(col, width=widths[col], anchor=anchor, stretch=stretch)
    return tree


def load_last_game_id():
    try:
        if STATE_PATH.exists():
            with STATE_PATH.open("r") as f:
                data = json.load(f)
                return data.get("last_game_id")
    except Exception:
        return None
    return None


def save_last_game_id(game_id: str | None):
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with STATE_PATH.open("w") as f:
            json.dump({"last_game_id": game_id}, f)
    except Exception:
        pass

# Initialize persisted selection after helpers are defined.
selected_game_id = load_last_game_id()


away_panel = tk.Frame(scoreboard_frame, bg=PANEL_BG, bd=0, highlightthickness=1, highlightbackground=BORDER)
away_panel.grid(row=1, column=0, sticky="nsew", padx=(6, 6))
away_panel.rowconfigure(0, weight=1)
away_panel.columnconfigure(0, weight=1)

home_panel = tk.Frame(scoreboard_frame, bg=PANEL_BG, bd=0, highlightthickness=1, highlightbackground=BORDER)
home_panel.grid(row=1, column=2, sticky="nsew", padx=(6, 6))
home_panel.rowconfigure(0, weight=1)
home_panel.columnconfigure(0, weight=1)

away_players_table = build_player_table(away_panel)
away_players_table.grid(row=0, column=0, sticky="nsew")
away_scroll = tk.Scrollbar(away_panel, orient=tk.VERTICAL, command=away_players_table.yview)
away_scroll.grid(row=0, column=1, sticky="ns")
away_scroll.configure(troughcolor=PANEL_BG, background=BORDER, highlightthickness=0, relief="flat")
away_players_table.configure(yscrollcommand=away_scroll.set)

home_players_table = build_player_table(home_panel)
home_players_table.grid(row=0, column=0, sticky="nsew")
home_scroll = tk.Scrollbar(home_panel, orient=tk.VERTICAL, command=home_players_table.yview)
home_scroll.grid(row=0, column=1, sticky="ns")
home_scroll.configure(troughcolor=PANEL_BG, background=BORDER, highlightthickness=0, relief="flat")
home_players_table.configure(yscrollcommand=home_scroll.set)

# --- UTILITY FUNCTIONS ---
def clear_table(table: ttk.Treeview, message: str):
    table.delete(*table.get_children())
    table.insert("", "end", values=(message, "", "", "", "", "", "", ""))


def populate_table(table: ttk.Treeview, team: dict):
    table.delete(*table.get_children())
    players = team.get("players", []) or []
    if not players:
        clear_table(table, "No player stats yet.")
        return
    off_bg, on_bg, text_color = team_palette(team)
    table.tag_configure("team_off", background=off_bg, foreground=text_color)
    table.tag_configure("team_on", background=on_bg, foreground=text_color)
    on_court = []
    off_court = []
    for player in players:
        stats = player.get("statistics", {}) or {}
        if bool(stats.get("isOnCourt")):
            on_court.append(player)
        else:
            off_court.append(player)

    ordered = on_court + off_court

    for idx, player in enumerate(ordered):
        try:
            stats = player.get("statistics", {}) or {}
            first = (player.get("firstName", "") or "").strip()
            last = (player.get("familyName", "") or "").strip()
            name = f"{first[:1] + '. ' if first else ''}{last}".strip() or "Player"
            jersey = player.get("jerseyNum") or ""
            pos = player.get("position") or ""
            num_display = f"{str(jersey)[:2]:<2}" if jersey else ""
            suffix = f" {pos}" if pos else ""
            display_name = f"{name}{suffix}".strip()
            fg = f"{stats.get('fieldGoalsMade', 0)}-{stats.get('fieldGoalsAttempted', 0)}"
            tp = f"{stats.get('threePointersMade', 0)}-{stats.get('threePointersAttempted', 0)}"
            ft = f"{stats.get('freeThrowsMade', 0)}-{stats.get('freeThrowsAttempted', 0)}"
            time_played = format_time_played(stats.get("minutes") or stats.get("minutesCalculated"))
            table.insert(
                "",
                "end",
                values=(
                    num_display,
                    display_name,
                    stats.get("points", 0),
                    stats.get("reboundsTotal", stats.get("rebounds", 0)),
                    stats.get("assists", 0),
                    fg,
                    tp,
                    ft,
                    time_played,
                ),
                tags=("team_on",) if idx < len(on_court) else ("team_off",),
            )
        except Exception:
            # Skip any row with malformed data instead of failing the whole table.
            continue


def clear_scoreboard(message=""):
    global boxscore_job
    if boxscore_job:
        root.after_cancel(boxscore_job)
        boxscore_job = None
    center_status_label.config(text=message)
    quarter_label.config(text="")
    shotclock_label.config(text="SC --")
    away_name_label.config(text="")
    home_name_label.config(text="")
    away_score_label.config(text="")
    home_score_label.config(text="")

    away_logo_label.config(image="", text="")
    home_logo_label.config(image="", text="")
    away_logo_label.image = None
    home_logo_label.image = None

    clear_table(away_players_table, message)
    clear_table(home_players_table, message)


LOGO_VERSION = "2025-01"


def load_logo(team_id: str, tricode: str = ""):
    key = (team_id or "", (tricode or "").upper(), LOGO_VERSION)
    if key in logo_cache:
        return logo_cache[key]

    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    tc = (tricode or "").upper()
    cache_name = f"{team_id or tc or 'unknown'}.png"
    # Special-case Pelicans (NBA sometimes serves 'NO' instead of NOP)
    alt_tcodes = [tc]
    if tc == "NOP":
        alt_tcodes.append("NO")

    cache_path = LOGO_DIR / cache_name

    def build_photoimage(raw_bytes: bytes):
        img_data = base64.b64encode(raw_bytes).decode("ascii")
        logo = tk.PhotoImage(data=img_data)
        max_dim = max(logo.width(), logo.height())
        target = 140
        factor = max(1, math.ceil(max_dim / target))
        if factor > 1:
            logo = logo.subsample(factor, factor)
        return logo

    # Try cache first
    if cache_path.exists():
        try:
            with cache_path.open("rb") as f:
                logo = build_photoimage(f.read())
                logo_cache[key] = logo
                return logo
        except Exception:
            pass

    urls = []
    for code in alt_tcodes:
        urls.extend([
            f"https://a.espncdn.com/i/teamlogos/nba/500/{code}.png",
            f"https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/{code}.png",
            f"https://cdn.nba.com/logos/nba/{code}/global/L/logo.png",
        ])
    if team_id:
        base = f"https://cdn.nba.com/logos/nba/{team_id}"
        urls.extend([
            f"{base}/global/L/logo.png",
            f"{base}/primary/L/logo.png",
        ])

    for url in urls:
        try:
            response = logo_session.get(url, timeout=3)
            response.raise_for_status()
            content = response.content
            try:
                cache_path.write_bytes(content)
            except Exception:
                pass
            logo = build_photoimage(content)
            logo_cache[key] = logo
            return logo
        except Exception:
            continue

    logo_cache[key] = None
    return None


def derive_shotclock_from_pbp(game_id: str):
    if not NBA_API_AVAILABLE or playbyplay is None:
        return None
    now = time.monotonic()
    cached = shotclock_cache.get(game_id)
    if cached and now - cached[0] <= SHOTCLOCK_TTL:
        return cached[1]
    try:
        data = playbyplay.PlayByPlay(game_id=game_id).get_dict()
        actions = data.get("game", {}).get("actions", []) or []
        for action in reversed(actions):
            sc = action.get("shotClock")
            if sc not in (None, ""):
                shotclock_cache[game_id] = (now, sc)
                return sc
    except Exception:
        return None
    return None


def format_clock(clock_raw):
    minutes = 0
    seconds = 0
    if not clock_raw:
        return "--:--"
    if isinstance(clock_raw, (int, float)):
        minutes = int(clock_raw // 60)
        seconds = int(clock_raw % 60)
        return f"{minutes}:{seconds:02d}"
    if not isinstance(clock_raw, str):
        return str(clock_raw)
    # Handle ISO-like "PT5M23.00S"
    match = re.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", clock_raw)
    if match:
        minutes = int(match.group(1) or 0)
        seconds_val = float(match.group(2) or 0)
        seconds = int(seconds_val)
        return f"{minutes}:{seconds:02d}"
    # If already MM:SS or similar, return as-is
    return clock_raw


def format_time_played(value):
    minutes = 0
    seconds = 0
    if value in (None, "", 0):
        return ""
    try:
        # Already formatted like MM:SS
        if isinstance(value, str) and ":" in value:
            return value
        if isinstance(value, (int, float)):
            minutes = int(value)
            seconds = int(round((value - minutes) * 60))
            return f"{minutes}:{seconds:02d}"
        if isinstance(value, str):
            match = re.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", value)
            if match:
                minutes = int(match.group(1) or 0)
                seconds_val = float(match.group(2) or 0)
                seconds = int(seconds_val)
                return f"{minutes}:{seconds:02d}"
    except Exception:
        return ""
    return str(value)


def format_shotclock(value):
    if value is None or value == "":
        return "--"
    try:
        num = float(value)
        if num.is_integer():
            return str(int(num))
        return f"{num:.1f}".rstrip("0").rstrip(".")
    except Exception:
        return str(value)


def _hex_to_rgb(color: str):
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join([c * 2 for c in color])
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _mix(color: str, factor: float, target=(26, 26, 26)):
    # factor: -1..1 (negative moves toward target/darker, positive toward white)
    base = _hex_to_rgb(color)
    if factor >= 0:
        mixed = tuple(int(b + (255 - b) * factor) for b in base)
    else:
        mixed = tuple(int(b + (t - b) * (-factor)) for b, t in zip(base, target))
    return _rgb_to_hex(mixed)


def _text_contrast(color: str):
    r, g, b = _hex_to_rgb(color)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if luminance > 0.6 else "#ffffff"


def team_palette(team: dict):
    tricode = (team.get("teamTricode") or "").upper()
    primary = TEAM_COLORS.get(tricode, PANEL_BG)
    off_bg = _mix(primary, -0.35)
    on_bg = _mix(primary, -0.15)
    text = _text_contrast(on_bg)
    return off_bg, on_bg, text


def safe_score(team: dict):
    val = team.get("score")
    if val in (None, ""):
        val = team.get("points") or team.get("scoreTotal")
    try:
        return int(val)
    except Exception:
        return val or 0


# --- FETCHING GAMES ---
def format_game(game):
    home_team = game.get("homeTeam", {}) or {}
    away_team = game.get("awayTeam", {}) or {}
    home = home_team.get("teamName", "Home")
    away = away_team.get("teamName", "Away")
    hs = safe_score(home_team)
    as_ = safe_score(away_team)

    status = game.get("gameStatusText", "Scheduled")
    period = game.get("period")
    clock = format_clock(game.get("gameClock"))

    current_period = None
    if isinstance(period, dict):
        current_period = period.get("current")
    elif isinstance(period, int):
        current_period = period

    if current_period:
        status = f"Q{current_period}"
        if clock:
            status += f" {clock}"
    elif clock:
        status = clock

    return f"{away} {as_} @ {home} {hs}  ({status})"


def map_status(game: dict) -> str:
    # nba_api scoreboard: gameStatus 1=sched, 2=live, 3=final
    status_map = {1: "scheduled", 2: "live", 3: "final"}
    return status_map.get(game.get("gameStatus"), (game.get("gameStatusText") or "").lower() or "scheduled")


# --- DEMO DATA ---
def demo_scoreboard():
    games = [
        {
            "gameId": "DEMO123",
            "homeTeam": {
                "teamId": "9001",
                "teamName": "Demo Home",
                "teamTricode": "DMH",
                "score": 72,
            },
            "awayTeam": {
                "teamId": "9002",
                "teamName": "Demo Away",
                "teamTricode": "DMA",
                "score": 68,
            },
            "gameStatusText": "Q3 6:12",
            "period": {"current": 3},
            "gameClock": "PT6M12S",
            "seasonYear": "2025",
        }
    ]
    lines = [format_game(g) for g in games]
    return {"games": games, "lines": lines}


def demo_boxscore():
    def player(first, last, num, pos, pts, reb, ast, fg_m, fg_a, tp_m, tp_a, ft_m, ft_a, minutes):
        return {
            "firstName": first,
            "familyName": last,
            "position": pos,
            "jerseyNum": num,
            "statistics": {
                "isOnCourt": True,
                "points": pts,
                "reboundsTotal": reb,
                "assists": ast,
                "fieldGoalsMade": fg_m,
                "fieldGoalsAttempted": fg_a,
                "threePointersMade": tp_m,
                "threePointersAttempted": tp_a,
                "freeThrowsMade": ft_m,
                "freeThrowsAttempted": ft_a,
                "minutesCalculated": minutes,
            },
        }

    game = {
        "gameClock": "PT6M12S",
        "shotClock": 14,
        "period": {"current": 3},
    }
    home_players = [
        player("H", "Leader", "11", "G", 18, 4, 6, 7, 12, 2, 5, 2, 2, "22:34"),
        player("H", "Big", "32", "C", 12, 8, 1, 5, 9, 0, 1, 2, 3, "20:10"),
        player("H", "Spark", "3", "G", 9, 2, 4, 3, 7, 1, 2, 2, 2, "18:45"),
    ]
    away_players = [
        player("A", "Star", "7", "F", 21, 6, 3, 8, 14, 3, 6, 2, 2, "23:18"),
        player("A", "Guard", "1", "G", 14, 3, 5, 6, 11, 1, 3, 1, 1, "21:40"),
        player("A", "Wing", "15", "F", 8, 5, 2, 3, 8, 0, 2, 2, 2, "19:05"),
    ]

    home = {
        "teamId": "9001",
        "teamName": "Demo Home",
        "teamTricode": "DMH",
        "score": 72,
        "players": home_players,
    }
    away = {
        "teamId": "9002",
        "teamName": "Demo Away",
        "teamTricode": "DMA",
        "score": 68,
        "players": away_players,
    }
    return {"game": game, "home": home, "away": away, "header": "Q3 6:12", "shotclock": 14}


def fetch_scores():
    if DEMO_MODE or not NBA_API_AVAILABLE or scoreboard is None:
        return demo_scoreboard()
    now = time.monotonic()
    if scoreboard_cache["data"] and now - scoreboard_cache["ts"] < SCOREBOARD_TTL:
        return scoreboard_cache["data"]

    try:
        data = scoreboard.ScoreBoard().get_dict()
        games = data.get("scoreboard", {}).get("games", [])
        lines = [format_game(game) for game in games]
        result = {"games": games, "lines": lines}
        if not games:
            # No games returned; fallback to demo so UI is never empty.
            demo = demo_scoreboard()
            result = demo
        scoreboard_cache["data"] = result
        scoreboard_cache["ts"] = now
        return result
    except Exception:
        # On error, use cached; if none, use demo to keep UI working.
        if scoreboard_cache["data"]:
            return scoreboard_cache["data"]
        return demo_scoreboard()


def prefetch_boxscores(games):
    # Warm the boxscore cache for the first few games so UI loads instantly.
    limit = min(PREFETCH_LIMIT, len(games))
    for g in games[:limit]:
        gid = g.get("gameId")
        if not gid:
            continue
        cached = boxscore_cache.get(gid)
        if cached and time.monotonic() - cached[0] < BOXSCORE_TTL:
            continue
        if gid in prefetch_tracker:
            continue
        prefetch_tracker.add(gid)
        prefetch_executor.submit(_prefetch_wrapper, gid)


def _prefetch_wrapper(gid: str):
    try:
        fetch_boxscore(gid)
    finally:
        prefetch_tracker.discard(gid)


def apply_scores(result):
    global games_index, selected_game_id

    games = result["games"]
    lines = result["lines"]
    center_status_label.config(text="")

    games_dropdown["values"] = lines

    games_index = games

    if not games:
        status_label.config(text="No games right now.")
        clear_scoreboard()
        return

    status_label.config(text="Select a game.")

    chosen_index = None

    # Prefer live game if present
    for idx, g in enumerate(games):
        if (g.get("gameStatus") == 2) or (map_status(g) == "live"):
            chosen_index = idx
            selected_game_id = g.get("gameId")
            save_last_game_id(selected_game_id)
            break

    # Otherwise use saved selection
    if selected_game_id:
        for idx, g in enumerate(games):
            if g["gameId"] == selected_game_id:
                chosen_index = idx
                break

    if chosen_index is None:
        if games:
            selected_game_id = games[0]["gameId"]
            save_last_game_id(selected_game_id)
            chosen_index = 0
        else:
            selected_game_id = None

    if chosen_index is not None:
        games_dropdown.current(chosen_index)
        dropdown_var.set(lines[chosen_index])
        # Auto-load boxscore for the selected game.
        try:
            load_boxscore(selected_game_id)
        except Exception as exc:
            status_label.config(text=f"Error loading boxscore: {exc}")
    else:
        dropdown_var.set("")

    # Warm cache so clicking a game loads instantly.
    prefetch_boxscores(games)


def handle_result(future):
    global pending_request
    try:
        apply_scores(future.result())
    except Exception as exc:
        logging.exception("Error applying scores")
        status_label.config(text=f"Error: {exc}")
        clear_scoreboard("Error loading games.")
    pending_request = False
    schedule_update()


def update_scores():
    global pending_request
    if pending_request:
        return
    pending_request = True
    status_label.config(text="Refreshing...")
    future = executor.submit(fetch_scores)
    future.add_done_callback(lambda fut:
                             root.after(0, partial(handle_result, fut)))


def schedule_update():
    root.after(REFRESH_MS, update_scores)



# --- BOX SCORE ---
def fetch_boxscore(game_id):
    if DEMO_MODE or not NBA_API_AVAILABLE or boxscore is None:
        return demo_boxscore()
    if game_id == "DEMO123":
        return demo_boxscore()
    now = time.monotonic()
    cached = boxscore_cache.get(game_id)
    if cached and now - cached[0] < BOXSCORE_TTL:
        return cached[1]

    try:
        data = boxscore.BoxScore(game_id=game_id).get_dict()
    except Exception:
        # Fallback to demo if the API fails
        return demo_boxscore()
    game = data["game"]
    home = game["homeTeam"]
    away = game["awayTeam"]

    period_field = game.get("period")
    current_period = None
    if isinstance(period_field, dict):
        current_period = period_field.get("current")
    elif isinstance(period_field, int):
        current_period = period_field
    period = current_period if current_period is not None else "-"
    clock = format_clock(game.get("gameClock"))
    shotclock_raw = game.get("shotClock")
    if shotclock_raw in (None, "", "--"):
        shotclock_raw = derive_shotclock_from_pbp(game_id)
    shotclock = format_shotclock(shotclock_raw)

    header = f"Q{period}" if period != "-" else (game.get("gameStatusText") or "Scheduled")

    result = {
        "game": game,
        "home": home,
        "away": away,
        "header": header,
        "shotclock": shotclock,
    }
    boxscore_cache[game_id] = (now, result)
    return result


def apply_boxscore(data):
    game = data["game"]
    home = data["home"]
    away = data["away"]

    # Quarter and shot clock only in center
    shotclock_label.config(text=f"{data.get('shotclock')}")
    quarter_label.config(text=data["header"])
    center_status_label.config(text="")

    a_score = safe_score(away)
    h_score = safe_score(home)

    # Names
    away_name_label.config(text=f"{away['teamName']}")
    home_name_label.config(text=f"{home['teamName']}")

    # Scores
    away_score_label.config(text=str(a_score))
    home_score_label.config(text=str(h_score))

    # Logos
    a_logo = load_logo(away.get("teamId"), away.get("teamTricode"))
    h_logo = load_logo(home.get("teamId"), home.get("teamTricode"))

    # Logos with fallback to tricodes; never leave blank
    if a_logo:
        away_logo_label.config(image=a_logo, text="", relief="ridge")
        away_logo_label.image = a_logo
    else:
        away_logo_label.config(image=PLACEHOLDER_LOGO, text=away.get("teamTricode", ""), relief="flat")
        away_logo_label.image = PLACEHOLDER_LOGO

    if h_logo:
        home_logo_label.config(image=h_logo, text="", relief="ridge")
        home_logo_label.image = h_logo
    else:
        home_logo_label.config(image=PLACEHOLDER_LOGO, text=home.get("teamTricode", ""), relief="flat")
        home_logo_label.image = PLACEHOLDER_LOGO

    # Players
    populate_table(away_players_table, away)
    populate_table(home_players_table, home)

def handle_boxscore_result(future):
    global boxscore_pending, boxscore_job
    try:
        apply_boxscore(future.result())
    except Exception as exc:
        logging.exception("Error applying boxscore")
        clear_scoreboard(f"Error loading stats (stats/minutes issue?):\n{exc}")
    boxscore_pending = False
    if selected_game_id:
        boxscore_job = root.after(BOX_REFRESH_MS, lambda: load_boxscore(selected_game_id))


def load_boxscore(game_id):
    global boxscore_pending, boxscore_job
    if boxscore_pending:
        return
    refreshing = boxscore_job is not None
    if boxscore_job:
        root.after_cancel(boxscore_job)
        boxscore_job = None
    boxscore_pending = True

    if not refreshing:
        center_status_label.config(text="Loading stats...")

    future = executor.submit(fetch_boxscore, game_id)
    future.add_done_callback(lambda fut:
                             root.after(0,
                                        partial(handle_boxscore_result, fut)))


# --- EVENT: SELECT GAME ---
def on_dropdown_select(_event):
    global selected_game_id
    idx = games_dropdown.current()
    if idx < 0 or idx >= len(games_index):
        return
    selected_game_id = games_index[idx]["gameId"]
    save_last_game_id(selected_game_id)
    load_boxscore(selected_game_id)


games_dropdown.bind("<<ComboboxSelected>>", on_dropdown_select)

# --- CLEAN EXIT ---
def on_close():
    global boxscore_job
    if boxscore_job:
        root.after_cancel(boxscore_job)
        boxscore_job = None
    executor.shutdown(wait=False, cancel_futures=True)
    prefetch_executor.shutdown(wait=False, cancel_futures=True)
    logo_session.close()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)

# --- STARTUP ---
if DEMO_REASON:
    status_label.config(text=f"Demo mode ({DEMO_REASON}). Install nba_api for live data.")
clear_scoreboard()
root.after(0, update_scores)
root.mainloop()
