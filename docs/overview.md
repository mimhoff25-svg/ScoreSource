# ScoreSource Overview

LED-focused scoreboard (1280x400) with multi-sport coverage. This doc summarizes architecture, realtime behavior, and known gaps.

## Architecture (high level)
- UI: PySide6 layout optimized for 1280x400, tabs, game list, center scoreboard with team cards and boxscore scroll.
- Sports backends: `scoresource/sports/` per-league modules wrap ESPN-style APIs; unified game model feeds UI.
- Common utilities: `scoresource/common/` for time formatting, logging, colors, lineups, and helpers.
- Core runtime: `scoresource/logic.py` orchestrates fetches, normalization, and fallbacks; `scoresource/realtime.py` houses live hooks.
- Legacy UI: `pyside/` contains earlier PySide layers (kept for compatibility).

## Realtime status
- Current state: polling-based realtime for NBA only; other sports return null/placeholder clients.
- Env flags: `SCORESOURCE_REALTIME_ENABLED`, `SCORESOURCE_REALTIME_POLL_INTERVAL`, `SCORESOURCE_REALTIME_TIMEOUT`.
- Planned: backoff/jitter on failures, generalized realtime across sports, clearer UI error/loader states.

## Known gaps (see also Change log_IMPROVEMENTS_NEEDED.md)
- Caching: manual dict caches without TTL; migrate to `cachetools.TTLCache` (see TODO_LOADING_IMPROVEMENTS.md).
- Error handling: some silent failures remain; unify logging and retries across backends.
- UI threading: ensure network calls avoid blocking the UI thread; standardize ThreadPool/async usage.
- Tests: limited coverage; add fixtures/mocks for API calls and edge cases.
- Architecture: large modules (e.g., nfl.py) need splitting and shared base classes.

## Development notes
- Keep constants (resolution, timing, caching) centralized; avoid magic numbers.
- Use the shared logger from `scoresource/common/logging.py`; avoid silent exceptions.
- Prefer typed function signatures for new/modified code.

## References
- Improvement log: [../Change log_IMPROVEMENTS_NEEDED.md](../Change%20log_IMPROVEMENTS_NEEDED.md)
- Release history: [../CHANGELOG.md](../CHANGELOG.md)
