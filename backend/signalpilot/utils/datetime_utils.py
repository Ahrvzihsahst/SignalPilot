"""Datetime utility functions for consistent timezone handling."""

from datetime import datetime

from signalpilot.utils.constants import IST


def parse_ist_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-format datetime string, ensuring IST timezone awareness.

    Returns ``None`` when *value* is ``None``.  If the parsed datetime is
    naive (no tzinfo), IST is attached so all datetimes stored in the DB
    are treated uniformly.
    """
    if value is None:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt
