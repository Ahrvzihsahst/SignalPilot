"""Tests for PositionSizer."""

import pytest

from signalpilot.risk.position_sizer import PositionSizer


@pytest.fixture
def sizer() -> PositionSizer:
    return PositionSizer()


# ── Capital=50000, max_positions=5 ──────────────────────────────


def test_entry_645(sizer: PositionSizer) -> None:
    """50000/5 = 10000 per trade; floor(10000/645) = 15; capital_req = 9675."""
    result = sizer.calculate(entry_price=645.0, total_capital=50000.0, max_positions=5)

    assert result.per_trade_capital == pytest.approx(10000.0)
    assert result.quantity == 15
    assert result.capital_required == pytest.approx(9675.0)


def test_entry_2450(sizer: PositionSizer) -> None:
    """50000/5 = 10000 per trade; floor(10000/2450) = 4; capital_req = 9800."""
    result = sizer.calculate(entry_price=2450.0, total_capital=50000.0, max_positions=5)

    assert result.per_trade_capital == pytest.approx(10000.0)
    assert result.quantity == 4
    assert result.capital_required == pytest.approx(9800.0)


def test_stock_too_expensive(sizer: PositionSizer) -> None:
    """Entry price exceeds per-trade allocation → quantity = 0."""
    result = sizer.calculate(entry_price=120000.0, total_capital=50000.0, max_positions=5)

    assert result.quantity == 0
    assert result.capital_required == pytest.approx(0.0)
    assert result.per_trade_capital == pytest.approx(10000.0)


# ── Floor rounding ──────────────────────────────────────────────


def test_floor_rounding(sizer: PositionSizer) -> None:
    """Verify floor (not ceil or round). 10000/333 = 30.03 → 30."""
    result = sizer.calculate(entry_price=333.0, total_capital=50000.0, max_positions=5)

    assert result.quantity == 30
    assert result.capital_required == pytest.approx(30 * 333.0)


def test_floor_rounding_near_boundary(sizer: PositionSizer) -> None:
    """10000/999.99 = 10.0001 → floor = 10, not 11."""
    result = sizer.calculate(entry_price=999.99, total_capital=50000.0, max_positions=5)

    assert result.quantity == 10


# ── Varied capital / positions ──────────────────────────────────


def test_different_capital_and_positions(sizer: PositionSizer) -> None:
    """100000 capital, 4 positions → 25000 per trade."""
    result = sizer.calculate(entry_price=500.0, total_capital=100000.0, max_positions=4)

    assert result.per_trade_capital == pytest.approx(25000.0)
    assert result.quantity == 50
    assert result.capital_required == pytest.approx(25000.0)


def test_single_position(sizer: PositionSizer) -> None:
    """1 max position → entire capital per trade."""
    result = sizer.calculate(entry_price=100.0, total_capital=50000.0, max_positions=1)

    assert result.per_trade_capital == pytest.approx(50000.0)
    assert result.quantity == 500
    assert result.capital_required == pytest.approx(50000.0)


def test_exact_division(sizer: PositionSizer) -> None:
    """When entry price divides per-trade capital exactly."""
    result = sizer.calculate(entry_price=1000.0, total_capital=50000.0, max_positions=5)

    assert result.quantity == 10
    assert result.capital_required == pytest.approx(10000.0)


# ── Input validation ────────────────────────────────────────────


def test_zero_max_positions_raises(sizer: PositionSizer) -> None:
    with pytest.raises(ValueError, match="max_positions must be positive"):
        sizer.calculate(entry_price=100.0, total_capital=50000.0, max_positions=0)


def test_negative_max_positions_raises(sizer: PositionSizer) -> None:
    with pytest.raises(ValueError, match="max_positions must be positive"):
        sizer.calculate(entry_price=100.0, total_capital=50000.0, max_positions=-1)


def test_zero_entry_price_raises(sizer: PositionSizer) -> None:
    with pytest.raises(ValueError, match="entry_price must be positive"):
        sizer.calculate(entry_price=0.0, total_capital=50000.0, max_positions=5)


def test_negative_entry_price_raises(sizer: PositionSizer) -> None:
    with pytest.raises(ValueError, match="entry_price must be positive"):
        sizer.calculate(entry_price=-100.0, total_capital=50000.0, max_positions=5)


# ===========================================================================
# Phase 3: Multiplier tests
# ===========================================================================


class TestPositionSizerMultiplier:
    """Tests for Phase 3 position size multiplier feature."""

    def test_multiplier_1_0_unchanged(self, sizer: PositionSizer) -> None:
        """multiplier=1.0 should not change the result."""
        base = sizer.calculate(entry_price=500.0, total_capital=50000.0, max_positions=5)
        with_mult = sizer.calculate(
            entry_price=500.0, total_capital=50000.0, max_positions=5, multiplier=1.0
        )
        assert base.quantity == with_mult.quantity
        assert base.per_trade_capital == with_mult.per_trade_capital

    def test_multiplier_1_5_increases_capital(self, sizer: PositionSizer) -> None:
        """multiplier=1.5 should increase per-trade capital by 1.5x."""
        # base: 50000/5 = 10000. multiplied: 15000. cap at 20%: 10000. min(15000, 10000) = 10000
        result = sizer.calculate(
            entry_price=500.0, total_capital=50000.0, max_positions=5, multiplier=1.5
        )
        assert result.per_trade_capital == pytest.approx(10000.0)  # capped at 20%
        assert result.quantity == 20  # floor(10000/500)

    def test_multiplier_1_5_cap_at_20_pct(self, sizer: PositionSizer) -> None:
        """multiplier=1.5 caps at 20% of total capital."""
        # base: 100000/4 = 25000. multiplied: 37500. cap at 20%: 20000
        result = sizer.calculate(
            entry_price=500.0, total_capital=100000.0, max_positions=4, multiplier=1.5
        )
        assert result.per_trade_capital == pytest.approx(20000.0)
        assert result.quantity == 40  # floor(20000/500)

    def test_multiplier_2_0_cap_at_25_pct(self, sizer: PositionSizer) -> None:
        """multiplier=2.0 caps at 25% of total capital."""
        # base: 100000/8 = 12500. multiplied: 25000. cap at 25%: 25000
        result = sizer.calculate(
            entry_price=500.0, total_capital=100000.0, max_positions=8, multiplier=2.0
        )
        assert result.per_trade_capital == pytest.approx(25000.0)
        assert result.quantity == 50  # floor(25000/500)

    def test_multiplier_2_0_capped_when_exceeds(self, sizer: PositionSizer) -> None:
        """multiplier=2.0 with large base should cap at 25%."""
        # base: 100000/2 = 50000. multiplied: 100000. cap at 25%: 25000
        result = sizer.calculate(
            entry_price=500.0, total_capital=100000.0, max_positions=2, multiplier=2.0
        )
        assert result.per_trade_capital == pytest.approx(25000.0)

    def test_multiplier_below_1_no_effect(self, sizer: PositionSizer) -> None:
        """multiplier < 1.0 should not trigger the multiplier branch."""
        result = sizer.calculate(
            entry_price=500.0, total_capital=50000.0, max_positions=5, multiplier=0.5
        )
        # Should use base per_trade_capital without any modification
        assert result.per_trade_capital == pytest.approx(10000.0)

    def test_multiplier_exactly_1_0_no_effect(self, sizer: PositionSizer) -> None:
        """multiplier=1.0 (boundary) should not change anything."""
        result = sizer.calculate(
            entry_price=645.0, total_capital=50000.0, max_positions=5, multiplier=1.0
        )
        assert result.per_trade_capital == pytest.approx(10000.0)
        assert result.quantity == 15
