"""Tests for RegimeContextStage."""

import types
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from signalpilot.db.models import RegimeClassification
from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stages.regime_context import RegimeContextStage
from signalpilot.utils.constants import IST


def _make_config(**overrides):
    """Build a SimpleNamespace config with defaults."""
    defaults = {
        "regime_enabled": True,
        "regime_shadow_mode": False,
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _make_classifier(cached_regime=None):
    """Build a mock MarketRegimeClassifier that returns the given cached regime."""
    classifier = MagicMock()
    classifier.get_cached_regime = MagicMock(return_value=cached_regime)
    return classifier


def _make_ctx() -> ScanContext:
    """Build a fresh ScanContext with default values."""
    return ScanContext(
        cycle_id="test-cycle-001",
        now=datetime.now(IST),
    )


# ---------------------------------------------------------------------------
# Passthrough tests
# ---------------------------------------------------------------------------


class TestPassthrough:
    """Tests for conditions where the stage should not modify context."""

    async def test_no_classifier_passthrough(self):
        """When classifier is None, context should be returned unchanged."""
        config = _make_config()
        stage = RegimeContextStage(None, config)
        ctx = _make_ctx()

        result = await stage.process(ctx)

        assert result.regime is None
        assert result.regime_confidence == 0.0
        assert result.regime_min_stars == 3
        assert result.regime_position_modifier == 1.0
        assert result.regime_max_positions is None
        assert result.regime_strategy_weights is None

    async def test_disabled_passthrough(self):
        """When regime_enabled=False, context should be returned unchanged."""
        config = _make_config(regime_enabled=False)
        classifier = _make_classifier(cached_regime=RegimeClassification(
            regime="TRENDING", confidence=0.8,
        ))
        stage = RegimeContextStage(classifier, config)
        ctx = _make_ctx()

        result = await stage.process(ctx)

        assert result.regime is None
        assert result.regime_confidence == 0.0

    async def test_no_cached_regime(self):
        """Before 9:30 AM (no cached regime), context should be returned unchanged."""
        config = _make_config()
        classifier = _make_classifier(cached_regime=None)
        stage = RegimeContextStage(classifier, config)
        ctx = _make_ctx()

        result = await stage.process(ctx)

        assert result.regime is None
        assert result.regime_confidence == 0.0
        assert result.regime_min_stars == 3
        assert result.regime_position_modifier == 1.0


# ---------------------------------------------------------------------------
# Shadow mode tests
# ---------------------------------------------------------------------------


class TestShadowMode:
    """Tests for shadow mode behavior."""

    async def test_shadow_mode(self):
        """In shadow mode, regime/confidence set but modifiers NOT applied."""
        config = _make_config(regime_shadow_mode=True)
        classification = RegimeClassification(
            regime="VOLATILE",
            confidence=0.85,
            strategy_weights={"gap_go": 25, "orb": 25, "vwap": 25},
            min_star_rating=5,
            max_positions=4,
            position_size_modifier=0.65,
            classified_at=datetime.now(IST),
        )
        classifier = _make_classifier(cached_regime=classification)
        stage = RegimeContextStage(classifier, config)
        ctx = _make_ctx()

        result = await stage.process(ctx)

        # Regime identification IS set
        assert result.regime == "VOLATILE"
        assert result.regime_confidence == 0.85

        # Modifiers are NOT applied (still at defaults)
        assert result.regime_min_stars == 3
        assert result.regime_position_modifier == 1.0
        assert result.regime_max_positions is None
        assert result.regime_strategy_weights is None


# ---------------------------------------------------------------------------
# Active mode tests
# ---------------------------------------------------------------------------


class TestActiveMode:
    """Tests for active mode behavior."""

    async def test_active_mode(self):
        """In active mode, all modifiers should be applied to context."""
        config = _make_config(regime_shadow_mode=False)
        classification = RegimeClassification(
            regime="TRENDING",
            confidence=0.75,
            strategy_weights={"gap_go": 45, "orb": 35, "vwap": 20},
            min_star_rating=3,
            max_positions=8,
            position_size_modifier=1.0,
            classified_at=datetime.now(IST),
        )
        classifier = _make_classifier(cached_regime=classification)
        stage = RegimeContextStage(classifier, config)
        ctx = _make_ctx()

        result = await stage.process(ctx)

        assert result.regime == "TRENDING"
        assert result.regime_confidence == 0.75
        assert result.regime_min_stars == 3
        assert result.regime_position_modifier == 1.0
        assert result.regime_max_positions == 8
        assert result.regime_strategy_weights == {"gap_go": 45, "orb": 35, "vwap": 20}

    async def test_volatile_regime_modifiers(self):
        """Verify specific VOLATILE regime values are applied correctly."""
        config = _make_config(regime_shadow_mode=False)
        classification = RegimeClassification(
            regime="VOLATILE",
            confidence=0.9,
            strategy_weights={"gap_go": 25, "orb": 25, "vwap": 25},
            min_star_rating=5,
            max_positions=4,
            position_size_modifier=0.65,
            classified_at=datetime.now(IST),
        )
        classifier = _make_classifier(cached_regime=classification)
        stage = RegimeContextStage(classifier, config)
        ctx = _make_ctx()

        result = await stage.process(ctx)

        assert result.regime == "VOLATILE"
        assert result.regime_confidence == 0.9
        assert result.regime_min_stars == 5
        assert result.regime_position_modifier == 0.65
        assert result.regime_max_positions == 4
        assert result.regime_strategy_weights == {"gap_go": 25, "orb": 25, "vwap": 25}

    async def test_ranging_regime_modifiers(self):
        """Verify specific RANGING regime values are applied correctly."""
        config = _make_config(regime_shadow_mode=False)
        classification = RegimeClassification(
            regime="RANGING",
            confidence=0.6,
            strategy_weights={"gap_go": 20, "orb": 30, "vwap": 50},
            min_star_rating=3,
            max_positions=6,
            position_size_modifier=0.85,
            classified_at=datetime.now(IST),
        )
        classifier = _make_classifier(cached_regime=classification)
        stage = RegimeContextStage(classifier, config)
        ctx = _make_ctx()

        result = await stage.process(ctx)

        assert result.regime == "RANGING"
        assert result.regime_confidence == 0.6
        assert result.regime_min_stars == 3
        assert result.regime_position_modifier == 0.85
        assert result.regime_max_positions == 6
        assert result.regime_strategy_weights == {"gap_go": 20, "orb": 30, "vwap": 50}


# ---------------------------------------------------------------------------
# Stage name test
# ---------------------------------------------------------------------------


class TestStageName:
    """Test for the stage name property."""

    def test_name(self):
        """Stage name should be 'RegimeContext'."""
        config = _make_config()
        stage = RegimeContextStage(None, config)
        assert stage.name == "RegimeContext"
