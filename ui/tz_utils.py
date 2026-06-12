"""
Timezone conversion utilities for match display.

All times are stored in the DB as UTC (HH:MM strings, date as YYYY-MM-DD).
This module converts them to the user's configured offset for display.

Stored setting value examples:  "UTC", "UTC+1", "UTC-5", "UTC+5:30"
"""

import re
from datetime import datetime, timedelta, timezone, date as _date
from database.database import get_setting

# Regex to parse "UTC+H", "UTC-H:MM", etc.
_OFFSET_RE = re.compile(r'^UTC([+-])(\d{1,2})(?::(\d{2}))?$')


def _parse_offset_minutes(tz_str: str) -> int:
    """
    Parse a UTC offset string into total signed minutes.
    "UTC"      →   0
    "UTC+1"    →  60
    "UTC-5"    → -300
    "UTC+5:30" →  330
    "UTC+8 (CST)" → 480   (trailing label ignored)
    """
    if not tz_str:
        return 0
    # Strip trailing labels like " (CET)"
    tz_str = tz_str.split(" ")[0].strip()
    if tz_str == "UTC":
        return 0
    m = _OFFSET_RE.match(tz_str)
    if not m:
        return 0
    sign    = 1 if m.group(1) == "+" else -1
    hours   = int(m.group(2))
    minutes = int(m.group(3)) if m.group(3) else 0
    return sign * (hours * 60 + minutes)


def get_user_offset_minutes() -> int:
    """Return the user's configured UTC offset in minutes (cached per call)."""
    tz_str = get_setting("timezone", "UTC") or "UTC"
    return _parse_offset_minutes(tz_str)


def convert_match_time(date_str: str, time_str: str) -> tuple[str, str]:
    """
    Apply the user's UTC offset to a UTC match date+time.

    Returns (local_date_str, local_time_str) where:
      local_date_str is YYYY-MM-DD  (may differ from date_str if offset crosses midnight)
      local_time_str is HH:MM

    If either input is empty/unparseable the originals are returned unchanged.
    """
    if not date_str or not time_str:
        return date_str, time_str

    offset_min = get_user_offset_minutes()
    if offset_min == 0:
        return date_str, time_str

    try:
        dt_utc = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        dt_local = dt_utc + timedelta(minutes=offset_min)
        return dt_local.strftime("%Y-%m-%d"), dt_local.strftime("%H:%M")
    except ValueError:
        return date_str, time_str


def format_kickoff(date_str: str, time_str: str) -> str:
    """
    Return a display string like "19:00" adjusted to the user's timezone,
    appending the offset label when it is not UTC.
    e.g.  "20:00 (UTC+1)"
    """
    local_date, local_time = convert_match_time(date_str, time_str)
    tz_str = (get_setting("timezone", "UTC") or "UTC").split(" ")[0]
    if tz_str == "UTC":
        return local_time
    return f"{local_time} ({tz_str})"


def local_dates_for_match(date_str: str, time_str: str) -> str:
    """Return only the local date string (for calendar grouping)."""
    local_date, _ = convert_match_time(date_str, time_str)
    return local_date
