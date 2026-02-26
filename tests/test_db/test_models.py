"""Tests for core data models."""

from datetime import date, datetime

import pytest

from signalpilot.db.models import (
    AdaptationLogRecord,
    CandidateSignal,
    CircuitBreakerRecord,
    DailySummary,
    ExitAlert,
    ExitType,
    FinalSignal,
    HistoricalReference,
    HybridScoreRecord,
    Instrument,
    PerformanceMetrics,
    PositionSize,
    PreviousDayData,
    RankedSignal,
    ScoringWeights,
    SignalDirection,
    SignalRecord,
    StrategyPhase,
    TickData,
    TradeRecord,
    UserConfig,
)
from signalpilot.utils.constants import IST


class TestSignalDirection:
    def test_buy_value(self):
        assert SignalDirection.BUY.value == "BUY"

    def test_sell_value(self):
        assert SignalDirection.SELL.value == "SELL"

    def test_members(self):
        assert set(SignalDirection) == {SignalDirection.BUY, SignalDirection.SELL}


class TestExitType:
    def test_sl_hit(self):
        assert ExitType.SL_HIT.value == "sl_hit"

    def test_t1_hit(self):
        assert ExitType.T1_HIT.value == "t1_hit"

    def test_t2_hit(self):
        assert ExitType.T2_HIT.value == "t2_hit"

    def test_trailing_sl_hit(self):
        assert ExitType.TRAILING_SL_HIT.value == "trailing_sl"

    def test_time_exit(self):
        assert ExitType.TIME_EXIT.value == "time_exit"

    def test_members(self):
        assert len(ExitType) == 5


class TestStrategyPhase:
    def test_re_exported_from_market_calendar(self):
        from signalpilot.utils.market_calendar import (
            StrategyPhase as OriginalPhase,
        )

        assert StrategyPhase is OriginalPhase

    def test_has_expected_phases(self):
        expected = {
            "PRE_MARKET",
            "OPENING",
            "ENTRY_WINDOW",
            "CONTINUOUS",
            "WIND_DOWN",
            "POST_MARKET",
        }
        assert {p.name for p in StrategyPhase} == expected


class TestInstrument:
    def test_instantiation(self):
        inst = Instrument(
            symbol="SBIN",
            name="State Bank of India",
            angel_token="3045",
            exchange="NSE",
            nse_symbol="SBIN-EQ",
            yfinance_symbol="SBIN.NS",
        )
        assert inst.symbol == "SBIN"
        assert inst.name == "State Bank of India"
        assert inst.angel_token == "3045"
        assert inst.exchange == "NSE"
        assert inst.nse_symbol == "SBIN-EQ"
        assert inst.yfinance_symbol == "SBIN.NS"

    def test_default_lot_size(self):
        inst = Instrument(
            symbol="SBIN",
            name="State Bank of India",
            angel_token="3045",
            exchange="NSE",
            nse_symbol="SBIN-EQ",
            yfinance_symbol="SBIN.NS",
        )
        assert inst.lot_size == 1


class TestTickData:
    def test_instantiation(self):
        now = datetime(2026, 2, 16, 10, 0, 0)
        tick = TickData(
            symbol="SBIN",
            ltp=750.50,
            open_price=745.00,
            high=752.00,
            low=744.00,
            close=740.00,
            volume=1_000_000,
            last_traded_timestamp=now,
            updated_at=now,
        )
        assert tick.symbol == "SBIN"
        assert tick.ltp == 750.50
        assert tick.open_price == 745.00
        assert tick.high == 752.00
        assert tick.low == 744.00
        assert tick.close == 740.00
        assert tick.volume == 1_000_000


class TestHistoricalReference:
    def test_instantiation(self):
        ref = HistoricalReference(
            previous_close=740.00,
            previous_high=745.00,
            average_daily_volume=2_000_000.0,
        )
        assert ref.previous_close == 740.00
        assert ref.previous_high == 745.00
        assert ref.average_daily_volume == 2_000_000.0


