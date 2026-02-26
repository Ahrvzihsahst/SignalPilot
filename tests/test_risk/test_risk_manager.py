"""Tests for RiskManager."""

from datetime import datetime, timedelta

import pytest

from signalpilot.db.models import (
    CandidateSignal,
    FinalSignal,
    RankedSignal,
    SignalDirection,
    UserConfig,
)
from signalpilot.risk.position_sizer import PositionSizer
from signalpilot.risk.risk_manager import RiskManager
from signalpilot.utils.constants import IST


def _make_ranked(
    symbol: str = "SBIN",
    entry_price: float = 645.0,
    gap_pct: float = 4.0,
    volume_ratio: float = 1.5,
    price_distance_pct: float = 1.5,
    rank: int = 1,
    composite_score: float = 0.8,
    signal_strength: int = 5,
    generated_at: datetime | None = None,
) -> RankedSignal:
    if generated_at is None:
        generated_at = datetime(2025, 1, 6, 9, 35, 0, tzinfo=IST)
    return RankedSignal(
        candidate=CandidateSignal(
            symbol=symbol,
            direction=SignalDirection.BUY,
            strategy_name="Gap & Go",
            entry_price=entry_price,
            stop_loss=entry_price * 0.97,
            target_1=entry_price * 1.05,
            target_2=entry_price * 1.07,
            gap_pct=gap_pct,
            volume_ratio=volume_ratio,
            price_distance_from_open_pct=price_distance_pct,
            reason="test signal",
            generated_at=generated_at,
        ),
        composite_score=composite_score,
        rank=rank,
        signal_strength=signal_strength,
    )


@pytest.fixture
def user_config() -> UserConfig:
    return UserConfig(total_capital=50000.0, max_positions=5)


@pytest.fixture
def risk_manager() -> RiskManager:
    return RiskManager(PositionSizer())


# ── Position limit enforcement ──────────────────────────────────


def test_at_max_positions_returns_empty(
    risk_manager: RiskManager, user_config: UserConfig
) -> None:
    """active_trade_count == max_positions → no new signals."""
    ranked = [_make_ranked()]

    result = risk_manager.filter_and_size(ranked, user_config, active_trade_count=5)

    assert result == []


def test_over_max_positions_returns_empty(
    risk_manager: RiskManager, user_config: UserConfig
) -> None:
    """active_trade_count > max_positions → no new signals."""
    ranked = [_make_ranked()]

    result = risk_manager.filter_and_size(ranked, user_config, active_trade_count=6)

    assert result == []


# ── Auto-skip expensive stocks ──────────────────────────────────


def test_auto_skip_expensive_stock(
    risk_manager: RiskManager, user_config: UserConfig
) -> None:
    """Entry price exceeds per-trade allocation → signal skipped."""
    ranked = [_make_ranked(entry_price=120000.0)]

    result = risk_manager.filter_and_size(ranked, user_config, active_trade_count=0)

    assert result == []


def test_auto_skip_logs_reason(
    risk_manager: RiskManager, user_config: UserConfig, caplog: pytest.LogCaptureFixture
) -> None:
    """Auto-skip should log the reason."""
    ranked = [_make_ranked(symbol="EXPENSIVE", entry_price=120000.0)]

    with caplog.at_level("INFO"):
        risk_manager.filter_and_size(ranked, user_config, active_trade_count=0)

    assert "Auto-skipped EXPENSIVE" in caplog.text
    assert "120000" in caplog.text


# ── Normal flow ─────────────────────────────────────────────────


def test_normal_flow_passes_through(
    risk_manager: RiskManager, user_config: UserConfig
) -> None:
    """Signal with affordable entry passes through with correct sizing."""
    ranked = [_make_ranked(entry_price=645.0)]

    result = risk_manager.filter_and_size(ranked, user_config, active_trade_count=0)

    assert len(result) == 1
    signal = result[0]
    assert isinstance(signal, FinalSignal)
    assert signal.quantity == 15  # floor(10000/645)
    assert signal.capital_required == pytest.approx(9675.0)
    assert signal.ranked_signal is ranked[0]


