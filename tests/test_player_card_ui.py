import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLabel, QGraphicsDropShadowEffect, QTableWidget, QTableWidgetItem, QWidget

from scoresource.ui.window import PLAYER_CONTEXT_ROLE, PlayerCardDialog, ScoreSourceWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _grid_labels(layout, object_name):
    labels = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        if widget is None:
            continue
        labels.extend(
            label.text()
            for label in widget.findChildren(QLabel)
            if label.objectName() == object_name and label.text()
        )
    return labels


class _FakeTextLabel:
    def __init__(self, text: str):
        self._text = text

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:
        self._text = text


class _FakeCenterPanel:
    def __init__(self, left: str, center: str, right: str):
        self.bottom_left = _FakeTextLabel(left)
        self.bottom_center = _FakeTextLabel(center)
        self.bottom_right = _FakeTextLabel(right)
        self.last_state = None

    def set_state(self, period_text: str, clock_text: str, bottom_left: str, bottom_right: str, bottom_center: str):
        self.last_state = {
            "period_text": period_text,
            "clock_text": clock_text,
            "bottom_left": bottom_left,
            "bottom_right": bottom_right,
            "bottom_center": bottom_center,
        }


class _CardNavParent(QWidget):
    def __init__(self):
        super().__init__()
        self.steps: list[int] = []

    def _step_active_player_card(self, delta: int) -> bool:
        self.steps.append(delta)
        return True


def test_player_card_promotes_hero_stat_and_hot_state(qapp):
    dialog = PlayerCardDialog(
        {
            "sport": "NBA",
            "playerName": "Jalen Johnson",
            "jersey": "1",
            "position": "SF",
            "teamTricode": "ATL",
            "teamColor": "#c8102e",
            "rowStats": {
                "#": "1",
                "Player": "J. Johnson",
                "Pos": "SF",
                "MIN": "31",
                "PTS": "24",
                "REB": "7",
                "AST": "5",
                "+/-": "+8",
            },
            "playerData": {
                "statistics": {
                    "isOnCourt": True,
                }
            },
        }
    )

    assert dialog.jersey_badge.text() == "#1"
    assert dialog.hero_stat_value.text() == "24"
    assert dialog.hero_stat_label.text() == "PTS"
    assert "SF" in dialog.meta_label.text()
    assert "ATL" in dialog.meta_label.text()
    assert "MIN" not in dialog.meta_label.text()
    assert dialog.status_badge.isVisible() is False
    assert dialog.surface.property("cardState") == "hot"
    assert dialog.hero_stat_value.graphicsEffect() is None
    assert isinstance(dialog.hero_stat_wrap.graphicsEffect(), QGraphicsDropShadowEffect)
    assert dialog.bio_grid.count() > 0

    dialog.close()


def test_player_card_arrow_keys_delegate_to_parent_navigation(qapp):
    parent = _CardNavParent()
    dialog = PlayerCardDialog(
        {
            "sport": "NBA",
            "playerName": "Jalen Johnson",
            "jersey": "1",
            "position": "SF",
            "teamTricode": "ATL",
            "rowStats": {"PTS": "24"},
        },
        parent=parent,
    )
    dialog.show()
    dialog.setFocus()
    qapp.processEvents()

    QApplication.sendEvent(dialog, QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier))
    QApplication.sendEvent(dialog, QKeyEvent(QEvent.KeyPress, Qt.Key_Left, Qt.NoModifier))

    assert parent.steps == [1, -1]

    dialog.close()
    parent.close()


