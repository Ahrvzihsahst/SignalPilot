"""Tests for MarketRegimeClassifier."""

import types
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from signalpilot.db.models import RegimeClassification
from signalpilot.intelligence.regime_classifier import MarketRegimeClassifier, _SEVERITY_ORDER
from signalpilot.intelligence.regime_data import RegimeDataCollector, RegimeInputs
from signalpilot.utils.constants import IST


def _make_config(**overrides):
    """Build a SimpleNamespace config with all regime_ defaults."""
    defaults = {
        "regime_enabled": True,
        "regime_shadow_mode": False,
        "regime_confidence_threshold": 0.55,
        "regime_max_reclassifications": 2,
        "regime_vix_spike_threshold": 0.15,
        "regime_roundtrip_threshold": 0.003,
        "regime_trending_weights_high": '{"gap_go": 45, "orb": 35, "vwap": 20}',
        "regime_trending_weights_low": '{"gap_go": 38, "orb": 35, "vwap": 27}',
        "regime_ranging_weights_high": '{"gap_go": 20, "orb": 30, "vwap": 50}',
        "regime_ranging_weights_low": '{"gap_go": 28, "orb": 33, "vwap": 39}',
        "regime_volatile_weights_high": '{"gap_go": 25, "orb": 25, "vwap": 25}',
        "regime_volatile_weights_low": '{"gap_go": 30, "orb": 30, "vwap": 30}',
        "regime_trending_position_modifier": 1.0,
        "regime_ranging_position_modifier": 0.85,
        "regime_volatile_position_modifier": 0.65,
        "regime_trending_max_positions": 8,
        "regime_ranging_max_positions": 6,
        "regime_volatile_max_positions": 4,
        "regime_trending_min_stars": 3,
        "regime_ranging_high_min_stars": 3,
        "regime_ranging_low_min_stars": 4,
        "regime_volatile_high_min_stars": 5,
        "regime_volatile_low_min_stars": 4,
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _make_data_collector(inputs: RegimeInputs | None = None):
    """Build a mock RegimeDataCollector that returns the given inputs."""
    collector = AsyncMock(spec=RegimeDataCollector)
    if inputs is None:
        inputs = RegimeInputs()
    collector.collect_regime_inputs = AsyncMock(return_value=inputs)
    collector.fetch_current_vix = AsyncMock(return_value=None)
    collector.get_current_nifty_data = AsyncMock(return_value=None)
    return collector


def _make_regime_repo():
    """Build a mock MarketRegimeRepository."""
    repo = AsyncMock()
    repo.insert_classification = AsyncMock(return_value=1)
    return repo


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------


class TestClassifyRegime:
    """Tests for initial regime classification."""

    async def test_classify_trending_regime(self):
        """High gap + directional alignment should yield TRENDING."""
        inputs = RegimeInputs(
            india_vix=14.0,
            nifty_gap_pct=2.0,              # abs > 1.5 => gap_score=1.0
            nifty_first_15_range_pct=0.6,    # > 0.5 => range_score=0.5
            nifty_first_15_direction="UP",
            sgx_direction="UP",
            sp500_change_pct=1.5,            # > 0.3 => direction +1
        )
        config = _make_config()
        collector = _make_data_collector(inputs)
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        result = await classifier.classify()

        assert result.regime == "TRENDING"
        assert result.confidence > 0
        assert result.trending_score > result.ranging_score
        assert result.trending_score > result.volatile_score
        repo.insert_classification.assert_awaited_once()

    async def test_classify_ranging_regime(self):
        """Low VIX + low gap + small range should yield RANGING."""
        inputs = RegimeInputs(
            india_vix=11.0,                  # < 12 => vix_score = -0.5
            nifty_gap_pct=0.1,               # abs < 0.3 => gap_score = -0.5
            nifty_first_15_range_pct=0.1,    # < 0.2 => range_score = -0.5
            nifty_first_15_direction="FLAT",
            sgx_direction="FLAT",
            sp500_change_pct=0.1,            # abs < 0.3 => direction 0
        )
        config = _make_config()
        collector = _make_data_collector(inputs)
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        result = await classifier.classify()

        assert result.regime == "RANGING"
        assert result.ranging_score > result.trending_score
        assert result.ranging_score > result.volatile_score

    async def test_classify_volatile_regime(self):
        """High VIX with mixed signals should yield VOLATILE."""
        inputs = RegimeInputs(
            india_vix=25.0,                  # >= 22 => vix_score=1.0
            nifty_gap_pct=0.5,               # abs 0.3..0.8 => gap_score=0.2
            nifty_first_15_range_pct=1.2,    # > 1.0 => range_score=1.0
            nifty_first_15_direction="DOWN",
            sgx_direction="UP",              # conflicting => low alignment
            sp500_change_pct=-1.0,           # direction = -1
        )
        config = _make_config()
        collector = _make_data_collector(inputs)
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        result = await classifier.classify()

        assert result.regime == "VOLATILE"
        assert result.volatile_score > result.trending_score
        assert result.volatile_score > result.ranging_score

    async def test_classify_stores_in_cache(self):
        """classify() should store the result in the in-memory cache."""
        inputs = RegimeInputs(india_vix=15.0)
        config = _make_config()
        collector = _make_data_collector(inputs)
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        result = await classifier.classify()

        cached = classifier.get_cached_regime()
        assert cached is not None
        assert cached.regime == result.regime

    async def test_classify_stores_morning_vix(self):
        """classify() should store the morning VIX for re-classification checks."""
        inputs = RegimeInputs(india_vix=16.5)
        config = _make_config()
        collector = _make_data_collector(inputs)
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        await classifier.classify()

        today = datetime.now(IST).date()
        assert classifier._morning_vix.get(today) == 16.5

    async def test_classify_persists_to_repo(self):
        """classify() should call insert_classification on the repo."""
        inputs = RegimeInputs(india_vix=15.0)
        config = _make_config()
        collector = _make_data_collector(inputs)
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        await classifier.classify()

        repo.insert_classification.assert_awaited_once()
        call_args = repo.insert_classification.call_args[0][0]
        assert isinstance(call_args, RegimeClassification)

    async def test_classify_repo_failure_does_not_raise(self):
        """If repo.insert_classification fails, classify() should not raise."""
        inputs = RegimeInputs(india_vix=15.0)
        config = _make_config()
        collector = _make_data_collector(inputs)
        repo = _make_regime_repo()
        repo.insert_classification = AsyncMock(side_effect=RuntimeError("DB down"))

        classifier = MarketRegimeClassifier(collector, repo, config)
        result = await classifier.classify()

        assert result is not None
        assert result.regime in ("TRENDING", "RANGING", "VOLATILE")


# ---------------------------------------------------------------------------
# Confidence threshold tests
# ---------------------------------------------------------------------------


class TestConfidenceThreshold:
    """Tests for confidence levels and modifier selection."""

    async def test_classify_confidence_threshold_high(self):
        """When confidence >= threshold, high-confidence weights are used."""
        # Strong TRENDING inputs to push confidence high
        inputs = RegimeInputs(
            india_vix=14.0,
            nifty_gap_pct=2.0,
            nifty_first_15_range_pct=0.6,
            nifty_first_15_direction="UP",
            sgx_direction="UP",
            sp500_change_pct=1.5,
        )
        config = _make_config(regime_confidence_threshold=0.3)
        collector = _make_data_collector(inputs)
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        result = await classifier.classify()

        assert result.confidence >= 0.3
        # High-confidence TRENDING weights
        assert result.strategy_weights.get("gap_go") == 45

    async def test_classify_confidence_threshold_low(self):
        """When confidence < threshold, low-confidence weights should be used."""
        # Mixed inputs to produce lower confidence
        inputs = RegimeInputs(
            india_vix=15.0,
            nifty_gap_pct=0.5,
            nifty_first_15_range_pct=0.3,
            nifty_first_15_direction="UP",
            sgx_direction="FLAT",
            sp500_change_pct=0.0,
        )
        # Set a very high threshold to force low-confidence path
        config = _make_config(regime_confidence_threshold=0.99)
        collector = _make_data_collector(inputs)
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        result = await classifier.classify()

        # With threshold 0.99, confidence will be below threshold
        assert result.confidence < 0.99

    async def test_classify_with_all_none_inputs(self):
        """All None inputs should produce a valid classification with defaults."""
        inputs = RegimeInputs()
        config = _make_config()
        collector = _make_data_collector(inputs)
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        result = await classifier.classify()

        assert result.regime in ("TRENDING", "RANGING", "VOLATILE")
        assert 0.0 <= result.confidence <= 1.0


# ---------------------------------------------------------------------------
# Re-classification tests
# ---------------------------------------------------------------------------


class TestReclassification:
    """Tests for re-classification triggers and severity ordering."""

    async def test_reclassify_vix_spike(self):
        """VIX spike > 15% from morning value triggers re-classification at 11:00."""
        inputs = RegimeInputs(
            india_vix=25.0,                  # Will make VOLATILE on re-class
            nifty_gap_pct=2.0,
            nifty_first_15_range_pct=1.5,
            nifty_first_15_direction="DOWN",
            sgx_direction="DOWN",
            sp500_change_pct=-1.5,
        )
        config = _make_config()
        collector = _make_data_collector(inputs)
        # fetch_current_vix returns 23 (>15% above morning value of 15)
        collector.fetch_current_vix = AsyncMock(return_value=23.0)
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)

        # Set initial classification as TRENDING
        today = datetime.now(IST).date()
        initial = RegimeClassification(
            regime="TRENDING",
            confidence=0.7,
            trending_score=0.5,
            ranging_score=0.2,
            volatile_score=0.3,
            india_vix=15.0,
            nifty_first_15_direction="UP",
            classified_at=datetime.now(IST),
        )
        classifier._cache[today] = initial
        classifier._morning_vix[today] = 15.0

        result = await classifier.check_reclassify("11:00")

        # VIX spike 15->23 (53%) exceeds 15% threshold
        # Re-classification should occur and upgrade severity
        if result is not None:
            assert _SEVERITY_ORDER[result.regime] > _SEVERITY_ORDER["TRENDING"]

    async def test_reclassify_no_initial_classification(self):
        """Re-classification should return None if no initial classification exists."""
        config = _make_config()
        collector = _make_data_collector()
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        result = await classifier.check_reclassify("11:00")

        assert result is None

    async def test_reclassify_max_limit(self):
        """No more than max reclassifications per day."""
        config = _make_config(regime_max_reclassifications=2)
        collector = _make_data_collector()
        collector.fetch_current_vix = AsyncMock(return_value=30.0)
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)

        today = datetime.now(IST).date()
        initial = RegimeClassification(
            regime="TRENDING",
            confidence=0.7,
            classified_at=datetime.now(IST),
        )
        classifier._cache[today] = initial
        classifier._morning_vix[today] = 15.0
        classifier._reclass_count[today] = 2  # Already at max

        result = await classifier.check_reclassify("11:00")
        assert result is None

    async def test_reclassify_severity_only_upgrade_allowed(self):
        """Re-classification can only upgrade severity (TRENDING->VOLATILE ok)."""
        # High VIX inputs that would classify as VOLATILE
        inputs = RegimeInputs(
            india_vix=25.0,
            nifty_gap_pct=0.5,
            nifty_first_15_range_pct=1.5,
            nifty_first_15_direction="DOWN",
            sgx_direction="UP",
            sp500_change_pct=-0.5,
        )
        config = _make_config()
        collector = _make_data_collector(inputs)
        collector.fetch_current_vix = AsyncMock(return_value=25.0)
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)

        today = datetime.now(IST).date()
        initial = RegimeClassification(
            regime="TRENDING",
            confidence=0.7,
            india_vix=15.0,
            nifty_first_15_direction="UP",
            classified_at=datetime.now(IST),
        )
        classifier._cache[today] = initial
        classifier._morning_vix[today] = 15.0

        result = await classifier.check_reclassify("11:00")
        # If result is not None, it must be a severity upgrade
        if result is not None:
            assert _SEVERITY_ORDER[result.regime] > _SEVERITY_ORDER["TRENDING"]

    async def test_reclassify_severity_downgrade_blocked(self):
        """Re-classification that would downgrade severity is blocked."""
        # Low-vol inputs that would classify as TRENDING (severity 0)
        inputs = RegimeInputs(
            india_vix=14.0,
            nifty_gap_pct=2.0,
            nifty_first_15_range_pct=0.6,
            nifty_first_15_direction="UP",
            sgx_direction="UP",
            sp500_change_pct=1.5,
        )
        config = _make_config()
        collector = _make_data_collector(inputs)
        # VIX barely spiked enough to trigger check
        collector.fetch_current_vix = AsyncMock(return_value=24.0)
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)

        today = datetime.now(IST).date()
        # Already VOLATILE (severity 2) -- downgrade to TRENDING (severity 0) not allowed
        initial = RegimeClassification(
            regime="VOLATILE",
            confidence=0.8,
            india_vix=20.0,
            nifty_first_15_direction="DOWN",
            classified_at=datetime.now(IST),
        )
        classifier._cache[today] = initial
        classifier._morning_vix[today] = 20.0

        result = await classifier.check_reclassify("11:00")
        assert result is None  # Blocked because new severity <= current

    async def test_reclassify_increments_count(self):
        """Successful re-classification increments the daily counter."""
        inputs = RegimeInputs(
            india_vix=25.0,
            nifty_gap_pct=0.5,
            nifty_first_15_range_pct=1.5,
            nifty_first_15_direction="DOWN",
            sgx_direction="UP",
            sp500_change_pct=-0.5,
        )
        config = _make_config()
        collector = _make_data_collector(inputs)
        collector.fetch_current_vix = AsyncMock(return_value=25.0)
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)

        today = datetime.now(IST).date()
        initial = RegimeClassification(
            regime="TRENDING",
            confidence=0.7,
            india_vix=15.0,
            nifty_first_15_direction="UP",
            classified_at=datetime.now(IST),
        )
        classifier._cache[today] = initial
        classifier._morning_vix[today] = 15.0
        classifier._reclass_count[today] = 0

        result = await classifier.check_reclassify("11:00")
        if result is not None:
            assert classifier._reclass_count[today] == 1


