import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QLabel

from scoresource.ui.window import PlayerCardDialog, ScoreSourceWindow


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
    assert "31 MIN" in dialog.meta_label.text()
    assert "ATL" in dialog.meta_label.text()
    assert dialog.status_badge.isVisible() is False
    assert dialog.surface.property("cardState") == "hot"
    assert dialog.bio_grid.count() > 0

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
    assert "3PT" in stat_labels

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
