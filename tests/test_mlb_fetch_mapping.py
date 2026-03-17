from __future__ import annotations

from typing import Any, Dict

from scoresource import mlb


class _Response:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Dict[str, Any]:
        return self._payload


def test_mlb_scoreboard_pregame_ignores_fake_period_clock(monkeypatch):
    payload = {
        "events": [
            {
                "id": "401833149",
                "date": "2026-03-11T17:05Z",
                "season": {"year": 2026},
                "status": {
                    "period": 1,
                    "displayClock": "0:00",
                    "type": {"state": "pre", "shortDetail": "3/11 - 1:05 PM EDT", "detail": "Scheduled"},
                },
                "competitions": [
                    {
                        "competitors": [
                            {"homeAway": "home", "score": "0", "team": {"id": "1", "displayName": "Baltimore Orioles", "abbreviation": "BAL"}},
                            {"homeAway": "away", "score": "0", "team": {"id": "2", "displayName": "Pittsburgh Pirates", "abbreviation": "PIT"}},
                        ]
                    }
                ],
            }
        ]
    }

    monkeypatch.setattr(mlb, "_scoreboard_cache", {"ts": 0.0, "data": None})
    monkeypatch.setattr(
        mlb,
        "_session",
        type("S", (), {"get": staticmethod(lambda url, headers=None, timeout=None: _Response(payload))})(),
    )

    board = mlb.get_scoreboard()
    game = board["games"][0]
    assert game["gameStatus"] == 1
    assert game["period"] == {}
    assert game["gameClock"] is None


def test_mlb_scoreboard_live_extracts_inning_and_bases(monkeypatch):
    payload = {
        "events": [
            {
                "id": "LIVE123",
                "date": "2026-03-11T19:05Z",
                "season": {"year": 2026},
                "status": {
                    "period": None,
                    "displayClock": "2:17",
                    "type": {"state": "in", "shortDetail": "Top 3rd", "detail": "Top 3rd"},
                },
                "competitions": [
                    {
                        "situation": {
                            "occupiedBases": [1, 2, 3],
                            "count": {"balls": 3, "strikes": 2, "outs": 1},
                            "batter": {"athlete": {"shortName": "A. Hitter"}},
                            "pitcher": {"athlete": {"shortName": "B. Pitcher"}},
                        },
                        "competitors": [
                            {"homeAway": "home", "score": "1", "team": {"id": "1", "displayName": "Home Team", "abbreviation": "BAL"}},
                            {"homeAway": "away", "score": "2", "team": {"id": "2", "displayName": "Away Team", "abbreviation": "PIT"}},
                        ],
                    }
                ],
            }
        ]
    }

    monkeypatch.setattr(mlb, "_scoreboard_cache", {"ts": 0.0, "data": None})
    monkeypatch.setattr(
        mlb,
        "_session",
        type("S", (), {"get": staticmethod(lambda url, headers=None, timeout=None: _Response(payload))})(),
    )

    board = mlb.get_scoreboard()
    game = board["games"][0]
    assert game["gameStatus"] == 2
    assert game["period"] == {"current": 3}
    assert game["gameClock"] == "2:17"
    situation = game["situation"]
    assert situation["onFirst"] is True
    assert situation["onSecond"] is True
    assert situation["onThird"] is True
    assert situation["basesLoaded"] is True
    assert situation["inningHalf"] == "TOP"
    assert situation["balls"] == 3
    assert situation["strikes"] == 2
    assert situation["outs"] == 1


def test_mlb_scoreboard_live_hides_placeholder_clock(monkeypatch):
    payload = {
        "events": [
            {
                "id": "LIVE124",
                "date": "2026-03-11T19:05Z",
                "season": {"year": 2026},
                "status": {
                    "period": 2,
                    "displayClock": "0:00",
                    "type": {"state": "in", "shortDetail": "Bot 2nd", "detail": "Bottom 2nd"},
                },
                "competitions": [
                    {
                        "competitors": [
                            {"homeAway": "home", "score": "1", "team": {"id": "1", "displayName": "Home Team", "abbreviation": "BAL"}},
                            {"homeAway": "away", "score": "2", "team": {"id": "2", "displayName": "Away Team", "abbreviation": "PIT"}},
                        ]
                    }
                ],
            }
        ]
    }

    monkeypatch.setattr(mlb, "_scoreboard_cache", {"ts": 0.0, "data": None})
    monkeypatch.setattr(
        mlb,
        "_session",
        type("S", (), {"get": staticmethod(lambda url, headers=None, timeout=None: _Response(payload))})(),
    )

    board = mlb.get_scoreboard()
    game = board["games"][0]
    assert game["gameStatus"] == 2
    assert game["period"] == {"current": 2}
    assert game["gameClock"] is None