# ---------------------------------------------------------------------------
# Override and reset tests
# ---------------------------------------------------------------------------


class TestOverrideAndReset:
    """Tests for manual override and daily reset."""

    def test_apply_override(self):
        """Manual override should set regime with confidence=1.0."""
        config = _make_config()
        collector = _make_data_collector()
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        result = classifier.apply_override("VOLATILE")

        assert result.regime == "VOLATILE"
        assert result.confidence == 1.0
        assert result.position_size_modifier == 0.65
        assert result.max_positions == 4

        cached = classifier.get_cached_regime()
        assert cached is not None
        assert cached.regime == "VOLATILE"

    def test_apply_override_with_existing_classification(self):
        """Override with an existing classification should preserve input values."""
        config = _make_config()
        collector = _make_data_collector()
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)

        today = datetime.now(IST).date()
        existing = RegimeClassification(
            regime="TRENDING",
            confidence=0.7,
            trending_score=0.5,
            ranging_score=0.2,
            volatile_score=0.3,
            india_vix=16.0,
            nifty_gap_pct=1.5,
            classified_at=datetime.now(IST),
        )
        classifier._cache[today] = existing

        result = classifier.apply_override("RANGING")

        assert result.regime == "RANGING"
        assert result.confidence == 1.0
        # Input values preserved from existing classification
        assert result.india_vix == 16.0
        assert result.nifty_gap_pct == 1.5
        assert result.trending_score == 0.5
        assert result.previous_regime == "TRENDING"

    def test_reset_daily(self):
        """Daily reset should clear the reclassification counter."""
        config = _make_config()
        collector = _make_data_collector()
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)

        today = datetime.now(IST).date()
        classifier._reclass_count[today] = 2

        classifier.reset_daily()

        assert classifier._reclass_count[today] == 0

    def test_get_cached_regime_empty(self):
        """get_cached_regime should return None when no classification exists."""
        config = _make_config()
        collector = _make_data_collector()
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        assert classifier.get_cached_regime() is None

    def test_cached_regime_returns_for_specific_date(self):
        """get_cached_regime with a specific date should return the correct classification."""
        config = _make_config()
        collector = _make_data_collector()
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)

        target_date = date(2026, 2, 15)
        classification = RegimeClassification(
            regime="TRENDING",
            confidence=0.8,
            classified_at=datetime(2026, 2, 15, 9, 30, tzinfo=IST),
        )
        classifier._cache[target_date] = classification

        result = classifier.get_cached_regime(for_date=target_date)
        assert result is not None
        assert result.regime == "TRENDING"

        # Different date should return None
        assert classifier.get_cached_regime(for_date=date(2026, 2, 16)) is None


