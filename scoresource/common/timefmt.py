"""Shared helpers for time formatting across sports."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


def format_start_time(ts: Any, timezone: str | None = None) -> str:
    """
    Friendly start-time formatter shared by all sports:
    - Same-day: time only (e.g., '3:25 PM CT')
    - Within 7 days: weekday + time (e.g., 'Sat 3:25 PM CT')
    - Beyond 7 days: M/D + time (e.g., '1/08 3:25 PM CT')
    """
    tz_name = timezone or os.environ.get("SCORESOURCE_TZ", "America/Chicago")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/Chicago")

    dt = _to_datetime(ts, tz)
    if dt is None:
        return "Starts TBA"

    now = datetime.now(tz)
    days_ahead = (dt.date() - now.date()).days

    if days_ahead == 0:
        return dt.strftime("%-I:%M %p %Z").replace(" 0", " ")
    if 0 < days_ahead <= 7:
        return dt.strftime("%a %-I:%M %p %Z").replace(" 0", " ")
    return dt.strftime("%-m/%-d %-I:%M %p %Z").replace(" 0", " ")


def _to_datetime(ts: Any, tz: ZoneInfo) -> datetime | None:
    if isinstance(ts, (int, float)):
        # Handle millisecond epoch inputs
        value = ts / 1000.0 if ts > 1e11 else ts
        return datetime.fromtimestamp(value, tz=ZoneInfo("UTC")).astimezone(tz)
    elif isinstance(ts, str):
        parsed = _parse_iso_like(ts)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(tz)
    return None


def _parse_iso_like(value: str) -> datetime | None:
    """Best-effort ISO parser that tolerates missing Z/offset and milliseconds."""
    cleaned = value.strip()
    cleaned = cleaned.replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(cleaned)
    except Exception:
        pass

    patterns = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ]
    for fmt in patterns:
        try:
            return datetime.strptime(cleaned, fmt)
        except Exception:
            continue
    return None
