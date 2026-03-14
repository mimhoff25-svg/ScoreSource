import time

from scoresource.logic import ScoreSourceLogic


def test_fetch_scores_for_sport_returns_normalized_games(monkeypatch):
    logic = ScoreSourceLogic()

    data = logic.fetch_scores_for_sport("NBA")
    games = data.get("games") or []
    # Note: games list may be empty when API is unavailable

    if games:
        sample = games[0]
        assert isinstance(sample.get("home"), str)
        assert isinstance(sample.get("away"), str)
        assert isinstance(sample.get("homeScore"), int)
        assert isinstance(sample.get("awayScore"), int)
        assert isinstance(sample.get("homeTricode"), str)
        assert isinstance(sample.get("awayTricode"), str)
        assert isinstance(sample.get("startTimeLocal"), str)


def test_nba_boxscore_contains_player_stats(monkeypatch):
    """Test that NBA boxscore contains player data for popup overlays."""
    logic = ScoreSourceLogic()
    data = logic.fetch_scores_for_sport("NBA")
    games = data.get("games") or []
    # Note: games list may be empty when API is unavailable
    if games:
        game_id = games[0]["gameId"]
        box = logic.get_boxscore(game_id)
    # Check home and away player lists
    for team_key in ("home", "away"):
        team = box.get(team_key, {})
        players = team.get("players", [])
        assert isinstance(players, list), f"{team_key} players should be a list"
        # For demo, may be empty, but if present, check fields
        if players:
            player = players[0]
            assert "firstName" in player or "familyName" in player or "name" in player, "Player should have a name field"
            stats = player.get("statistics", {})
            # Check for at least one stat field
            stat_fields = ["points", "assists", "rebounds", "minutes"]
            assert any(f in stats for f in stat_fields), "Player stats should include points, assists, rebounds, or minutes"


def test_fetch_player_profile_matches_roster_id(monkeypatch):
    logic = ScoreSourceLogic()
    roster_payload = {
        "athletes": [
            {
                "id": "6578",
                "displayName": "Harrison Barnes",
                "fullName": "Harrison Barnes",
                "displayHeight": "6' 7\"",
                "displayWeight": "225 lbs",
                "position": {"abbreviation": "F"},
                "jersey": "40",
                "headshot": {"href": "https://a.espncdn.com/i/headshots/nba/players/full/6578.png"},
            }
        ]
    }

    def fake_fetch_json(url: str):
        if "/teams/24/roster" in url:
            return roster_payload
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    profile = logic.fetch_player_profile("NBA", "24", player_id="6578", player_name="H. Barnes")

    assert profile["id"] == "6578"
    assert profile["displayName"] == "Harrison Barnes"
    assert profile["position"] == "F"
    assert profile["jersey"] == "40"


def test_fetch_player_profile_matches_initial_last_name(monkeypatch):
    logic = ScoreSourceLogic()
    roster_payload = {
        "athletes": [
            {
                "position": "Forwards",
                "items": [
                    {
                        "id": "6578",
                        "displayName": "Harrison Barnes",
                        "fullName": "Harrison Barnes",
                        "position": {"abbreviation": "F"},
                        "jersey": "40",
                    }
                ],
            }
        ]
    }

    def fake_fetch_json(url: str):
        if "/teams/24/roster" in url:
            return roster_payload
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    profile = logic.fetch_player_profile("NBA", "24", player_name="H. Barnes")

    assert profile["id"] == "6578"
    assert profile["displayName"] == "Harrison Barnes"


