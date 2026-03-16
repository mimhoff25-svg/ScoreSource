"""Normalized per-sport backend modules for ScoreSource.

This package intentionally stays lightweight. The active application path
loads sport metadata from ``scoresource.registry`` and imports individual
backend modules directly, e.g. ``scoresource.sports.nba``.
"""

__all__ = [
    "mlb",
    "mls",
    "nba",
    "ncaa_basketball",
    "ncaa_football",
    "nfl",
    "nhl",
    "template_sport",
]
