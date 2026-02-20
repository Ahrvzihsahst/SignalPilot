"""Market time constants for SignalPilot.

Strategy-tunable parameters (gap thresholds, targets, scoring weights, etc.)
are configured via ``signalpilot.config.AppConfig`` and loaded from environment
variables / ``.env`` file. Only truly static market timing constants live here.
"""

from datetime import time
from zoneinfo import ZoneInfo

# Timezone
IST = ZoneInfo("Asia/Kolkata")

# Market timing constants (IST)
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
PRE_MARKET_ALERT = time(9, 0)
GAP_SCAN_END = time(9, 30)
ENTRY_WINDOW_END = time(9, 45)
NEW_SIGNAL_CUTOFF = time(14, 30)
EXIT_REMINDER = time(15, 0)
MANDATORY_EXIT = time(15, 15)
DAILY_SUMMARY = time(15, 30)
APP_SHUTDOWN = time(15, 35)
APP_AUTO_START = time(8, 50)

# Phase 2 time constants
ORB_WINDOW_END = time(11, 0)
VWAP_SCAN_START = time(10, 0)
OPENING_RANGE_LOCK = time(9, 45)

# Signal management (static, non-configurable)
MAX_SIGNALS_PER_BATCH = 8