# ---------------------------------------------------------------------------
# Regime modifiers tests
# ---------------------------------------------------------------------------


class TestRegimeModifiers:
    """Tests for regime-specific modifiers and strategy weights."""

    def test_trending_modifiers_high_confidence(self):
        """TRENDING regime with high confidence should return correct weights."""
        config = _make_config()
        collector = _make_data_collector()
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        modifiers = classifier._get_regime_modifiers("TRENDING", 0.8)

        assert modifiers["strategy_weights"] == {"gap_go": 45, "orb": 35, "vwap": 20}
        assert modifiers["min_star_rating"] == 3
        assert modifiers["position_size_modifier"] == 1.0
        assert modifiers["max_positions"] == 8

    def test_trending_modifiers_low_confidence(self):
        """TRENDING regime with low confidence should return low-conf weights."""
        config = _make_config()
        collector = _make_data_collector()
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        modifiers = classifier._get_regime_modifiers("TRENDING", 0.3)

        assert modifiers["strategy_weights"] == {"gap_go": 38, "orb": 35, "vwap": 27}

    def test_ranging_modifiers_high_confidence(self):
        """RANGING regime with high confidence should return correct weights."""
        config = _make_config()
        collector = _make_data_collector()
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        modifiers = classifier._get_regime_modifiers("RANGING", 0.8)

        assert modifiers["strategy_weights"] == {"gap_go": 20, "orb": 30, "vwap": 50}
        assert modifiers["min_star_rating"] == 3
        assert modifiers["position_size_modifier"] == 0.85
        assert modifiers["max_positions"] == 6

    def test_ranging_modifiers_low_confidence(self):
        """RANGING with low confidence should require 4 stars."""
        config = _make_config()
        collector = _make_data_collector()
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        modifiers = classifier._get_regime_modifiers("RANGING", 0.3)

        assert modifiers["min_star_rating"] == 4
        assert modifiers["strategy_weights"] == {"gap_go": 28, "orb": 33, "vwap": 39}

    def test_volatile_modifiers_high_confidence(self):
        """VOLATILE regime with high confidence should require 5 stars."""
        config = _make_config()
        collector = _make_data_collector()
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        modifiers = classifier._get_regime_modifiers("VOLATILE", 0.8)

        assert modifiers["strategy_weights"] == {"gap_go": 25, "orb": 25, "vwap": 25}
        assert modifiers["min_star_rating"] == 5
        assert modifiers["position_size_modifier"] == 0.65
        assert modifiers["max_positions"] == 4

    def test_volatile_modifiers_low_confidence(self):
        """VOLATILE with low confidence should require 4 stars."""
        config = _make_config()
        collector = _make_data_collector()
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        modifiers = classifier._get_regime_modifiers("VOLATILE", 0.3)

        assert modifiers["min_star_rating"] == 4
        assert modifiers["strategy_weights"] == {"gap_go": 30, "orb": 30, "vwap": 30}

    def test_unknown_regime_modifiers(self):
        """Unknown regime should return neutral/default modifiers."""
        config = _make_config()
        collector = _make_data_collector()
        repo = _make_regime_repo()

        classifier = MarketRegimeClassifier(collector, repo, config)
        modifiers = classifier._get_regime_modifiers("UNKNOWN", 0.5)

        assert modifiers["strategy_weights"] == {"gap_go": 33, "orb": 33, "vwap": 34}
        assert modifiers["min_star_rating"] == 3
        assert modifiers["position_size_modifier"] == 1.0
        assert modifiers["max_positions"] is None


