import types
import time
import importlib

from scoresource import nba, nhl


def _load_nba_backend_module():
    return importlib.import_module("scoresource.sports.nba")


def test_nba_get_scoreboard_preserves_live_fields(monkeypatch):
    fake_backend = types.SimpleNamespace(
        fetch_scores=lambda: {
            "games": [
                {
                    "gameId": "0022500958",
                    "homeTeam": {"teamId": "1610612759", "teamName": "Spurs", "teamTricode": "SAS", "score": 19},
                    "awayTeam": {"teamId": "1610612743", "teamName": "Nuggets", "teamTricode": "DEN", "score": 12},
                    "gameStatus": 2,
                    "gameStatusText": "Q1 6:01",
                    "gameClock": "PT06M01.00S",
                    "period": {"current": 1},
                    "shotClock": 18.0,
                    "gameTimeUTC": "2026-03-13T01:00:00Z",
                    "seasonYear": "2025",
                }
            ],
            "lines": ["DEN 12 @ SAS 19 (Q1 6:01)"],
        },
        demo_scoreboard=lambda: {"games": [], "lines": []},
        format_clock=lambda raw: "6:01",
    )

    monkeypatch.setattr(nba, "backend", fake_backend)

    result = nba.get_scoreboard()
    game = result["games"][0]

    assert game["status"] == "live"
    assert game["gameStatus"] == 2
    assert game["gameClock"] == "PT06M01.00S"
    assert game["period"] == {"current": 1}
    assert game["shotClock"] == 18.0
    assert game["gameStatusText"] == "Q1 6:01"


