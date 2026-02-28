"""Tests for MorningBriefGenerator."""

import types
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.intelligence.morning_brief import MorningBriefGenerator
from signalpilot.intelligence.regime_data import PreMarketData, RegimeDataCollector
from signalpilot.utils.constants import IST


def _make_config(**overrides):
    """Build a SimpleNamespace config with defaults."""
    defaults = {
        "regime_enabled": True,
        "regime_shadow_mode": False,
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _make_data_collector(pre_market_data=None):
    """Build a mock RegimeDataCollector."""
    collector = AsyncMock(spec=RegimeDataCollector)
    if pre_market_data is None:
        pre_market_data = PreMarketData()
    collector.collect_pre_market_data = AsyncMock(return_value=pre_market_data)
    return collector


def _make_watchlist_repo(entries=None):
    """Build a mock WatchlistRepository."""
    repo = AsyncMock()
    repo.get_active_entries = AsyncMock(return_value=entries or [])
    return repo


# ---------------------------------------------------------------------------
# Brief generation tests
# ---------------------------------------------------------------------------


class TestGenerateBrief:
    """Tests for the generate() method."""

    async def test_generate_brief_with_data(self):
        """Brief should include all global cues, India context, and regime prediction."""
        pre_market = PreMarketData(
            india_vix=16.5,
            sp500_change_pct=0.8,
            nasdaq_change_pct=1.2,
            sgx_direction="UP",
            sgx_change_pct=0.5,
            nikkei_change_pct=-0.3,
            hang_seng_change_pct=-0.1,
            fii_net_crores=1000.0,
            dii_net_crores=-500.0,
            collected_at=datetime.now(IST),
        )
        config = _make_config()
        collector = _make_data_collector(pre_market)
        watchlist_repo = _make_watchlist_repo()

        generator = MorningBriefGenerator(collector, watchlist_repo, config)
        brief = await generator.generate()

        assert isinstance(brief, str)
        assert "MORNING BRIEF" in brief
        assert "GLOBAL CUES" in brief
        assert "S&P 500" in brief
        assert "+0.8%" in brief
        assert "Nasdaq" in brief
        assert "INDIA CONTEXT" in brief
        assert "16.5" in brief
        assert "FII" in brief
        assert "DII" in brief
        assert "REGIME PREDICTION" in brief
        assert "9:30 AM" in brief

    async def test_generate_brief_with_watchlist(self):
        """Brief should include watchlist entries when present."""
        pre_market = PreMarketData(
            india_vix=14.0,
            collected_at=datetime.now(IST),
        )
        config = _make_config()
        collector = _make_data_collector(pre_market)

        # Create mock watchlist entries with symbol attribute
        entry1 = types.SimpleNamespace(symbol="SBIN")
        entry2 = types.SimpleNamespace(symbol="TCS")
        watchlist_repo = _make_watchlist_repo([entry1, entry2])

        generator = MorningBriefGenerator(collector, watchlist_repo, config)
        brief = await generator.generate()

        assert "WATCHLIST ALERTS" in brief
        assert "SBIN" in brief
        assert "TCS" in brief

    async def test_generate_brief_no_watchlist(self):
        """Brief should not include watchlist section when empty."""
        pre_market = PreMarketData(
            india_vix=14.0,
            collected_at=datetime.now(IST),
        )
        config = _make_config()
        collector = _make_data_collector(pre_market)
        watchlist_repo = _make_watchlist_repo([])

        generator = MorningBriefGenerator(collector, watchlist_repo, config)
        brief = await generator.generate()

        assert "WATCHLIST ALERTS" not in brief

    async def test_generate_brief_with_none_values(self):
        """Brief should handle None values gracefully (showing 'N/A')."""
        pre_market = PreMarketData(collected_at=datetime.now(IST))
        config = _make_config()
        collector = _make_data_collector(pre_market)
        watchlist_repo = _make_watchlist_repo()

        generator = MorningBriefGenerator(collector, watchlist_repo, config)
        brief = await generator.generate()

        assert "N/A" in brief

    async def test_generate_brief_watchlist_repo_none(self):
        """Brief should not crash when watchlist_repo is None."""
        pre_market = PreMarketData(india_vix=14.0, collected_at=datetime.now(IST))
        config = _make_config()
        collector = _make_data_collector(pre_market)

        generator = MorningBriefGenerator(collector, None, config)
        brief = await generator.generate()

        assert isinstance(brief, str)
        assert "MORNING BRIEF" in brief

    async def test_generate_brief_watchlist_max_five(self):
        """Brief should show at most 5 watchlist entries."""
        pre_market = PreMarketData(india_vix=14.0, collected_at=datetime.now(IST))
        config = _make_config()
        collector = _make_data_collector(pre_market)

        entries = [types.SimpleNamespace(symbol=f"SYM{i}") for i in range(10)]
        watchlist_repo = _make_watchlist_repo(entries)

        generator = MorningBriefGenerator(collector, watchlist_repo, config)
        brief = await generator.generate()

        assert "SYM0" in brief
        assert "SYM4" in brief
        assert "SYM5" not in brief  # Only first 5 shown


# ---------------------------------------------------------------------------
# Regime prediction tests
# ---------------------------------------------------------------------------


class TestPredictRegime:
    """Tests for the _predict_regime method."""

    def test_predict_regime_high_vix_volatile(self):
        """High VIX (>=22) should strongly predict VOLATILE."""
        config = _make_config()
        collector = _make_data_collector()
        generator = MorningBriefGenerator(collector, None, config)

        data = PreMarketData(india_vix=25.0)
        predicted, reasoning = generator._predict_regime(data)

        assert predicted == "VOLATILE"
        assert "VIX elevated" in reasoning

    def test_predict_regime_moderate_vix_volatile(self):
        """Moderately high VIX (18-22) should signal VOLATILE with weight 1."""
        config = _make_config()
        collector = _make_data_collector()
        generator = MorningBriefGenerator(collector, None, config)

        data = PreMarketData(india_vix=20.0, sgx_direction="FLAT")
        predicted, reasoning = generator._predict_regime(data)

        assert "VIX moderately high" in reasoning

    def test_predict_regime_trending(self):
        """SGX UP and strong S&P move should predict TRENDING."""
        config = _make_config()
        collector = _make_data_collector()
        generator = MorningBriefGenerator(collector, None, config)

        data = PreMarketData(
            india_vix=14.0,
            sgx_direction="UP",
            sp500_change_pct=1.5,
        )
        predicted, reasoning = generator._predict_regime(data)

        assert predicted == "TRENDING"
        assert "SGX Nifty pointing UP" in reasoning
        assert "S&P 500 moved" in reasoning

    def test_predict_regime_ranging_low_vix(self):
        """Low VIX (<12) with flat SGX should predict RANGING."""
        config = _make_config()
        collector = _make_data_collector()
        generator = MorningBriefGenerator(collector, None, config)

        data = PreMarketData(
            india_vix=10.0,
            sgx_direction="FLAT",
            sp500_change_pct=0.1,
        )
        predicted, reasoning = generator._predict_regime(data)

        assert predicted == "RANGING"
        assert "VIX low" in reasoning
        assert "SGX Nifty flat" in reasoning

    def test_predict_regime_insufficient_data(self):
        """No data at all should return UNKNOWN with appropriate reasoning."""
        config = _make_config()
        collector = _make_data_collector()
        generator = MorningBriefGenerator(collector, None, config)

        data = PreMarketData()
        predicted, reasoning = generator._predict_regime(data)

        assert predicted == "UNKNOWN"
        assert "Insufficient" in reasoning

    def test_predict_regime_normal_vix_no_signal(self):
        """Normal VIX (12-18) with no other signals should default to TRENDING."""
        config = _make_config()
        collector = _make_data_collector()
        generator = MorningBriefGenerator(collector, None, config)

        data = PreMarketData(india_vix=13.0)
        predicted, reasoning = generator._predict_regime(data)

        # VIX normal gives reason but no score, so max is 0 and default is TRENDING
        assert predicted == "TRENDING"
        assert "VIX normal" in reasoning


# ---------------------------------------------------------------------------
# Cached brief tests
# ---------------------------------------------------------------------------


class TestCachedBrief:
    """Tests for get_cached_brief."""

    def test_cached_brief_initially_none(self):
        """Cached brief should be None before generation."""
        config = _make_config()
        collector = _make_data_collector()
        generator = MorningBriefGenerator(collector, None, config)

        assert generator.get_cached_brief() is None

    async def test_cached_brief_after_generation(self):
        """Cached brief should return the generated brief."""
        pre_market = PreMarketData(india_vix=14.0, collected_at=datetime.now(IST))
        config = _make_config()
        collector = _make_data_collector(pre_market)

        generator = MorningBriefGenerator(collector, None, config)
        brief = await generator.generate()

        cached = generator.get_cached_brief()
        assert cached is not None
        assert cached == brief
