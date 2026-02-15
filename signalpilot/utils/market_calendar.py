"""NSE trading day checks and market phase determination."""

import logging
from datetime import date, datetime, time
from enum import Enum

from signalpilot.utils.constants import (
    ENTRY_WINDOW_END,
    GAP_SCAN_END,
    IST,
    MARKET_CLOSE,
    MARKET_OPEN,
    NEW_SIGNAL_CUTOFF,
)

logger = logging.getLogger("signalpilot.utils.market_calendar")

# NSE holidays indexed by year.
# Add new years before each calendar year begins.
NSE_HOLIDAYS: dict[int, frozenset[date]] = {
    2026: frozenset(
        {
            date(2026, 1, 26),   # Republic Day
            date(2026, 3, 10),   # Maha Shivaratri
            date(2026, 3, 30),   # Holi
            date(2026, 3, 31),   # Id-ul-Fitr (Tentative)
            date(2026, 4, 2),    # Ram Navami
            date(2026, 4, 3),    # Good Friday
            date(2026, 4, 14),   # Dr. Ambedkar Jayanti
            date(2026, 5, 1),    # Maharashtra Day
            date(2026, 6, 7),    # Id-ul-Adha (Bakri Id) (Tentative)
            date(2026, 7, 7),    # Muharram (Tentative)
            date(2026, 8, 15),   # Independence Day
            date(2026, 8, 19),   # Janmashtami
            date(2026, 9, 5),    # Milad-un-Nabi (Tentative)
            date(2026, 10, 2),   # Mahatma Gandhi Jayanti
            date(2026, 10, 20),  # Dussehra
            date(2026, 11, 9),   # Diwali (Laxmi Pujan)
            date(2026, 11, 10),  # Diwali (Balipratipada)
            date(2026, 11, 30),  # Guru Nanak Jayanti
            date(2026, 12, 25),  # Christmas
        }
    ),
}


class StrategyPhase(Enum):
    """Phases of the trading day that a strategy may operate in."""

    PRE_MARKET = "pre_market"       # Before 9:15 AM
    OPENING = "opening"             # 9:15 AM - 9:30 AM
    ENTRY_WINDOW = "entry_window"   # 9:30 AM - 9:45 AM
    CONTINUOUS = "continuous"       # 9:45 AM - 2:30 PM
    WIND_DOWN = "wind_down"         # 2:30 PM - 3:30 PM
    POST_MARKET = "post_market"     # After 3:30 PM


def is_trading_day(d: date) -> bool:
    """Check if a given date is a trading day (not weekend, not NSE holiday).

    Raises:
        ValueError: If no holiday data is available for the given year.
    """
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    holidays = NSE_HOLIDAYS.get(d.year)
    if holidays is None:
        raise ValueError(
            f"No NSE holiday data for year {d.year}. "
            f"Available years: {sorted(NSE_HOLIDAYS.keys())}. "
            f"Update NSE_HOLIDAYS in market_calendar.py."
        )
    return d not in holidays


def is_market_hours(dt: datetime) -> bool:
    """Check if the given datetime falls within NSE market hours (9:15 AM - 3:30 PM IST).

    Note: This checks time-of-day only, not whether the date is a trading day.
    Use ``is_trading_day(dt.date())`` separately if you need a full market-open check.

    Naive datetimes are treated as IST.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    ist_time = dt.astimezone(IST).time()
    return MARKET_OPEN <= ist_time < MARKET_CLOSE


def get_current_phase(dt: datetime) -> StrategyPhase:
    """Map a datetime to the current strategy phase based on market timing.

    Naive datetimes are treated as IST.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    t = dt.astimezone(IST).time()

    if t < MARKET_OPEN:
        return StrategyPhase.PRE_MARKET
    if t < GAP_SCAN_END:
        return StrategyPhase.OPENING
    if t < ENTRY_WINDOW_END:
        return StrategyPhase.ENTRY_WINDOW
    if t < NEW_SIGNAL_CUTOFF:
        return StrategyPhase.CONTINUOUS
    if t < MARKET_CLOSE:
        return StrategyPhase.WIND_DOWN
    return StrategyPhase.POST_MARKET
