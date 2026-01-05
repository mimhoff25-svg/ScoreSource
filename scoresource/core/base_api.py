"""Base API plumbing for ScoreSource multi-sport scoreboard."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

log = logging.getLogger(__name__)


@dataclass
class ScoreboardResult:
    games: list[Dict[str, Any]]
    lines: list[str]


class BaseSportsAPI:
    """Simple fetcher wrapper with caching to throttle free endpoints."""

    def __init__(self, ttl_seconds: int = 20):
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, Any]] = {}
        self.session = requests.Session()

    def _cached_get_json(self, url: str, *, ttl: Optional[int] = None) -> Any:
        ttl = ttl or self.ttl_seconds
        now = time.time()
        cached = self._cache.get(url)
        if cached and now - cached[0] < ttl:
            return cached[1]
        resp = self.session.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self._cache[url] = (now, data)
        return data

    # API surface for implementors -------------------------------------------------
    def fetch_scoreboard(self) -> ScoreboardResult:
        raise NotImplementedError

    def fetch_game_detail(self, game_id: str) -> Dict[str, Any]:
        raise NotImplementedError
