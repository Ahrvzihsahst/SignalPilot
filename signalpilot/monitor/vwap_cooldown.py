"""VWAP cooldown tracker — limits signal frequency per stock."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class _CooldownEntry:
    signal_count: int
    last_signal_at: datetime


class VWAPCooldownTracker:
    """Tracks per-stock signal counts and cooldown periods for VWAP strategy."""

    def __init__(
        self,
        max_signals_per_stock: int = 2,
        cooldown_minutes: int = 60,
    ) -> None:
        self._max_signals = max_signals_per_stock
        self._cooldown = timedelta(minutes=cooldown_minutes)
        self._entries: dict[str, _CooldownEntry] = {}

    def can_signal(self, symbol: str, now: datetime) -> bool:
        """Check if a new signal is allowed for this symbol."""
        entry = self._entries.get(symbol)
        if entry is None:
            return True
        if entry.signal_count >= self._max_signals:
            return False
        if now - entry.last_signal_at < self._cooldown:
            return False
        return True

    def record_signal(self, symbol: str, now: datetime) -> None:
        """Record that a signal was generated for this symbol."""
        entry = self._entries.get(symbol)
        if entry is None:
            self._entries[symbol] = _CooldownEntry(signal_count=1, last_signal_at=now)
        else:
            entry.signal_count += 1
            entry.last_signal_at = now

    def reset(self) -> None:
        """Clear all entries (called at start of each trading day)."""
        self._entries.clear()

    def get_state(self) -> dict[str, tuple[int, str]]:
        """Serialize state for crash recovery."""
        return {
            symbol: (entry.signal_count, entry.last_signal_at.isoformat())
            for symbol, entry in self._entries.items()
        }

    def restore_state(self, state: dict[str, tuple[int, str]]) -> None:
        """Restore state from crash recovery data."""
        self._entries.clear()
        for symbol, (count, iso_time) in state.items():
            self._entries[symbol] = _CooldownEntry(
                signal_count=count,
                last_signal_at=datetime.fromisoformat(iso_time),
            )