def test_fetch_player_profile_mlb_prefers_mlb_headshot_over_team_logo(monkeypatch):
    logic = ScoreSourceLogic()
    roster_payload = {
        "athletes": [
            {
                "id": "5136815",
                "displayName": "Zach Cole",
                "fullName": "Zach Cole",
                "position": {"abbreviation": "CF"},
                "jersey": "16",
            }
        ]
    }
    common_payload = {
        "athlete": {
            "id": "5136815",
            "displayName": "Zach Cole",
            "fullName": "Zach Cole",
            "jersey": "16",
            "position": {"abbreviation": "CF"},
            "team": {
                "logos": [
                    {"href": "https://a.espncdn.com/i/teamlogos/mlb/500/hou.png"},
                ]
            },
        }
    }

    def fake_fetch_json(url: str):
        if "/teams/18/roster" in url:
            return roster_payload
        if "/apis/common/v3/sports/baseball/mlb/athletes/5136815" in url:
            return common_payload
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    monkeypatch.setattr(
        logic,
        "_mlb_headshot_url",
        lambda name, tri: "https://img.mlbstatic.com/mlb-photos/image/upload/w_213,q_auto:best/v1/people/805904/headshot/67/current",
    )
    profile = logic.fetch_player_profile(
        "MLB",
        "18",
        player_id="5136815",
        player_name="Zach Cole",
        team_tricode="HOU",
    )

    assert profile["displayName"] == "Zach Cole"
    assert profile["headshotUrl"].startswith("https://img.mlbstatic.com/")


def test_fetch_player_profile_mlb_does_not_fallback_to_team_logo(monkeypatch):
    logic = ScoreSourceLogic()
    roster_payload = {
        "athletes": [
            {
                "id": "5136815",
                "displayName": "Zach Cole",
                "fullName": "Zach Cole",
                "position": {"abbreviation": "CF"},
                "jersey": "16",
            }
        ]
    }
    common_payload = {
        "athlete": {
            "id": "5136815",
            "displayName": "Zach Cole",
            "fullName": "Zach Cole",
            "jersey": "16",
            "position": {"abbreviation": "CF"},
            "team": {
                "logos": [
                    {"href": "https://a.espncdn.com/i/teamlogos/mlb/500/hou.png"},
                ]
            },
        }
    }

    def fake_fetch_json(url: str):
        if "/teams/18/roster" in url:
            return roster_payload
        if "/apis/common/v3/sports/baseball/mlb/athletes/5136815" in url:
            return common_payload
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    monkeypatch.setattr(logic, "_mlb_headshot_url", lambda name, tri: "")
    profile = logic.fetch_player_profile(
        "MLB",
        "18",
        player_id="5136815",
        player_name="Zach Cole",
        team_tricode="HOU",
    )

    assert profile["displayName"] == "Zach Cole"
    assert profile.get("headshotUrl") == ""


def test_fetch_player_profile_mlb_refetches_cached_team_logo_placeholder(monkeypatch):
    logic = ScoreSourceLogic()
    cache_key = ("MLB", "18", "HOU", "5136815", "zach cole", "")
    logic._player_profile_cache[cache_key] = (
        time.monotonic(),
        {
            "displayName": "Zach Cole",
            "headshotUrl": "https://a.espncdn.com/i/teamlogos/mlb/500/hou.png",
        },
    )
    calls: list[str] = []
    roster_payload = {
        "athletes": [
            {
                "id": "5136815",
                "displayName": "Zach Cole",
                "fullName": "Zach Cole",
                "position": {"abbreviation": "CF"},
                "jersey": "16",
            }
        ]
    }

    def fake_fetch_json(url: str):
        calls.append(url)
        if "/teams/18/roster" in url:
            return roster_payload
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    monkeypatch.setattr(
        logic,
        "_mlb_headshot_url",
        lambda name, tri: "https://img.mlbstatic.com/mlb-photos/image/upload/w_213,q_auto:best/v1/people/805904/headshot/67/current",
    )

    profile = logic.fetch_player_profile(
        "MLB",
        "18",
        player_id="5136815",
        player_name="Zach Cole",
        team_tricode="HOU",
    )

    assert profile["headshotUrl"].startswith("https://img.mlbstatic.com/")
    assert any("/teams/18/roster" in url for url in calls)


def test_fetch_player_profile_falls_back_to_core_athlete(monkeypatch):
    logic = ScoreSourceLogic()
    core_payload = {
        "id": "6578",
        "displayName": "Harrison Barnes",
        "fullName": "Harrison Barnes",
        "displayHeight": "6' 7\"",
        "displayWeight": "225 lbs",
        "jersey": "40",
        "position": {"abbreviation": "F"},
    }

    def fake_fetch_json(url: str):
        if "/athletes/6578" in url:
            return core_payload
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    profile = logic.fetch_player_profile("NBA", None, player_id="6578")

    assert profile["id"] == "6578"
    assert profile["displayName"] == "Harrison Barnes"
    assert profile["position"] == "F"


