import types

from scoresource.sports import nba


def _live_scoreboard_payload():
    return {
        "scoreboard": {
            "games": [
                {
                    "gameId": "LIVE_1",
                    "homeTeam": {"teamId": "1", "teamName": "Live Home", "teamTricode": "LHM", "score": 10},
                    "awayTeam": {"teamId": "2", "teamName": "Live Away", "teamTricode": "LAW", "score": 9},
                    "gameStatus": 2,
                    "gameStatusText": "Q1 10:00",
                    "period": {"current": 1},
                    "gameClock": "PT10M0.0S",
                }
            ]
        }
    }


def test_build_header_defaults_final_when_status_text_missing():
    assert nba._build_header({"gameStatus": 3, "gameStatusText": "", "period": {}, "gameClock": "PT0M0.0S"}) == "Final"


def test_fetch_scores_prefers_live_feed_over_disk_seed(monkeypatch):
    stale = {
        "games": [
            {
                "gameId": "STALE_1",
                "homeTeam": {"teamName": "Old Home", "teamTricode": "OLD", "score": 1},
                "awayTeam": {"teamName": "Old Away", "teamTricode": "OLD", "score": 2},
                "gameStatus": 3,
                "gameStatusText": "Final",
            }
        ],
        "lines": ["stale"],
    }

    class _ScoreBoard:
        def get_dict(self):
            return _live_scoreboard_payload()

    monkeypatch.setattr(nba, "_scoreboard_cache", {"ts": 0.0, "data": None})
    monkeypatch.setattr(nba, "_load_disk_scoreboard", lambda: stale)
    monkeypatch.setattr(nba, "_save_disk_scoreboard", lambda _payload: None)
    monkeypatch.setattr(nba, "NBA_API_AVAILABLE", True)
    monkeypatch.setattr(nba, "DEMO_MODE", False)
    monkeypatch.setattr(nba, "scoreboard", types.SimpleNamespace(ScoreBoard=lambda: _ScoreBoard()))

    result = nba.fetch_scores()
    assert result["games"][0]["gameId"] == "LIVE_1"


def test_fetch_boxscore_prefers_live_feed_over_disk_seed(monkeypatch):
    stale_box = {
        "game": {"gameStatus": 3, "gameStatusText": "Final", "period": {"current": 4}, "gameClock": "PT0M0.0S"},
        "home": {"teamName": "Old Home", "teamTricode": "OLD", "score": 99},
        "away": {"teamName": "Old Away", "teamTricode": "OLD", "score": 98},
        "header": "Final",
        "shotclock": "--",
    }

    class _BoxScore:
        def __init__(self, game_id: str):
            self.game_id = game_id

        def get_dict(self):
            return {
                "game": {
                    "gameId": self.game_id,
                    "homeTeam": {"teamId": "1", "teamName": "Live Home", "teamTricode": "LHM", "score": 12, "players": []},
                    "awayTeam": {"teamId": "2", "teamName": "Live Away", "teamTricode": "LAW", "score": 11, "players": []},
                    "gameStatus": 2,
                    "gameStatusText": "Q1 10:00",
                    "period": {"current": 1},
                    "gameClock": "PT10M0.0S",
                }
            }

    monkeypatch.setattr(nba, "_boxscore_cache", {})
    monkeypatch.setattr(nba, "_load_disk_boxscore", lambda _game_id: stale_box)
    monkeypatch.setattr(nba, "_save_disk_boxscore", lambda _game_id, _payload: None)
    monkeypatch.setattr(nba, "_stub_boxscore_from_scoreboard", lambda _game_id: None)
    monkeypatch.setattr(nba, "_fetch_live_clock", lambda _game_id: None)
    monkeypatch.setattr(nba, "_resolve_shotclock", lambda _game_id, _game, _period: "--")
    monkeypatch.setattr(nba, "NBA_API_AVAILABLE", True)
    monkeypatch.setattr(nba, "DEMO_MODE", False)
    monkeypatch.setattr(nba, "boxscore", types.SimpleNamespace(BoxScore=_BoxScore))

    result = nba.fetch_boxscore("LIVE_GAME")
    assert result["home"]["teamName"] == "Live Home"
    assert (result["game"] or {}).get("gameStatus") == 2