class TestPreviousDayData:
    def test_instantiation(self):
        prev = PreviousDayData(
            close=740.0,
            high=745.0,
            low=735.0,
            open=738.0,
            volume=1_500_000,
        )
        assert prev.close == 740.0
        assert prev.high == 745.0
        assert prev.low == 735.0
        assert prev.open == 738.0
        assert prev.volume == 1_500_000


class TestCandidateSignal:
    def test_instantiation(self):
        now = datetime(2026, 2, 16, 9, 35, 0)
        sig = CandidateSignal(
            symbol="SBIN",
            direction=SignalDirection.BUY,
            strategy_name="gap_and_go",
            entry_price=770.0,
            stop_loss=745.0,
            target_1=808.5,
            target_2=823.9,
            gap_pct=4.05,
            volume_ratio=1.8,
            price_distance_from_open_pct=1.2,
            reason="Gap up 4.05% above prev high with 1.8x volume",
            generated_at=now,
        )
        assert sig.symbol == "SBIN"
        assert sig.direction == SignalDirection.BUY
        assert sig.strategy_name == "gap_and_go"
        assert sig.entry_price == 770.0
        assert sig.stop_loss == 745.0
        assert sig.target_1 == 808.5
        assert sig.target_2 == 823.9
        assert sig.gap_pct == 4.05
        assert sig.volume_ratio == 1.8
        assert sig.reason == "Gap up 4.05% above prev high with 1.8x volume"
        assert sig.generated_at == now


class TestScoringWeights:
    def test_default_weights(self):
        w = ScoringWeights()
        assert w.gap_pct_weight == 0.40
        assert w.volume_ratio_weight == 0.35
        assert w.price_distance_weight == 0.25

    def test_custom_weights(self):
        w = ScoringWeights(gap_pct_weight=0.5, volume_ratio_weight=0.3, price_distance_weight=0.2)
        assert w.gap_pct_weight == 0.5
        assert w.volume_ratio_weight == 0.3
        assert w.price_distance_weight == 0.2

    def test_default_weights_sum_to_one(self):
        w = ScoringWeights()
        total = w.gap_pct_weight + w.volume_ratio_weight + w.price_distance_weight
        assert total == pytest.approx(1.0)


class TestRankedSignal:
    def test_instantiation(self):
        now = datetime(2026, 2, 16, 9, 35, 0)
        candidate = CandidateSignal(
            symbol="SBIN",
            direction=SignalDirection.BUY,
            strategy_name="gap_and_go",
            entry_price=770.0,
            stop_loss=745.0,
            target_1=808.5,
            target_2=823.9,
            gap_pct=4.05,
            volume_ratio=1.8,
            price_distance_from_open_pct=1.2,
            reason="Gap up",
            generated_at=now,
        )
        ranked = RankedSignal(
            candidate=candidate,
            composite_score=0.85,
            rank=1,
            signal_strength=4,
        )
        assert ranked.candidate is candidate
        assert ranked.composite_score == 0.85
        assert ranked.rank == 1
        assert ranked.signal_strength == 4


class TestPositionSize:
    def test_instantiation(self):
        ps = PositionSize(
            quantity=13,
            capital_required=10010.0,
            per_trade_capital=10000.0,
        )
        assert ps.quantity == 13
        assert ps.capital_required == 10010.0
        assert ps.per_trade_capital == 10000.0


class TestFinalSignal:
    def test_instantiation(self):
        now = datetime(2026, 2, 16, 9, 35, 0)
        expires = datetime(2026, 2, 16, 10, 5, 0)
        candidate = CandidateSignal(
            symbol="SBIN",
            direction=SignalDirection.BUY,
            strategy_name="gap_and_go",
            entry_price=770.0,
            stop_loss=745.0,
            target_1=808.5,
            target_2=823.9,
            gap_pct=4.05,
            volume_ratio=1.8,
            price_distance_from_open_pct=1.2,
            reason="Gap up",
            generated_at=now,
        )
        ranked = RankedSignal(
            candidate=candidate,
            composite_score=0.85,
            rank=1,
            signal_strength=4,
        )
        final = FinalSignal(
            ranked_signal=ranked,
            quantity=13,
            capital_required=10010.0,
            expires_at=expires,
        )
        assert final.ranked_signal is ranked
        assert final.quantity == 13
        assert final.capital_required == 10010.0
        assert final.expires_at == expires