def test_normal_flow_multiple_signals(
    risk_manager: RiskManager, user_config: UserConfig
) -> None:
    """Multiple affordable signals all pass through."""
    ranked = [
        _make_ranked("A", entry_price=500.0, rank=1),
        _make_ranked("B", entry_price=1000.0, rank=2),
        _make_ranked("C", entry_price=2000.0, rank=3),
    ]

    result = risk_manager.filter_and_size(ranked, user_config, active_trade_count=0)

    assert len(result) == 3
    assert result[0].ranked_signal.candidate.symbol == "A"
    assert result[0].quantity == 20  # floor(10000/500)
    assert result[1].quantity == 10  # floor(10000/1000)
    assert result[2].quantity == 5   # floor(10000/2000)


# ── Partial slots ───────────────────────────────────────────────


def test_partial_slots_limits_output(
    risk_manager: RiskManager, user_config: UserConfig
) -> None:
    """active_trade_count=3, max_positions=5 → max 2 signals."""
    ranked = [
        _make_ranked("A", entry_price=500.0, rank=1),
        _make_ranked("B", entry_price=500.0, rank=2),
        _make_ranked("C", entry_price=500.0, rank=3),
    ]

    result = risk_manager.filter_and_size(ranked, user_config, active_trade_count=3)

    assert len(result) == 2
    assert result[0].ranked_signal.candidate.symbol == "A"
    assert result[1].ranked_signal.candidate.symbol == "B"


def test_partial_slots_with_expensive_skip(
    risk_manager: RiskManager, user_config: UserConfig
) -> None:
    """2 slots but first signal is too expensive → only second passes."""
    ranked = [
        _make_ranked("EXPENSIVE", entry_price=120000.0, rank=1),
        _make_ranked("CHEAP", entry_price=500.0, rank=2),
    ]

    result = risk_manager.filter_and_size(ranked, user_config, active_trade_count=3)

    assert len(result) == 1
    assert result[0].ranked_signal.candidate.symbol == "CHEAP"


# ── Expiry timestamp ───────────────────────────────────────────


def test_expiry_30_minutes_after_generated_at(
    risk_manager: RiskManager, user_config: UserConfig
) -> None:
    """expires_at should be exactly 30 minutes after generated_at."""
    gen_time = datetime(2025, 1, 6, 9, 35, 0, tzinfo=IST)
    ranked = [_make_ranked(generated_at=gen_time)]

    result = risk_manager.filter_and_size(ranked, user_config, active_trade_count=0)

    assert len(result) == 1
    expected_expiry = gen_time + timedelta(minutes=30)
    assert result[0].expires_at == expected_expiry


def test_expiry_different_generation_times(
    risk_manager: RiskManager, user_config: UserConfig
) -> None:
    """Each signal gets its own expiry based on its generated_at."""
    gen_time_1 = datetime(2025, 1, 6, 9, 30, 0, tzinfo=IST)
    gen_time_2 = datetime(2025, 1, 6, 9, 40, 0, tzinfo=IST)
    ranked = [
        _make_ranked("A", generated_at=gen_time_1, rank=1),
        _make_ranked("B", generated_at=gen_time_2, rank=2),
    ]

    result = risk_manager.filter_and_size(ranked, user_config, active_trade_count=0)

    assert result[0].expires_at == gen_time_1 + timedelta(minutes=30)
    assert result[1].expires_at == gen_time_2 + timedelta(minutes=30)


# ── Empty input ─────────────────────────────────────────────────


def test_empty_ranked_returns_empty(
    risk_manager: RiskManager, user_config: UserConfig
) -> None:
    result = risk_manager.filter_and_size([], user_config, active_trade_count=0)
    assert result == []


# ── Position limit logging ──────────────────────────────────────


def test_position_limit_logs_message(
    risk_manager: RiskManager, user_config: UserConfig, caplog: pytest.LogCaptureFixture
) -> None:
    """Hitting position limit should log an info message."""
    ranked = [_make_ranked()]

    with caplog.at_level("INFO"):
        risk_manager.filter_and_size(ranked, user_config, active_trade_count=5)

    assert "Position limit reached" in caplog.text
    assert "5/5" in caplog.text