def test_fetch_boxscore_uses_live_boxscore_when_nba_api_is_unavailable(monkeypatch):
    live_payload = {
        "game": {
            "gameClock": "PT10M41.00S",
            "shotClock": None,
            "period": 1,
            "gameStatus": 2,
            "gameStatusText": "Q1 10:41",
            "homeTeam": {
                "teamId": "1",
                "teamName": "Live Home",
                "teamTricode": "LHM",
                "score": 5,
                "players": [
                    {
                        "personId": 1,
                        "firstName": "Live",
                        "familyName": "Home",
                        "jerseyNum": "1",
                        "position": "G",
                        "statistics": {"points": 3},
                    }
                ],
            },
            "awayTeam": {
                "teamId": "2",
                "teamName": "Live Away",
                "teamTricode": "LAW",
                "score": 4,
                "players": [
                    {
                        "personId": 2,
                        "firstName": "Live",
                        "familyName": "Away",
                        "jerseyNum": "2",
                        "position": "F",
                        "statistics": {"points": 2},
                    }
                ],
            },
        }
    }

    monkeypatch.setattr(nba, "_boxscore_cache", {})
    monkeypatch.setattr(nba, "_load_disk_boxscore", lambda _game_id: None)
    monkeypatch.setattr(nba, "_save_disk_boxscore", lambda _game_id, _payload: None)
    monkeypatch.setattr(nba, "_stub_boxscore_from_scoreboard", lambda _game_id: None)
    monkeypatch.setattr(nba, "_fetch_live_boxscore", lambda _game_id: live_payload)
    monkeypatch.setattr(
        nba,
        "_fetch_live_clock",
        lambda _game_id: {
            "gameClock": "PT10M41.00S",
            "period": 1,
            "statusText": "Q1 10:41",
            "homeScore": 5,
            "awayScore": 4,
            "homeTeam": {"score": 5},
            "awayTeam": {"score": 4},
        },
    )
    monkeypatch.setattr(nba, "_resolve_shotclock", lambda _game_id, _game, _period: "--")
    monkeypatch.setattr(nba, "NBA_API_AVAILABLE", False)
    monkeypatch.setattr(nba, "DEMO_MODE", True)
    monkeypatch.setattr(nba, "boxscore", None)

    result = nba.fetch_boxscore("LIVE_GAME")

    assert len(result["home"]["players"]) == 1
    assert len(result["away"]["players"]) == 1
    assert result["home"]["teamName"] == "Live Home"
    assert result["away"]["teamName"] == "Live Away"


def test_live_cache_ttls_are_shortened():
    scoreboard_ttl = nba._scoreboard_cache_ttl(
        {
            "games": [
                {
                    "gameStatus": 2,
                    "gameStatusText": "Q2 8:30",
                    "period": {"current": 2},
                }
            ]
        }
    )
    boxscore_ttl = nba._boxscore_cache_ttl(
        {
            "game": {
                "gameStatus": 2,
                "gameStatusText": "Q2 8:30",
                "period": {"current": 2},
            }
        }
    )

    assert scoreboard_ttl == min(nba.SCOREBOARD_TTL, nba.LIVE_SCOREBOARD_TTL)
    assert boxscore_ttl == min(nba.BOXSCORE_TTL, nba.LIVE_BOXSCORE_TTL)


def test_build_player_rows_backfills_missing_position(monkeypatch):
    monkeypatch.setattr(nba, "_get_player_position", lambda _pid: "SF")

    team = {
        "players": [
            {
                "personId": "6578",
                "firstName": "Harrison",
                "familyName": "Barnes",
                "jerseyNum": "40",
                "position": None,
                "statistics": {
                    "minutes": "PT12M17.00S",
                    "points": 5,
                    "reboundsTotal": 3,
                    "assists": 2,
                    "threePointersMade": 1,
                },
            }
        ]
    }

    rows = nba.build_player_rows(team)

    assert rows[0][3] == "SF"
    assert rows[0][4] == "5"
    assert team["players"][0]["position"] == "SF"