class TestSignalRecord:
    def test_defaults(self):
        rec = SignalRecord()
        assert rec.id is None
        assert rec.symbol == ""
        assert rec.strategy == ""
        assert rec.entry_price == 0.0
        assert rec.stop_loss == 0.0
        assert rec.target_1 == 0.0
        assert rec.target_2 == 0.0
        assert rec.quantity == 0
        assert rec.capital_required == 0.0
        assert rec.signal_strength == 0
        assert rec.gap_pct == 0.0
        assert rec.volume_ratio == 0.0
        assert rec.reason == ""
        assert rec.created_at is None
        assert rec.expires_at is None
        assert rec.status == "sent"

    def test_date_defaults_to_today(self):
        rec = SignalRecord()
        assert rec.date == date.today()

    def test_custom_values(self):
        rec = SignalRecord(
            id=1,
            symbol="SBIN",
            strategy="gap_and_go",
            entry_price=770.0,
            status="expired",
        )
        assert rec.id == 1
        assert rec.symbol == "SBIN"
        assert rec.strategy == "gap_and_go"
        assert rec.entry_price == 770.0
        assert rec.status == "expired"

    def test_equality(self):
        a = SignalRecord(id=1, symbol="SBIN", strategy="gap_and_go")
        b = SignalRecord(id=1, symbol="SBIN", strategy="gap_and_go")
        assert a == b
        assert a is not b

    def test_inequality(self):
        a = SignalRecord(id=1, symbol="SBIN")
        b = SignalRecord(id=2, symbol="SBIN")
        assert a != b


class TestTradeRecord:
    def test_defaults(self):
        rec = TradeRecord()
        assert rec.id is None
        assert rec.signal_id == 0
        assert rec.symbol == ""
        assert rec.entry_price == 0.0
        assert rec.exit_price is None
        assert rec.stop_loss == 0.0
        assert rec.target_1 == 0.0
        assert rec.target_2 == 0.0
        assert rec.quantity == 0
        assert rec.pnl_amount is None
        assert rec.pnl_pct is None
        assert rec.exit_reason is None
        assert rec.taken_at is None
        assert rec.exited_at is None

    def test_date_defaults_to_today(self):
        rec = TradeRecord()
        assert rec.date == date.today()


class TestUserConfig:
    def test_defaults(self):
        cfg = UserConfig()
        assert cfg.id is None
        assert cfg.telegram_chat_id == ""
        assert cfg.total_capital == 50000.0
        assert cfg.max_positions == 8
        assert cfg.gap_go_enabled is True
        assert cfg.orb_enabled is True
        assert cfg.vwap_enabled is True
        assert cfg.created_at is None
        assert cfg.updated_at is None

    def test_custom_values(self):
        cfg = UserConfig(
            id=1,
            telegram_chat_id="123456",
            total_capital=100000.0,
            max_positions=3,
        )
        assert cfg.id == 1
        assert cfg.telegram_chat_id == "123456"
        assert cfg.total_capital == 100000.0
        assert cfg.max_positions == 3


class TestExitAlert:
    def test_instantiation(self):
        trade = TradeRecord(symbol="SBIN", entry_price=770.0)
        alert = ExitAlert(
            trade=trade,
            exit_type=ExitType.T1_HIT,
            current_price=808.5,
            pnl_pct=5.0,
            is_alert_only=True,
        )
        assert alert.trade is trade
        assert alert.exit_type == ExitType.T1_HIT
        assert alert.current_price == 808.5
        assert alert.pnl_pct == 5.0
        assert alert.is_alert_only is True
        assert alert.trailing_sl_update is None

    def test_with_trailing_sl_update(self):
        trade = TradeRecord(symbol="SBIN", entry_price=770.0)
        alert = ExitAlert(
            trade=trade,
            exit_type=None,
            current_price=800.0,
            pnl_pct=3.9,
            is_alert_only=True,
            trailing_sl_update=784.0,
        )
        assert alert.exit_type is None
        assert alert.trailing_sl_update == 784.0


