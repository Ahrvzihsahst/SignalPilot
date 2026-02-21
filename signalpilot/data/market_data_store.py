"""Async-safe in-memory store for real-time and historical market data.

Uses asyncio.Lock for mutual exclusion between concurrent coroutines.
Not safe for direct access from OS threads -- all callers must be in the
same asyncio event loop (WebSocket thread bridges via call_soon_threadsafe).
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime

from signalpilot.db.models import HistoricalReference, TickData


@dataclass
class OpeningRange:
    """Opening range (9:15-9:45) high/low for a symbol."""

    range_high: float
    range_low: float
    locked: bool = False
    range_size_pct: float = 0.0


@dataclass
class VWAPState:
    """Running VWAP accumulator for a symbol."""

    cumulative_price_volume: float = 0.0
    cumulative_volume: float = 0.0
    current_vwap: float = 0.0


@dataclass
class Candle15Min:
    """15-minute OHLCV candle."""

    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    start_time: datetime
    end_time: datetime
    is_complete: bool = False


class MarketDataStore:
    """Async-safe in-memory store for real-time and historical market data."""

    def __init__(self) -> None:
        self._ticks: dict[str, TickData] = {}
        self._historical: dict[str, HistoricalReference] = {}
        self._volume_accumulator: dict[str, int] = {}
        self._opening_ranges: dict[str, OpeningRange] = {}
        self._vwap_state: dict[str, VWAPState] = {}
        self._candles_15m: dict[str, list[Candle15Min]] = {}
        self._current_candle: dict[str, Candle15Min] = {}
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
        """Update cumulative volume for a symbol."""
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

    # -- Opening Range tracking ---------------------------------------------------

    async def update_opening_range(self, symbol: str, high: float, low: float) -> None:
        """Update opening range high/low from tick data (only before lock)."""
        async with self._lock:
            existing = self._opening_ranges.get(symbol)
            if existing and existing.locked:
                return
            if existing:
                existing.range_high = max(existing.range_high, high)
                existing.range_low = min(existing.range_low, low)
            else:
                self._opening_ranges[symbol] = OpeningRange(
                    range_high=high, range_low=low
                )

    async def lock_opening_ranges(self) -> None:
        """Lock all opening ranges (called at 9:45 AM)."""
        async with self._lock:
            for symbol, rng in self._opening_ranges.items():
                if not rng.locked:
                    rng.locked = True
                    if rng.range_low > 0:
                        rng.range_size_pct = (
                            (rng.range_high - rng.range_low) / rng.range_low
                        ) * 100

    async def get_opening_range(self, symbol: str) -> OpeningRange | None:
        """Get the opening range for a symbol."""
        async with self._lock:
            return self._opening_ranges.get(symbol)

    # -- VWAP calculation ---------------------------------------------------------

    async def update_vwap(self, symbol: str, price: float, volume: float) -> None:
        """Update running VWAP for a symbol."""
        async with self._lock:
            state = self._vwap_state.get(symbol)
            if state is None:
                state = VWAPState()
                self._vwap_state[symbol] = state
            state.cumulative_price_volume += price * volume
            state.cumulative_volume += volume
            if state.cumulative_volume > 0:
                state.current_vwap = (
                    state.cumulative_price_volume / state.cumulative_volume
                )

    async def get_vwap(self, symbol: str) -> float | None:
        """Get the current VWAP for a symbol."""
        async with self._lock:
            state = self._vwap_state.get(symbol)
            return state.current_vwap if state and state.cumulative_volume > 0 else None

    async def reset_vwap(self) -> None:
        """Reset all VWAP accumulators (called at session start)."""
        async with self._lock:
            self._vwap_state.clear()

    # -- 15-minute candle aggregation ---------------------------------------------

    @staticmethod
    def _get_candle_bucket(timestamp: datetime) -> datetime:
        """Snap timestamp to 15-min boundary."""
        minute = (timestamp.minute // 15) * 15
        return timestamp.replace(minute=minute, second=0, microsecond=0)

    async def update_candle(
        self, symbol: str, price: float, volume: float, timestamp: datetime
    ) -> None:
        """Aggregate tick into a 15-min candle bucket."""
        async with self._lock:
            bucket = self._get_candle_bucket(timestamp)
            current = self._current_candle.get(symbol)

            if current is not None and current.start_time == bucket:
                # Update existing candle
                current.high = max(current.high, price)
                current.low = min(current.low, price)
                current.close = price
                current.volume += volume
            else:
                # New bucket — finalize previous candle if any
                if current is not None:
                    current.is_complete = True
                    if symbol not in self._candles_15m:
                        self._candles_15m[symbol] = []
                    self._candles_15m[symbol].append(current)

                from datetime import timedelta

                self._current_candle[symbol] = Candle15Min(
                    symbol=symbol,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=volume,
                    start_time=bucket,
                    end_time=bucket + timedelta(minutes=15),
                )

    async def get_completed_candles(self, symbol: str) -> list[Candle15Min]:
        """Return all finalized 15-min candles for a symbol."""
        async with self._lock:
            return list(self._candles_15m.get(symbol, []))

    async def get_current_candle(self, symbol: str) -> Candle15Min | None:
        """Return the in-progress 15-min candle for a symbol."""
        async with self._lock:
            return self._current_candle.get(symbol)

    async def get_avg_candle_volume(self, symbol: str) -> float:
        """Average volume of completed candles (excluding current)."""
        async with self._lock:
            candles = self._candles_15m.get(symbol, [])
            if not candles:
                return 0.0
            return sum(c.volume for c in candles) / len(candles)

    # -- Clear all ----------------------------------------------------------------

    async def clear(self) -> None:
        """Clear all stored data (used for daily reset)."""
        async with self._lock:
            self._ticks.clear()
            self._historical.clear()
            self._volume_accumulator.clear()
            self._opening_ranges.clear()
            self._vwap_state.clear()
            self._candles_15m.clear()
            self._current_candle.clear()