def test_step_active_player_card_wraps_across_player_tables(qapp):
    away_table = QTableWidget(2, 2)
    home_table = QTableWidget(1, 2)
    away_table.setHorizontalHeaderLabels(["#", "Player"])
    home_table.setHorizontalHeaderLabels(["#", "Player"])

    away_player = QTableWidgetItem("Player A")
    away_player.setData(
        PLAYER_CONTEXT_ROLE,
        {
            "sport": "NBA",
            "playerName": "Player A",
            "teamTricode": "SAS",
            "rowStats": {"PTS": "10"},
        },
    )
    away_table.setItem(0, 1, away_player)
    away_table.setItem(1, 1, QTableWidgetItem("No stats available"))

    home_player = QTableWidgetItem("Player B")
    home_player.setData(
        PLAYER_CONTEXT_ROLE,
        {
            "sport": "NBA",
            "playerName": "Player B",
            "teamTricode": "LAC",
            "rowStats": {"PTS": "12"},
        },
    )
    home_table.setItem(0, 1, home_player)

    calls = []
    stub = SimpleNamespace(
        away_table=away_table,
        home_table=home_table,
        _active_player_card=object(),
        _active_player_card_table=away_table,
        _active_player_card_row=0,
        _active_player_card_context={"playerName": "Player A"},
    )
    stub._is_player_card_row_navigable = lambda table, row: ScoreSourceWindow._is_player_card_row_navigable(
        stub, table, row
    )
    stub._player_card_row_sequence = lambda: ScoreSourceWindow._player_card_row_sequence(stub)
    stub._on_player_cell_clicked = lambda table, row, col: calls.append((table, row, col))

    assert ScoreSourceWindow._step_active_player_card(stub, 1) is True
    qapp.processEvents()

    assert calls == [(home_table, 0, 1)]


def test_player_card_click_refreshes_row_stats_from_current_table(qapp):
    table = QTableWidget(1, 8)
    table.setHorizontalHeaderLabels(["#", "Player", "Pos", "Min", "Pts", "Reb", "Ast", "3PT"])

    values = ["3", "K. Johnson", "F", "21:57", "8", "5", "0", "0"]
    for col, value in enumerate(values):
        table.setItem(0, col, QTableWidgetItem(value))

    name_item = table.item(0, 1)
    name_item.setData(
        PLAYER_CONTEXT_ROLE,
        {
            "sport": "NBA",
            "playerName": "Keldon Johnson",
            "teamTricode": "SAS",
            "position": "",
            "rowStats": {"#": "3", "Player": "K. Johnson", "Pts": ""},
        },
    )

    opened = []
    stub = SimpleNamespace(
        _is_player_card_row_navigable=lambda current_table, row: ScoreSourceWindow._is_player_card_row_navigable(
            stub, current_table, row
        ),
        _table_row_stats=lambda current_table, row: ScoreSourceWindow._table_row_stats(stub, current_table, row),
        _fallback_player_context=lambda current_table, row, player_name: {},
        _open_player_card=lambda context, table=None, row=None: opened.append((context, table, row)),
    )
    stub._current_player_context_for_row = lambda current_table, row: ScoreSourceWindow._current_player_context_for_row(
        stub, current_table, row
    )

    ScoreSourceWindow._on_player_cell_clicked(stub, table, 0, 1)

    assert len(opened) == 1
    context, opened_table, opened_row = opened[0]
    assert opened_table is table
    assert opened_row == 0
    assert context["rowStats"]["Pts"] == "8"
    assert context["position"] == "F"


