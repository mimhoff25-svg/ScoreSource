"""Utility helpers for ScoreSource."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import requests
import logging

from .paths import cache_dir

CACHE_DIR = cache_dir()
CACHE_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


def http_get_json(url: str, timeout: float = 5.0) -> Dict[str, Any] | None:
    """Perform a GET and return parsed JSON or None on failure."""
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001 - we want to catch network/json errors here
        logger.exception("http_get_json failed for %s: %s", url, exc)
        return None


def iso_to_local(iso_str: Any) -> str:
    """Convert a timestamp-like value to configured local display time."""
    if not iso_str:
        return "--:--"
    try:
        from .timefmt import format_start_time
        label = format_start_time(iso_str)
        return label if label and label != "Starts TBA" else "--:--"
    except Exception:
        return "--:--"


def now_ts() -> float:
    return time.monotonic()


def cache_get(cache: Dict[str, Tuple[float, Any]], key: str, ttl: float) -> Any:
    """Return cached value if within TTL."""
    if key in cache:
        ts, val = cache[key]
        if now_ts() - ts <= ttl:
            return val
    return None


def cache_set(cache: Dict[str, Tuple[float, Any]], key: str, val: Any) -> Any:
    cache[key] = (now_ts(), val)
    return val


def format_player_initial_name(first: str | None, last: str | None) -> str:
    """Return a name like 'J. Doe' (initial + full last) with sensible fallbacks."""
    first = (first or "").strip()
    last = (last or "").strip()
    initial = f"{first[:1]}." if first else ""
    if last and initial:
        return f"{initial} {last}".strip()
    if last:
        return last
    if initial:
        return initial
    return "Player"


def extract_three_point_made(stats: Dict[str, Any]) -> int:
    """Return the first available three-point made value from a stats dict."""
    keys = (
        "threePointersMade",
        "threePointFieldGoalsMade",
        "threePointMade",
        "threePointers",
        "three_point_made",
        "threePoints",
    )
    for key in keys:
        val = stats.get(key)
        if val in (None, ""):
            continue
        try:
            return int(float(val))
        except Exception:
            continue
    return 0
