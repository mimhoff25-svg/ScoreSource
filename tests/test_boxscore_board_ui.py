import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QTableWidget

from scoresource.ui.window import BOARD_PLAYER_ROW_LIMIT, BOARD_ROW_HEIGHT, NBA_BROADCAST_HEADERS, ScoreSourceWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_resolve_headers_uses_broadcast_nba_layout():
    window = ScoreSourceWindow.__new__(ScoreSourceWindow)
    window.sport_name = "NBA"

    assert window._resolve_headers(None) == NBA_BROADCAST_HEADERS


def test_resolve_headers_uses_broadcast_ncaa_basketball_layout():
    window = ScoreSourceWindow.__new__(ScoreSourceWindow)
    window.sport_name = "NCAA Basketball"

    assert window._resolve_headers(None) == NBA_BROADCAST_HEADERS


def test_set_table_titles_uses_team_tricode_and_mode():
    away_title = SimpleNamespace(text="", setText=lambda value: setattr(away_title, "text", value))
    home_title = SimpleNamespace(text="", setText=lambda value: setattr(home_title, "text", value))
    stub = SimpleNamespace(
        away_table_title=away_title,
        home_table_title=home_title,
        _display_tricode=lambda team, fallback: team.get("teamTricode") or fallback,
    )

    ScoreSourceWindow._set_table_titles(
        stub,
        {"teamTricode": "SAS"},
        {"teamTricode": "LAL"},
        show_lineups=False,
    )

    assert away_title.text == "SAS LEADERS"
    assert home_title.text == "LAL LEADERS"


def test_fill_nba_scroll_table_maps_broadcast_columns(qapp):
    table = QTableWidget(0, len(NBA_BROADCAST_HEADERS))
    table.setHorizontalHeaderLabels(NBA_BROADCAST_HEADERS)

    stub = ScoreSourceWindow.__new__(ScoreSourceWindow)
    stub.sport_name = "NBA"
    stub.backend = SimpleNamespace(format_time_played=lambda value: "21:57")
    stub._configure_nba_table = lambda current_table: None
    stub._player_position = lambda player: player.get("position") or ""
    stub._build_player_context = lambda team, player, row_stats=None: {
        "playerName": "Keldon Johnson",
        "rowStats": dict(row_stats or {}),
        "position": "F",
    }
    stub._set_player_context_on_row = lambda current_table, row, context: None
    stub._polish_table_contents = lambda current_table: ScoreSourceWindow._polish_table_contents(stub, current_table)
    stub._style_player_table_item = lambda current_table, item, col: None
    stub._polish_table_headers = lambda current_table: None
    stub._table_font = lambda pixel_size, weight=None, stretch=None: table.font()
    stub._board_row_limit = lambda: ScoreSourceWindow._board_row_limit(stub)
    stub._prefer_final_leader_board = lambda: False
    stub._row_stats_from_values = lambda current_table, values: ScoreSourceWindow._row_stats_from_values(
        stub, current_table, values
    )

    team = {
        "players": []
    }
    for idx in range(BOARD_PLAYER_ROW_LIMIT + 2):
        team["players"].append(
            {
                "jerseyNum": str(idx),
                "firstName": f"Player{idx}",
                "familyName": "Test",
                "position": "F",
                "order": idx,
                "statistics": {
                    "minutes": "21:57",
                    "points": 8 + idx,
                    "reboundsTotal": 5,
                    "assists": 3,
                    "threePointersMade": 1,
                },
            }
        )

    ScoreSourceWindow._fill_nba_scroll_table(stub, table, team)

    assert table.columnCount() == len(NBA_BROADCAST_HEADERS)
    assert table.rowCount() == BOARD_PLAYER_ROW_LIMIT + 2
    assert table.item(0, 1).text() == "P. Test"
    assert table.item(0, 2).text() == "21:57"
    assert table.item(0, 3).text() == "8"
    assert table.item(0, 4).text() == "5"
    assert table.item(0, 5).text() == "3"
    assert table.item(0, 6).text() == "1"
    assert table.rowHeight(0) == BOARD_ROW_HEIGHT


