"""Shared helpers for time formatting across sports."""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

# ESPN returns raw status text like "7:00 PM EST" for pre-game — map those to CT
_ESPN_TZ_MAP = {
    "EST": ZoneInfo("America/New_York"),
    "EDT": ZoneInfo("America/New_York"),
    "ET":  ZoneInfo("America/New_York"),
    "PST": ZoneInfo("America/Los_Angeles"),
    "PDT": ZoneInfo("America/Los_Angeles"),
    "PT":  ZoneInfo("America/Los_Angeles"),
    "MST": ZoneInfo("America/Denver"),
    "MDT": ZoneInfo("America/Denver"),
    "MT":  ZoneInfo("America/Denver"),
    "CST": ZoneInfo("America/Chicago"),
    "CDT": ZoneInfo("America/Chicago"),
    "CT":  ZoneInfo("America/Chicago"),
}
_ESPN_TIME_RE = re.compile(
    r"^(\d{1,2}:\d{2}\s*(?:AM|PM))\s+(" + "|".join(_ESPN_TZ_MAP) + r")\b",
    re.IGNORECASE,
)

_DEFAULT_TZ = "America/Chicago"


def _display_tz() -> ZoneInfo:
    tz_name = (os.environ.get("SCORESOURCE_TZ") or _DEFAULT_TZ).strip() or _DEFAULT_TZ
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo(_DEFAULT_TZ)


def _format_display_datetime(dt: datetime) -> str:
    # Uniform display across all sports for upcoming games.
    return dt.strftime("%a %-m/%-d %-I:%M %p %Z").replace(" 0", " ")


def normalize_espn_time_str(text: str | None) -> str | None:
    """
    If *text* is an ESPN raw game-time string like '7:00 PM EST', convert it
    into the selected display timezone and return e.g. '6:00 PM CT'. Returns
    None if not matched so callers can fall back to the original string.
    """
    if not text:
        return None
    m = _ESPN_TIME_RE.match(text.strip())
    if not m:
        return None
    time_part, tz_abbr = m.group(1).strip(), m.group(2).upper()
    src_tz = _ESPN_TZ_MAP.get(tz_abbr)
    if src_tz is None:
        return None
    display_tz = _display_tz()
    today = datetime.now(display_tz).date()
    try:
        naive = datetime.strptime(f"{today} {time_part}", "%Y-%m-%d %I:%M %p")
    except ValueError:
        return None
    src_dt = naive.replace(tzinfo=src_tz)
    local_dt = src_dt.astimezone(display_tz)
    return local_dt.strftime("%-I:%M %p %Z")


def format_start_time(ts: Any) -> str:
    """
    Uniform start-time formatter shared by all sports:
    - Always returns weekday + date + time in selected timezone
      (e.g., 'Thu 3/12 7:00 PM CDT')
    """
    tz = _display_tz()

    dt = _to_datetime(ts, tz)
    if dt is None:
        return "Starts TBA"
    return _format_display_datetime(dt)


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
