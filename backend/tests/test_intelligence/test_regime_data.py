"""Tests for RegimeDataCollector and regime data models."""

import types
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.intelligence.regime_data import (
    PreMarketData,
    RegimeDataCollector,
    RegimeInputs,
)
from signalpilot.utils.constants import IST


def _make_config(**overrides):
    """Build a SimpleNamespace config with defaults."""
    defaults = {
        "regime_enabled": True,
        "regime_shadow_mode": False,
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _make_market_data(
    vix=None,
    nifty_data=None,
    has_get_vix=True,
    has_get_nifty_data=True,
):
    """Build a mock MarketDataStore."""
    md = AsyncMock()
    if has_get_vix:
        md.get_vix = AsyncMock(return_value=vix)
    else:
        # Remove the attribute so hasattr check fails
        if hasattr(md, "get_vix"):
            del md.get_vix
    if has_get_nifty_data:
        md.get_nifty_data = AsyncMock(return_value=nifty_data)
    else:
        if hasattr(md, "get_nifty_data"):
            del md.get_nifty_data
    return md


# ---------------------------------------------------------------------------
# Data model defaults
# ---------------------------------------------------------------------------


class TestRegimeInputsDefaults:
    """Tests for RegimeInputs dataclass defaults."""

    def test_regime_inputs_defaults(self):
        """All fields should default to None."""
        inputs = RegimeInputs()
        assert inputs.india_vix is None
        assert inputs.nifty_gap_pct is None
        assert inputs.nifty_first_15_range_pct is None
        assert inputs.nifty_first_15_direction is None
        assert inputs.prev_day_range_pct is None
        assert inputs.fii_net_crores is None
        assert inputs.dii_net_crores is None
        assert inputs.sgx_direction is None
        assert inputs.sp500_change_pct is None
        assert inputs.collected_at is None

    def test_regime_inputs_with_values(self):
        """RegimeInputs should accept all fields."""
        now = datetime.now(IST)
        inputs = RegimeInputs(
            india_vix=15.0,
            nifty_gap_pct=1.5,
            nifty_first_15_range_pct=0.8,
            nifty_first_15_direction="UP",
            prev_day_range_pct=1.2,
            fii_net_crores=500.0,
            dii_net_crores=-300.0,
            sgx_direction="UP",
            sp500_change_pct=0.5,
            collected_at=now,
        )
        assert inputs.india_vix == 15.0
        assert inputs.nifty_first_15_direction == "UP"
        assert inputs.collected_at == now


class TestPreMarketDataDefaults:
    """Tests for PreMarketData dataclass defaults."""

    def test_pre_market_data_defaults(self):
        """All fields should default to None."""
        data = PreMarketData()
        assert data.india_vix is None
        assert data.sp500_change_pct is None
        assert data.nasdaq_change_pct is None
        assert data.sgx_direction is None
        assert data.sgx_change_pct is None
        assert data.nikkei_change_pct is None
        assert data.hang_seng_change_pct is None
        assert data.fii_net_crores is None
        assert data.dii_net_crores is None
        assert data.collected_at is None

    def test_pre_market_data_with_values(self):
        """PreMarketData should accept all fields."""
        now = datetime.now(IST)
        data = PreMarketData(
            india_vix=16.0,
            sp500_change_pct=0.8,
            nasdaq_change_pct=1.2,
            sgx_direction="UP",
            sgx_change_pct=0.5,
            nikkei_change_pct=-0.3,
            hang_seng_change_pct=-0.1,
            fii_net_crores=1000.0,
            dii_net_crores=-500.0,
            collected_at=now,
        )
        assert data.india_vix == 16.0
        assert data.sp500_change_pct == 0.8
        assert data.sgx_direction == "UP"


# ---------------------------------------------------------------------------
# RegimeDataCollector session cache tests
# ---------------------------------------------------------------------------


class TestRegimeDataCollectorSessionCache:
    """Tests for RegimeDataCollector session cache and setter methods."""

    def test_set_global_cues(self):
        """set_global_cues stores data in the session cache."""
        md = _make_market_data()
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        cues = {
            "sgx_direction": "UP",
            "sgx_change_pct": 0.5,
            "sp500_change_pct": 1.2,
            "nasdaq_change_pct": 0.8,
        }
        collector.set_global_cues(cues)

        assert collector._session_cache["global_cues"] == cues

    def test_set_prev_day_data(self):
        """set_prev_day_data stores data in the session cache."""
        md = _make_market_data()
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        prev_data = {"high": 18000, "low": 17800, "close": 17900}
        collector.set_prev_day_data(prev_data)

        assert collector._session_cache["prev_day_data"] == prev_data

    def test_reset_session(self):
        """reset_session clears the session cache and pre-market data."""
        md = _make_market_data()
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        collector.set_global_cues({"sgx_direction": "UP"})
        collector.set_prev_day_data({"high": 18000})
        collector._pre_market_data = PreMarketData(india_vix=15.0)

        collector.reset_session()

        assert collector._session_cache == {}
        assert collector._pre_market_data is None


# ---------------------------------------------------------------------------
# collect_regime_inputs tests
# ---------------------------------------------------------------------------


class TestCollectRegimeInputs:
    """Tests for collect_regime_inputs method."""

    async def test_collect_regime_inputs_minimal(self):
        """With no data sources, inputs should have None fields but not raise."""
        md = _make_market_data(vix=None, nifty_data=None)
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        inputs = await collector.collect_regime_inputs()

        assert isinstance(inputs, RegimeInputs)
        assert inputs.collected_at is not None
        # VIX is None since market_data.get_vix returned None
        assert inputs.india_vix is None

    async def test_collect_regime_inputs_with_vix_from_pre_market(self):
        """When pre-market data was collected, VIX should come from cache."""
        md = _make_market_data(vix=16.0, nifty_data=None)
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        # Simulate pre-market data collection
        collector._pre_market_data = PreMarketData(
            india_vix=16.0,
            sgx_direction="UP",
            sp500_change_pct=0.5,
            fii_net_crores=500.0,
            dii_net_crores=-200.0,
        )

        inputs = await collector.collect_regime_inputs()

        assert inputs.india_vix == 16.0
        assert inputs.sgx_direction == "UP"
        assert inputs.sp500_change_pct == 0.5
        assert inputs.fii_net_crores == 500.0
        assert inputs.dii_net_crores == -200.0

    async def test_collect_regime_inputs_with_nifty_data(self):
        """Nifty data should be used to compute gap, range, and direction."""
        nifty_data = {
            "open": 18000.0,
            "prev_close": 17900.0,
            "high": 18100.0,
            "low": 17950.0,
            "ltp": 18050.0,
        }
        md = _make_market_data(vix=15.0, nifty_data=nifty_data)
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        inputs = await collector.collect_regime_inputs()

        # gap = (18000 - 17900) / 17900 * 100 = 0.5586..
        assert inputs.nifty_gap_pct is not None
        assert inputs.nifty_gap_pct == pytest.approx(
            (18000.0 - 17900.0) / 17900.0 * 100, rel=1e-3,
        )
        # range = (18100 - 17950) / 18000 * 100 = 0.8333..
        assert inputs.nifty_first_15_range_pct is not None
        assert inputs.nifty_first_15_range_pct == pytest.approx(
            (18100.0 - 17950.0) / 18000.0 * 100, rel=1e-3,
        )
        # ltp > open => direction = UP
        assert inputs.nifty_first_15_direction == "UP"

    async def test_collect_regime_inputs_down_direction(self):
        """When LTP < open, direction should be DOWN."""
        nifty_data = {
            "open": 18000.0,
            "prev_close": 17900.0,
            "high": 18050.0,
            "low": 17850.0,
            "ltp": 17900.0,
        }
        md = _make_market_data(vix=15.0, nifty_data=nifty_data)
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        inputs = await collector.collect_regime_inputs()
        assert inputs.nifty_first_15_direction == "DOWN"

    async def test_collect_regime_inputs_flat_direction(self):
        """When LTP is very close to open, direction should be FLAT."""
        nifty_data = {
            "open": 18000.0,
            "prev_close": 17900.0,
            "high": 18050.0,
            "low": 17950.0,
            "ltp": 18000.0,  # exactly at open
        }
        md = _make_market_data(vix=15.0, nifty_data=nifty_data)
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        inputs = await collector.collect_regime_inputs()
        assert inputs.nifty_first_15_direction == "FLAT"

    async def test_collect_regime_inputs_with_prev_day_data(self):
        """Previous day data should compute prev_day_range_pct."""
        md = _make_market_data(vix=None, nifty_data=None)
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        collector.set_prev_day_data({
            "high": 18100.0,
            "low": 17900.0,
            "close": 18000.0,
        })

        inputs = await collector.collect_regime_inputs()

        # (18100 - 17900) / 18000 * 100 = 1.111...
        assert inputs.prev_day_range_pct is not None
        assert inputs.prev_day_range_pct == pytest.approx(
            (18100.0 - 17900.0) / 18000.0 * 100, rel=1e-3,
        )


# ---------------------------------------------------------------------------
# collect_pre_market_data tests
# ---------------------------------------------------------------------------


class TestCollectPreMarketData:
    """Tests for collect_pre_market_data method."""

    async def test_collect_pre_market_data_minimal(self):
        """With no data sources, pre-market data should have None fields."""
        md = _make_market_data(vix=None, nifty_data=None)
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        data = await collector.collect_pre_market_data()

        assert isinstance(data, PreMarketData)
        assert data.collected_at is not None
        # VIX fetch returned None
        assert data.india_vix is None

    async def test_collect_pre_market_data_with_vix(self):
        """Pre-market data should include VIX when available."""
        md = _make_market_data(vix=16.5)
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        data = await collector.collect_pre_market_data()

        assert data.india_vix == 16.5

    async def test_collect_pre_market_data_caches_result(self):
        """Pre-market data should be cached for later use."""
        md = _make_market_data(vix=16.5)
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        data = await collector.collect_pre_market_data()

        cached = collector.get_cached_pre_market_data()
        assert cached is data


# ---------------------------------------------------------------------------
# Fetch methods
# ---------------------------------------------------------------------------


class TestFetchMethods:
    """Tests for individual fetch methods."""

    async def test_fetch_current_vix_primary(self):
        """Primary VIX source should be used when available."""
        md = _make_market_data(vix=17.5)
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        vix = await collector.fetch_current_vix()
        assert vix == 17.5

    async def test_fetch_current_vix_cache_fallback(self):
        """Session cache should be used when primary VIX source fails."""
        md = _make_market_data(vix=None)
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        collector._session_cache["india_vix"] = 16.0

        vix = await collector.fetch_current_vix()
        assert vix == 16.0

    async def test_fetch_current_vix_all_fail(self):
        """When all VIX sources fail, return None."""
        md = _make_market_data(vix=None)
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        vix = await collector.fetch_current_vix()
        assert vix is None

    async def test_fetch_global_cues_from_cache(self):
        """Global cues should return cached data."""
        md = _make_market_data()
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        collector.set_global_cues({
            "sgx_direction": "DOWN",
            "sp500_change_pct": -0.5,
        })

        cues = await collector.fetch_global_cues()
        assert cues["sgx_direction"] == "DOWN"
        assert cues["sp500_change_pct"] == -0.5

    async def test_fetch_global_cues_empty(self):
        """Global cues with no cache should return all-None dict."""
        md = _make_market_data()
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        cues = await collector.fetch_global_cues()
        assert cues["sgx_direction"] is None
        assert cues["sp500_change_pct"] is None

    async def test_fetch_fii_dii_from_cache(self):
        """FII/DII should return cached values."""
        md = _make_market_data()
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        collector._session_cache["fii_dii"] = (500.0, -300.0)

        fii, dii = await collector.fetch_fii_dii()
        assert fii == 500.0
        assert dii == -300.0

    async def test_fetch_fii_dii_no_cache(self):
        """FII/DII with no cache should return (None, None)."""
        md = _make_market_data()
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        fii, dii = await collector.fetch_fii_dii()
        assert fii is None
        assert dii is None

    async def test_get_current_nifty_data_via_get_nifty_data(self):
        """Should use get_nifty_data when available."""
        expected = {"ltp": 18000, "open": 17900}
        md = _make_market_data(nifty_data=expected)
        config = _make_config()
        collector = RegimeDataCollector(md, config)

        result = await collector.get_current_nifty_data()
        assert result == expected
