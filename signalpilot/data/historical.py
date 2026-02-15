"""Historical data fetcher with Angel One primary and yfinance fallback."""

import asyncio
import logging
from datetime import datetime, timedelta

import yfinance as yf

from signalpilot.data.auth import SmartAPIAuthenticator
from signalpilot.data.instruments import InstrumentManager
from signalpilot.db.models import HistoricalReference, PreviousDayData

logger = logging.getLogger("signalpilot.data.historical")


class HistoricalDataFetcher:
    """Fetches historical OHLCV data from Angel One or yfinance."""

    def __init__(
        self,
        authenticator: SmartAPIAuthenticator,
        instruments: InstrumentManager,
        rate_limit: int = 3,
    ) -> None:
        self._auth = authenticator
        self._instruments = instruments
        self._semaphore = asyncio.Semaphore(rate_limit)

    async def fetch_previous_day_data(self) -> dict[str, PreviousDayData]:
        """Fetch previous day's OHLCV for all Nifty 500 stocks.

        Returns mapping of symbol -> PreviousDayData.
        Falls back to yfinance on Angel One failure.
        Excludes instruments where both sources fail.
        """
        results: dict[str, PreviousDayData] = {}
        tasks = []
        for symbol in self._instruments.symbols:
            tasks.append(self._fetch_single_previous_day(symbol))

        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        for symbol, outcome in zip(self._instruments.symbols, outcomes):
            if isinstance(outcome, Exception):
                logger.error("Failed to fetch previous day data for %s: %s", symbol, outcome)
            elif outcome is not None:
                results[symbol] = outcome

        logger.info(
            "Fetched previous day data for %d/%d instruments",
            len(results),
            len(self._instruments.symbols),
        )
        return results

    async def _fetch_single_previous_day(self, symbol: str) -> PreviousDayData | None:
        """Fetch previous day data for a single symbol with fallback."""
        instrument = self._instruments.get_instrument(symbol)
        if instrument is None:
            return None

        # Try Angel One first
        try:
            async with self._semaphore:
                data = await self._fetch_from_angel_one(
                    symbol, instrument.angel_token, days=2
                )
            if data is not None:
                return data
        except Exception as e:
            logger.warning("Angel One failed for %s: %s, trying yfinance", symbol, e)

        # Fallback to yfinance
        try:
            data = await self._fetch_from_yfinance(symbol, instrument.yfinance_symbol, days=2)
            if data is not None:
                logger.warning("Used yfinance fallback for %s", symbol)
                return data
        except Exception as e:
            logger.error("yfinance also failed for %s: %s — excluding", symbol, e)

        return None

    async def fetch_average_daily_volume(
        self, lookback_days: int = 20
    ) -> dict[str, float]:
        """Fetch ADV over the last N trading sessions.

        Returns mapping of symbol -> average daily volume.
        Falls back to yfinance on Angel One failure.
        """
        results: dict[str, float] = {}
        tasks = []
        for symbol in self._instruments.symbols:
            tasks.append(self._fetch_single_adv(symbol, lookback_days))

        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        for symbol, outcome in zip(self._instruments.symbols, outcomes):
            if isinstance(outcome, Exception):
                logger.error("Failed to fetch ADV for %s: %s", symbol, outcome)
            elif outcome is not None:
                results[symbol] = outcome

        logger.info(
            "Fetched ADV for %d/%d instruments",
            len(results),
            len(self._instruments.symbols),
        )
        return results

    async def _fetch_single_adv(self, symbol: str, lookback_days: int) -> float | None:
        """Fetch ADV for a single symbol with fallback."""
        instrument = self._instruments.get_instrument(symbol)
        if instrument is None:
            return None

        # Try Angel One first
        try:
            async with self._semaphore:
                adv = await self._fetch_adv_from_angel_one(
                    symbol, instrument.angel_token, lookback_days
                )
            if adv is not None:
                return adv
        except Exception as e:
            logger.warning("Angel One ADV failed for %s: %s, trying yfinance", symbol, e)

        # Fallback to yfinance
        try:
            adv = await self._fetch_adv_from_yfinance(
                symbol, instrument.yfinance_symbol, lookback_days
            )
            if adv is not None:
                logger.warning("Used yfinance fallback for ADV of %s", symbol)
                return adv
        except Exception as e:
            logger.error("yfinance ADV also failed for %s: %s — excluding", symbol, e)

        return None

    async def _fetch_from_angel_one(
        self, symbol: str, token: str, days: int
    ) -> PreviousDayData | None:
        """Fetch historical candle data from Angel One SmartAPI."""
        smart_connect = self._auth.smart_connect
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days + 5)  # Extra days for weekends/holidays

        params = {
            "exchange": "NSE",
            "symboltoken": token,
            "interval": "ONE_DAY",
            "fromdate": from_date.strftime("%Y-%m-%d %H:%M"),
            "todate": to_date.strftime("%Y-%m-%d %H:%M"),
        }

        def _call():
            return smart_connect.getCandleData(params)

        result = await asyncio.to_thread(_call)

        if result.get("status") is False or not result.get("data"):
            return None

        candles = result["data"]
        if len(candles) < 2:
            return None

        # Previous day is the second-to-last candle
        prev = candles[-2]
        if len(prev) < 6:
            logger.warning("Incomplete candle data for %s: %s", symbol, prev)
            return None

        return PreviousDayData(
            open=prev[1],
            high=prev[2],
            low=prev[3],
            close=prev[4],
            volume=prev[5],
        )

    async def _fetch_from_yfinance(
        self, symbol: str, yf_symbol: str, days: int
    ) -> PreviousDayData | None:
        """Fallback: fetch data from yfinance. Logs a warning."""

        def _call():
            ticker = yf.Ticker(yf_symbol)
            hist = ticker.history(period=f"{days + 5}d")
            return hist

        hist = await asyncio.to_thread(_call)

        if hist is None or len(hist) < 2:
            return None

        prev = hist.iloc[-2]
        return PreviousDayData(
            open=float(prev["Open"]),
            high=float(prev["High"]),
            low=float(prev["Low"]),
            close=float(prev["Close"]),
            volume=int(prev["Volume"]),
        )

    async def _fetch_adv_from_angel_one(
        self, symbol: str, token: str, lookback_days: int
    ) -> float | None:
        """Fetch ADV from Angel One."""
        smart_connect = self._auth.smart_connect
        to_date = datetime.now()
        from_date = to_date - timedelta(days=lookback_days + 10)

        params = {
            "exchange": "NSE",
            "symboltoken": token,
            "interval": "ONE_DAY",
            "fromdate": from_date.strftime("%Y-%m-%d %H:%M"),
            "todate": to_date.strftime("%Y-%m-%d %H:%M"),
        }

        def _call():
            return smart_connect.getCandleData(params)

        result = await asyncio.to_thread(_call)

        if result.get("status") is False or not result.get("data"):
            return None

        candles = result["data"]
        if not candles:
            return None

        volumes = [c[5] for c in candles[-lookback_days:]]
        return sum(volumes) / len(volumes) if volumes else None

    async def _fetch_adv_from_yfinance(
        self, symbol: str, yf_symbol: str, lookback_days: int
    ) -> float | None:
        """Fallback: fetch ADV from yfinance."""

        def _call():
            ticker = yf.Ticker(yf_symbol)
            hist = ticker.history(period=f"{lookback_days + 10}d")
            return hist

        hist = await asyncio.to_thread(_call)

        if hist is None or len(hist) == 0:
            return None

        volumes = hist["Volume"].tail(lookback_days).tolist()
        return sum(volumes) / len(volumes) if volumes else None

    async def build_historical_references(
        self,
    ) -> dict[str, HistoricalReference]:
        """Convenience method: fetch prev day data + ADV, build HistoricalReference map."""
        prev_data, adv_data = await asyncio.gather(
            self.fetch_previous_day_data(),
            self.fetch_average_daily_volume(),
        )

        refs: dict[str, HistoricalReference] = {}
        for symbol in self._instruments.symbols:
            prev = prev_data.get(symbol)
            adv = adv_data.get(symbol)
            if prev is not None and adv is not None:
                refs[symbol] = HistoricalReference(
                    previous_close=prev.close,
                    previous_high=prev.high,
                    average_daily_volume=adv,
                )
            elif prev is None and adv is not None:
                logger.warning("Excluding %s: previous day data unavailable", symbol)
            elif prev is not None and adv is None:
                logger.warning("Excluding %s: ADV data unavailable", symbol)

        logger.info("Built historical references for %d instruments", len(refs))
        return refs