def test_active_player_card_refreshes_from_latest_table_row(qapp):
    table = QTableWidget(1, 8)
    table.setHorizontalHeaderLabels(["#", "Player", "Pos", "Min", "Pts", "Reb", "Ast", "3PT"])
    values = ["3", "K. Johnson", "F", "21:57", "8", "5", "0", "0"]
    for col, value in enumerate(values):
        table.setItem(0, col, QTableWidgetItem(value))

    name_item = table.item(0, 1)
    name_item.setData(
        PLAYER_CONTEXT_ROLE,
        {
            "sport": "NBA",
            "playerId": "1629640",
            "playerName": "Keldon Johnson",
            "teamTricode": "SAS",
            "position": "",
            "rowStats": {"#": "3", "Player": "K. Johnson", "Pts": ""},
        },
    )

    dialog = PlayerCardDialog(
        {
            "sport": "NBA",
            "playerId": "1629640",
            "playerName": "Keldon Johnson",
            "teamTricode": "SAS",
            "position": "",
            "rowStats": {"#": "3", "Player": "K. Johnson", "Pts": ""},
        }
    )
    dialog.apply_profile({"displayName": "Keldon Johnson", "position": "F"})
    dialog.show()
    qapp.processEvents()

    stub = SimpleNamespace(
        away_table=table,
        home_table=None,
        _active_player_card=dialog,
        _active_player_card_table=table,
        _active_player_card_row=0,
        _active_player_card_context={"playerId": "1629640", "playerName": "Keldon Johnson", "teamTricode": "SAS"},
    )
    stub._is_player_card_row_navigable = lambda current_table, row: ScoreSourceWindow._is_player_card_row_navigable(
        stub, current_table, row
    )
    stub._table_row_stats = lambda current_table, row: ScoreSourceWindow._table_row_stats(stub, current_table, row)
    stub._fallback_player_context = lambda current_table, row, player_name: {}
    stub._current_player_context_for_row = lambda current_table, row: ScoreSourceWindow._current_player_context_for_row(
        stub, current_table, row
    )
    stub._find_player_row_for_context = lambda context: ScoreSourceWindow._find_player_row_for_context(stub, context)

    ScoreSourceWindow._refresh_active_player_card_from_tables(stub)

    assert dialog.hero_stat_label.text() == "PTS"
    assert dialog.hero_stat_value.text() == "8"
    assert "F" in dialog.meta_label.text()

    dialog.close()


def test_player_card_nba_supplements_missing_points_and_position_from_player_data(qapp):
    dialog = PlayerCardDialog(
        {
            "sport": "NBA",
            "playerName": "Harrison Barnes",
            "jersey": "40",
            "position": "",
            "teamTricode": "SAS",
            "teamColor": "#c4ced4",
            "rowStats": {
                "#": "40",
                "Player": "H. Barnes",
                "Min": "12:17",
                "Pos": "",
                "Reb": "3",
                "Ast": "2",
            },
            "playerData": {
                "position": "SF",
                "statistics": {
                    "minutes": "PT12M17.00S",
                    "points": 5,
                    "reboundsTotal": 3,
                    "assists": 2,
                    "threePointersMade": 1,
                    "steals": 1,
                    "blocks": 0,
                    "turnovers": 0,
                    "plusMinusPoints": 7,
                }
            },
        }
    )

    qapp.processEvents()

    stat_labels = _grid_labels(dialog.stat_grid, "chipKey")

    assert dialog.hero_stat_label.text() == "PTS"
    assert dialog.hero_stat_value.text() == "5"
    assert "SF" in dialog.meta_label.text()
    assert "MIN" in stat_labels
    assert "3PT" in stat_labels

    dialog.close()


def test_player_card_nba_normalizes_title_case_row_stats_for_points(qapp):
    dialog = PlayerCardDialog(
        {
            "sport": "NBA",
            "playerName": "Carter Bryant",
            "jersey": "11",
            "position": "F",
            "teamTricode": "SAS",
            "teamColor": "#c4ced4",
            "rowStats": {
                "#": "11",
                "Player": "C. Bryant",
                "Pos": "F",
                "Min": "17:57",
                "Pts": "10",
                "Reb": "4",
                "Ast": "1",
                "Stl": "0",
                "Blk": "0",
                "TO": "0",
            },
        }
    )

    qapp.processEvents()

    assert dialog.hero_stat_label.text() == "PTS"
    assert dialog.hero_stat_value.text() == "10"
    assert "F" in dialog.meta_label.text()
    assert "SAS" in dialog.meta_label.text()

    dialog.close()


