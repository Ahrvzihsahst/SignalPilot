"""Tests for regime-related Telegram handler functions."""

import types
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from signalpilot.db.models import RegimeClassification
from signalpilot.telegram.handlers import (
    handle_morning_command,
    handle_regime_command,
    handle_regime_history_command,
    handle_regime_override_command,
    handle_vix_command,
)
from signalpilot.utils.constants import IST


def _make_classification(**overrides) -> RegimeClassification:
    """Build a RegimeClassification with sensible defaults."""
    defaults = {
        "regime": "TRENDING",
        "confidence": 0.75,
        "trending_score": 0.5,
        "ranging_score": 0.2,
        "volatile_score": 0.3,
        "india_vix": 15.0,
        "nifty_gap_pct": 1.5,
        "nifty_first_15_range_pct": 0.6,
        "nifty_first_15_direction": "UP",
        "directional_alignment": 0.75,
        "sp500_change_pct": 0.8,
        "sgx_direction": "UP",
        "fii_net_crores": 500.0,
        "dii_net_crores": -200.0,
        "strategy_weights": {"gap_go": 45, "orb": 35, "vwap": 20},
        "min_star_rating": 3,
        "max_positions": 8,
        "position_size_modifier": 1.0,
        "classified_at": datetime(2026, 2, 28, 9, 30, tzinfo=IST),
    }
    defaults.update(overrides)
    return RegimeClassification(**defaults)


# ---------------------------------------------------------------------------
# handle_regime_command
# ---------------------------------------------------------------------------


class TestRegimeCommand:
    """Tests for handle_regime_command."""

    async def test_regime_command_no_classifier(self):
        """When classifier is None, should return 'not configured' message."""
        result = await handle_regime_command(None)
        assert "not configured" in result

    async def test_regime_command_no_classification(self):
        """When no cached regime, should return 'no classification yet' message."""
        classifier = MagicMock()
        classifier.get_cached_regime = MagicMock(return_value=None)

        result = await handle_regime_command(classifier)
        assert "No regime classification yet" in result
        assert "9:30 AM" in result

    async def test_regime_command_with_classification(self):
        """When cached regime exists, should return formatted display."""
        classification = _make_classification()
        classifier = MagicMock()
        classifier.get_cached_regime = MagicMock(return_value=classification)

        result = await handle_regime_command(classifier)

        assert "TRENDING" in result
        assert "MARKET REGIME" in result


# ---------------------------------------------------------------------------
# handle_regime_history_command
# ---------------------------------------------------------------------------


class TestRegimeHistoryCommand:
    """Tests for handle_regime_history_command."""

    async def test_regime_history_command_no_repo(self):
        """When repo is None, should return 'not configured' message."""
        result = await handle_regime_history_command(None)
        assert "not configured" in result

    @patch("signalpilot.telegram.formatters.format_regime_history")
    async def test_regime_history_command(self, mock_format):
        """Should call get_regime_history and return formatted history."""
        mock_format.return_value = "formatted history"
        repo = AsyncMock()
        history_data = [
            {
                "regime_date": "2026-02-28",
                "regime": "TRENDING",
                "confidence": 0.75,
                "classification_time": "09:30:00",
            },
            {
                "regime_date": "2026-02-27",
                "regime": "RANGING",
                "confidence": 0.6,
                "classification_time": "09:30:00",
            },
        ]
        repo.get_regime_history = AsyncMock(return_value=history_data)

        result = await handle_regime_history_command(repo, days=7)

        assert isinstance(result, str)
        repo.get_regime_history.assert_awaited_once_with(7)
        # Handler passes (history, days) to format_regime_history
        mock_format.assert_called_once_with(history_data, 7)

    @patch("signalpilot.telegram.formatters.format_regime_history")
    async def test_regime_history_command_empty(self, mock_format):
        """Should handle empty history gracefully."""
        mock_format.return_value = "no history"
        repo = AsyncMock()
        repo.get_regime_history = AsyncMock(return_value=[])

        result = await handle_regime_history_command(repo, days=7)
        assert isinstance(result, str)
        mock_format.assert_called_once_with([], 7)


# ---------------------------------------------------------------------------
# handle_regime_override_command
# ---------------------------------------------------------------------------