def test_nba_backend_cached_boxscore_overlays_live_scores(monkeypatch):
    backend = _load_nba_backend_module()
    cached_payload = {
        "game": {
            "gameStatus": 2,
            "gameStatusText": "Q1 10:00",
            "period": {"current": 1},
            "gameClock": "PT10M0.0S",
        },
        "home": {"teamName": "Spurs", "teamTricode": "SAS", "score": 10},
        "away": {"teamName": "Nuggets", "teamTricode": "DEN", "score": 9},
        "header": "Q1 10:00",
        "shotclock": "--",
    }

    monkeypatch.setattr(backend, "DEMO_MODE", False)
    monkeypatch.setattr(backend, "NBA_API_AVAILABLE", True)
    monkeypatch.setattr(backend, "boxscore", object())
    monkeypatch.setattr(backend, "BOXSCORE_TTL", 60.0)
    monkeypatch.setattr(backend, "_boxscore_cache", {"LIVE": (time.monotonic(), cached_payload)})
    monkeypatch.setattr(
        backend,
        "_fetch_live_clock",
        lambda _game_id: {
            "gameClock": "PT09M50.0S",
            "period": 1,
            "statusText": "Q1 9:50",
            "homeScore": 22,
            "awayScore": 18,
            "homeTeam": {"score": 22},
            "awayTeam": {"score": 18},
        },
    )
    monkeypatch.setattr(backend, "_resolve_shotclock", lambda *_args, **_kwargs: "--")
    monkeypatch.setattr(backend, "_apply_player_positions", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr(backend, "_apply_logo_map_to_result", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr(backend, "_apply_period_fouls", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr(backend, "_save_disk_boxscore", lambda *_args, **_kwargs: None)

    result = backend.fetch_boxscore("LIVE")

    assert result["home"]["score"] == 22
    assert result["away"]["score"] == 18
    assert result["game"]["gameStatusText"] == "Q1 9:50"


def test_nba_backend_uses_live_boxscore_when_nba_api_is_unavailable(monkeypatch):
    backend = _load_nba_backend_module()
    live_payload = {
        "game": {
            "gameClock": "PT10M41.00S",
            "shotClock": None,
            "period": 1,
            "gameStatus": 2,
            "gameStatusText": "Q1 10:41",
            "homeTeam": {
                "teamId": 1610612759,
                "teamName": "Spurs",
                "teamTricode": "SAS",
                "score": 5,
                "players": [
                    {
                        "personId": 1630170,
                        "firstName": "Devin",
                        "familyName": "Vassell",
                        "jerseyNum": "24",
                        "position": "SF",
                        "starter": "1",
                        "oncourt": "1",
                        "statistics": {"points": 0, "reboundsTotal": 0, "assists": 0},
                    }
                ],
            },
            "awayTeam": {
                "teamId": 1610612766,
                "teamName": "Hornets",
                "teamTricode": "CHA",
                "score": 4,
                "players": [
                    {
                        "personId": 1631217,
                        "firstName": "Moussa",
                        "familyName": "Diabate",
                        "jerseyNum": "14",
                        "position": "C",
                        "starter": "1",
                        "oncourt": "1",
                        "statistics": {"points": 2, "reboundsTotal": 1, "assists": 0},
                    }
                ],
            },
        }
    }

    monkeypatch.setattr(backend, "DEMO_MODE", True)
    monkeypatch.setattr(backend, "NBA_API_AVAILABLE", False)
    monkeypatch.setattr(backend, "boxscore", None)
    monkeypatch.setattr(backend, "_boxscore_cache", {})
    monkeypatch.setattr(backend, "_load_disk_boxscore", lambda _game_id: None)
    monkeypatch.setattr(backend, "_stub_boxscore_from_scoreboard", lambda _game_id: None)
    monkeypatch.setattr(backend, "_fetch_live_boxscore", lambda _game_id: live_payload)
    monkeypatch.setattr(
        backend,
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
    monkeypatch.setattr(backend, "_resolve_shotclock", lambda *_args, **_kwargs: "--")
    monkeypatch.setattr(backend, "_apply_player_positions", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr(backend, "_apply_logo_map_to_result", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr(backend, "_apply_period_fouls", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr(backend, "_save_disk_boxscore", lambda *_args, **_kwargs: None)

    result = backend.fetch_boxscore("LIVE")

    assert len(result["home"]["players"]) == 1
    assert len(result["away"]["players"]) == 1
    assert result["home"]["players"][0]["familyName"] == "Vassell"
    assert result["away"]["players"][0]["familyName"] == "Diabate"


def test_nba_backend_live_cache_ttls_are_shortened():
    backend = _load_nba_backend_module()

    scoreboard_ttl = backend._scoreboard_cache_ttl(
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
    boxscore_ttl = backend._boxscore_cache_ttl(
        {
            "game": {
                "gameStatus": 2,
                "gameStatusText": "Q2 8:30",
                "period": {"current": 2},
            }
        }
    )

    assert scoreboard_ttl == min(backend.SCOREBOARD_TTL, backend.LIVE_SCOREBOARD_TTL)
    assert boxscore_ttl == min(backend.BOXSCORE_TTL, backend.LIVE_BOXSCORE_TTL)


def test_nhl_get_boxscore_uses_live_summary_header_and_scores(monkeypatch):
    board = {
        "games": [
            {
                "gameId": "401803385",
                "homeTeam": {"teamId": "9", "teamName": "Dallas Stars", "teamTricode": "DAL", "score": 5},
                "awayTeam": {"teamId": "6", "teamName": "Edmonton Oilers", "teamTricode": "EDM", "score": 1},
                "status": "live",
                "gameStatus": 2,
                "startTime": "2026-03-13T00:00Z",
                "header": "7:26 - 2nd",
                "gameStatusText": "7:26 - 2nd",
                "gameClock": "7:26",
                "period": {"current": 2},
            }
        ],
        "lines": ["EDM 1 @ DAL 5 (7:26 - 2nd)"],
    }

    monkeypatch.setattr(nhl, "_boxscore_cache", {})
    monkeypatch.setattr(nhl, "_scoreboard_cache", {"ts": 0.0, "data": board})
    monkeypatch.setattr(nhl, "get_scoreboard", lambda: board)
    monkeypatch.setattr(nhl, "apply_starting_lineups", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        nhl,
        "_fetch_boxscore_players",
        lambda *_args, **_kwargs: ({}, {}, {}, "7:42", 2, "7:42 - 2nd", {}, {"home": 6, "away": 2}),
    )

    result = nhl.get_boxscore("401803385")

    assert result["header"] == "7:42 - 2nd"
    assert result["game"]["gameClock"] == "7:42"
    assert result["game"]["gameStatusText"] == "7:42 - 2nd"
    assert result["home"]["score"] == 6
    assert result["away"]["score"] == 2


def test_nhl_penalty_duration_reads_type_penalty_minutes():
    play = {
        "type": {
            "text": "Hooking",
            "penaltyMinutes": "2",
            "penaltyType": "Minor",
        },
        "text": "Lars Eller Hooking against Jackson LaCombe",
    }

    assert nhl._penalty_duration_seconds(play) == 120


def test_nhl_penalty_clocks_from_plays_accepts_infraction_types_on_countdown_clock():
    plays = [
        {
            "sequenceNumber": "240",
            "type": {
                "text": "Hooking",
                "penaltyMinutes": "2",
                "penaltyType": "Minor",
            },
            "text": "Lars Eller Hooking against Jackson LaCombe",
            "team": {"id": "14"},
            "period": {"number": 3, "displayValue": "3rd"},
            "clock": {"displayValue": "18:00"},
            "strength": {"text": "Even Strength"},
        }
    ]

    clocks = nhl._penalty_clocks_from_plays(plays, current_period=3, current_clock_secs=16 * 60 + 30)

    assert clocks == {"14": [30]}
