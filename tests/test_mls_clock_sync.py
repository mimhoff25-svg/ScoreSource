import time

from scoresource.realtime import REALTIME_POLL_INTERVAL, RealTimeGameState, RealTimePollingClient
from scoresource.ui import ScoreSourceWindow


def test_mls_clock_state_holds_running_between_live_polls():
    window = ScoreSourceWindow.__new__(ScoreSourceWindow)
    window._clock_state = None
    window.sport_name = "MLS"
    window.clock_buffer_sec = 0.0
    window.clock_feed_stale_sec = 15.0
    window.clock_feed_interval_avg = 3.0

    _, _, state = ScoreSourceWindow._compute_clock_state(
        window,
        "2H",
        3720.0,
        "--",
        "62'",
        force_live=True,
        buffer_sec=0.0,
        stale_window_sec=8.0,
    )
    assert state["running"] is True
    assert state["count_up"] is True

    # Simulate a gap larger than the old 4s cap but smaller than the new MLS window.
    state["last_feed_ts"] -= 5.1
    state["last_ts"] -= 5.1
    window._clock_state = state

    _, _, next_state = ScoreSourceWindow._compute_clock_state(
        window,
        "2H",
        3720.0,
        "--",
        "62'",
        force_live=True,
        buffer_sec=0.0,
        stale_window_sec=8.0,
    )

    assert next_state["running"] is True
    assert next_state["count_up"] is True


def test_mls_clock_state_stays_running_during_long_stale_feed_gap():
    window = ScoreSourceWindow.__new__(ScoreSourceWindow)
    window._clock_state = None
    window.sport_name = "MLS"
    window.clock_buffer_sec = 0.0
    window.clock_feed_stale_sec = 15.0
    window.clock_feed_interval_avg = 3.0

    _, _, state = ScoreSourceWindow._compute_clock_state(
        window,
        "2H",
        5220.0,
        "--",
        "87'",
        force_live=True,
        buffer_sec=0.0,
        stale_window_sec=8.0,
    )
    assert state["running"] is True

    # ESPN can leave MLS raw clock values unchanged for well over the old holdover
    # window while the match is still active.
    state["last_feed_ts"] -= 18.0
    state["last_ts"] -= 18.0
    window._clock_state = state

    _, _, next_state = ScoreSourceWindow._compute_clock_state(
        window,
        "2H",
        5220.0,
        "--",
        "87'",
        force_live=True,
        buffer_sec=0.0,
        stale_window_sec=8.0,
    )

    assert next_state["running"] is True
    assert next_state["count_up"] is True


def test_nhl_clock_state_holds_running_between_live_polls():
    window = ScoreSourceWindow.__new__(ScoreSourceWindow)
    window._clock_state = None
    window.sport_name = "NHL"
    window.clock_buffer_sec = 0.0
    window.clock_feed_stale_sec = 15.0
    window.clock_feed_interval_avg = 3.0

    _, _, state = ScoreSourceWindow._compute_clock_state(
        window,
        "P 2",
        122.0,
        "--",
        "2:02",
        force_live=True,
        buffer_sec=0.0,
        stale_window_sec=3.0,
    )
    assert state["running"] is True
    assert state["count_up"] is False

    state["last_feed_ts"] -= 2.1
    state["last_ts"] -= 2.1
    window._clock_state = state

    _, _, next_state = ScoreSourceWindow._compute_clock_state(
        window,
        "P 2",
        122.0,
        "--",
        "2:02",
        force_live=True,
        buffer_sec=0.0,
        stale_window_sec=3.0,
    )

    assert next_state["running"] is True
    assert next_state["count_up"] is False


class _DummyLabel:
    def __init__(self, text: str = "") -> None:
        self._text = text

    def text(self) -> str:
        return self._text

    def setText(self, value: str) -> None:
        self._text = value


class _DummyCenterPanel:
    def __init__(self) -> None:
        self.bottom_left = _DummyLabel("")
        self.bottom_center = _DummyLabel("")
        self.bottom_right = _DummyLabel("")

    def set_state(
        self,
        period_text: str,
        clock_text: str,
        bottom_left: str = "",
        bottom_right: str = "",
        bottom_center: str = "",
    ) -> None:
        self.bottom_left.setText(bottom_left)
        self.bottom_center.setText(bottom_center)
        self.bottom_right.setText(bottom_right)