def test_fetch_player_profile_includes_career_stats_from_core_statistics(monkeypatch):
    logic = ScoreSourceLogic()
    roster_payload = {
        "athletes": [
            {
                "id": "6578",
                "displayName": "Harrison Barnes",
                "fullName": "Harrison Barnes",
                "position": {"abbreviation": "F"},
                "jersey": "40",
            }
        ]
    }
    core_stats_payload = {
        "splits": {
            "name": "All Splits",
            "abbreviation": "Total",
            "type": "total",
            "categories": [
                {
                    "name": "general",
                    "stats": [
                        {"name": "gamesPlayed", "abbreviation": "GP", "displayValue": "1053"},
                        {"name": "points", "abbreviation": "PTS", "displayValue": "14416"},
                        {"name": "rebounds", "abbreviation": "REB", "displayValue": "4913"},
                        {"name": "assists", "abbreviation": "AST", "displayValue": "1864"},
                        {"name": "fieldGoalPct", "abbreviation": "FG%", "displayValue": "45.9"},
                    ],
                }
            ],
        }
    }

    def fake_fetch_json(url: str):
        if "/teams/24/roster" in url:
            return roster_payload
        if "/athletes/6578/statistics" in url:
            return core_stats_payload
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    profile = logic.fetch_player_profile("NBA", "24", player_name="H. Barnes")

    career = profile.get("careerStats")
    assert isinstance(career, dict)
    assert career.get("GP") == "1053"
    assert career.get("PTS") == "14416"
    assert career.get("REB") == "4913"
    assert career.get("AST") == "1864"


def test_get_starting_lineup_mls_uses_roster_positions(monkeypatch):
    from scoresource.common import lineups

    roster_payload = {
        "athletes": [
            {"id": "1", "displayName": "Goalie One", "position": {"abbreviation": "G"}, "jersey": "1"},
            {"id": "2", "displayName": "Defender One", "position": {"abbreviation": "D"}, "jersey": "2"},
            {"id": "3", "displayName": "Defender Two", "position": {"abbreviation": "D"}, "jersey": "3"},
            {"id": "4", "displayName": "Defender Three", "position": {"abbreviation": "D"}, "jersey": "4"},
            {"id": "5", "displayName": "Defender Four", "position": {"abbreviation": "D"}, "jersey": "5"},
            {"id": "6", "displayName": "Midfielder One", "position": {"abbreviation": "M"}, "jersey": "6"},
            {"id": "7", "displayName": "Midfielder Two", "position": {"abbreviation": "M"}, "jersey": "7"},
            {"id": "8", "displayName": "Midfielder Three", "position": {"abbreviation": "M"}, "jersey": "8"},
            {"id": "9", "displayName": "Forward One", "position": {"abbreviation": "F"}, "jersey": "9"},
            {"id": "10", "displayName": "Forward Two", "position": {"abbreviation": "F"}, "jersey": "10"},
            {"id": "11", "displayName": "Forward Three", "position": {"abbreviation": "F"}, "jersey": "11"},
            {"id": "12", "displayName": "Bench One", "position": {"abbreviation": "M"}, "jersey": "12"},
        ]
    }

    def fake_fetch_json(url: str):
        if "/teams/7318/depthcharts" in url:
            return {"timestamp": "2026-03-12T15:45:45Z", "status": "success", "team": {"id": "7318"}}
        if "/teams/7318/roster" in url:
            return roster_payload
        return None

    monkeypatch.setattr(lineups, "_fetch_json", fake_fetch_json)
    monkeypatch.setattr(lineups, "_lineup_cache", {})
    lineup = lineups.get_starting_lineup("MLS", "7318", "TOR")

    assert len(lineup) == 11
    assert lineup[0]["position"] in {"G", "GK"}
    assert sum(1 for p in lineup if p.get("position") == "D") == 4
    assert sum(1 for p in lineup if p.get("position") == "M") == 3
    assert sum(1 for p in lineup if p.get("position") == "F") == 3


