from scoresource.sports import nhl


def _primary_cache_game():
    return {
        "gameId": "401803363",
        "homeTeam": {"teamId": "1", "teamName": "Boston Bruins", "teamTricode": "BOS", "score": 2},
        "awayTeam": {"teamId": "8", "teamName": "Los Angeles Kings", "teamTricode": "LAK", "score": 1},
        "status": "final",
        "startTime": "2026-03-10T23:00Z",
        "header": "Final/OT",
        "gameStatusText": "Final/OT",
        "gameClock": "0:00",
        "period": {"current": 4},
        "seasonYear": "2025",
    }


def test_status_from_game_accepts_status_strings():
    assert nhl._status_from_game({"status": "final"}) == "final"
    assert nhl._status_from_game({"status": "upcoming"}) == "upcoming"
    assert nhl._status_from_game({"status": "live"}) == "live"


def test_normalize_game_for_tests_uses_start_time_fallback():
    normalized = nhl._normalize_game_for_tests(_primary_cache_game())
    assert normalized["status"] == "final"
    assert normalized["startTime"] == "2026-03-10T23:00Z"


def test_fetch_scores_coerces_primary_cache_shape_when_offline(monkeypatch):
    payload = {"games": [_primary_cache_game()], "lines": ["LAK 1 @ BOS 2 (Final/OT)"]}

    monkeypatch.setattr(nhl, "_scoreboard_cache", {"ts": 0.0, "data": None})
    monkeypatch.setattr(nhl, "_load_disk_scoreboard", lambda: payload)

    class _OfflineSession:
        def get(self, *_args, **_kwargs):
            raise RuntimeError("offline")

    monkeypatch.setattr(nhl, "_logo_session", _OfflineSession())

    result = nhl.fetch_scores()
    game = result["games"][0]

    assert game["gameStatus"] == 3
    assert game["gameStatusText"] == "Final/OT"
    assert game["gameTimeUTC"] == "2026-03-10T23:00Z"
