from scoresource import ncaa_basketball as facade
from scoresource.common.utils import extract_three_point_made
from scoresource.sports import ncaa_basketball as backend


def test_event_meta_marks_march_tournament_games():
    meta = backend._event_meta(  # type: ignore[attr-defined]
        {
            "tournamentId": 68,
            "notes": [{"headline": "NCAA Tournament - Sweet 16"}],
            "groups": {"name": "NCAA Tournament", "shortName": "NCAA"},
        },
        {"date": "2026-03-27T01:15Z"},
    )

    assert meta["eventNote"] == "NCAA Tournament - Sweet 16"
    assert meta["eventBucket"] == "NCAA Tournament"
    assert meta["eventStage"] == "Sweet 16"
    assert meta["isTournament"] is True
    assert meta["isMarchMadness"] is True


def test_parse_players_block_maps_basketball_stats_for_rows():
    players = backend._parse_players_block(  # type: ignore[attr-defined]
        {
            "statistics": [
                {
                    "labels": ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "TO", "STL", "BLK", "OREB", "DREB", "PF"],
                    "keys": [
                        "minutes",
                        "points",
                        "fieldGoalsMade-fieldGoalsAttempted",
                        "threePointFieldGoalsMade-threePointFieldGoalsAttempted",
                        "freeThrowsMade-freeThrowsAttempted",
                        "rebounds",
                        "assists",
                        "turnovers",
                        "steals",
                        "blocks",
                        "offensiveRebounds",
                        "defensiveRebounds",
                        "fouls",
                    ],
                    "athletes": [
                        {
                            "active": True,
                            "starter": True,
                            "athlete": {
                                "id": "5041935",
                                "displayName": "Cameron Boozer",
                                "jersey": "12",
                                "position": {"abbreviation": "F"},
                            },
                            "stats": ["35", "24", "6-9", "3-5", "9-12", "14", "5", "4", "1", "0", "6", "8", "3"],
                        }
                    ],
                }
            ]
        }
    )

    assert len(players) == 1
    player = players[0]
    assert player["id"] == "5041935"
    assert player["displayName"] == "Cameron Boozer"
    assert player["statistics"]["points"] == 24
    assert player["statistics"]["reboundsTotal"] == 14
    assert player["statistics"]["assists"] == 5
    assert player["statistics"]["personalFouls"] == 3
    assert extract_three_point_made(player["statistics"]) == 3

    rows = facade.build_player_rows({"players": players})
    assert rows == [["12", "C. Boozer", "35", "F", "24", "14", "5", "3"]]
