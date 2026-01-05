# ScoreSource

Multi-sport PySide6 scoreboard with live/scheduled coverage for NBA, NFL, NHL, MLS, MLB, and NCAA Football.

## Run

```bash
pip install -r requirements.txt
python -m scoresource.main
```

## Features
- Unified game model across sports (live + scheduled fallback)
- Pre-game mode always shows upcoming matchups
- Tabbed UI, game list, center panel with team cards
- Pluggable sport fetchers and realtime scaffold