def test_player_card_nba_support_stats_use_single_row_strip(qapp):
    dialog = PlayerCardDialog(
        {
            "sport": "NBA",
            "playerName": "Keldon Johnson",
            "jersey": "3",
            "position": "F",
            "teamTricode": "SAS",
            "teamColor": "#c4ced4",
            "rowStats": {
                "#": "3",
                "Player": "K. Johnson",
                "Pos": "F",
                "Min": "21:57",
                "Pts": "8",
                "Reb": "5",
                "Ast": "0",
                "3PT": "0",
            },
        }
    )

    qapp.processEvents()

    stat_labels = _grid_labels(dialog.stat_grid, "chipKey")

    assert stat_labels == ["MIN", "REB", "AST", "3PT"]
    assert dialog.stat_grid.count() == 4
    min_chip = dialog.stat_grid.itemAtPosition(0, 0).widget()
    reb_chip = dialog.stat_grid.itemAtPosition(1, 0).widget()
    ast_chip = dialog.stat_grid.itemAtPosition(1, 1).widget()
    three_chip = dialog.stat_grid.itemAtPosition(1, 2).widget()
    assert min_chip is not None
    assert reb_chip is not None
    assert ast_chip is not None
    assert three_chip is not None
    min_value = next(label for label in min_chip.findChildren(QLabel) if label.objectName() == "chipValue")
    reb_value = next(label for label in reb_chip.findChildren(QLabel) if label.objectName() == "chipValue")
    assert min_value.alignment() & Qt.AlignHCenter
    assert reb_value.alignment() & Qt.AlignHCenter

    dialog.close()


def test_player_card_profile_shows_dob_and_college_across_sports(qapp):
    samples = [
        ("NBA", "SF"),
        ("NFL", "WR"),
        ("NHL", "LW"),
        ("MLB", "CF"),
        ("MLS", "FW"),
    ]

    for sport, position in samples:
        dialog = PlayerCardDialog(
            {
                "sport": sport,
                "playerName": f"{sport} Player",
                "jersey": "1",
                "position": position,
                "teamTricode": "AAA",
                "rowStats": {},
            }
        )
        dialog.apply_profile(
            {
                "displayName": f"{sport} Player",
                "position": position,
                "jersey": "1",
                "height": "6'3\"",
                "weight": "210 lbs",
                "age": "27",
                "experience": "5",
                "dateOfBirth": "1998-01-15",
                "college": "North Carolina",
                "shootsCatches": "L",
                "bats": "R",
                "throws": "R",
            }
        )
        qapp.processEvents()

        bio_labels = _grid_labels(dialog.bio_grid, "infoKey")

        assert "DOB" in bio_labels
        assert "College" in bio_labels

        dialog.close()


def test_player_card_status_badge_prefers_profile_alerts(qapp):
    dialog = PlayerCardDialog(
        {
            "sport": "NBA",
            "playerName": "Bench Guard",
            "jersey": "12",
            "position": "G",
            "teamTricode": "SAS",
            "rowStats": {
                "#": "12",
                "Player": "B. Guard",
                "Pos": "G",
                "MIN": "0",
                "PTS": "0",
            },
            "playerData": {
                "statistics": {
                    "isOnCourt": False,
                }
            },
        }
    )

    dialog.apply_profile(
        {
            "displayName": "Bench Guard",
            "position": "G",
            "jersey": "12",
            "status": "Questionable",
        }
    )

    assert dialog.status_badge.isVisible() is False
    assert dialog.surface.property("cardState") == "alert"

    dialog.close()


