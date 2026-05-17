## ScoreSource

Fixed-resolution (1280x400) PySide6 LED scoreboard for multi-sport coverage (NBA, NCAA Basketball, NFL, NCAA Football, NHL, MLS, MLB) with live and scheduled views.

### Features
- LED-first layout: 1280x400 canvas with tabbed UI, game list, and team cards optimized for readability at distance
- Unified game model across sports with pre-game mode and live fallback
- Pluggable sport fetchers and realtime scaffold (polling today; WebSocket-ready later)
- Shared time formatting across leagues; boxscore scroll for dense stats
- Condensed cross-sport player cards with larger headshots, opposite-side team logos, compact info chips, and career stats
- Roster/profile matching that carries athlete ids from lineup rows and uses jersey-aware disambiguation for duplicate names
- Safer media fallback path: real player headshots first, initials when a player photo is unavailable, never a team logo in the headshot slot

### Prerequisites
- Python 3.10 or 3.11
- pip and virtualenv (recommended)
- LED target: 1280x400 panel (desktop works for development)
- Windows 10 support currently targets source-based launches (`python -m scoresource.main` or `launch_scoresource.bat`), not a packaged `.exe`

### Quickstart
Linux/macOS:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m scoresource.main
```

Windows 10 (PowerShell):
```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m scoresource.main
```

Convenience launchers:
```bash
python launcher.py
```

- Linux: `./launch_scoresource.sh`
- Windows: `launch_scoresource.bat`

### Environment
- `SCORESOURCE_REALTIME_ENABLED` (default: on) — disable to force scheduled-only mode
- `SCORESOURCE_REALTIME_POLL_INTERVAL` (seconds) — poll cadence for live games
- `SCORESOURCE_REALTIME_TIMEOUT` (seconds) — HTTP timeout for live calls

### Testing
```bash
python -m pip install -r requirements.txt
python -m pip install pytest
QT_QPA_PLATFORM=offscreen python -m pytest
```

On Windows PowerShell, use:
```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest
```

Targeted regression coverage for the recent card/profile work lives in `tests/test_logic.py`.

### Recent Updates
- Player cards were rebuilt to use a denser layout across all sports: larger player photo, shorter meta line, side-by-side profile and game stats, and career stats below.
- The card no longer shows a `Profile loaded from API` status line.
- Team logos now render on the opposite side of the player photo instead of being reused as a player-photo fallback.
- Lineup and profile fetches now preserve athlete ids and resolve ESPN team ids from tricodes when feeds return placeholders such as `0`, `AWY`, or `HOM`.
- NBA player-card matching now uses jersey numbers to disambiguate same-initial/same-last-name cases such as the Curry brothers.

### Repo Map
- `scoresource/` — core app, sport backends, UI, common utilities
- `pyside/` — legacy compatibility shims for older PySide entrypoints
- `tests/` — smoke tests for backends/logic
- `Change log_IMPROVEMENTS_NEEDED.md` — working log of fixes and gaps
- `CHANGELOG.md` — release history

### Roadmap (short list)
- Cache cleanup (TTL caches for logos/boxscores)
- Async/polling consistency across sports
- UI loading states and clearer error surfacing
- Broader test coverage with mocks/fixtures
- Realtime generalization beyond NBA

### Docs & Support
- Architecture and realtime notes: [docs/overview.md](docs/overview.md)
- Active improvement log: [Change log_IMPROVEMENTS_NEEDED.md](Change%20log_IMPROVEMENTS_NEEDED.md)
- Release history: [CHANGELOG.md](CHANGELOG.md)

### License
This project is licensed under the MIT License. See [LICENSE](LICENSE).