def test_roster_lineup_mls_supports_string_positions():
    from scoresource.common import lineups

    items = [
        {"id": "1", "displayName": "Goalie One", "position": "GK"},
        {"id": "2", "displayName": "Defender One", "position": "DF"},
        {"id": "3", "displayName": "Defender Two", "position": "DF"},
        {"id": "4", "displayName": "Defender Three", "position": "DF"},
        {"id": "5", "displayName": "Defender Four", "position": "DF"},
        {"id": "6", "displayName": "Midfielder One", "position": "MF"},
        {"id": "7", "displayName": "Midfielder Two", "position": "MF"},
        {"id": "8", "displayName": "Midfielder Three", "position": "MF"},
        {"id": "9", "displayName": "Forward One", "position": "FW"},
        {"id": "10", "displayName": "Forward Two", "position": "FW"},
        {"id": "11", "displayName": "Forward Three", "position": "FW"},
    ]
    lineup = lineups._roster_lineup_for_sport("MLS", items, [])  # type: ignore[attr-defined]

    assert len(lineup) == 11
    assert lineup[0]["position"] in {"GK", "G"}
    assert any(p.get("position") == "FW" for p in lineup)


def test_fetch_remote_bytes_uses_cache(monkeypatch):
    logic = ScoreSourceLogic()
    calls = {"count": 0}

    class DummyResponse:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return

    def fake_get(url: str, headers=None, timeout=None):
        calls["count"] += 1
        return DummyResponse(b"img")

    monkeypatch.setattr(logic._http_session, "get", fake_get)
    first = logic.fetch_remote_bytes("https://example.com/headshot.png")
    second = logic.fetch_remote_bytes("https://example.com/headshot.png")

    assert first == b"img"
    assert second == b"img"
    assert calls["count"] == 1


def test_fetch_player_profile_maps_nba_team_id_from_tricode(monkeypatch):
    logic = ScoreSourceLogic()
    calls = []
    teams_payload = {
        "sports": [
            {
                "leagues": [
                    {
                        "teams": [
                            {"team": {"id": "5", "abbreviation": "CLE"}},
                        ]
                    }
                ]
            }
        ]
    }
    roster_payload = {
        "athletes": [
            {
                "id": "12345",
                "displayName": "Sam Merrill",
                "fullName": "Sam Merrill",
                "position": {"abbreviation": "G"},
                "jersey": "5",
            }
        ]
    }

    def fake_fetch_json(url: str):
        calls.append(url)
        if url.endswith("/basketball/nba/teams"):
            return teams_payload
        if "/teams/5/roster" in url:
            return roster_payload
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    profile = logic.fetch_player_profile(
        "NBA",
        "1610612739",
        player_id="1630241",
        player_name="S. Merrill",
        team_tricode="CLE",
    )

    assert profile["displayName"] == "Sam Merrill"
    assert any("/teams/5/roster" in url for url in calls)


def test_fetch_player_profile_invalid_core_payload_returns_empty(monkeypatch):
    logic = ScoreSourceLogic()

    def fake_fetch_json(url: str):
        if "/athletes/1630241" in url:
            return {"code": 404}
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    profile = logic.fetch_player_profile("NBA", None, player_id="1630241")

    assert profile == {}


def test_fetch_player_profile_maps_nop_alias_from_espn_no(monkeypatch):
    logic = ScoreSourceLogic()
    teams_payload = {
        "sports": [
            {
                "leagues": [
                    {
                        "teams": [
                            {"team": {"id": "3", "abbreviation": "NO"}},
                        ]
                    }
                ]
            }
        ]
    }
    roster_payload = {
        "athletes": [
            {
                "id": "4267839",
                "displayName": "Zion Williamson",
                "fullName": "Zion Williamson",
                "position": {"abbreviation": "F"},
                "jersey": "1",
            }
        ]
    }

    def fake_fetch_json(url: str):
        if url.endswith("/basketball/nba/teams"):
            return teams_payload
        if "/teams/3/roster" in url:
            return roster_payload
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    profile = logic.fetch_player_profile(
        "NBA",
        "1610612740",
        player_id="1629627",
        player_name="Z. Williamson",
        team_tricode="NOP",
    )

    assert profile["displayName"] == "Zion Williamson"


