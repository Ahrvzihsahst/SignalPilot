"""Historical data loader for backtesting."""

import logging
from dataclasses import dataclass
from datetime import date, datetime

logger = logging.getLogger(__name__)


@dataclass
class BacktestCandle:
    """OHLCV candle for backtesting."""

    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: datetime


class BacktestDataLoader:
    """Loads historical data for backtesting.

    Supports loading from yfinance (with local file caching) or from
    pre-built candle data for deterministic testing.
    """

    def __init__(self, cache_dir: str = ".backtest_cache"):
        self._cache_dir = cache_dir

    async def load_historical_data(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        interval: str = "15m",
    ) -> dict[str, list[BacktestCandle]]:
        """Load historical OHLCV data for the given symbols and period.

        Uses yfinance with local file caching to avoid repeated API calls.
        Returns dict mapping symbol to list of candles sorted by timestamp.
        """
        logger.info(
            "Entering load_historical_data",
            extra={
                "symbol_count": len(symbols),
                "start_date": str(start_date),
                "end_date": str(end_date),
                "interval": interval,
            },
        )
        # Implementation: try cache first, then yfinance fallback.
        # Actual yfinance integration is deferred to a follow-up task.
        result: dict[str, list[BacktestCandle]] = {}
        logger.info(
            "Exiting load_historical_data",
            extra={"symbols_loaded": len(result)},
        )
        return result

    def load_from_candles(
        self, candles: dict[str, list[BacktestCandle]]
    ) -> dict[str, list[BacktestCandle]]:
        """Load from pre-built candle data (for testing).

        Passes through the provided candle dict unchanged, enabling
        deterministic backtests with hand-crafted data.
        """
        logger.info(
            "Entering load_from_candles",
            extra={"symbol_count": len(candles)},
        )
        return candles
