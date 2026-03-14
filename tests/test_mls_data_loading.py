from scoresource.sports import mls


def _cached_game_shape():
    return {
        "gameId": "761484",
        "homeTeam": {"teamId": "111", "teamName": "Toronto FC", "teamTricode": "TOR", "score": 2},
        "awayTeam": {"teamId": "222", "teamName": "Red Bull New York", "teamTricode": "RBNY", "score": 1},
        "status": "final",
        "startTime": "2026-03-14T17:00Z",
        "header": "Final",
        "gameStatusText": "Final",
        "gameClock": "90'",
        "period": {"current": 2},
        "seasonYear": "2026",
    }


def test_normalize_game_for_tests_uses_status_and_period_fallbacks():
    normalized = mls._normalize_game_for_tests(_cached_game_shape())
    assert normalized["status"] == 3
    assert normalized["startTime"] == "2026-03-14T17:00Z"
    assert normalized["period"] == 2


def test_fetch_scores_coerces_cached_shape_when_offline(monkeypatch):
    payload = {"games": [_cached_game_shape()], "lines": ["RBNY 1 @ TOR 2 (Final)"]}

    monkeypatch.setattr(mls, "_scoreboard_cache", {"ts": 0.0, "data": None})
    monkeypatch.setattr(mls, "_load_disk_scoreboard", lambda: payload)

    class _OfflineSession:
        def get(self, *_args, **_kwargs):
            raise RuntimeError("offline")

    monkeypatch.setattr(mls, "_logo_session", _OfflineSession())

    result = mls.fetch_scores()
    game = result["games"][0]

    assert game["gameStatus"] == 3
    assert game["gameStatusText"] == "Final"
    assert game["gameTimeUTC"] == "2026-03-14T17:00Z"


def test_fetch_boxscore_uses_fetch_scores_without_disk_probe(monkeypatch):
    board = {
        "games": [
            {
                "gameId": "761484",
                "homeTeam": {"teamName": "Toronto FC", "teamTricode": "TOR", "score": 0},
                "awayTeam": {"teamName": "Red Bull New York", "teamTricode": "RBNY", "score": 0},
                "gameStatus": 1,
                "gameStatusText": "7:00 PM CT",
                "period": {},
                "gameClock": "0'",
                "gameTimeUTC": "2026-03-14T17:00Z",
            }
        ],
        "lines": [],
    }

    monkeypatch.setattr(mls, "_boxscore_cache", {})
    monkeypatch.setattr(mls, "_scoreboard_cache", {"ts": 0.0, "data": None})
    monkeypatch.setattr(mls, "fetch_scores", lambda: board)
    monkeypatch.setattr(mls, "_fetch_summary_payload", lambda game_id: None)

    def _disk_should_not_be_called():
        raise AssertionError("_load_disk_scoreboard should not be called by fetch_boxscore")

    monkeypatch.setattr(mls, "_load_disk_scoreboard", _disk_should_not_be_called)

    box = mls.fetch_boxscore("761484")
    assert box["home"]["teamTricode"] == "TOR"
    assert box["away"]["teamTricode"] == "RBNY"


def test_fetch_scores_maps_records_and_clears_pregame_zero_clock(monkeypatch):
    payload = {
        "events": [
            {
                "id": "761484",
                "date": "2026-03-14T17:00Z",
                "status": {
                    "type": {
                        "state": "pre",
                        "detail": "Sat, March 14th at 1:00 PM EDT",
                        "shortDetail": "Scheduled",
                    },
                    "displayClock": "0'",
                },
                "competitions": [
                    {
                        "competitors": [
                            {
                                "homeAway": "home",
                                "score": "0",
                                "records": [{"summary": "1-0-2"}],
                                "team": {
                                    "id": "111",
                                    "abbreviation": "TOR",
                                    "displayName": "Toronto FC",
                                    "location": "Toronto FC",
                                    "color": "aa182c",
                                    "alternateColor": "a2a9ad",
                                    "logos": [{"href": "https://a.espncdn.com/i/teamlogos/soccer/500/111.png"}],
                                },
                            },
                            {
                                "homeAway": "away",
                                "score": "0",
                                "records": [{"summary": "2-0-1"}],
                                "team": {
                                    "id": "222",
                                    "abbreviation": "RBNY",
                                    "displayName": "Red Bull New York",
                                    "location": "Red Bull New York",
                                    "color": "ed1e36",
                                    "alternateColor": "1d1d1d",
                                    "logos": [{"href": "https://a.espncdn.com/i/teamlogos/soccer/500/222.png"}],
                                },
                            },
                        ]
                    }
                ],
            }
        ]
    }

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class _Session:
        def get(self, *_args, **_kwargs):
            return _Response()

    monkeypatch.setattr(mls, "_scoreboard_cache", {"ts": 0.0, "data": None})
    monkeypatch.setattr(mls, "_logo_session", _Session())
    monkeypatch.setattr(mls, "_save_disk_scoreboard", lambda payload: None)

    result = mls.fetch_scores()
    game = result["games"][0]

    assert game["gameClock"] == ""
    assert game["homeTeam"]["record"] == "1-0-2"
    assert game["awayTeam"]["record"] == "2-0-1"
    assert game["homeTeam"]["teamLogo"].endswith("/111.png")
    assert game["awayTeam"]["teamLogo"].endswith("/222.png")


