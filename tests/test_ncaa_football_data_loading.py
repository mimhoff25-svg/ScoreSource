from scoresource import ncaa_football
from scoresource.sports import ncaa_football as backend


def test_fetch_boxscore_parses_summary_player_stats(monkeypatch):
    summary_payload = {
        "header": {
            "competitions": [
                {
                    "date": "2025-12-31T19:00Z",
                    "status": {
                        "period": 4,
                        "displayClock": "5:21",
                        "type": {
                            "state": "in",
                            "shortDetail": "4th 5:21",
                        },
                    },
                    "competitors": [
                        {
                            "homeAway": "home",
                            "score": "21",
                            "team": {
                                "id": "1",
                                "displayName": "Ohio State Buckeyes",
                                "abbreviation": "OSU",
                                "color": "bb0000",
                                "alternateColor": "666666",
                            },
                        },
                        {
                            "homeAway": "away",
                            "score": "14",
                            "team": {
                                "id": "2",
                                "displayName": "Miami Hurricanes",
                                "abbreviation": "MIA",
                                "color": "005030",
                                "alternateColor": "f47321",
                            },
                        },
                    ],
                }
            ]
        },
        "boxscore": {
            "players": [
                {
                    "team": {"id": "1"},
                    "statistics": [
                        {
                            "name": "passing",
                            "keys": ["passingYards", "passingTouchdowns", "interceptions"],
                            "athletes": [
                                {
                                    "athlete": {
                                        "id": "101",
                                        "firstName": "Will",
                                        "lastName": "Howard",
                                        "displayName": "Will Howard",
                                        "jersey": "18",
                                        "position": {"abbreviation": "QB"},
                                    },
                                    "stats": ["312", "3", "1"],
                                }
                            ],
                        },
                        {
                            "name": "defensive",
                            "keys": ["totalTackles", "soloTackles", "sacks", "passesDefended"],
                            "athletes": [
                                {
                                    "athlete": {
                                        "id": "102",
                                        "firstName": "Caleb",
                                        "lastName": "Downs",
                                        "displayName": "Caleb Downs",
                                        "jersey": "2",
                                        "position": {"abbreviation": "S"},
                                    },
                                    "stats": ["9", "6", "1", "2"],
                                }
                            ],
                        },
                    ],
                },
                {
                    "team": {"id": "2"},
                    "statistics": [
                        {
                            "name": "rushing",
                            "keys": ["rushingAttempts", "rushingYards", "rushingTouchdowns"],
                            "athletes": [
                                {
                                    "athlete": {
                                        "id": "201",
                                        "firstName": "Mark",
                                        "lastName": "Fletcher",
                                        "displayName": "Mark Fletcher",
                                        "jersey": "4",
                                        "position": {"abbreviation": "RB"},
                                    },
                                    "stats": ["18", "97", "1"],
                                }
                            ],
                        }
                    ],
                },
            ]
        },
    }

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return summary_payload

    monkeypatch.setattr(backend, "_boxscore_cache", {})
    monkeypatch.setattr(backend.requests, "get", lambda *args, **kwargs: _Resp())
    monkeypatch.setattr(backend, "_save_disk_boxscore", lambda *_args, **_kwargs: None)

    box = backend.fetch_boxscore("401769070")

    assert box["header"] == "Q4 5:21"
    assert box["home"]["teamTricode"] == "OSU"
    assert box["away"]["teamTricode"] == "MIA"
    assert box["home"]["players"][0]["statistics"]["yardsTotal"] == 312
    assert box["home"]["players"][0]["statistics"]["touchdowns"] == 3
    assert box["home"]["players"][1]["statistics"]["tacklesTotal"] == 9
    assert box["home"]["players"][1]["statistics"]["passesDefended"] == 2
    assert box["away"]["players"][0]["statistics"]["carries"] == 18


def test_wrapper_build_player_rows_uses_backend_rows(monkeypatch):
    expected = [["18", "W. Howard", "QB", 312, 3, 0, 0, 1]]
    monkeypatch.setattr(ncaa_football.backend, "build_player_rows", lambda team: expected)

    assert ncaa_football.build_player_rows({"players": []}) == expected