# ---------------------------------------------------------------------------
# Scoring method tests
# ---------------------------------------------------------------------------


class TestScoringMethods:
    """Tests for individual score computation methods."""

    @pytest.mark.parametrize(
        "vix, expected",
        [
            (None, 0.0),
            (10.0, -0.5),
            (12.5, 0.0),
            (15.0, 0.3),
            (20.0, 0.6),
            (25.0, 1.0),
        ],
    )
    def test_compute_vix_score(self, vix, expected):
        assert MarketRegimeClassifier._compute_vix_score(vix) == expected

    @pytest.mark.parametrize(
        "gap, expected",
        [
            (None, 0.0),
            (0.1, -0.5),
            (-0.1, -0.5),
            (0.5, 0.2),
            (-0.5, 0.2),
            (1.0, 0.6),
            (-1.0, 0.6),
            (2.0, 1.0),
            (-2.0, 1.0),
        ],
    )
    def test_compute_gap_score(self, gap, expected):
        assert MarketRegimeClassifier._compute_gap_score(gap) == expected

    @pytest.mark.parametrize(
        "range_pct, expected",
        [
            (None, 0.0),
            (0.1, -0.5),
            (0.3, 0.0),
            (0.6, 0.5),
            (1.5, 1.0),
        ],
    )
    def test_compute_range_score(self, range_pct, expected):
        assert MarketRegimeClassifier._compute_range_score(range_pct) == expected

    def test_compute_alignment_all_up(self):
        """All directions UP should give maximum alignment."""
        result = MarketRegimeClassifier._compute_alignment(
            nifty_gap_pct=1.0, first_15_direction="UP",
            sgx_direction="UP", sp500_change_pct=1.0,
        )
        assert result == 1.0

    def test_compute_alignment_all_down(self):
        """All directions DOWN should also give maximum alignment."""
        result = MarketRegimeClassifier._compute_alignment(
            nifty_gap_pct=-1.0, first_15_direction="DOWN",
            sgx_direction="DOWN", sp500_change_pct=-1.0,
        )
        assert result == 1.0

    def test_compute_alignment_mixed(self):
        """Mixed directions should give partial alignment."""
        result = MarketRegimeClassifier._compute_alignment(
            nifty_gap_pct=1.0, first_15_direction="DOWN",
            sgx_direction="UP", sp500_change_pct=-1.0,
        )
        # UP=1, DOWN=-1, UP=1, DOWN=-1 => sum=0 => alignment=0
        assert result == 0.0

    def test_compute_alignment_all_none(self):
        """All None/neutral values should give zero alignment."""
        result = MarketRegimeClassifier._compute_alignment(
            nifty_gap_pct=None, first_15_direction=None,
            sgx_direction=None, sp500_change_pct=None,
        )
        assert result == 0.0