def test_fetch_scores_preserves_live_elapsed_clock(monkeypatch):
    payload = {
        "events": [
            {
                "id": "761484",
                "date": "2026-03-14T17:00Z",
                "status": {
                    "clock": 3540.0,
                    "displayClock": "59'",
                    "period": 2,
                    "type": {
                        "state": "in",
                        "detail": "59'",
                        "shortDetail": "59'",
                    },
                },
                "competitions": [
                    {
                        "competitors": [
                            {
                                "homeAway": "home",
                                "score": "1",
                                "team": {"id": "111", "abbreviation": "TOR", "displayName": "Toronto FC"},
                            },
                            {
                                "homeAway": "away",
                                "score": "0",
                                "team": {"id": "222", "abbreviation": "RBNY", "displayName": "Red Bull New York"},
                            },
                        ]
                    }
                ],
            }
        ]
    }

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class _Session:
        def get(self, *_args, **_kwargs):
            return _Response()

    monkeypatch.setattr(mls, "_scoreboard_cache", {"ts": 0.0, "data": None})
    monkeypatch.setattr(mls, "_logo_session", _Session())
    monkeypatch.setattr(mls, "_save_disk_scoreboard", lambda payload: None)

    result = mls.fetch_scores()
    game = result["games"][0]

    assert game["gameClock"] == 3540.0
    assert game["gameClockText"] == "59'"
    assert game["gameStatusText"] == "59'"