def test_apply_clock_preserves_hockey_bottom_labels():
    center_panel = _FakeCenterPanel("15\n6", "SHOTS\nPIM", "21\n8")
    stub = SimpleNamespace(
        sport_name="NHL",
        feed_delay_ms=0,
        _clock_state={},
        center_panel=center_panel,
        _selected_game_live=lambda: False,
        _format_period_badge=lambda payload: "P2",
        _extract_clock_text=lambda raw: str(raw or ""),
        _clock_to_seconds=lambda raw: 120.0 if raw else None,
        _clock_sync_settings=lambda sport, period_text, header: (False, 0.0, 0.0),
        _compute_clock_state=lambda *args, **kwargs: (
            "2:00",
            "0",
            {"clock_secs": 120.0, "running": True},
        ),
        _clean_nhl_clock_text=lambda text: text,
        _is_game_active=lambda game, period_text, header: True,
        _apply_period_label_style=lambda sport: None,
        _team_in_bonus=lambda team: False,
        _team_fouls_text=lambda team: "",
        _down_text_from_game=lambda game: "",
        _apply_nfl_possession_highlight=lambda *args, **kwargs: None,
        _reset_center_bottom_styles=lambda: None,
        _preserve_bottom_labels_for_clock=lambda sport: sport in {"NBA", "MLB", "NHL", "MLS"},
    )

    ScoreSourceWindow._apply_clock(
        stub,
        {
            "game": {"gameClock": "2:00", "gameStatusText": "2:00 - 2nd"},
            "header": "2:00 - 2nd",
            "away": {"shotsOnGoal": 15},
            "home": {"shotsOnGoal": 21},
            "shotclock": "--",
        },
    )

    assert center_panel.last_state == {
        "period_text": "P2",
        "clock_text": "2:00",
        "bottom_left": "15\n6",
        "bottom_right": "21\n8",
        "bottom_center": "SHOTS\nPIM",
    }


def test_apply_realtime_state_preserves_hockey_bottom_labels():
    center_panel = _FakeCenterPanel("15\n6", "SHOTS\nPIM", "21\n8")
    stub = SimpleNamespace(
        _alive=True,
        feed_delay_ms=0,
        selected_game_id="401803418",
        sport_name="NHL",
        center_panel=center_panel,
        away_score=_FakeTextLabel("6"),
        home_score=_FakeTextLabel("2"),
        _clock_state={},
        _format_period_badge=lambda payload: "P2",
        _clock_to_seconds=lambda raw: 120.0 if raw else None,
        _clock_sync_settings=lambda sport, period_text, header: (False, 0.0, 0.0),
        _extract_clock_text=lambda raw: str(raw or ""),
        _compute_clock_state=lambda *args, **kwargs: (
            "2:00",
            "0",
            {"clock_secs": 120.0, "running": True},
        ),
        _clean_nhl_clock_text=lambda text: text,
        _is_game_active=lambda game, period_text, header: True,
        _apply_period_label_style=lambda sport: None,
        _preserve_bottom_labels_for_clock=lambda sport: sport in {"NBA", "MLB", "NHL", "MLS"},
        _merge_live_game_state=lambda *args, **kwargs: None,
    )

    realtime_state = SimpleNamespace(
        game_id="401803418",
        period=2,
        game_clock_text="2:00 - 2nd",
        game_clock_raw="2:00",
        shot_clock="0",
        away_score=6,
        home_score=2,
    )

    ScoreSourceWindow._apply_realtime_state(stub, realtime_state)

    assert center_panel.last_state == {
        "period_text": "P2",
        "clock_text": "2:00",
        "bottom_left": "15\n6",
        "bottom_right": "21\n8",
        "bottom_center": "SHOTS\nPIM",
    }


def test_player_card_removes_placeholder_labels_after_profile_load(qapp):
    dialog = PlayerCardDialog(
        {
            "sport": "NBA",
            "playerName": "Jalen Johnson",
            "jersey": "1",
            "position": "SF",
            "teamTricode": "ATL",
            "rowStats": {
                "#": "1",
                "Player": "J. Johnson",
                "Pos": "SF",
                "MIN": "31",
                "PTS": "24",
                "REB": "7",
                "AST": "5",
            },
        }
    )

    dialog.apply_profile(
        {
            "displayName": "Jalen Johnson",
            "position": "SF",
            "jersey": "1",
            "height": "6'8\"",
            "weight": "220 lbs",
            "age": "23",
            "college": "Duke",
            "experience": "3",
            "careerStats": {
                "GP": "180",
                "PTS": "15.6",
                "REB": "7.2",
            },
        }
    )
    qapp.processEvents()

    visible_text = [
        label.text()
        for label in dialog.findChildren(QLabel)
        if label.isVisible() and label.text()
    ]
    assert "No profile details available yet." not in visible_text
    assert "No career stats available yet." not in visible_text

    dialog.close()