def test_nhl_penalty_clock_ticks_when_display_clock_is_synthetic_live():
    window = ScoreSourceWindow.__new__(ScoreSourceWindow)
    window.sport_name = "NHL"
    window.center_panel = _DummyCenterPanel()
    window._clock_state = {
        "period": "P 2",
        "clock_secs": 122.0,
        "shot_secs": None,
        "raw_secs": 122.0,
        "running": True,
        "raw_running": False,
        "last_ts": 100.0,
        "last_feed_ts": 100.0,
        "feed_interval_avg": 3.0,
        "source": "boxscore",
        "count_up": False,
    }
    window._penalty_state = {
        "last_ts": 100.0,
        "left": [61.0],
        "right": [],
    }
    window.away_penalty_clock = _DummyLabel("")
    window.home_penalty_clock = _DummyLabel("")

    original_monotonic = time.monotonic
    try:
        time.monotonic = lambda: 101.0  # type: ignore[assignment]
        ScoreSourceWindow._tick_clock(window)
    finally:
        time.monotonic = original_monotonic  # type: ignore[assignment]

    assert window.away_penalty_clock.text() == "PEN 1:00"


def test_nba_realtime_clock_stops_after_synthetic_window_expires():
    window = ScoreSourceWindow.__new__(ScoreSourceWindow)
    window.sport_name = "NBA"
    window.center_panel = _DummyCenterPanel()
    window._clock_state = {
        "period": "1ST",
        "clock_secs": 246.0,
        "shot_secs": None,
        "raw_secs": 252.0,
        "running": True,
        "raw_running": False,
        "last_ts": 100.0,
        "last_feed_ts": 100.0,
        "feed_interval_avg": 0.5,
        "source": "realtime",
        "count_up": False,
        "synthetic_window_sec": 2.0,
    }
    window._penalty_state = None

    original_monotonic = time.monotonic
    try:
        time.monotonic = lambda: 106.0  # type: ignore[assignment]
        ScoreSourceWindow._tick_clock(window)
    finally:
        time.monotonic = original_monotonic  # type: ignore[assignment]

    assert window._clock_state["running"] is False
    assert window._clock_state["clock_secs"] == 246.0


def test_nba_clock_snaps_back_to_official_stop_after_local_drift():
    window = ScoreSourceWindow.__new__(ScoreSourceWindow)
    window.sport_name = "NBA"
    window.clock_buffer_sec = 0.0
    window.clock_feed_stale_sec = 2.0
    window.clock_feed_interval_avg = None
    window._clock_state = {
        "period": "1ST",
        "clock_secs": 246.0,
        "shot_secs": None,
        "raw_secs": 252.0,
        "running": False,
        "raw_running": False,
        "last_ts": 100.0,
        "last_feed_ts": 100.0,
        "feed_interval_avg": 0.5,
        "source": "realtime",
        "count_up": False,
        "synthetic_window_sec": 2.0,
    }

    original_monotonic = time.monotonic
    try:
        time.monotonic = lambda: 106.0  # type: ignore[assignment]
        _, _, state = ScoreSourceWindow._compute_clock_state(
            window,
            "1ST",
            252.0,
            None,
            "4:12",
            force_live=True,
            buffer_sec=0.0,
            stale_window_sec=2.0,
            source="realtime",
        )
    finally:
        time.monotonic = original_monotonic  # type: ignore[assignment]

    assert state["running"] is False
    assert state["raw_running"] is False
    assert state["clock_secs"] == 252.0


def test_nba_realtime_client_emits_heartbeat_for_unchanged_state():
    client = RealTimePollingClient("0022500973", lambda state: None)
    stable_state = RealTimeGameState(
        game_id="0022500973",
        period=1,
        game_clock_raw="PT04M12.00S",
        game_clock_text="4:12",
        shot_clock=None,
        home_score=10,
        away_score=8,
        possession_team_id=None,
    )
    client._last_state = stable_state
    client._last_emit_ts = 100.0

    original_monotonic = time.monotonic
    try:
        time.monotonic = lambda: 100.0 + REALTIME_POLL_INTERVAL + 0.01  # type: ignore[assignment]
        assert client._should_emit_state(stable_state) is True
    finally:
        time.monotonic = original_monotonic  # type: ignore[assignment]
