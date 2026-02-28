"""Regime data collection for Market Regime Detection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from signalpilot.utils.constants import IST

logger = logging.getLogger(__name__)


@dataclass
class RegimeInputs:
    """All inputs needed for regime classification."""

    india_vix: float | None = None
    nifty_gap_pct: float | None = None
    nifty_first_15_range_pct: float | None = None
    nifty_first_15_direction: str | None = None  # 'UP', 'DOWN', 'FLAT'
    prev_day_range_pct: float | None = None
    fii_net_crores: float | None = None
    dii_net_crores: float | None = None
    sgx_direction: str | None = None  # 'UP', 'DOWN', 'FLAT'
    sp500_change_pct: float | None = None
    collected_at: datetime | None = None


@dataclass
class PreMarketData:
    """Pre-market data collected at 8:45 AM for the morning brief."""

    india_vix: float | None = None
    sp500_change_pct: float | None = None
    nasdaq_change_pct: float | None = None
    sgx_direction: str | None = None
    sgx_change_pct: float | None = None
    nikkei_change_pct: float | None = None
    hang_seng_change_pct: float | None = None
    fii_net_crores: float | None = None
    dii_net_crores: float | None = None
    collected_at: datetime | None = None


class RegimeDataCollector:
    """Async data collector for regime classification inputs.

    Fetches VIX, Nifty gap/range, global cues, and FII/DII flows.
    All fetching is async. Results are cached for the current session.
    """

    def __init__(self, market_data, config) -> None:
        self._market_data = market_data  # MarketDataStore
        self._config = config  # AppConfig
        self._session_cache: dict[str, object] = {}
        self._pre_market_data: PreMarketData | None = None

    async def collect_pre_market_data(self) -> PreMarketData:
        """Fetch pre-market data at 8:45 AM for the morning brief."""
        data = PreMarketData(collected_at=datetime.now(IST))

        try:
            data.india_vix = await self.fetch_current_vix()
        except Exception:
            logger.warning("Failed to fetch VIX for pre-market data")

        try:
            cues = await self.fetch_global_cues()
            data.sp500_change_pct = cues.get("sp500_change_pct")
            data.nasdaq_change_pct = cues.get("nasdaq_change_pct")
            data.sgx_direction = cues.get("sgx_direction")
            data.sgx_change_pct = cues.get("sgx_change_pct")
            data.nikkei_change_pct = cues.get("nikkei_change_pct")
            data.hang_seng_change_pct = cues.get("hang_seng_change_pct")
        except Exception:
            logger.warning("Failed to fetch global cues for pre-market data")

        try:
            fii, dii = await self.fetch_fii_dii()
            data.fii_net_crores = fii
            data.dii_net_crores = dii
        except Exception:
            logger.warning("Failed to fetch FII/DII for pre-market data")

        self._pre_market_data = data
        logger.info("Pre-market data collected: VIX=%s", data.india_vix)
        return data

    async def collect_regime_inputs(self) -> RegimeInputs:
        """Collect all inputs for regime classification at 9:30 AM."""
        inputs = RegimeInputs(collected_at=datetime.now(IST))

        # Use cached pre-market data if available
        pre = self._pre_market_data
        if pre:
            inputs.india_vix = pre.india_vix
            inputs.sgx_direction = pre.sgx_direction
            inputs.sp500_change_pct = pre.sp500_change_pct
            inputs.fii_net_crores = pre.fii_net_crores
            inputs.dii_net_crores = pre.dii_net_crores
        else:
            try:
                inputs.india_vix = await self.fetch_current_vix()
            except Exception:
                logger.warning("Failed to fetch VIX for regime inputs")
            try:
                cues = await self.fetch_global_cues()
                inputs.sgx_direction = cues.get("sgx_direction")
                inputs.sp500_change_pct = cues.get("sp500_change_pct")
            except Exception:
                logger.warning("Failed to fetch global cues for regime inputs")
            try:
                fii, dii = await self.fetch_fii_dii()
                inputs.fii_net_crores = fii
                inputs.dii_net_crores = dii
            except Exception:
                logger.warning("Failed to fetch FII/DII for regime inputs")

        # Fetch Nifty 50 data from MarketDataStore
        try:
            nifty_data = await self.get_current_nifty_data()
            if nifty_data:
                today_open = nifty_data.get("open")
                prev_close = nifty_data.get("prev_close")
                high = nifty_data.get("high")
                low = nifty_data.get("low")
                close = nifty_data.get("ltp")

                if today_open and prev_close and prev_close != 0:
                    inputs.nifty_gap_pct = (today_open - prev_close) / prev_close * 100

                if high and low and today_open and today_open != 0:
                    inputs.nifty_first_15_range_pct = (high - low) / today_open * 100

                if close is not None and today_open is not None:
                    diff_pct = abs(close - today_open) / today_open * 100 if today_open != 0 else 0
                    if diff_pct < 0.01:
                        inputs.nifty_first_15_direction = "FLAT"
                    elif close > today_open:
                        inputs.nifty_first_15_direction = "UP"
                    else:
                        inputs.nifty_first_15_direction = "DOWN"
        except Exception:
            logger.warning("Failed to fetch Nifty 50 data for regime inputs")

        # Previous day range
        try:
            prev_data = self._session_cache.get("prev_day_data")
            if prev_data and isinstance(prev_data, dict):
                prev_high = prev_data.get("high")
                prev_low = prev_data.get("low")
                prev_cls = prev_data.get("close")
                if prev_high and prev_low and prev_cls and prev_cls != 0:
                    inputs.prev_day_range_pct = (prev_high - prev_low) / prev_cls * 100
        except Exception:
            logger.warning("Failed to calculate previous day range")

        logger.info(
            "Regime inputs collected: VIX=%s, gap=%s, range=%s, direction=%s",
            inputs.india_vix, inputs.nifty_gap_pct,
            inputs.nifty_first_15_range_pct, inputs.nifty_first_15_direction,
        )
        return inputs

    async def fetch_current_vix(self) -> float | None:
        """Fetch the current India VIX value with fallback chain."""
        try:
            if hasattr(self._market_data, "get_vix"):
                vix = await self._market_data.get_vix()
                if vix is not None:
                    self._session_cache["india_vix"] = vix
                    return vix
        except Exception:
            logger.debug("Primary VIX source failed")

        cached = self._session_cache.get("india_vix")
        if cached is not None:
            return cached

        logger.warning("All VIX sources failed, returning None")
        return None

    async def fetch_global_cues(self) -> dict:
        """Fetch SGX Nifty direction and S&P 500 change."""
        result: dict = {
            "sgx_direction": None,
            "sgx_change_pct": None,
            "sp500_change_pct": None,
            "nasdaq_change_pct": None,
            "nikkei_change_pct": None,
            "hang_seng_change_pct": None,
        }
        cached = self._session_cache.get("global_cues")
        if cached and isinstance(cached, dict):
            result.update(cached)
        return result

    async def fetch_fii_dii(self) -> tuple[float | None, float | None]:
        """Fetch previous day's FII and DII net flows in crores."""
        cached = self._session_cache.get("fii_dii")
        if cached and isinstance(cached, tuple):
            return cached
        return (None, None)

    def get_cached_pre_market_data(self) -> PreMarketData | None:
        """Return cached pre-market data (collected at 8:45 AM)."""
        return self._pre_market_data

    async def get_current_nifty_data(self) -> dict | None:
        """Get current Nifty 50 data from MarketDataStore."""
        try:
            if hasattr(self._market_data, "get_nifty_data"):
                return await self._market_data.get_nifty_data()
            if hasattr(self._market_data, "get_tick"):
                tick = self._market_data.get_tick("Nifty 50")
                if tick:
                    return {
                        "ltp": getattr(tick, "ltp", None),
                        "open": getattr(tick, "open_price", None),
                        "high": getattr(tick, "high", None),
                        "low": getattr(tick, "low", None),
                        "prev_close": getattr(tick, "close", None),
                        "change_pct": None,
                    }
        except Exception:
            logger.warning("Failed to get current Nifty data")
        return None

    def set_prev_day_data(self, data: dict) -> None:
        """Store previous day data for gap/range calculations."""
        self._session_cache["prev_day_data"] = data

    def set_global_cues(self, cues: dict) -> None:
        """Store global cues data for classification."""
        self._session_cache["global_cues"] = cues

    def reset_session(self) -> None:
        """Reset session cache for a new trading day."""
        self._session_cache.clear()
        self._pre_market_data = None
