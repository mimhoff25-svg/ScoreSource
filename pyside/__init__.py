"""Legacy compatibility package for old PySide entrypoints.

The active ScoreSource application lives under ``scoresource``. Modules in this
package are thin shims kept so older imports do not immediately break.
"""

__all__ = ["app", "logic", "nba", "realtime", "team_panel", "ui"]