# ── Mixed affordable and expensive ─────────────────────────────


def test_mixed_affordable_and_expensive(
    risk_manager: RiskManager, user_config: UserConfig
) -> None:
    """Expensive signals skipped, affordable ones pass through."""
    ranked = [
        _make_ranked("CHEAP1", entry_price=500.0, rank=1),
        _make_ranked("EXPENSIVE", entry_price=120000.0, rank=2),
        _make_ranked("CHEAP2", entry_price=1000.0, rank=3),
    ]

    result = risk_manager.filter_and_size(ranked, user_config, active_trade_count=0)

    assert len(result) == 2
    symbols = [r.ranked_signal.candidate.symbol for r in result]
    assert symbols == ["CHEAP1", "CHEAP2"]


# ===========================================================================
# Phase 3: Confirmation map tests
# ===========================================================================

from signalpilot.ranking.confidence import ConfirmationResult


class TestRiskManagerConfirmationMap:
    """Tests for Phase 3 confirmation_map in filter_and_size."""

    def test_confirmation_map_none_is_backward_compatible(self) -> None:
        """No confirmation_map means multiplier=1.0 (legacy behavior)."""
        rm = RiskManager(PositionSizer())
        config = UserConfig(total_capital=50000.0, max_positions=5)
        ranked = [_make_ranked("SBIN", entry_price=500.0)]

        result = rm.filter_and_size(ranked, config, active_trade_count=0)

        assert len(result) == 1
        assert result[0].quantity == 20  # floor(10000/500)

    def test_double_confirmation_increases_quantity(self) -> None:
        """Double confirmation (1.5x) should increase position size."""
        rm = RiskManager(PositionSizer())
        config = UserConfig(total_capital=100000.0, max_positions=8)
        ranked = [_make_ranked("SBIN", entry_price=500.0)]
        conf_map = {
            "SBIN": ConfirmationResult(
                confirmation_level="double",
                confirmed_by=["Gap & Go", "ORB"],
                star_boost=1,
                position_size_multiplier=1.5,
            )
        }

        result = rm.filter_and_size(
            ranked, config, active_trade_count=0, confirmation_map=conf_map,
        )

        # base: 100000/8 = 12500. multiplied: 18750. cap at 20%: 20000. min(18750, 20000) = 18750
        assert len(result) == 1
        assert result[0].quantity == 37  # floor(18750/500)

    def test_triple_confirmation_capped_at_25_pct(self) -> None:
        """Triple confirmation (2.0x) is capped at 25% of total capital."""
        rm = RiskManager(PositionSizer())
        config = UserConfig(total_capital=100000.0, max_positions=4)
        ranked = [_make_ranked("SBIN", entry_price=500.0)]
        conf_map = {
            "SBIN": ConfirmationResult(
                confirmation_level="triple",
                confirmed_by=["Gap & Go", "ORB", "VWAP Reversal"],
                star_boost=2,
                position_size_multiplier=2.0,
            )
        }

        result = rm.filter_and_size(
            ranked, config, active_trade_count=0, confirmation_map=conf_map,
        )

        # base: 100000/4 = 25000. multiplied: 50000. cap at 25%: 25000
        assert len(result) == 1
        assert result[0].quantity == 50  # floor(25000/500)

    def test_symbol_not_in_confirmation_map_gets_default(self) -> None:
        """Symbols not in confirmation_map get multiplier=1.0."""
        rm = RiskManager(PositionSizer())
        config = UserConfig(total_capital=50000.0, max_positions=5)
        ranked = [_make_ranked("TCS", entry_price=500.0)]
        conf_map = {
            "SBIN": ConfirmationResult(
                confirmation_level="double",
                confirmed_by=["Gap & Go", "ORB"],
                star_boost=1,
                position_size_multiplier=1.5,
            )
        }

        result = rm.filter_and_size(
            ranked, config, active_trade_count=0, confirmation_map=conf_map,
        )

        # TCS not in map -> multiplier=1.0 -> 10000/500 = 20
        assert len(result) == 1
        assert result[0].quantity == 20