def test_player_card_uses_snapshot_stats_when_no_live_game_data(qapp):
    dialog = PlayerCardDialog(
        {
            "sport": "NFL",
            "playerName": "Sam Darnold",
            "jersey": "14",
            "position": "QB",
            "teamTricode": "SEA",
            "teamColor": "#002244",
            "rowStats": {},
        }
    )

    dialog.apply_profile(
        {
            "displayName": "Sam Darnold",
            "position": "QB",
            "jersey": "14",
            "height": "6'3\"",
            "weight": "225 lbs",
            "age": "29",
            "experience": "7",
            "college": "USC",
            "careerStats": {
                "GP": "82",
                "PASS YDS": "16789",
                "PASS TD": "102",
                "INT": "67",
                "RUSH YDS": "1098",
                "RUSH TD": "15",
            },
        }
    )
    qapp.processEvents()

    visible_text = [
        label.text()
        for label in dialog.findChildren(QLabel)
        if label.isVisible() and label.text()
    ]
    assert dialog.hero_stat_value.text() in {"16789", "102"}
    assert "No player snapshot available yet." not in visible_text
    assert dialog.stat_grid.count() > 0

    dialog.close()


def test_player_card_snapshot_receiver_prefers_receiving_profile(qapp):
    dialog = PlayerCardDialog(
        {
            "sport": "NFL",
            "playerName": "Mack Hollins",
            "jersey": "13",
            "position": "WR",
            "teamTricode": "BUF",
            "teamColor": "#00338d",
            "rowStats": {},
        }
    )

    dialog.apply_profile(
        {
            "displayName": "Mack Hollins",
            "position": "WR",
            "jersey": "13",
            "height": "6'4\"",
            "weight": "221 lbs",
            "age": "32",
            "experience": "8",
            "college": "North Carolina",
            "careerStats": {
                "GP": "111",
                "REC": "162",
                "REC YDS": "2214",
                "REC TD": "18",
                "RUSH YDS": "67",
                "RUSH TD": "1",
                "TKL": "9",
            },
        }
    )
    qapp.processEvents()

    stat_labels = set(_grid_labels(dialog.stat_grid, "chipKey"))

    assert dialog.hero_stat_label.text() == "REC YDS"
    assert dialog.hero_stat_value.text() == "2214"
    assert dialog.hero_stat_value.font().pointSize() < 32
    assert dialog.hero_stat_wrap.width() <= dialog.HERO_STAT_MAX_WIDTH
    assert "REC" in stat_labels
    assert "REC TD" in stat_labels

    dialog.close()


def test_player_card_snapshot_career_section_skips_primary_stats_when_enough_data(qapp):
    dialog = PlayerCardDialog(
        {
            "sport": "NBA",
            "playerName": "Jalen Johnson",
            "jersey": "1",
            "position": "SF",
            "teamTricode": "ATL",
            "teamColor": "#c8102e",
            "rowStats": {},
        }
    )

    dialog.apply_profile(
        {
            "displayName": "Jalen Johnson",
            "position": "SF",
            "jersey": "1",
            "height": "6'8\"",
            "weight": "220 lbs",
            "age": "23",
            "college": "Duke",
            "experience": "3",
            "careerStats": {
                "GP": "180",
                "PTS": "15.6",
                "REB": "7.2",
                "AST": "4.1",
                "STL": "1.3",
                "BLK": "0.8",
                "FG%": "47.8",
                "3P%": "33.9",
                "FT%": "74.5",
            },
        }
    )
    qapp.processEvents()

    stat_labels = set(_grid_labels(dialog.stat_grid, "chipKey"))
    career_labels = set(_grid_labels(dialog.career_grid, "chipKey"))

    assert "REB" in stat_labels
    assert "AST" in stat_labels
    assert "REB" not in career_labels
    assert "AST" not in career_labels
    assert "GP" in career_labels
    assert "FT%" in career_labels

    dialog.close()


