#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from collections import Counter
from typing import Any, Dict, Tuple

import requests


SCOREBOARD_URL = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
BOXSCORE_URL = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
PBP_URL = "https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"


def _period_value(period: Any) -> Any:
    if isinstance(period, dict):
        return period.get("current")
    return period


def _choose_game(games: list[Dict[str, Any]], game_id: str | None) -> Dict[str, Any] | None:
    if not games:
        return None
    if game_id:
        for game in games:
            if str(game.get("gameId") or "") == str(game_id):
                return game
        return None
    for game in games:
        if game.get("gameStatus") == 2:
            return game
    return games[0]


def _fetch_json(session: requests.Session, url: str, timeout: float) -> Dict[str, Any]:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        return {}
    return data


def _fetch_scoreboard_game(
    session: requests.Session, game_id: str | None, timeout: float
) -> Tuple[str | None, Dict[str, Any], int]:
    board = _fetch_json(session, SCOREBOARD_URL, timeout)
    games = ((board.get("scoreboard") or {}).get("games") or []) if isinstance(board, dict) else []
    if not isinstance(games, list):
        games = []
    selected = _choose_game(games, game_id)
    if not isinstance(selected, dict):
        return None, {}, len(games)
    resolved_id = str(selected.get("gameId") or "")
    return (resolved_id or None), selected, len(games)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe NBA API field-change cadence for one game.")
    parser.add_argument("--game-id", default="", help="NBA gameId (default: auto-pick live game, else first game)")
    parser.add_argument("--samples", type=int, default=12, help="number of samples to collect")
    parser.add_argument("--interval-sec", type=float, default=2.0, help="seconds between samples")
    parser.add_argument("--timeout-sec", type=float, default=6.0, help="HTTP timeout in seconds")
    args = parser.parse_args()

    samples = max(1, int(args.samples))
    interval_sec = max(0.2, float(args.interval_sec))
    timeout_sec = max(1.0, float(args.timeout_sec))
    requested_game_id = (args.game_id or "").strip() or None

    session = requests.Session()
    changes = Counter()
    prev: Dict[str, Any] = {}

    print("sampling_start")
    for i in range(samples):
        t0 = time.time()
        row: Dict[str, Any] = {"i": i, "ts": round(t0, 1)}

        try:
            resolved_game_id, sb_game, game_count = _fetch_scoreboard_game(session, requested_game_id, timeout_sec)
            row["board_games"] = game_count
            row["gameId"] = resolved_game_id
        except Exception as exc:
            row["error"] = f"scoreboard: {exc}"
            print(row)
            break

        if not resolved_game_id:
            row["error"] = "no games found on scoreboard"
            print(row)
            break

        try:
            box = (_fetch_json(session, BOXSCORE_URL.format(game_id=resolved_game_id), timeout_sec).get("game") or {})
            if not isinstance(box, dict):
                box = {}
        except Exception:
            box = {}

        try:
            pbp_actions = (
                (_fetch_json(session, PBP_URL.format(game_id=resolved_game_id), timeout_sec).get("game") or {}).get("actions")
                or []
            )
            if not isinstance(pbp_actions, list):
                pbp_actions = []
        except Exception:
            pbp_actions = []

        last_action = pbp_actions[-1] if pbp_actions else {}
        if not isinstance(last_action, dict):
            last_action = {}

        row.update(
            {
                "sb_status": sb_game.get("gameStatus"),
                "sb_clock": sb_game.get("gameClock"),
                "sb_status_text": sb_game.get("gameStatusText"),
                "box_status": box.get("gameStatus"),
                "box_clock": box.get("gameClock"),
                "box_status_text": box.get("gameStatusText"),
                "box_shot": box.get("shotClock"),
                "box_period": _period_value(box.get("period")),
                "home_score": (box.get("homeTeam") or {}).get("score"),
                "away_score": (box.get("awayTeam") or {}).get("score"),
                "pbp_count": len(pbp_actions),
                "pbp_last_clock": last_action.get("clock"),
                "pbp_last_type": last_action.get("actionType"),
                "pbp_last_shot": last_action.get("shotClock"),
            }
        )

        for key, value in row.items():
            if key in {"i", "ts"}:
                continue
            if key in prev and prev[key] != value:
                changes[key] += 1
            prev[key] = value

        print(row)
        elapsed = time.time() - t0
        time.sleep(max(0.0, interval_sec - elapsed))

    print(f"change_counts {dict(changes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
