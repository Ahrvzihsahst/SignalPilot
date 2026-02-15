"""Async-safe in-memory store for real-time and historical market data.

Uses asyncio.Lock for mutual exclusion between concurrent coroutines.
Not safe for direct access from OS threads -- all callers must be in the
same asyncio event loop (WebSocket thread bridges via call_soon_threadsafe).
"""

import asyncio

from signalpilot.db.models import HistoricalReference, TickData


class MarketDataStore:
    """Async-safe in-memory store for real-time and historical market data."""

    def __init__(self) -> None:
        self._ticks: dict[str, TickData] = {}
        self._historical: dict[str, HistoricalReference] = {}
        self._volume_accumulator: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def update_tick(self, symbol: str, tick: TickData) -> None:
        """Update the latest tick data for a symbol."""
        async with self._lock:
            self._ticks[symbol] = tick

    async def get_tick(self, symbol: str) -> TickData | None:
        """Get the latest tick data for a symbol."""
        async with self._lock:
            return self._ticks.get(symbol)

    async def set_historical(self, symbol: str, data: HistoricalReference) -> None:
        """Set historical reference data for a symbol."""
        async with self._lock:
            self._historical[symbol] = data

    async def get_historical(self, symbol: str) -> HistoricalReference | None:
        """Get historical reference data for a symbol."""
        async with self._lock:
            return self._historical.get(symbol)

    async def accumulate_volume(self, symbol: str, volume: int) -> None:
        """Update cumulative volume for a symbol.

        Since Angel One provides volume_trade_for_the_day in the tick,
        the accumulator simply stores the latest cumulative volume value.
        """
        async with self._lock:
            self._volume_accumulator[symbol] = volume

    async def get_accumulated_volume(self, symbol: str) -> int:
        """Get the cumulative volume accumulated for a symbol."""
        async with self._lock:
            return self._volume_accumulator.get(symbol, 0)

    async def get_all_ticks(self) -> dict[str, TickData]:
        """Get a snapshot of all current tick data."""
        async with self._lock:
            return dict(self._ticks)

    async def clear(self) -> None:
        """Clear all stored data (used for daily reset)."""
        async with self._lock:
            self._ticks.clear()
            self._historical.clear()
            self._volume_accumulator.clear()
