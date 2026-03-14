# ScoreSource Overview

LED-focused scoreboard (1280x400) with multi-sport coverage. This doc summarizes architecture, realtime behavior, player-card data flow, and known gaps.

## Architecture (high level)
- UI: PySide6 layout optimized for 1280x400, tabs, game list, center scoreboard with team cards and boxscore scroll.
- Sports backends: `scoresource/sports/` per-league modules wrap ESPN-style APIs; unified game model feeds UI.
- Common utilities: `scoresource/common/` for time formatting, logging, colors, lineups, and helpers.
- Core runtime: `scoresource/logic.py` orchestrates fetches, normalization, and fallbacks; `scoresource/realtime.py` houses live hooks.
- Legacy UI: `pyside/` contains earlier PySide layers (kept for compatibility).

## Player cards
- Shared card shell lives in `scoresource/ui.py` and now uses the same condensed layout across sports.
- Hero row is split into three anchors: player headshot on one side, condensed identity/meta text in the middle, and team logo on the opposite side.
- Card body is denser by design: `Profile` and `Game Stats` render side by side, while `Career Stats` spans below as compact chips.
- The old `Profile loaded from API` status text was removed to keep the card visually quiet.

## Player-card data flow
- Lineup rows now preserve athlete ids when they are available from roster or depth chart payloads.
- `scoresource/common/lineups.py` resolves team ids from tricodes when ESPN feeds return placeholders such as `0`, `AWY`, or `HOM`.
- `scoresource/logic.py` uses sport-aware team alias maps plus jersey-aware player matching to reduce bad profile matches.
- Full names are preferred over abbreviated lineup labels when the card requests profile data, which avoids ambiguous matches like `S. Curry`.
- Headshot fetching prefers real player images. When no valid player photo exists, the UI falls back to player initials instead of showing a team logo in the headshot slot.

## Cross-sport profile behavior
- NBA and NHL alias tricodes are normalized before roster lookup.
- MLS and NFL profile fetches can recover from missing or zero team ids by resolving the ESPN team map first.
- MLB still prefers MLB-specific person headshots when available, then falls back to ESPN-derived player images.
- Career stat extraction is normalized into compact card-friendly fields per sport.

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
- Some ESPN player records still have no usable headshot asset; those cards intentionally show initials until a better secondary image source is added.

## Development notes
- Keep constants (resolution, timing, caching) centralized; avoid magic numbers.
- Use the shared logger from `scoresource/common/logging.py`; avoid silent exceptions.
- Prefer typed function signatures for new/modified code.
- When changing card fetch logic, update `tests/test_logic.py` with the relevant roster/profile fallback case before widening the cache surface.

## References
- Improvement log: [../Change log_IMPROVEMENTS_NEEDED.md](../Change%20log_IMPROVEMENTS_NEEDED.md)
- Release history: [../CHANGELOG.md](../CHANGELOG.md)