class TestPerformanceMetrics:
    def test_instantiation(self):
        metrics = PerformanceMetrics(
            date_range_start=date(2026, 2, 1),
            date_range_end=date(2026, 2, 15),
            total_signals=50,
            trades_taken=30,
            wins=20,
            losses=10,
            win_rate=66.67,
            total_pnl=15000.0,
            avg_win=1200.0,
            avg_loss=-600.0,
            risk_reward_ratio=2.0,
            best_trade_symbol="SBIN",
            best_trade_pnl=3000.0,
            worst_trade_symbol="INFY",
            worst_trade_pnl=-1500.0,
        )
        assert metrics.total_signals == 50
        assert metrics.trades_taken == 30
        assert metrics.win_rate == 66.67
        assert metrics.risk_reward_ratio == 2.0
        assert metrics.best_trade_symbol == "SBIN"
        assert metrics.worst_trade_symbol == "INFY"


class TestDailySummary:
    def test_instantiation(self):
        summary = DailySummary(
            date=date(2026, 2, 16),
            signals_sent=10,
            trades_taken=5,
            wins=3,
            losses=2,
            total_pnl=2500.0,
            cumulative_pnl=15000.0,
        )
        assert summary.date == date(2026, 2, 16)
        assert summary.signals_sent == 10
        assert summary.trades_taken == 5
        assert summary.wins == 3
        assert summary.losses == 2
        assert summary.total_pnl == 2500.0
        assert summary.cumulative_pnl == 15000.0

    def test_trades_default_empty(self):
        summary = DailySummary(
            date=date(2026, 2, 16),
            signals_sent=0,
            trades_taken=0,
            wins=0,
            losses=0,
            total_pnl=0.0,
            cumulative_pnl=0.0,
        )
        assert summary.trades == []

    def test_trades_with_records(self):
        trade = TradeRecord(symbol="SBIN", entry_price=770.0)
        summary = DailySummary(
            date=date(2026, 2, 16),
            signals_sent=1,
            trades_taken=1,
            wins=1,
            losses=0,
            total_pnl=500.0,
            cumulative_pnl=500.0,
            trades=[trade],
        )
        assert len(summary.trades) == 1
        assert summary.trades[0] is trade

    def test_trades_default_not_shared(self):
        s1 = DailySummary(
            date=date(2026, 2, 16), signals_sent=0, trades_taken=0,
            wins=0, losses=0, total_pnl=0.0, cumulative_pnl=0.0,
        )
        s2 = DailySummary(
            date=date(2026, 2, 16), signals_sent=0, trades_taken=0,
            wins=0, losses=0, total_pnl=0.0, cumulative_pnl=0.0,
        )
        assert s1.trades is not s2.trades
        s1.trades.append(TradeRecord(symbol="SBIN"))
        assert len(s2.trades) == 0


# ---------------------------------------------------------------------------
# Phase 3 Model Tests
# ---------------------------------------------------------------------------