class TestRegimeOverrideCommand:
    """Tests for handle_regime_override_command."""

    async def test_regime_override_command_no_classifier(self):
        """When classifier is None, should return 'not configured' message."""
        result = await handle_regime_override_command(None, "REGIME OVERRIDE VOLATILE")
        assert "not configured" in result

    async def test_regime_override_command_valid(self):
        """Valid override command should apply the override."""
        classifier = MagicMock()
        classification = _make_classification(regime="VOLATILE", confidence=1.0)
        classifier.apply_override = MagicMock(return_value=classification)

        result = await handle_regime_override_command(
            classifier, "REGIME OVERRIDE VOLATILE",
        )

        assert "overridden" in result.lower() or "VOLATILE" in result
        classifier.apply_override.assert_called_once_with("VOLATILE")

    async def test_regime_override_command_case_insensitive(self):
        """Override command should be case-insensitive."""
        classifier = MagicMock()
        classification = _make_classification(regime="TRENDING", confidence=1.0)
        classifier.apply_override = MagicMock(return_value=classification)

        result = await handle_regime_override_command(
            classifier, "regime override trending",
        )

        classifier.apply_override.assert_called_once_with("TRENDING")

    async def test_regime_override_command_invalid_text(self):
        """Invalid override text should return usage message."""
        classifier = MagicMock()

        result = await handle_regime_override_command(
            classifier, "REGIME OVERRIDE INVALID",
        )

        assert "Usage" in result

    async def test_regime_override_command_no_regime_name(self):
        """Missing regime name should return usage message."""
        classifier = MagicMock()

        result = await handle_regime_override_command(
            classifier, "REGIME OVERRIDE",
        )

        assert "Usage" in result

    async def test_regime_override_command_apply_returns_none(self):
        """When apply_override returns None, should return failure message."""
        classifier = MagicMock()
        classifier.apply_override = MagicMock(return_value=None)

        result = await handle_regime_override_command(
            classifier, "REGIME OVERRIDE VOLATILE",
        )

        assert "Failed" in result


# ---------------------------------------------------------------------------
# handle_vix_command
# ---------------------------------------------------------------------------


class TestVixCommand:
    """Tests for handle_vix_command."""

    async def test_vix_command_no_collector(self):
        """When collector is None, should return 'not configured' message."""
        result = await handle_vix_command(None)
        assert "not configured" in result

    async def test_vix_command_vix_unavailable(self):
        """When VIX is None, should return 'could not fetch' message."""
        collector = AsyncMock()
        collector.fetch_current_vix = AsyncMock(return_value=None)

        result = await handle_vix_command(collector)
        assert "Could not fetch" in result

    async def test_vix_command_very_calm(self):
        """VIX < 12 should show 'Very calm' interpretation."""
        collector = AsyncMock()
        collector.fetch_current_vix = AsyncMock(return_value=10.5)

        result = await handle_vix_command(collector)

        assert "10.50" in result
        assert "Very calm" in result

    async def test_vix_command_normal(self):
        """VIX 12-14 should show 'Normal' interpretation."""
        collector = AsyncMock()
        collector.fetch_current_vix = AsyncMock(return_value=13.0)

        result = await handle_vix_command(collector)

        assert "13.00" in result
        assert "Normal" in result

    async def test_vix_command_slightly_elevated(self):
        """VIX 14-18 should show 'Slightly elevated' interpretation."""
        collector = AsyncMock()
        collector.fetch_current_vix = AsyncMock(return_value=16.0)

        result = await handle_vix_command(collector)

        assert "16.00" in result
        assert "Slightly elevated" in result

    async def test_vix_command_high(self):
        """VIX 18-22 should show 'High' interpretation."""
        collector = AsyncMock()
        collector.fetch_current_vix = AsyncMock(return_value=20.0)

        result = await handle_vix_command(collector)

        assert "20.00" in result
        assert "High" in result

    async def test_vix_command_very_high(self):
        """VIX >= 22 should show 'Very high' interpretation."""
        collector = AsyncMock()
        collector.fetch_current_vix = AsyncMock(return_value=25.0)

        result = await handle_vix_command(collector)

        assert "25.00" in result
        assert "Very high" in result
        assert "defensive" in result


# ---------------------------------------------------------------------------
# handle_morning_command
# ---------------------------------------------------------------------------


class TestMorningCommand:
    """Tests for handle_morning_command."""

    async def test_morning_command_no_generator(self):
        """When generator is None, should return 'not configured' message."""
        result = await handle_morning_command(None)
        assert "not configured" in result

    async def test_morning_command_no_cached_brief(self):
        """When no cached brief, should return 'not available yet' message."""
        generator = MagicMock()
        generator.get_cached_brief = MagicMock(return_value=None)

        result = await handle_morning_command(generator)
        assert "No morning brief available" in result
        assert "8:45 AM" in result

    async def test_morning_command_with_cached_brief(self):
        """When cached brief exists, should return it."""
        generator = MagicMock()
        brief_text = "SIGNALPILOT MORNING BRIEF\nRegime: TRENDING\n..."
        generator.get_cached_brief = MagicMock(return_value=brief_text)

        result = await handle_morning_command(generator)
        assert result == brief_text