def test_mlb_boxscore_merges_summary_situation(monkeypatch):
    board = {
        "games": [
            {
                "gameId": "401833149",
                "homeTeam": {"teamId": "1", "teamName": "Baltimore Orioles", "teamTricode": "BAL", "score": 0},
                "awayTeam": {"teamId": "2", "teamName": "Pittsburgh Pirates", "teamTricode": "PIT", "score": 0},
                "gameStatus": 2,
                "status": "live",
                "startTime": "2026-03-11T17:05Z",
                "header": "Top 1st",
                "gameStatusText": "Top 1st",
                "period": {"current": 1},
                "gameClock": "3:00",
                "situation": {},
                "seasonYear": "2026",
            }
        ],
        "lines": [],
    }

    summary_payload = {
        "header": {
            "competitions": [
                {
                    "status": {
                        "period": 4,
                        "displayClock": "1:11",
                        "type": {"state": "in", "shortDetail": "Bot 4th", "detail": "Bot 4th"},
                    },
                    "situation": {
                        "onFirst": {"id": "r1"},
                        "onSecond": {"id": "r2"},
                        "onThird": {"id": "r3"},
                        "balls": 2,
                        "strikes": 1,
                        "outs": 2,
                    },
                    "competitors": [
                        {"homeAway": "home", "score": "3", "team": {"id": "1", "displayName": "Baltimore Orioles", "abbreviation": "BAL"}},
                        {"homeAway": "away", "score": "2", "team": {"id": "2", "displayName": "Pittsburgh Pirates", "abbreviation": "PIT"}},
                    ],
                }
            ]
        }
    }

    def _get(url, headers=None, timeout=None):
        if "summary?event=401833149" in url:
            return _Response(summary_payload)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mlb, "_boxscore_cache", {})
    monkeypatch.setattr(mlb, "_summary_cache", {})
    monkeypatch.setattr(mlb, "get_scoreboard", lambda: board)
    monkeypatch.setattr(mlb, "_session", type("S", (), {"get": staticmethod(_get)})())

    box = mlb.get_boxscore("401833149")
    game = box["game"]
    situation = game["situation"]

    assert game["gameStatus"] == 2
    assert game["period"] == {"current": 4}
    assert game["gameStatusText"] == "Bot 4th"
    assert situation["basesLoaded"] is True
    assert situation["inningHalf"] == "BOT"
    assert situation["balls"] == 2
    assert situation["strikes"] == 1
    assert situation["outs"] == 2


def test_mlb_boxscore_keeps_scoreboard_situation_when_summary_is_sparse(monkeypatch):
    board = {
        "games": [
            {
                "gameId": "401833149",
                "homeTeam": {"teamId": "1", "teamName": "Baltimore Orioles", "teamTricode": "BAL", "score": 0},
                "awayTeam": {"teamId": "2", "teamName": "Pittsburgh Pirates", "teamTricode": "PIT", "score": 0},
                "gameStatus": 2,
                "status": "live",
                "startTime": "2026-03-11T17:05Z",
                "header": "Mid 1st",
                "gameStatusText": "Mid 1st",
                "period": {"current": 1},
                "gameClock": "0:00",
                "situation": {
                    "balls": 0,
                    "strikes": 0,
                    "outs": 0,
                    "onFirst": False,
                    "onSecond": False,
                    "onThird": False,
                    "basesLoaded": False,
                },
                "seasonYear": "2026",
            }
        ],
        "lines": [],
    }

    summary_payload = {
        "header": {
            "competitions": [
                {
                    "status": {
                        "period": 1,
                        "displayClock": "0:00",
                        "type": {"state": "in", "shortDetail": "Mid 1st", "detail": "Mid 1st"},
                    },
                    "situation": None,
                    "competitors": [
                        {"homeAway": "home", "score": "0", "team": {"id": "1", "displayName": "Baltimore Orioles", "abbreviation": "BAL"}},
                        {"homeAway": "away", "score": "0", "team": {"id": "2", "displayName": "Pittsburgh Pirates", "abbreviation": "PIT"}},
                    ],
                }
            ]
        }
    }

    def _get(url, headers=None, timeout=None):
        if "summary?event=401833149" in url:
            return _Response(summary_payload)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mlb, "_boxscore_cache", {})
    monkeypatch.setattr(mlb, "_summary_cache", {})
    monkeypatch.setattr(mlb, "get_scoreboard", lambda: board)
    monkeypatch.setattr(mlb, "_session", type("S", (), {"get": staticmethod(_get)})())

    box = mlb.get_boxscore("401833149")
    game = box["game"]
    situation = (box["game"] or {}).get("situation") or {}
    assert game["gameClock"] is None
    assert situation["balls"] == 0
    assert situation["strikes"] == 0
    assert situation["outs"] == 0


