## ScoreSource

Fixed-resolution (1280x400) PySide6 LED scoreboard for multi-sport coverage (NBA, NFL, NHL, MLS, MLB, NCAA Football) with live and scheduled views.

### Features
- LED-first layout: 1280x400 canvas with tabbed UI, game list, and team cards optimized for readability at distance
- Unified game model across sports with pre-game mode and live fallback
- Pluggable sport fetchers and realtime scaffold (polling today; WebSocket-ready later)
- Shared time formatting across leagues; boxscore scroll for dense stats

### Prerequisites
- Python 3.10 or 3.11
- pip and virtualenv (recommended)
- LED target: 1280x400 panel (desktop works for development)

### Quickstart
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m scoresource.main
```

### Environment
- `SCORESOURCE_REALTIME_ENABLED` (default: on) — disable to force scheduled-only mode
- `SCORESOURCE_REALTIME_POLL_INTERVAL` (seconds) — poll cadence for live games
- `SCORESOURCE_REALTIME_TIMEOUT` (seconds) — HTTP timeout for live calls

### Testing
```bash
python -m pip install -r requirements.txt
pytest
```

### Repo Map
- `scoresource/` — core app, sport backends, UI, common utilities
- `pyside/` — legacy PySide UI pieces
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