class TestHybridScoreRecord:
    def test_defaults(self):
        rec = HybridScoreRecord()
        assert rec.id is None
        assert rec.signal_id == 0
        assert rec.composite_score == 0.0
        assert rec.strategy_strength_score == 0.0
        assert rec.win_rate_score == 0.0
        assert rec.risk_reward_score == 0.0
        assert rec.confirmation_bonus == 0.0
        assert rec.confirmed_by is None
        assert rec.confirmation_level == "single"
        assert rec.position_size_multiplier == 1.0
        assert rec.created_at is None

    def test_custom_values(self):
        now = datetime(2025, 1, 15, 10, 0, tzinfo=IST)
        rec = HybridScoreRecord(
            id=1,
            signal_id=42,
            composite_score=85.5,
            strategy_strength_score=90.0,
            win_rate_score=75.0,
            risk_reward_score=80.0,
            confirmation_bonus=100.0,
            confirmed_by="Gap & Go,ORB",
            confirmation_level="double",
            position_size_multiplier=1.5,
            created_at=now,
        )
        assert rec.id == 1
        assert rec.signal_id == 42
        assert rec.composite_score == 85.5
        assert rec.confirmed_by == "Gap & Go,ORB"
        assert rec.confirmation_level == "double"
        assert rec.position_size_multiplier == 1.5


class TestCircuitBreakerRecord:
    def test_defaults(self):
        rec = CircuitBreakerRecord()
        assert rec.id is None
        assert rec.sl_count == 0
        assert rec.triggered_at is None
        assert rec.resumed_at is None
        assert rec.manual_override is False
        assert rec.override_at is None

    def test_custom_values(self):
        now = datetime(2025, 1, 15, 12, 0, tzinfo=IST)
        rec = CircuitBreakerRecord(
            id=1,
            date=date(2025, 1, 15),
            sl_count=3,
            triggered_at=now,
            manual_override=True,
            override_at=now,
        )
        assert rec.sl_count == 3
        assert rec.manual_override is True


class TestAdaptationLogRecord:
    def test_defaults(self):
        rec = AdaptationLogRecord()
        assert rec.id is None
        assert rec.strategy == ""
        assert rec.event_type == ""
        assert rec.details == ""
        assert rec.old_weight is None
        assert rec.new_weight is None
        assert rec.created_at is None

    def test_custom_values(self):
        rec = AdaptationLogRecord(
            id=1,
            date=date(2025, 1, 15),
            strategy="ORB",
            event_type="throttle",
            details="3 consecutive losses",
            old_weight=0.33,
            new_weight=0.20,
        )
        assert rec.strategy == "ORB"
        assert rec.event_type == "throttle"


class TestSignalRecordPhase3:
    def test_backward_compatible(self):
        """Phase 1/2 construction still works with Phase 3 defaults."""
        rec = SignalRecord(
            id=1, symbol="SBIN", strategy="gap_go",
            entry_price=500.0, stop_loss=485.0,
        )
        assert rec.composite_score is None
        assert rec.confirmation_level is None
        assert rec.confirmed_by is None
        assert rec.position_size_multiplier == 1.0
        assert rec.adaptation_status == "normal"

    def test_phase3_fields(self):
        rec = SignalRecord(
            composite_score=85.0,
            confirmation_level="double",
            confirmed_by="Gap & Go,ORB",
            position_size_multiplier=1.5,
            adaptation_status="reduced",
        )
        assert rec.composite_score == 85.0
        assert rec.confirmation_level == "double"
        assert rec.position_size_multiplier == 1.5
        assert rec.adaptation_status == "reduced"


class TestUserConfigPhase3:
    def test_backward_compatible(self):
        """Phase 1/2 construction still works with Phase 3 defaults."""
        cfg = UserConfig(telegram_chat_id="123", total_capital=50000.0)
        assert cfg.circuit_breaker_limit == 3
        assert cfg.confidence_boost_enabled is True
        assert cfg.adaptive_learning_enabled is True
        assert cfg.auto_rebalance_enabled is True
        assert cfg.adaptation_mode == "aggressive"

    def test_phase3_fields(self):
        cfg = UserConfig(
            circuit_breaker_limit=5,
            confidence_boost_enabled=False,
            adaptive_learning_enabled=False,
            auto_rebalance_enabled=False,
            adaptation_mode="conservative",
        )
        assert cfg.circuit_breaker_limit == 5
        assert cfg.confidence_boost_enabled is False
        assert cfg.adaptation_mode == "conservative"
