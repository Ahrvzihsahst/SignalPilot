"""Tests for ConfidenceDetector."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from signalpilot.db.models import CandidateSignal, SignalDirection
from signalpilot.ranking.confidence import ConfidenceDetector
from signalpilot.utils.constants import IST


def _make_candidate(symbol: str, strategy_name: str, **kwargs) -> CandidateSignal:
    """Create a CandidateSignal for testing with sensible defaults."""
    return CandidateSignal(
        symbol=symbol,
        direction=kwargs.get("direction", SignalDirection.BUY),
        strategy_name=strategy_name,
        entry_price=kwargs.get("entry_price", 100.0),
        stop_loss=kwargs.get("stop_loss", 95.0),
        target_1=kwargs.get("target_1", 105.0),
        target_2=kwargs.get("target_2", 110.0),
        reason=kwargs.get("reason", "test signal"),
        generated_at=kwargs.get("generated_at", datetime.now(IST)),
    )


# ---------------------------------------------------------------------------
# _calculate_confirmation (static method)
# ---------------------------------------------------------------------------


class TestCalculateConfirmation:
    def test_single_strategy(self):
        result = ConfidenceDetector._calculate_confirmation(["Gap & Go"])
        assert result.confirmation_level == "single"
        assert result.star_boost == 0
        assert result.position_size_multiplier == 1.0

    def test_double_strategy(self):
        result = ConfidenceDetector._calculate_confirmation(["Gap & Go", "ORB"])
        assert result.confirmation_level == "double"
        assert result.star_boost == 1
        assert result.position_size_multiplier == 1.5
        assert set(result.confirmed_by) == {"Gap & Go", "ORB"}

    def test_triple_strategy(self):
        result = ConfidenceDetector._calculate_confirmation(
            ["Gap & Go", "ORB", "VWAP Reversal"]
        )
        assert result.confirmation_level == "triple"
        assert result.star_boost == 2
        assert result.position_size_multiplier == 2.0

    def test_duplicate_strategies_treated_as_single(self):
        result = ConfidenceDetector._calculate_confirmation(["Gap & Go", "Gap & Go"])
        assert result.confirmation_level == "single"

    def test_four_strategies_still_triple(self):
        result = ConfidenceDetector._calculate_confirmation(
            ["Gap & Go", "ORB", "VWAP Reversal", "MomentumX"]
        )
        assert result.confirmation_level == "triple"
        assert result.star_boost == 2
        assert result.position_size_multiplier == 2.0

    def test_empty_list(self):
        """Empty strategy list should not crash; returns single with empty list."""
        result = ConfidenceDetector._calculate_confirmation([])
        # 0 unique -> falls to the else branch (count < 2)
        assert result.confirmation_level == "single"
        assert result.confirmed_by == []


# ---------------------------------------------------------------------------
# _group_by_symbol (static method)
# ---------------------------------------------------------------------------


class TestGroupBySymbol:
    def test_single_symbol(self):
        candidates = [_make_candidate("RELIANCE", "Gap & Go")]
        groups = ConfidenceDetector._group_by_symbol(candidates)
        assert list(groups.keys()) == ["RELIANCE"]
        assert len(groups["RELIANCE"]) == 1

    def test_multiple_symbols(self):
        candidates = [
            _make_candidate("RELIANCE", "Gap & Go"),
            _make_candidate("TCS", "ORB"),
            _make_candidate("RELIANCE", "ORB"),
        ]
        groups = ConfidenceDetector._group_by_symbol(candidates)
        assert set(groups.keys()) == {"RELIANCE", "TCS"}
        assert len(groups["RELIANCE"]) == 2
        assert len(groups["TCS"]) == 1

    def test_empty_list(self):
        groups = ConfidenceDetector._group_by_symbol([])
        assert groups == {}


# ---------------------------------------------------------------------------
# detect_confirmations (async)
# ---------------------------------------------------------------------------


class TestDetectConfirmations:
    @pytest.fixture
    def detector(self):
        return ConfidenceDetector(signal_repo=None)

    async def test_single_candidate_single_confirmation(self, detector):
        now = datetime.now(IST)
        candidates = [_make_candidate("RELIANCE", "Gap & Go")]
        results = await detector.detect_confirmations(candidates, now)
        assert len(results) == 1
        _, conf = results[0]
        assert conf.confirmation_level == "single"
        assert conf.star_boost == 0
        assert conf.position_size_multiplier == 1.0

    async def test_two_strategies_same_symbol_in_batch(self, detector):
        now = datetime.now(IST)
        candidates = [
            _make_candidate("RELIANCE", "Gap & Go"),
            _make_candidate("RELIANCE", "ORB"),
        ]
        results = await detector.detect_confirmations(candidates, now)
        assert len(results) == 2
        for _, conf in results:
            assert conf.confirmation_level == "double"
            assert conf.star_boost == 1
            assert conf.position_size_multiplier == 1.5

    async def test_three_strategies_same_symbol(self, detector):
        now = datetime.now(IST)
        candidates = [
            _make_candidate("RELIANCE", "Gap & Go"),
            _make_candidate("RELIANCE", "ORB"),
            _make_candidate("RELIANCE", "VWAP Reversal"),
        ]
        results = await detector.detect_confirmations(candidates, now)
        assert len(results) == 3
        for _, conf in results:
            assert conf.confirmation_level == "triple"
            assert conf.star_boost == 2
            assert conf.position_size_multiplier == 2.0

    async def test_different_symbols_independent(self, detector):
        now = datetime.now(IST)
        candidates = [
            _make_candidate("RELIANCE", "Gap & Go"),
            _make_candidate("TCS", "ORB"),
        ]
        results = await detector.detect_confirmations(candidates, now)
        assert len(results) == 2
        for _, conf in results:
            assert conf.confirmation_level == "single"

    async def test_same_strategy_same_stock_stays_single(self, detector):
        """Two candidates from the same strategy for the same symbol are deduplicated."""
        now = datetime.now(IST)
        candidates = [
            _make_candidate("RELIANCE", "Gap & Go"),
            _make_candidate("RELIANCE", "Gap & Go"),
        ]
        results = await detector.detect_confirmations(candidates, now)
        assert len(results) == 2
        for _, conf in results:
            assert conf.confirmation_level == "single"

    async def test_mixed_symbols_with_double(self, detector):
        """Two symbols: one with double confirmation, one with single."""
        now = datetime.now(IST)
        candidates = [
            _make_candidate("RELIANCE", "Gap & Go"),
            _make_candidate("RELIANCE", "ORB"),
            _make_candidate("TCS", "VWAP Reversal"),
        ]
        results = await detector.detect_confirmations(candidates, now)
        assert len(results) == 3

        reliance_confs = [conf for cand, conf in results if cand.symbol == "RELIANCE"]
        tcs_confs = [conf for cand, conf in results if cand.symbol == "TCS"]

        assert all(c.confirmation_level == "double" for c in reliance_confs)
        assert all(c.confirmation_level == "single" for c in tcs_confs)

    async def test_empty_candidates(self, detector):
        now = datetime.now(IST)
        results = await detector.detect_confirmations([], now)
        assert results == []

    async def test_all_candidates_returned_exactly_once(self, detector):
        """Every input candidate appears exactly once in the output."""
        now = datetime.now(IST)
        candidates = [
            _make_candidate("RELIANCE", "Gap & Go"),
            _make_candidate("RELIANCE", "ORB"),
            _make_candidate("TCS", "VWAP Reversal"),
            _make_candidate("SBIN", "Gap & Go"),
        ]
        results = await detector.detect_confirmations(candidates, now)
        returned_candidates = [cand for cand, _ in results]
        assert len(returned_candidates) == len(candidates)
        # Each candidate object should appear exactly once
        for c in candidates:
            assert c in returned_candidates


# ---------------------------------------------------------------------------
# Cross-cycle confirmations (with mocked signal_repo)
# ---------------------------------------------------------------------------


class TestCrossCycleConfirmations:
    async def test_cross_cycle_double_confirmation(self):
        """A batch candidate + a recent DB signal from another strategy -> double."""
        mock_repo = AsyncMock()
        now = datetime.now(IST)
        mock_repo.get_recent_signals_by_symbol = AsyncMock(
            return_value=[("ORB", now - timedelta(minutes=5))]
        )
        detector = ConfidenceDetector(signal_repo=mock_repo)

        candidates = [_make_candidate("RELIANCE", "Gap & Go")]
        results = await detector.detect_confirmations(candidates, now)
        assert len(results) == 1
        _, conf = results[0]
        assert conf.confirmation_level == "double"
        assert conf.star_boost == 1
        assert conf.position_size_multiplier == 1.5

    async def test_cross_cycle_triple_confirmation(self):
        """A batch candidate + two recent DB signals -> triple."""
        mock_repo = AsyncMock()
        now = datetime.now(IST)
        mock_repo.get_recent_signals_by_symbol = AsyncMock(
            return_value=[
                ("ORB", now - timedelta(minutes=5)),
                ("VWAP Reversal", now - timedelta(minutes=10)),
            ]
        )
        detector = ConfidenceDetector(signal_repo=mock_repo)

        candidates = [_make_candidate("RELIANCE", "Gap & Go")]
        results = await detector.detect_confirmations(candidates, now)
        _, conf = results[0]
        assert conf.confirmation_level == "triple"

    async def test_cross_cycle_outside_window_returns_single(self):
        """When the repo returns nothing (signal outside window), stays single."""
        mock_repo = AsyncMock()
        now = datetime.now(IST)
        # The detector passes since=now-15min to the repo, and the repo
        # filters by that time. So returning empty means no recent signals.
        mock_repo.get_recent_signals_by_symbol = AsyncMock(return_value=[])
        detector = ConfidenceDetector(signal_repo=mock_repo)

        candidates = [_make_candidate("RELIANCE", "Gap & Go")]
        results = await detector.detect_confirmations(candidates, now)
        _, conf = results[0]
        assert conf.confirmation_level == "single"

    async def test_cross_cycle_same_strategy_no_upgrade(self):
        """DB signal from the same strategy does not upgrade confirmation."""
        mock_repo = AsyncMock()
        now = datetime.now(IST)
        mock_repo.get_recent_signals_by_symbol = AsyncMock(
            return_value=[("Gap & Go", now - timedelta(minutes=3))]
        )
        detector = ConfidenceDetector(signal_repo=mock_repo)

        candidates = [_make_candidate("RELIANCE", "Gap & Go")]
        results = await detector.detect_confirmations(candidates, now)
        _, conf = results[0]
        assert conf.confirmation_level == "single"

    async def test_repo_called_with_correct_since(self):
        """Verify that the repo is called with since = now - CONFIRMATION_WINDOW."""
        mock_repo = AsyncMock()
        now = datetime(2025, 1, 15, 10, 0, tzinfo=IST)
        mock_repo.get_recent_signals_by_symbol = AsyncMock(return_value=[])
        detector = ConfidenceDetector(signal_repo=mock_repo)

        candidates = [_make_candidate("RELIANCE", "Gap & Go")]
        await detector.detect_confirmations(candidates, now)

        expected_since = now - ConfidenceDetector.CONFIRMATION_WINDOW
        mock_repo.get_recent_signals_by_symbol.assert_called_once_with(
            "RELIANCE", expected_since
        )

    async def test_repo_called_per_symbol(self):
        """Repo is called once per unique symbol in the batch."""
        mock_repo = AsyncMock()
        now = datetime.now(IST)
        mock_repo.get_recent_signals_by_symbol = AsyncMock(return_value=[])
        detector = ConfidenceDetector(signal_repo=mock_repo)

        candidates = [
            _make_candidate("RELIANCE", "Gap & Go"),
            _make_candidate("RELIANCE", "ORB"),
            _make_candidate("TCS", "VWAP Reversal"),
        ]
        await detector.detect_confirmations(candidates, now)

        # Should be called once for RELIANCE and once for TCS
        assert mock_repo.get_recent_signals_by_symbol.call_count == 2
