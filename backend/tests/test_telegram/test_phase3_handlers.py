"""Tests for Phase 3 Telegram command handlers and enhanced existing handlers."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from signalpilot.db.models import (
    HybridScoreRecord,
    PerformanceMetrics,
    SignalRecord,
    StrategyPerformanceRecord,
    UserConfig,
)
from signalpilot.telegram.handlers import (
    handle_adapt,
    handle_help,
    handle_journal,
    handle_override_circuit,
    handle_override_confirm,
    handle_rebalance,
    handle_score,
    handle_status,
    handle_strategy,
)
from signalpilot.utils.constants import IST

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hybrid_score(
    signal_id: int = 1,
    composite_score: float = 75.0,
    strategy_strength_score: float = 80.0,
    win_rate_score: float = 65.0,
    risk_reward_score: float = 70.0,
    confirmation_bonus: float = 50.0,
    confirmed_by: str = "Gap & Go,ORB",
    confirmation_level: str = "double",
    position_size_multiplier: float = 1.5,
) -> HybridScoreRecord:
    return HybridScoreRecord(
        id=1,
        signal_id=signal_id,
        composite_score=composite_score,
        strategy_strength_score=strategy_strength_score,
        win_rate_score=win_rate_score,
        risk_reward_score=risk_reward_score,
        confirmation_bonus=confirmation_bonus,
        confirmed_by=confirmed_by,
        confirmation_level=confirmation_level,
        position_size_multiplier=position_size_multiplier,
        created_at=datetime(2026, 2, 26, 10, 0, tzinfo=IST),
    )


def _make_signal_record(
    signal_id: int = 1,
    symbol: str = "SBIN",
    entry_price: float = 645.0,
    expires_at: datetime | None = None,
) -> SignalRecord:
    now = datetime(2026, 2, 26, 9, 35, 0, tzinfo=IST)
    return SignalRecord(
        id=signal_id,
        date=now.date(),
        symbol=symbol,
        strategy="Gap & Go",
        entry_price=entry_price,
        stop_loss=625.65,
        target_1=677.25,
        target_2=690.15,
        quantity=15,
        capital_required=9675.0,
        signal_strength=4,
        gap_pct=4.2,
        volume_ratio=2.1,
        reason="test",
        created_at=now,
        expires_at=expires_at or (now + timedelta(minutes=30)),
        status="sent",
    )


@dataclass
class _AllocationResult:
    strategy_name: str
    weight_pct: float
    allocated_capital: float
    max_positions: int


# ========================================================================
# Task 10.1: OVERRIDE CIRCUIT
# ========================================================================


class TestOverrideCircuit:
    """Tests for the OVERRIDE CIRCUIT command handler."""

    @pytest.mark.asyncio
    async def test_override_circuit_not_configured(self) -> None:
        """OVERRIDE CIRCUIT with no circuit breaker -> not configured message."""
        result = await handle_override_circuit(None)
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_override_circuit_not_active(self) -> None:
        """OVERRIDE CIRCUIT when circuit breaker is inactive -> not active message."""
        cb = MagicMock()
        type(cb).is_active = PropertyMock(return_value=False)

        result = await handle_override_circuit(cb)
        assert "not active" in result.lower()

    @pytest.mark.asyncio
    async def test_override_circuit_active_prompts_confirmation(self) -> None:
        """OVERRIDE CIRCUIT when active -> prompts for YES confirmation."""
        cb = MagicMock()
        type(cb).is_active = PropertyMock(return_value=True)
        type(cb).daily_sl_count = PropertyMock(return_value=3)
        type(cb).sl_limit = PropertyMock(return_value=3)

        result = await handle_override_circuit(cb)
        assert "Reply YES" in result
        assert "3/3" in result

    @pytest.mark.asyncio
    async def test_override_confirm_not_configured(self) -> None:
        """YES confirm with no circuit breaker -> not configured message."""
        result = await handle_override_confirm(None)
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_override_confirm_not_active(self) -> None:
        """YES confirm when circuit breaker is not active -> no override needed."""
        cb = MagicMock()
        type(cb).is_active = PropertyMock(return_value=False)

        result = await handle_override_confirm(cb)
        assert "not active" in result.lower()

    @pytest.mark.asyncio
    async def test_override_confirm_success(self) -> None:
        """YES confirm -> calls override(), re-enables signals on app."""
        cb = MagicMock()
        type(cb).is_active = PropertyMock(return_value=True)
        cb.override = AsyncMock(return_value=True)

        app = MagicMock()
        app._accepting_signals = False

        result = await handle_override_confirm(cb, app=app)
        assert "overridden" in result.lower()
        assert "resumed" in result.lower()
        assert app._accepting_signals is True
        cb.override.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_override_confirm_failure(self) -> None:
        """YES confirm when override returns False -> failure message."""
        cb = MagicMock()
        type(cb).is_active = PropertyMock(return_value=True)
        cb.override = AsyncMock(return_value=False)

        result = await handle_override_confirm(cb)
        assert "failed" in result.lower()


# ========================================================================
# Task 10.2: SCORE command
# ========================================================================


class TestScore:
    """Tests for the SCORE command handler."""

    @pytest.mark.asyncio
    async def test_score_not_configured(self) -> None:
        """SCORE with no hybrid_score_repo -> not configured message."""
        result = await handle_score(None, "SCORE SBIN")
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_score_invalid_format(self) -> None:
        """SCORE without symbol -> usage message."""
        repo = AsyncMock()
        result = await handle_score(repo, "SCORE")
        assert "Usage:" in result

    @pytest.mark.asyncio
    async def test_score_symbol_not_found(self) -> None:
        """SCORE UNKNOWN -> no signal found message."""
        repo = AsyncMock()
        repo.get_latest_for_symbol.return_value = None

        result = await handle_score(repo, "SCORE UNKNOWN")
        assert "No signal found for UNKNOWN today" in result
        repo.get_latest_for_symbol.assert_awaited_once_with("UNKNOWN")

    @pytest.mark.asyncio
    async def test_score_found(self) -> None:
        """SCORE SBIN with data -> composite score breakdown displayed."""
        hs = _make_hybrid_score()
        repo = AsyncMock()
        repo.get_latest_for_symbol.return_value = hs

        result = await handle_score(repo, "SCORE SBIN")
        assert "Composite Score -- SBIN" in result
        assert "75.0/100" in result
        assert "Strategy Strength: 80.0" in result
        assert "Win Rate Score: 65.0" in result
        assert "Risk-Reward Score: 70.0" in result
        assert "Confirmation Bonus: 50" in result
        assert "double" in result
        assert "Gap & Go,ORB" in result
        assert "1.5x" in result

    @pytest.mark.asyncio
    async def test_score_case_insensitive(self) -> None:
        """SCORE sbin -> normalized to SBIN."""
        repo = AsyncMock()
        repo.get_latest_for_symbol.return_value = None

        await handle_score(repo, "score sbin")
        repo.get_latest_for_symbol.assert_awaited_once_with("SBIN")


# ========================================================================
# Task 10.3: ADAPT command
# ========================================================================


class TestAdapt:
    """Tests for the ADAPT command handler."""

    @pytest.mark.asyncio
    async def test_adapt_not_configured(self) -> None:
        """ADAPT with no adaptive_manager -> not configured message."""
        result = await handle_adapt(None)
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_adapt_no_states(self) -> None:
        """ADAPT with empty states -> 'no adaptation data' message."""
        am = MagicMock()
        am.get_all_states.return_value = {}

        result = await handle_adapt(am)
        assert "No adaptation data yet" in result
        assert "NORMAL" in result

    @pytest.mark.asyncio
    async def test_adapt_with_states(self) -> None:
        """ADAPT with strategy states -> displays per-strategy status."""
        from signalpilot.monitor.adaptive_manager import (
            AdaptationLevel,
            StrategyAdaptationState,
        )

        states = {
            "Gap & Go": StrategyAdaptationState(
                strategy_name="Gap & Go",
                consecutive_losses=0,
                consecutive_wins=3,
                level=AdaptationLevel.NORMAL,
                daily_wins=3,
                daily_losses=1,
            ),
            "ORB": StrategyAdaptationState(
                strategy_name="ORB",
                consecutive_losses=4,
                consecutive_wins=0,
                level=AdaptationLevel.REDUCED,
                daily_wins=1,
                daily_losses=4,
            ),
        }
        am = MagicMock()
        am.get_all_states.return_value = states

        result = await handle_adapt(am)
        assert "Adaptive Strategy Status" in result
        assert "Gap & Go" in result
        assert "OK" in result
        assert "ORB" in result
        assert "THROTTLED" in result
        assert "3W / 1L" in result
        assert "1W / 4L" in result

    @pytest.mark.asyncio
    async def test_adapt_paused_strategy(self) -> None:
        """ADAPT with paused strategy -> shows STOPPED status."""
        from signalpilot.monitor.adaptive_manager import (
            AdaptationLevel,
            StrategyAdaptationState,
        )

        states = {
            "VWAP Reversal": StrategyAdaptationState(
                strategy_name="VWAP Reversal",
                consecutive_losses=5,
                consecutive_wins=0,
                level=AdaptationLevel.PAUSED,
                daily_wins=0,
                daily_losses=5,
            ),
        }
        am = MagicMock()
        am.get_all_states.return_value = states

        result = await handle_adapt(am)
        assert "STOPPED" in result


# ========================================================================
# Task 10.4: REBALANCE command
# ========================================================================


class TestRebalance:
    """Tests for the REBALANCE command handler."""

    @pytest.mark.asyncio
    async def test_rebalance_not_configured(self) -> None:
        """REBALANCE with no capital_allocator -> not configured message."""
        result = await handle_rebalance(None, MagicMock())
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_rebalance_no_config_repo(self) -> None:
        """REBALANCE with no config_repo -> not available message."""
        result = await handle_rebalance(MagicMock(), None)
        assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_rebalance_no_user_config(self) -> None:
        """REBALANCE with no user_config -> no config found message."""
        config_repo = AsyncMock()
        config_repo.get_user_config.return_value = None

        result = await handle_rebalance(MagicMock(), config_repo)
        assert "No user config found" in result

    @pytest.mark.asyncio
    async def test_rebalance_success(self) -> None:
        """REBALANCE -> calculates allocations and formats result."""
        config_repo = AsyncMock()
        config_repo.get_user_config.return_value = UserConfig(
            total_capital=100_000, max_positions=8,
        )

        allocator = AsyncMock()
        allocator.calculate_allocations.return_value = {
            "Gap & Go": _AllocationResult("Gap & Go", 40.0, 40_000, 3),
            "ORB": _AllocationResult("ORB", 20.0, 20_000, 2),
            "VWAP Reversal": _AllocationResult("VWAP Reversal", 20.0, 20_000, 2),
        }

        result = await handle_rebalance(allocator, config_repo)
        assert "Manual Rebalance Complete" in result
        assert "Gap & Go" in result
        assert "40%" in result
        assert "Reserve: 20%" in result

    @pytest.mark.asyncio
    async def test_rebalance_logs_to_adaptation(self) -> None:
        """REBALANCE logs each strategy to adaptation_log."""
        config_repo = AsyncMock()
        config_repo.get_user_config.return_value = UserConfig(
            total_capital=100_000, max_positions=8,
        )

        allocator = AsyncMock()
        allocator.calculate_allocations.return_value = {
            "Gap & Go": _AllocationResult("Gap & Go", 40.0, 40_000, 3),
        }

        log_repo = AsyncMock()
        log_repo.insert_log = AsyncMock(return_value=1)

        result = await handle_rebalance(
            allocator, config_repo, adaptation_log_repo=log_repo,
        )
        assert "Manual Rebalance Complete" in result
        log_repo.insert_log.assert_awaited_once()
        call_kwargs = log_repo.insert_log.call_args
        assert call_kwargs[1]["event_type"] == "manual_rebalance"
        assert call_kwargs[1]["strategy"] == "Gap & Go"


# ========================================================================
# Task 10.5: Enhanced STATUS
# ========================================================================


class TestEnhancedStatus:
    """Tests for the enhanced STATUS command with Phase 3 features."""

    @pytest.mark.asyncio
    async def test_status_with_composite_scores(self) -> None:
        """STATUS with hybrid_score_repo -> signals sorted by score with ranks."""
        sig1 = _make_signal_record(signal_id=1, symbol="SBIN")
        sig2 = _make_signal_record(signal_id=2, symbol="TCS", entry_price=3500.0)

        signal_repo = AsyncMock()
        signal_repo.get_active_signals.return_value = [sig1, sig2]

        trade_repo = AsyncMock()
        trade_repo.get_active_trades.return_value = []

        async def get_prices(symbols):
            return {}

        # TCS has higher composite score than SBIN
        hs_sbin = _make_hybrid_score(signal_id=1, composite_score=60.0, confirmation_level="single")
        hs_tcs = _make_hybrid_score(signal_id=2, composite_score=85.0, confirmation_level="double")

        hybrid_repo = AsyncMock()
        async def get_by_signal_id(signal_id):
            if signal_id == 1:
                return hs_sbin
            elif signal_id == 2:
                return hs_tcs
            return None
        hybrid_repo.get_by_signal_id = AsyncMock(side_effect=get_by_signal_id)

        now = datetime(2026, 2, 26, 10, 0, 0, tzinfo=IST)
        result = await handle_status(
            signal_repo, trade_repo, get_prices,
            now=now, hybrid_score_repo=hybrid_repo,
        )

        # TCS (higher score) should appear first
        assert "Active Signals" in result
        tcs_pos = result.find("TCS")
        sbin_pos = result.find("SBIN")
        assert tcs_pos < sbin_pos, "TCS should appear before SBIN (higher composite score)"
        assert "#1" in result
        assert "#2" in result
        assert "Score: 85" in result
        assert "DOUBLE CONFIRMED" in result

    @pytest.mark.asyncio
    async def test_status_without_hybrid_repo(self) -> None:
        """STATUS without hybrid_score_repo -> original behavior (no ranks)."""
        sig = _make_signal_record()
        signal_repo = AsyncMock()
        signal_repo.get_active_signals.return_value = [sig]

        trade_repo = AsyncMock()
        trade_repo.get_active_trades.return_value = []

        async def get_prices(symbols):
            return {}

        now = datetime(2026, 2, 26, 10, 0, 0, tzinfo=IST)
        result = await handle_status(signal_repo, trade_repo, get_prices, now=now)

        assert "Active Signals" in result
        assert "#1" not in result  # No rank prefix without hybrid scores


# ========================================================================
# Task 10.6: Enhanced JOURNAL
# ========================================================================


class TestEnhancedJournal:
    """Tests for the enhanced JOURNAL command with confirmed signals section."""

    @pytest.mark.asyncio
    async def test_journal_with_confirmed_signals(self) -> None:
        """JOURNAL with confirmed signals -> shows confirmed count."""
        metrics = PerformanceMetrics(
            date_range_start=date(2026, 2, 20),
            date_range_end=date(2026, 2, 26),
            total_signals=10, trades_taken=8, wins=6, losses=2,
            win_rate=75.0, total_pnl=3000.0, avg_win=600.0, avg_loss=-150.0,
            risk_reward_ratio=4.0,
            best_trade_symbol="RELIANCE", best_trade_pnl=1500.0,
            worst_trade_symbol="TCS", worst_trade_pnl=-200.0,
        )
        metrics_calc = AsyncMock()
        metrics_calc.calculate_performance_metrics.return_value = metrics

        hybrid_repo = AsyncMock()
        hybrid_repo.get_by_date.return_value = [
            _make_hybrid_score(confirmation_level="double"),
            _make_hybrid_score(confirmation_level="triple"),
            _make_hybrid_score(confirmation_level="single"),  # Not counted
        ]

        result = await handle_journal(metrics_calc, hybrid_score_repo=hybrid_repo)
        assert "Trade Journal" in result
        assert "Confirmed Signals Today: 2" in result

    @pytest.mark.asyncio
    async def test_journal_without_hybrid_repo(self) -> None:
        """JOURNAL without hybrid_score_repo -> original format."""
        metrics = PerformanceMetrics(
            date_range_start=date(2026, 2, 20),
            date_range_end=date(2026, 2, 26),
            total_signals=5, trades_taken=3, wins=2, losses=1,
            win_rate=66.7, total_pnl=1000.0, avg_win=700.0, avg_loss=-400.0,
            risk_reward_ratio=1.75,
            best_trade_symbol="SBIN", best_trade_pnl=800.0,
            worst_trade_symbol="TCS", worst_trade_pnl=-400.0,
        )
        metrics_calc = AsyncMock()
        metrics_calc.calculate_performance_metrics.return_value = metrics

        result = await handle_journal(metrics_calc)
        assert "Trade Journal" in result
        assert "Confirmed Signals" not in result


# ========================================================================
# Task 10.7: Enhanced STRATEGY
# ========================================================================


class TestEnhancedStrategy:
    """Tests for the enhanced STRATEGY command with adaptation status."""

    @pytest.mark.asyncio
    async def test_strategy_with_adaptation_status(self) -> None:
        """STRATEGY with adaptive_manager -> shows adaptation status."""
        from signalpilot.monitor.adaptive_manager import (
            AdaptationLevel,
            StrategyAdaptationState,
        )

        records = [
            StrategyPerformanceRecord(
                strategy="Gap & Go", date="2026-02-20",
                signals_generated=5, signals_taken=3, wins=2, losses=1,
                total_pnl=1000.0, win_rate=66.7, avg_win=600.0, avg_loss=-200.0,
                capital_weight_pct=40.0,
            ),
        ]
        strategy_repo = AsyncMock()
        strategy_repo.get_by_date_range.return_value = records

        am = MagicMock()
        am.get_all_states.return_value = {
            "Gap & Go": StrategyAdaptationState(
                strategy_name="Gap & Go",
                consecutive_losses=0, consecutive_wins=2,
                level=AdaptationLevel.NORMAL,
                daily_wins=2, daily_losses=1,
            ),
        }

        result = await handle_strategy(strategy_repo, adaptive_manager=am)
        assert "Strategy Performance" in result
        assert "Adaptation Status" in result
        assert "NORMAL" in result
        assert "W:2 L:1" in result

    @pytest.mark.asyncio
    async def test_strategy_without_adaptive_manager(self) -> None:
        """STRATEGY without adaptive_manager -> original format."""
        records = [
            StrategyPerformanceRecord(
                strategy="ORB", date="2026-02-20",
                signals_generated=3, signals_taken=2, wins=1, losses=1,
                total_pnl=200.0, win_rate=50.0, avg_win=500.0, avg_loss=-300.0,
                capital_weight_pct=20.0,
            ),
        ]
        strategy_repo = AsyncMock()
        strategy_repo.get_by_date_range.return_value = records

        result = await handle_strategy(strategy_repo)
        assert "Strategy Performance" in result
        assert "Adaptation Status" not in result


# ========================================================================
# Task 10.8: Enhanced HELP
# ========================================================================


class TestEnhancedHelp:
    """Tests for the enhanced HELP command with Phase 3 commands."""

    @pytest.mark.asyncio
    async def test_help_includes_phase3_commands(self) -> None:
        """HELP lists all Phase 3 commands."""
        result = await handle_help()

        # Phase 1/2 commands
        assert "TAKEN" in result
        assert "STATUS" in result
        assert "JOURNAL" in result
        assert "CAPITAL" in result
        assert "PAUSE" in result
        assert "RESUME" in result
        assert "ALLOCATE" in result
        assert "STRATEGY" in result
        assert "HELP" in result

        # Phase 3 commands
        assert "SCORE" in result
        assert "ADAPT" in result
        assert "REBALANCE" in result
        assert "OVERRIDE CIRCUIT" in result


# ========================================================================
# Task 10.9: Signal formatter confirmation badges
# ========================================================================


class TestConfirmationBadges:
    """Tests for confirmation badges in signal formatting."""

    def test_confirmation_badge_single(self) -> None:
        """Single confirmation -> empty badge."""
        from signalpilot.telegram.formatters import _confirmation_badge

        assert _confirmation_badge("single") == ""
        assert _confirmation_badge(None) == ""

    def test_confirmation_badge_double(self) -> None:
        """Double confirmation -> DOUBLE CONFIRMED badge."""
        from signalpilot.telegram.formatters import _confirmation_badge

        badge = _confirmation_badge("double", "Gap & Go,ORB")
        assert "DOUBLE CONFIRMED" in badge
        assert "Gap & Go,ORB" in badge
        assert "1.5x" in badge

    def test_confirmation_badge_triple(self) -> None:
        """Triple confirmation -> TRIPLE CONFIRMED badge."""
        from signalpilot.telegram.formatters import _confirmation_badge

        badge = _confirmation_badge("triple", "Gap & Go,ORB,VWAP Reversal")
        assert "TRIPLE CONFIRMED" in badge
        assert "2.0x" in badge

    def test_format_signal_with_confirmation(self) -> None:
        """format_signal_message with confirmation_level -> includes badge."""
        from signalpilot.db.models import (
            CandidateSignal,
            FinalSignal,
            RankedSignal,
            SignalDirection,
        )
        from signalpilot.telegram.formatters import format_signal_message

        candidate = CandidateSignal(
            symbol="SBIN", direction=SignalDirection.BUY,
            strategy_name="Gap & Go",
            entry_price=500.0, stop_loss=485.0,
            target_1=525.0, target_2=535.0,
            generated_at=datetime(2026, 2, 26, 9, 35, tzinfo=IST),
        )
        ranked = RankedSignal(
            candidate=candidate, composite_score=75.0, rank=1, signal_strength=4,
        )
        signal = FinalSignal(
            ranked_signal=ranked, quantity=10, capital_required=5000.0,
            expires_at=datetime(2026, 2, 26, 10, 5, tzinfo=IST),
        )

        result = format_signal_message(
            signal, confirmation_level="double",
            confirmed_by="Gap & Go,ORB", boosted_stars=5,
        )
        assert "DOUBLE CONFIRMED" in result
        assert "Gap & Go,ORB" in result
        assert "1.5x" in result
        # Boosted stars should be used
        assert "Very Strong" in result

    def test_format_signal_without_confirmation(self) -> None:
        """format_signal_message without confirmation -> no badge."""
        from signalpilot.db.models import (
            CandidateSignal,
            FinalSignal,
            RankedSignal,
            SignalDirection,
        )
        from signalpilot.telegram.formatters import format_signal_message

        candidate = CandidateSignal(
            symbol="SBIN", direction=SignalDirection.BUY,
            strategy_name="Gap & Go",
            entry_price=500.0, stop_loss=485.0,
            target_1=525.0, target_2=535.0,
            generated_at=datetime(2026, 2, 26, 9, 35, tzinfo=IST),
        )
        ranked = RankedSignal(
            candidate=candidate, composite_score=75.0, rank=1, signal_strength=4,
        )
        signal = FinalSignal(
            ranked_signal=ranked, quantity=10, capital_required=5000.0,
            expires_at=datetime(2026, 2, 26, 10, 5, tzinfo=IST),
        )

        result = format_signal_message(signal)
        assert "CONFIRMED" not in result


# ========================================================================
# Status formatter with score_map and confirmation_map
# ========================================================================


class TestStatusFormatter:
    """Tests for enhanced format_status_message."""

    def test_status_with_score_map(self) -> None:
        """format_status_message with score_map -> rank numbers and scores."""
        from signalpilot.telegram.formatters import format_status_message

        signals = [
            _make_signal_record(signal_id=1, symbol="SBIN"),
            _make_signal_record(signal_id=2, symbol="TCS"),
        ]
        score_map = {"TCS": 85.0, "SBIN": 60.0}

        result = format_status_message(signals, [], {}, score_map=score_map)
        assert "#1" in result
        assert "#2" in result
        assert "[Score: 85]" in result
        assert "[Score: 60]" in result
        # TCS should be first (higher score)
        assert result.index("TCS") < result.index("SBIN")

    def test_status_with_confirmation_map(self) -> None:
        """format_status_message with confirmation_map -> badges."""
        from signalpilot.telegram.formatters import format_status_message

        signals = [_make_signal_record(symbol="SBIN")]
        confirmation_map = {"SBIN": "double"}

        result = format_status_message(
            signals, [], {},
            score_map={"SBIN": 75.0},
            confirmation_map=confirmation_map,
        )
        assert "DOUBLE CONFIRMED" in result

    def test_status_without_enhancements(self) -> None:
        """format_status_message without maps -> original format."""
        from signalpilot.telegram.formatters import format_status_message

        signals = [_make_signal_record(symbol="SBIN")]
        result = format_status_message(signals, [], {})
        assert "#1" not in result
        assert "Score:" not in result


# ========================================================================
# Journal formatter with confirmed count
# ========================================================================


class TestJournalFormatter:
    """Tests for enhanced format_journal_message."""

    def test_journal_with_confirmed_count(self) -> None:
        """format_journal_message with confirmed_count > 0 -> shows section."""
        from signalpilot.telegram.formatters import format_journal_message

        metrics = PerformanceMetrics(
            date_range_start=date(2026, 2, 20),
            date_range_end=date(2026, 2, 26),
            total_signals=10, trades_taken=8, wins=6, losses=2,
            win_rate=75.0, total_pnl=3000.0, avg_win=600.0, avg_loss=-150.0,
            risk_reward_ratio=4.0,
            best_trade_symbol="RELIANCE", best_trade_pnl=1500.0,
            worst_trade_symbol="TCS", worst_trade_pnl=-200.0,
        )
        result = format_journal_message(metrics, confirmed_count=3)
        assert "Confirmed Signals Today: 3" in result

    def test_journal_without_confirmed_count(self) -> None:
        """format_journal_message with confirmed_count=0 -> no section."""
        from signalpilot.telegram.formatters import format_journal_message

        metrics = PerformanceMetrics(
            date_range_start=date(2026, 2, 20),
            date_range_end=date(2026, 2, 26),
            total_signals=5, trades_taken=3, wins=2, losses=1,
            win_rate=66.7, total_pnl=1000.0, avg_win=700.0, avg_loss=-400.0,
            risk_reward_ratio=1.75,
            best_trade_symbol="SBIN", best_trade_pnl=800.0,
            worst_trade_symbol="TCS", worst_trade_pnl=-400.0,
        )
        result = format_journal_message(metrics, confirmed_count=0)
        assert "Confirmed Signals" not in result
