import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QLabel

from scoresource.ui.window import PlayerCardDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


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
