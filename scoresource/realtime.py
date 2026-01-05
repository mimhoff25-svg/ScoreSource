"""
Real-time game state updates using polling-based approach.

This implementation uses rapid polling of NBA's live data endpoints instead of WebSockets,
which is more reliable and doesn't require access to private WebSocket endpoints.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import requests

# Polling interval for live games (in seconds)
REALTIME_POLL_INTERVAL = float(os.environ.get("SCORESOURCE_REALTIME_POLL_INTERVAL", "2.0"))
REALTIME_TIMEOUT = float(os.environ.get("SCORESOURCE_REALTIME_TIMEOUT", "3.0"))


@dataclass
class RealTimeGameState:
    """Real-time game state data structure."""
    game_id: str
    period: int | None
    game_clock_raw: Any
    game_clock_text: str | None
    shot_clock: Any
    home_score: int | None
    away_score: int | None
    possession_team_id: str | None


class RealTimePollingClient:
    """
    Polling-based real-time client for NBA games.
    
    Fetches live game data from NBA's CDN endpoints at regular intervals
    and notifies the callback when updates are detected.
    """

    def __init__(self, game_id: str, on_update: Callable[[RealTimeGameState], None]):
        self.game_id = game_id
        self.on_update = on_update
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.nba.com/",
        })
        self._last_state: Optional[RealTimeGameState] = None

    def start(self):
        """Start the polling thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the polling thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _poll_loop(self):
        """Main polling loop that runs in a separate thread."""
        while not self._stop_event.is_set():
            try:
                state = self._fetch_live_state()
                if state and self._has_changed(state):
                    self._last_state = state
                    try:
                        self.on_update(state)
                    except Exception:
                        pass  # Don't let callback errors stop polling
            except Exception:
                pass  # Continue polling even if fetch fails
            
            # Wait for next poll interval
            self._stop_event.wait(REALTIME_POLL_INTERVAL)

    def _fetch_live_state(self) -> Optional[RealTimeGameState]:
        """
        Fetch current game state from NBA's live data endpoint.
        
        Uses the same endpoint as the main boxscore fetch but with
        a shorter timeout for real-time responsiveness.
        """
        url = f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{self.game_id}.json"
        
        try:
            response = self._session.get(url, timeout=REALTIME_TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except Exception:
            return None

        game = data.get("game", {})
        if not isinstance(game, dict):
            return None

        # Extract game state
        period_data = game.get("period")
        if isinstance(period_data, dict):
            period = period_data.get("current")
        elif isinstance(period_data, int):
            period = period_data
        else:
            period = None

        game_clock = game.get("gameClock")
        shot_clock = game.get("shotClock")
        
        # Extract scores
        home_team = game.get("homeTeam", {})
        away_team = game.get("awayTeam", {})
        
        home_score = self._safe_int(home_team.get("score"))
        away_score = self._safe_int(away_team.get("score"))

        # Try to determine possession (not always available)
        possession_team_id = None
        # Some endpoints include possession data
        if "possession" in game:
            possession_team_id = str(game.get("possession", {}).get("teamId") or "")

        return RealTimeGameState(
            game_id=self.game_id,
            period=period,
            game_clock_raw=game_clock,
            game_clock_text=self._format_clock(game_clock),
            shot_clock=shot_clock,
            home_score=home_score,
            away_score=away_score,
            possession_team_id=possession_team_id,
        )

    def _has_changed(self, new_state: RealTimeGameState) -> bool:
        """Check if the new state is different from the last state."""
        if self._last_state is None:
            return True
        
        # Compare key fields that indicate a change
        return (
            new_state.period != self._last_state.period
            or new_state.game_clock_raw != self._last_state.game_clock_raw
            or new_state.shot_clock != self._last_state.shot_clock
            or new_state.home_score != self._last_state.home_score
            or new_state.away_score != self._last_state.away_score
        )

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        """Safely convert a value to int."""
        if value is None or value == "":
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _format_clock(clock_raw: Any) -> str | None:
        """Format clock value to string."""
        if not clock_raw:
            return None
        
        if isinstance(clock_raw, str):
            return clock_raw
        
        if isinstance(clock_raw, (int, float)):
            minutes = int(clock_raw // 60)
            seconds = int(clock_raw % 60)
            return f"{minutes}:{seconds:02d}"
        
        return str(clock_raw)


class RealTimeNullClient:
    """Null client for sports without real-time support."""

    def __init__(self):
        self._stopped = False

    def start(self):
        """No-op start."""
        pass

    def stop(self):
        """No-op stop."""
        self._stopped = True


def start_client(
    game_id: str,
    on_update: Callable[[RealTimeGameState], None],
    sport: str | None = "NBA"
) -> RealTimePollingClient | RealTimeNullClient:
    """
    Start a real-time client for the specified game.
    
    Args:
        game_id: The game ID to monitor
        on_update: Callback function to receive state updates
        sport: Sport type (currently only NBA is supported)
        
    Returns:
        A real-time client instance (polling or null)
    """
    sport_upper = (sport or "NBA").upper()
    
    if sport_upper == "NBA":
        client = RealTimePollingClient(game_id, on_update)
        client.start()
        return client
    
    # Other sports: return null client
    return RealTimeNullClient()
