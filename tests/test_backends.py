import importlib

SPORT_MODULES = [
    "scoresource.sports.nba",
    "scoresource.sports.ncaa_basketball",
    "scoresource.sports.nfl",
    "scoresource.sports.nhl",
    "scoresource.sports.mlb",
    "scoresource.sports.ncaa_football",
    "scoresource.sports.mls",
]


def _assert_game_shape(game):
    required = {
        "gameId",
        "sport",
        "status",
        "home",
        "away",
        "homeTricode",
        "awayTricode",
        "homeScore",
        "awayScore",
        "startTime",
        "period",
        "clock",
        "shotClock",
    }
    assert required.issubset(game.keys())


def test_modules_return_games():
    for path in SPORT_MODULES:
        mod = importlib.import_module(path)
        live = mod.fetch_live()
        sched = mod.fetch_schedule()
        assert isinstance(live, dict)
        assert isinstance(sched, dict)
        games = live.get("games") or sched.get("games") or []
        assert isinstance(games, list)
        if not games:
            import pytest

            pytest.skip(f"No games returned for {path}; upstream data may be unavailable")
        _assert_game_shape(games[0])