def test_fetch_player_profile_matches_diacritic_initial_last_name(monkeypatch):
    logic = ScoreSourceLogic()
    roster_payload = {
        "athletes": [
            {
                "id": "3032979",
                "displayName": "Dennis Schroder",
                "fullName": "Dennis Schroder",
                "position": {"abbreviation": "G"},
                "jersey": "17",
            }
        ]
    }

    def fake_fetch_json(url: str):
        if "/teams/5/roster" in url:
            return roster_payload
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    profile = logic.fetch_player_profile("NBA", "5", player_name="D. Schröder")

    assert profile["displayName"] == "Dennis Schroder"


def test_fetch_player_profile_uses_jersey_to_disambiguate_same_initial_last_name(monkeypatch):
    logic = ScoreSourceLogic()
    roster_payload = {
        "athletes": [
            {
                "position": "Guards",
                "items": [
                    {
                        "id": "2326307",
                        "displayName": "Seth Curry",
                        "fullName": "Seth Curry",
                        "position": {"abbreviation": "G"},
                        "jersey": "31",
                    },
                    {
                        "id": "3975",
                        "displayName": "Stephen Curry",
                        "fullName": "Stephen Curry",
                        "position": {"abbreviation": "G"},
                        "jersey": "30",
                    },
                ],
            }
        ]
    }

    def fake_fetch_json(url: str):
        if "/teams/9/roster" in url:
            return roster_payload
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    profile = logic.fetch_player_profile(
        "NBA",
        "9",
        player_id="201939",
        player_name="S. Curry",
        player_jersey="30",
        team_tricode="GSW",
    )

    assert profile["id"] == "3975"
    assert profile["displayName"] == "Stephen Curry"
    assert profile["jersey"] == "30"


def test_fetch_player_profile_derives_missing_espn_headshot(monkeypatch):
    logic = ScoreSourceLogic()
    roster_payload = {
        "athletes": [
            {
                "id": "3975",
                "displayName": "Stephen Curry",
                "fullName": "Stephen Curry",
                "position": {"abbreviation": "G"},
                "jersey": "30",
            }
        ]
    }

    def fake_fetch_json(url: str):
        if "/teams/9/roster" in url:
            return roster_payload
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    monkeypatch.setattr(
        logic,
        "fetch_remote_bytes",
        lambda url: b"img" if str(url).endswith("/nba/players/full/3975.png") else None,
    )

    profile = logic.fetch_player_profile("NBA", "9", player_name="Stephen Curry")

    assert profile["displayName"] == "Stephen Curry"
    assert profile["headshotUrl"].endswith("/nba/players/full/3975.png")


def test_fetch_player_profile_maps_nfl_team_id_from_tricode_when_team_id_zero(monkeypatch):
    logic = ScoreSourceLogic()
    teams_payload = {
        "sports": [
            {
                "leagues": [
                    {
                        "teams": [
                            {"team": {"id": "17", "abbreviation": "NE"}},
                        ]
                    }
                ]
            }
        ]
    }
    roster_payload = {
        "athletes": [
            {
                "id": "4430807",
                "displayName": "Drake Maye",
                "fullName": "Drake Maye",
                "position": {"abbreviation": "QB"},
                "jersey": "10",
            }
        ]
    }

    def fake_fetch_json(url: str):
        if url.endswith("/football/nfl/teams"):
            return teams_payload
        if "/teams/17/roster" in url:
            return roster_payload
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    profile = logic.fetch_player_profile(
        "NFL",
        "0",
        player_name="Drake Maye",
        team_tricode="NE",
    )

    assert profile["id"] == "4430807"
    assert profile["displayName"] == "Drake Maye"
    assert profile["jersey"] == "10"