def test_fetch_boxscore_parses_summary_rosters_and_team_stats(monkeypatch):
    board = {
        "games": [
            {
                "gameId": "761470",
                "homeTeam": {
                    "teamId": "17606",
                    "teamName": "New York City FC",
                    "teamTricode": "NYC",
                    "score": 5,
                    "record": "1-1-0",
                },
                "awayTeam": {
                    "teamId": "18267",
                    "teamName": "Orlando City SC",
                    "teamTricode": "ORL",
                    "score": 0,
                    "record": "0-2-0",
                },
                "gameStatus": 3,
                "gameStatusText": "FT",
                "period": {"current": 2},
                "gameClock": "",
                "gameTimeUTC": "2026-03-01T00:30Z",
            }
        ],
        "lines": [],
    }
    summary = {
        "header": {
            "competitions": [
                {
                    "id": "761470",
                    "date": "2026-03-01T00:30Z",
                    "status": {
                        "type": {
                            "state": "post",
                            "detail": "FT",
                            "shortDetail": "FT",
                        }
                    },
                    "competitors": [
                        {
                            "homeAway": "home",
                            "score": "5",
                            "winner": True,
                            "team": {
                                "id": "17606",
                                "abbreviation": "NYC",
                                "displayName": "New York City FC",
                                "location": "New York City FC",
                                "nickname": "NYC FC",
                                "color": "9fd2ff",
                                "alternateColor": "000229",
                                "logos": [{"href": "https://a.espncdn.com/i/teamlogos/soccer/500/17606.png"}],
                            },
                        },
                        {
                            "homeAway": "away",
                            "score": "0",
                            "winner": False,
                            "team": {
                                "id": "18267",
                                "abbreviation": "ORL",
                                "displayName": "Orlando City SC",
                                "location": "Orlando City SC",
                                "nickname": "Orlando",
                                "color": "633492",
                                "alternateColor": "f0c34a",
                                "logos": [{"href": "https://a.espncdn.com/i/teamlogos/soccer/500/18267.png"}],
                            },
                        },
                    ],
                }
            ]
        },
        "boxscore": {
            "teams": [
                {
                    "homeAway": "home",
                    "team": {
                        "id": "17606",
                        "abbreviation": "NYC",
                        "displayName": "New York City FC",
                        "location": "New York City FC",
                        "nickname": "NYC FC",
                    },
                    "statistics": [
                        {"name": "shotsOnTarget", "displayValue": "5"},
                        {"name": "possessionPct", "displayValue": "71.5"},
                        {"name": "yellowCards", "displayValue": "0"},
                    ],
                },
                {
                    "homeAway": "away",
                    "team": {
                        "id": "18267",
                        "abbreviation": "ORL",
                        "displayName": "Orlando City SC",
                        "location": "Orlando City SC",
                        "nickname": "Orlando",
                    },
                    "statistics": [
                        {"name": "shotsOnTarget", "displayValue": "1"},
                        {"name": "possessionPct", "displayValue": "28.5"},
                        {"name": "yellowCards", "displayValue": "3"},
                    ],
                },
            ]
        },
        "rosters": [
            {
                "homeAway": "home",
                "formation": "4-2-3-1",
                "team": {"id": "17606", "abbreviation": "NYC", "displayName": "New York City FC"},
                "roster": [
                    {
                        "starter": True,
                        "active": True,
                        "subbedIn": False,
                        "subbedOut": False,
                        "jersey": "9",
                        "formationPlace": 9,
                        "athlete": {
                            "id": "1001",
                            "displayName": "Monsef Bakrar",
                            "fullName": "Monsef Bakrar",
                            "lastName": "Bakrar",
                            "headshot": {"href": "https://a.espncdn.com/i/headshots/soccer/players/full/1001.png"},
                        },
                        "position": {"abbreviation": "F"},
                        "stats": [
                            {"name": "totalGoals", "displayValue": "2"},
                            {"name": "goalAssists", "displayValue": "1"},
                            {"name": "shotsOnTarget", "displayValue": "3"},
                            {"name": "yellowCards", "displayValue": "1"},
                            {"name": "redCards", "displayValue": "0"},
                        ],
                    },
                    {
                        "starter": False,
                        "active": True,
                        "subbedIn": True,
                        "subbedOut": False,
                        "jersey": "19",
                        "formationPlace": 12,
                        "athlete": {
                            "id": "1002",
                            "displayName": "Julian Fernandez",
                            "fullName": "Julian Fernandez",
                            "lastName": "Fernandez",
                        },
                        "position": {"abbreviation": "F"},
                        "stats": [
                            {"name": "totalGoals", "displayValue": "1"},
                            {"name": "goalAssists", "displayValue": "0"},
                            {"name": "shotsOnTarget", "displayValue": "1"},
                            {"name": "yellowCards", "displayValue": "0"},
                            {"name": "redCards", "displayValue": "0"},
                        ],
                    },
                ],
            },
            {
                "homeAway": "away",
                "formation": "4-3-3",
                "team": {"id": "18267", "abbreviation": "ORL", "displayName": "Orlando City SC"},
                "roster": [
                    {
                        "starter": True,
                        "active": True,
                        "subbedIn": False,
                        "subbedOut": False,
                        "jersey": "1",
                        "formationPlace": 1,
                        "athlete": {
                            "id": "2001",
                            "displayName": "Pedro Gallese",
                            "fullName": "Pedro Gallese",
                            "lastName": "Gallese",
                        },
                        "position": {"abbreviation": "G"},
                        "stats": [
                            {"name": "saves", "displayValue": "0"},
                            {"name": "goalsConceded", "displayValue": "5"},
                            {"name": "yellowCards", "displayValue": "0"},
                            {"name": "redCards", "displayValue": "0"},
                        ],
                    }
                ],
            },
        ],
    }

    monkeypatch.setattr(mls, "_boxscore_cache", {})
    monkeypatch.setattr(mls, "_scoreboard_cache", {"ts": 0.0, "data": None})
    monkeypatch.setattr(mls, "fetch_scores", lambda: board)
    monkeypatch.setattr(mls, "_fetch_summary_payload", lambda game_id: summary)
    monkeypatch.setattr(mls, "_save_disk_boxscore", lambda game_id, payload: None)

    box = mls.fetch_boxscore("761470")

    assert box["header"] == "FT"
    assert box["home"]["formation"] == "4-2-3-1"
    assert box["home"]["shotsOnGoal"] == 5
    assert box["home"]["statistics"]["possessionPct"] == 71.5
    assert len(box["home"]["players"]) == 2
    assert box["home"]["players"][0]["playerId"] == "1001"
    assert box["home"]["startingLineup"][0]["playerId"] == "1001"
    assert box["away"]["statistics"]["yellowCards"] == 3


def test_build_player_rows_formats_real_mls_players():
    team = {
        "players": [
            {
                "playerId": "1001",
                "fullName": "Monsef Bakrar",
                "jerseyNum": "9",
                "position": "F",
                "starter": True,
                "active": True,
                "formationPlace": 9,
                "statistics": {
                    "totalGoals": 2,
                    "goalAssists": 1,
                    "shotsOnTarget": 3,
                    "yellowCards": 1,
                    "redCards": 0,
                },
            },
            {
                "playerId": "1002",
                "fullName": "Julian Fernandez",
                "jerseyNum": "19",
                "position": "F",
                "starter": False,
                "subbedIn": True,
                "active": True,
                "formationPlace": 12,
                "statistics": {
                    "totalGoals": 1,
                    "goalAssists": 0,
                    "shotsOnTarget": 1,
                    "yellowCards": 0,
                    "redCards": 0,
                },
            },
        ]
    }

    rows = mls.build_player_rows(team)

    assert rows == [
        ["9", "Monsef Bakrar", "F", "2", "1", "3", "1", "0"],
        ["19", "Julian Fernandez", "F", "1", "0", "1", "0", "0"],
    ]