def test_mlb_scoreboard_maps_linescores_hits_errors(monkeypatch):
    payload = {
        "events": [
            {
                "id": "LIVE125",
                "date": "2026-03-11T19:05Z",
                "season": {"year": 2026},
                "status": {
                    "period": 5,
                    "type": {"state": "in", "shortDetail": "Bot 5th", "detail": "Bottom 5th"},
                },
                "competitions": [
                    {
                        "competitors": [
                            {
                                "homeAway": "home",
                                "score": "3",
                                "hits": 6,
                                "errors": 1,
                                "linescores": [
                                    {"period": 1, "value": 1},
                                    {"period": 2, "value": 0},
                                    {"period": 3, "value": 2},
                                ],
                                "team": {"id": "1", "displayName": "Home Team", "abbreviation": "BAL"},
                            },
                            {
                                "homeAway": "away",
                                "score": "2",
                                "hits": 5,
                                "errors": 0,
                                "linescores": [
                                    {"period": 1, "value": 0},
                                    {"period": 2, "value": 1},
                                    {"period": 3, "value": 1},
                                ],
                                "team": {"id": "2", "displayName": "Away Team", "abbreviation": "PIT"},
                            },
                        ]
                    }
                ],
            }
        ]
    }

    monkeypatch.setattr(mlb, "_scoreboard_cache", {"ts": 0.0, "data": None})
    monkeypatch.setattr(
        mlb,
        "_session",
        type("S", (), {"get": staticmethod(lambda url, headers=None, timeout=None: _Response(payload))})(),
    )

    board = mlb.get_scoreboard()
    game = board["games"][0]
    home = game["homeTeam"]
    away = game["awayTeam"]
    assert home["hits"] == 6
    assert home["errors"] == 1
    assert away["hits"] == 5
    assert away["errors"] == 0
    assert home["linescores"][0] == {"inning": 1, "runs": 1}
    assert away["linescores"][2] == {"inning": 3, "runs": 1}


