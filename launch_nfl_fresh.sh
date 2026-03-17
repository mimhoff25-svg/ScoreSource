#!/bin/bash
# Launch ScoreSource with fresh NFL data (clears cache)

echo "Clearing NFL cache..."
rm -f ~/.cache/scoresource/nfl_scoreboard.json

echo "Launching ScoreSource..."
cd "$(dirname "$0")"
./launch_scoresource.sh