def test_fill_nba_scroll_table_sorts_final_games_by_points(qapp):
    table = QTableWidget(0, len(NBA_BROADCAST_HEADERS))
    table.setHorizontalHeaderLabels(NBA_BROADCAST_HEADERS)

    stub = ScoreSourceWindow.__new__(ScoreSourceWindow)
    stub.sport_name = "NBA"
    stub.backend = SimpleNamespace(format_time_played=lambda value: "21:57")
    stub._configure_nba_table = lambda current_table: None
    stub._player_position = lambda player: player.get("position") or ""
    stub._build_player_context = lambda team, player, row_stats=None: {
        "playerName": player.get("firstName", ""),
        "rowStats": dict(row_stats or {}),
        "position": player.get("position", ""),
    }
    stub._set_player_context_on_row = lambda current_table, row, context: None
    stub._polish_table_contents = lambda current_table: None
    stub._prefer_final_leader_board = lambda: True
    stub._numeric_sort_value = lambda value: ScoreSourceWindow._numeric_sort_value(stub, value)
    stub._final_player_sort_key = lambda player: ScoreSourceWindow._final_player_sort_key(stub, player)
    stub._row_stats_from_values = lambda current_table, values: ScoreSourceWindow._row_stats_from_values(
        stub, current_table, values
    )

    team = {
        "players": [
            {
                "jerseyNum": "5",
                "firstName": "First",
                "familyName": "Low",
                "position": "F",
                "order": 0,
                "statistics": {"minutes": "21:57", "points": 8, "reboundsTotal": 5, "assists": 1, "threePointersMade": 0},
            },
            {
                "jerseyNum": "9",
                "firstName": "Second",
                "familyName": "High",
                "position": "G",
                "order": 9,
                "statistics": {"minutes": "21:57", "points": 22, "reboundsTotal": 3, "assists": 6, "threePointersMade": 4},
            },
        ]
    }

    ScoreSourceWindow._fill_nba_scroll_table(stub, table, team)

    assert table.item(0, 1).text() == "S. High"
    assert table.item(0, 3).text() == "22"
    assert table.item(1, 1).text() == "F. Low"


def test_style_player_table_item_uses_white_for_min_column(qapp):
    table = QTableWidget(1, len(NBA_BROADCAST_HEADERS))
    table.setHorizontalHeaderLabels(NBA_BROADCAST_HEADERS)

    stub = ScoreSourceWindow.__new__(ScoreSourceWindow)
    stub._table_font = lambda pixel_size, weight=None, stretch=None: table.font()
    stub._with_alpha = lambda color, alpha: ScoreSourceWindow._with_alpha(stub, color, alpha)

    from PySide6.QtWidgets import QTableWidgetItem

    item = QTableWidgetItem("21:57")
    table.setItem(0, 2, item)

    ScoreSourceWindow._style_player_table_item(stub, table, item, 2)

    assert item.foreground().color() == QColor("#f5f9ff")


def test_fill_team_table_routes_ncaa_basketball_to_nba_board():
    stub = ScoreSourceWindow.__new__(ScoreSourceWindow)
    stub.sport_name = "NCAA Basketball"
    calls: list[tuple[str, dict]] = []
    stub._fill_lineup_table = lambda table, team: calls.append(("lineups", team))
    stub._fill_nfl_table = lambda table, team: calls.append(("nfl", team))
    stub._fill_nhl_table = lambda table, team: calls.append(("nhl", team))
    stub._fill_nba_scroll_table = lambda table, team: calls.append(("nba", team))

    team = {"teamTricode": "DUKE", "players": []}
    ScoreSourceWindow.fill_team_table(stub, None, team, show_lineups=False)

    assert calls == [("nba", team)]


def test_fill_team_table_routes_ncaa_football_to_nfl_board():
    stub = ScoreSourceWindow.__new__(ScoreSourceWindow)
    stub.sport_name = "NCAA Football"
    calls: list[tuple[str, dict]] = []
    stub._fill_lineup_table = lambda table, team: calls.append(("lineups", team))
    stub._fill_nfl_table = lambda table, team: calls.append(("nfl", team))
    stub._fill_nhl_table = lambda table, team: calls.append(("nhl", team))
    stub._fill_nba_scroll_table = lambda table, team: calls.append(("nba", team))

    team = {"teamTricode": "OSU", "players": []}
    ScoreSourceWindow.fill_team_table(stub, None, team, show_lineups=False)

    assert calls == [("nfl", team)]