def test_player_card_hockey_snapshot_prefers_goals(qapp):
    dialog = PlayerCardDialog(
        {
            "sport": "NHL",
            "playerName": "Jason Robertson",
            "jersey": "21",
            "position": "LW",
            "teamTricode": "DAL",
            "teamColor": "#006847",
            "rowStats": {},
        }
    )

    dialog.apply_profile(
        {
            "displayName": "Jason Robertson",
            "position": "LW",
            "jersey": "21",
            "height": "6'3\"",
            "weight": "207 lbs",
            "age": "26",
            "shootsCatches": "L",
            "careerStats": {
                "GP": "350",
                "G": "151",
                "A": "174",
                "PTS": "325",
                "SOG": "1018",
            },
        }
    )
    qapp.processEvents()

    assert dialog.hero_stat_label.text() == "POINTS"
    assert dialog.hero_stat_value.text() == "325"

    dialog.close()


def test_player_card_hockey_live_skater_prioritizes_points_and_supporting_game_data(qapp):
    dialog = PlayerCardDialog(
        {
            "sport": "NHL",
            "playerName": "Jason Robertson",
            "jersey": "21",
            "position": "LW",
            "teamTricode": "DAL",
            "teamColor": "#006847",
            "rowStats": {
                "#": "21",
                "Player": "J. Robertson",
                "Pos": "LW",
                "G": "2",
                "A": "1",
                "PTS": "3",
                "SOG": "6",
                "PIM": "0",
                "SV": "",
                "SV%": "",
            },
            "playerData": {
                "statistics": {
                    "goals": 2,
                    "assists": 1,
                    "points": 3,
                    "shotsOnGoal": 6,
                    "pim": 0,
                    "plusMinus": "+2",
                    "toi": "18:44",
                    "hits": 2,
                    "blockedShots": 1,
                }
            },
        }
    )

    qapp.processEvents()

    stat_labels = _grid_labels(dialog.stat_grid, "chipKey")

    assert dialog.hero_stat_label.text() == "POINTS"
    assert dialog.hero_stat_value.text() == "3"
    assert stat_labels[:5] == ["GOALS", "ASSISTS", "SOG", "TOI", "HITS"]
    assert "PIM" not in stat_labels

    dialog.close()


def test_player_card_hockey_goalie_keeps_save_pct_visible(qapp):
    dialog = PlayerCardDialog(
        {
            "sport": "NHL",
            "playerName": "Jake Oettinger",
            "jersey": "29",
            "position": "G",
            "teamTricode": "DAL",
            "teamColor": "#006847",
            "rowStats": {
                "#": "29",
                "Player": "J. Oettinger",
                "Pos": "G",
                "SV": "31",
            },
            "playerData": {
                "statistics": {
                    "saves": 31,
                    "savePct": ".939",
                    "shotsAgainst": 33,
                    "pim": 0,
                }
            },
        }
    )

    qapp.processEvents()

    stat_labels = _grid_labels(dialog.stat_grid, "chipKey")

    assert dialog.hero_stat_label.text() == "SAVES"
    assert dialog.hero_stat_value.text() == "31"
    assert "SAVE %" in stat_labels
    assert "SHOTS AG" in stat_labels
    assert "GOALS AG" in stat_labels
    assert "PIM" not in stat_labels

    dialog.close()
