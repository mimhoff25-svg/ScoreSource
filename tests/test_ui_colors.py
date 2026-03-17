from scoresource.ui import ScoreSourceWindow


def _window_for_sport(sport_name: str) -> ScoreSourceWindow:
    window = ScoreSourceWindow.__new__(ScoreSourceWindow)
    window.sport_name = sport_name
    return window


def test_theme_resolver_breaks_dark_blue_on_blue_panels():
    window = _window_for_sport("MLB")
    primary = "#002B5C"
    secondary = "#001b3b"

    before = window._color_contrast_ratio(primary, secondary)
    resolved_primary, resolved_secondary, _ = window._resolve_team_theme_colors("MIN", primary, secondary, primary)
    after = window._color_contrast_ratio(resolved_primary, resolved_secondary)

    assert resolved_secondary != secondary
    assert after > before
    assert after >= 1.6


def test_theme_resolver_keeps_dallas_stars_victory_green_override():
    window = _window_for_sport("NHL")

    resolved_primary, resolved_secondary, _ = window._resolve_team_theme_colors(
        "DAL",
        "#006847",
        "#0d2e21",
        "#0a7a55",
    )

    assert resolved_primary == "#006847"
    assert resolved_secondary == "#0a7a55"