def test_mlb_boxscore_maps_players_team_stats_and_linescore(monkeypatch):
    board = {
        "games": [
            {
                "gameId": "401833149",
                "homeTeam": {"teamId": "1", "teamName": "Baltimore Orioles", "teamTricode": "BAL", "score": 3},
                "awayTeam": {"teamId": "2", "teamName": "Pittsburgh Pirates", "teamTricode": "PIT", "score": 2},
                "gameStatus": 2,
                "status": "live",
                "startTime": "2026-03-11T17:05Z",
                "header": "Bot 5th",
                "gameStatusText": "Bot 5th",
                "period": {"current": 5},
                "gameClock": None,
                "situation": {},
                "seasonYear": "2026",
            }
        ],
        "lines": [],
    }

    summary_payload = {
        "header": {
            "competitions": [
                {
                    "status": {
                        "period": 5,
                        "type": {"state": "in", "shortDetail": "Bot 5th", "detail": "Bottom 5th"},
                    },
                    "competitors": [
                        {
                            "homeAway": "home",
                            "score": "3",
                            "hits": 7,
                            "errors": 0,
                            "linescores": [
                                {"period": 1, "value": 1},
                                {"period": 2, "value": 2},
                            ],
                            "team": {"id": "1", "displayName": "Baltimore Orioles", "abbreviation": "BAL"},
                        },
                        {
                            "homeAway": "away",
                            "score": "2",
                            "hits": 6,
                            "errors": 1,
                            "linescores": [
                                {"period": 1, "value": 0},
                                {"period": 2, "value": 2},
                            ],
                            "team": {"id": "2", "displayName": "Pittsburgh Pirates", "abbreviation": "PIT"},
                        },
                    ],
                }
            ]
        },
        "boxscore": {
            "teams": [
                {
                    "team": {"id": "1", "abbreviation": "BAL"},
                    "statistics": [
                        {"name": "batting", "stats": [{"name": "hits", "displayValue": "7"}, {"name": "homeRuns", "displayValue": "1"}]}
                    ],
                    "details": [
                        {"name": "battingDetails", "stats": [{"name": "teamRISP", "displayValue": "3-9"}]}
                    ],
                },
                {
                    "team": {"id": "2", "abbreviation": "PIT"},
                    "statistics": [
                        {"name": "batting", "stats": [{"name": "hits", "displayValue": "6"}, {"name": "homeRuns", "displayValue": "0"}]}
                    ],
                    "details": [
                        {"name": "battingDetails", "stats": [{"name": "teamRISP", "displayValue": "2-8"}]}
                    ],
                },
            ],
            "players": [
                {
                    "team": {"id": "1", "abbreviation": "BAL"},
                    "statistics": [
                        {
                            "name": "batting",
                            "labels": ["H-AB", "AVG", "HR", "RBI", "OBP", "SLG"],
                            "keys": ["H-AB", "AVG", "HR", "RBI", "OBP", "SLG"],
                            "athletes": [
                                {
                                    "athlete": {
                                        "id": "10",
                                        "firstName": "Adley",
                                        "lastName": "Rutschman",
                                        "fullName": "Adley Rutschman",
                                        "jersey": "35",
                                    },
                                    "position": {"abbreviation": "C"},
                                    "batOrder": 1,
                                    "starter": True,
                                    "stats": ["1-3", ".333", "1", "2", ".400", ".667"],
                                }
                            ],
                        }
                    ],
                },
                {
                    "team": {"id": "2", "abbreviation": "PIT"},
                    "statistics": [
                        {
                            "name": "batting",
                            "labels": ["H-AB", "AVG", "HR", "RBI", "OBP", "SLG"],
                            "keys": ["H-AB", "AVG", "HR", "RBI", "OBP", "SLG"],
                            "athletes": [
                                {
                                    "athlete": {
                                        "id": "20",
                                        "firstName": "Bryan",
                                        "lastName": "Reynolds",
                                        "fullName": "Bryan Reynolds",
                                        "jersey": "10",
                                    },
                                    "position": {"abbreviation": "LF"},
                                    "batOrder": 2,
                                    "starter": True,
                                    "stats": ["2-4", ".500", "0", "1", ".500", ".500"],
                                }
                            ],
                        }
                    ],
                },
            ],
        },
    }

    def _get(url, headers=None, timeout=None):
        if "summary?event=401833149" in url:
            return _Response(summary_payload)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mlb, "_boxscore_cache", {})
    monkeypatch.setattr(mlb, "_summary_cache", {})
    monkeypatch.setattr(mlb, "get_scoreboard", lambda: board)
    monkeypatch.setattr(mlb, "_session", type("S", (), {"get": staticmethod(_get)})())

    box = mlb.get_boxscore("401833149")
    game = box["game"]
    home = box["home"]
    away = box["away"]
    assert game["linescore"]["home"] == [{"inning": 1, "runs": 1}, {"inning": 2, "runs": 2}]
    assert game["linescore"]["away"] == [{"inning": 1, "runs": 0}, {"inning": 2, "runs": 2}]
    assert home["teamStats"]["batting"]["hits"] == "7"
    assert away["teamDetails"]["battingDetails"]["teamRISP"] == "2-8"
    assert home["players"][0]["statistics"]["avg"] == ".333"

    rows = mlb.build_player_rows(home)
    assert rows[0][:4] == ["35", "A. Rutschman", "C", ".333"]


def test_mlb_fetch_play_by_play_maps_summary_plays(monkeypatch):
    summary_payload = {
        "header": {
            "competitions": [
                {
                    "competitors": [
                        {"homeAway": "home", "team": {"id": "1", "abbreviation": "BAL"}},
                        {"homeAway": "away", "team": {"id": "2", "abbreviation": "PIT"}},
                    ]
                }
            ]
        },
        "plays": [
            {
                "id": "1",
                "period": {"number": 1},
                "team": {"id": "2"},
                "text": "Single to center",
                "homeScore": 0,
                "awayScore": 1,
            },
            {
                "id": "2",
                "period": {"number": 1},
                "team": {"id": "1"},
                "text": "Two-run homer to left",
                "homeScore": 2,
                "awayScore": 1,
            },
        ],
    }

    def _get(url, headers=None, timeout=None):
        if "summary?event=401833149" in url:
            return _Response(summary_payload)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mlb, "_summary_cache", {})
    monkeypatch.setattr(mlb, "_session", type("S", (), {"get": staticmethod(_get)})())

    plays = mlb.fetch_play_by_play("401833149", limit=2)
    assert len(plays) == 2
    assert plays[0]["teamTricode"] == "PIT"
    assert plays[1]["teamTricode"] == "BAL"
    assert plays[1]["description"] == "Two-run homer to left"
