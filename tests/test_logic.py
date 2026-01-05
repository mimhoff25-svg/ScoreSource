from scoresource.logic import ScoreSourceLogic


def test_fetch_scores_for_sport_returns_normalized_games(monkeypatch):
    monkeypatch.setenv("SCORESOURCE_DEMO", "1")
    logic = ScoreSourceLogic()

    data = logic.fetch_scores_for_sport("NBA")
    games = data.get("games") or []
    assert games, "Expected at least one demo game"

    sample = games[0]
    assert isinstance(sample.get("home"), str)
    assert isinstance(sample.get("away"), str)
    assert isinstance(sample.get("homeScore"), int)
    assert isinstance(sample.get("awayScore"), int)
    assert isinstance(sample.get("homeTricode"), str)
    assert isinstance(sample.get("awayTricode"), str)
    assert isinstance(sample.get("startTimeLocal"), str)