def test_fetch_player_profile_mls_does_not_fallback_to_team_logo(monkeypatch):
    logic = ScoreSourceLogic()
    teams_payload = {
        "sports": [
            {
                "leagues": [
                    {
                        "teams": [
                            {"team": {"id": "190", "abbreviation": "RBNY"}},
                        ]
                    }
                ]
            }
        ]
    }
    roster_payload = {
        "athletes": [
            {
                "id": "192027",
                "displayName": "Ethan Horvath",
                "fullName": "Ethan Horvath",
                "position": {"abbreviation": "GK"},
                "jersey": "34",
            }
        ]
    }
    common_payload = {
        "athlete": {
            "id": "192027",
            "displayName": "Ethan Horvath",
            "fullName": "Ethan Horvath",
            "team": {"logos": [{"href": "https://a.espncdn.com/i/teamlogos/soccer/500/190.png"}]},
        }
    }

    def fake_fetch_json(url: str):
        if url.endswith("/soccer/usa.1/teams"):
            return teams_payload
        if "/teams/190/roster" in url:
            return roster_payload
        if "/apis/common/v3/sports/soccer/usa.1/athletes/192027" in url:
            return common_payload
        return None

    logic._fetch_json = fake_fetch_json  # type: ignore[method-assign]
    monkeypatch.setattr(logic, "fetch_remote_bytes", lambda url: None)
    profile = logic.fetch_player_profile(
        "MLS",
        "0",
        player_id="192027",
        player_name="Ethan Horvath",
        team_tricode="RBNY",
    )

    assert profile["displayName"] == "Ethan Horvath"
    assert profile.get("headshotUrl") == ""


def test_get_starting_lineup_resolves_zero_team_id_by_tricode_and_preserves_ids(monkeypatch):
    from scoresource.common import lineups

    teams_payload = {
        "sports": [
            {
                "leagues": [
                    {
                        "teams": [
                            {"team": {"id": "26", "abbreviation": "SEA"}},
                            {"team": {"id": "17", "abbreviation": "NE"}},
                        ]
                    }
                ]
            }
        ]
    }
    sea_roster = {
        "athletes": [
            {
                "position": "Offense",
                "items": [
                    {"id": "1001", "displayName": "Sam Darnold", "position": {"abbreviation": "QB"}, "jersey": "14"},
                    {"id": "1002", "displayName": "Zach Charbonnet", "position": {"abbreviation": "RB"}, "jersey": "26"},
                    {"id": "1003", "displayName": "Jaxon Smith-Njigba", "position": {"abbreviation": "WR"}, "jersey": "11"},
                ],
            }
        ]
    }
    ne_roster = {
        "athletes": [
            {
                "position": "Offense",
                "items": [
                    {"id": "2001", "displayName": "Drake Maye", "position": {"abbreviation": "QB"}, "jersey": "10"},
                    {"id": "2002", "displayName": "Rhamondre Stevenson", "position": {"abbreviation": "RB"}, "jersey": "38"},
                    {"id": "2003", "displayName": "DeMario Douglas", "position": {"abbreviation": "WR"}, "jersey": "81"},
                ],
            }
        ]
    }

    def fake_fetch_json(url: str):
        if url.endswith("/football/nfl/teams"):
            return teams_payload
        if "/teams/26/roster" in url:
            return sea_roster
        if "/teams/17/roster" in url:
            return ne_roster
        return None

    monkeypatch.setattr(lineups, "_fetch_json", fake_fetch_json)
    monkeypatch.setattr(lineups, "_lineup_cache", {})
    monkeypatch.setattr(lineups, "_team_map_cache", {})

    sea_lineup = lineups.get_starting_lineup("NFL", "0", "SEA")
    ne_lineup = lineups.get_starting_lineup("NFL", "0", "NE")

    assert sea_lineup
    assert ne_lineup
    assert sea_lineup[0]["fullName"] == "Sam Darnold"
    assert ne_lineup[0]["fullName"] == "Drake Maye"
    assert sea_lineup[0]["id"] == "1001"
    assert ne_lineup[0]["id"] == "2001"


def test_get_starting_lineup_uses_nhl_alias_tricode(monkeypatch):
    from scoresource.common import lineups

    teams_payload = {
        "sports": [
            {
                "leagues": [
                    {
                        "teams": [
                            {"team": {"id": "8", "abbreviation": "LA"}},
                        ]
                    }
                ]
            }
        ]
    }
    la_roster = {
        "athletes": [
            {
                "items": [
                    {"id": "1", "displayName": "Anze Kopitar", "position": {"abbreviation": "C"}, "jersey": "11"},
                    {"id": "2", "displayName": "Kevin Fiala", "position": {"abbreviation": "LW"}, "jersey": "22"},
                    {"id": "3", "displayName": "Adrian Kempe", "position": {"abbreviation": "RW"}, "jersey": "9"},
                    {"id": "4", "displayName": "Mikey Anderson", "position": {"abbreviation": "D"}, "jersey": "44"},
                    {"id": "5", "displayName": "Drew Doughty", "position": {"abbreviation": "D"}, "jersey": "8"},
                    {"id": "6", "displayName": "Darcy Kuemper", "position": {"abbreviation": "G"}, "jersey": "35"},
                ]
            }
        ]
    }

    def fake_fetch_json(url: str):
        if url.endswith("/hockey/nhl/teams"):
            return teams_payload
        if "/teams/8/roster" in url:
            return la_roster
        return None

    monkeypatch.setattr(lineups, "_fetch_json", fake_fetch_json)
    monkeypatch.setattr(lineups, "_lineup_cache", {})
    monkeypatch.setattr(lineups, "_team_map_cache", {})

    lineup = lineups.get_starting_lineup("NHL", "0", "LAK")

    assert lineup
    assert lineup[0]["fullName"] == "Anze Kopitar"
    assert lineup[0]["id"] == "1"


def test_mlb_player_rows_use_uniform_number_not_lineup_slot():
    from scoresource import mlb

    team = {
        "players": [
            {
                "firstName": "Test",
                "familyName": "Hitter",
                "position": "CF",
                "order": 3,
                "statistics": {
                    "group": "batting",
                    "avg": 0.321,
                    "homeRuns": 2,
                    "rbi": 5,
                    "obp": 0.400,
                    "slg": 0.550,
                },
            }
        ]
    }
    rows = mlb.build_player_rows(team)
    assert rows
    assert rows[0][0] == ""

    team_with_jersey = {
        "players": [
            {
                "firstName": "Test",
                "familyName": "Hitter",
                "position": "CF",
                "jerseyNum": "27",
                "order": 3,
                "statistics": {"group": "batting", "avg": 0.250, "homeRuns": 1, "rbi": 1},
            }
        ]
    }
    rows_with_jersey = mlb.build_player_rows(team_with_jersey)
    assert rows_with_jersey
    assert rows_with_jersey[0][0] == "27"


def test_mlb_apply_roster_numbers_fills_missing_jersey_from_roster():
    from scoresource import mlb

    team = {
        "teamId": "30",
        "players": [
            {
                "id": "4679983",
                "fullName": "Chandler Simpson",
                "jerseyNum": "",
                "statistics": {"group": "batting"},
            }
        ],
        "startingLineup": [
            {"fullName": "Chandler Simpson", "jersey": ""},
        ],
    }

    def fake_maps(team_id: str):
        assert team_id == "30"
        return ({"4679983": "14"}, {"chandlersimpson": "14"})

    original = mlb._team_roster_number_maps  # type: ignore[attr-defined]
    mlb._team_roster_number_maps = fake_maps  # type: ignore[attr-defined]
    try:
        mlb._apply_roster_numbers(team)  # type: ignore[attr-defined]
    finally:
        mlb._team_roster_number_maps = original  # type: ignore[attr-defined]

    assert team["players"][0]["jerseyNum"] == "14"
    assert team["startingLineup"][0]["jersey"] == "14"


def test_mlb_apply_roster_numbers_falls_back_to_core_athlete():
    from scoresource import mlb

    team = {
        "teamId": "30",
        "players": [
            {
                "id": "5120296",
                "fullName": "Blake Sabol",
                "jerseyNum": "",
                "statistics": {"group": "batting"},
            }
        ],
    }

    def fake_maps(team_id: str):
        assert team_id == "30"
        return ({}, {})

    def fake_core(player_id: str):
        assert player_id == "5120296"
        return "74"

    original_maps = mlb._team_roster_number_maps  # type: ignore[attr-defined]
    original_core = mlb._core_athlete_number  # type: ignore[attr-defined]
    mlb._team_roster_number_maps = fake_maps  # type: ignore[attr-defined]
    mlb._core_athlete_number = fake_core  # type: ignore[attr-defined]
    try:
        mlb._apply_roster_numbers(team)  # type: ignore[attr-defined]
    finally:
        mlb._team_roster_number_maps = original_maps  # type: ignore[attr-defined]
        mlb._core_athlete_number = original_core  # type: ignore[attr-defined]

    assert team["players"][0]["jerseyNum"] == "74"
