"""Tests for paper trading mode logic in the scan loop."""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from signalpilot.db.models import (
    CandidateSignal,
    FinalSignal,
    RankedSignal,
    SignalDirection,
    UserConfig,
)
from signalpilot.scheduler.lifecycle import SignalPilotApp
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_strategy(evaluate_return=None, active_phases=None, name="Gap & Go"):
    """Create a mock strategy with required attributes for the scan loop."""
    mock = AsyncMock(evaluate=AsyncMock(return_value=evaluate_return or []))
    mock.name = name
    mock.active_phases = active_phases or [
        StrategyPhase.OPENING,
        StrategyPhase.ENTRY_WINDOW,
    ]
    return mock


def _make_app(**overrides) -> SignalPilotApp:
    """Create a SignalPilotApp with all mocked dependencies."""
    defaults = {
        "db": AsyncMock(),
        "signal_repo": AsyncMock(),
        "trade_repo": AsyncMock(),
        "config_repo": AsyncMock(),
        "metrics_calculator": AsyncMock(),
        "authenticator": AsyncMock(),
        "instruments": AsyncMock(),
        "market_data": MagicMock(),
        "historical": AsyncMock(),
        "websocket": AsyncMock(),
        "strategy": _make_mock_strategy(),
        "ranker": MagicMock(),
        "risk_manager": MagicMock(),
        "exit_monitor": MagicMock(
            check_trade=AsyncMock(return_value=None),
            trigger_time_exit=AsyncMock(return_value=[]),
            start_monitoring=MagicMock(),
        ),
        "bot": AsyncMock(),
        "scheduler": MagicMock(),
    }
    defaults.update(overrides)
    return SignalPilotApp(**defaults)


def _make_final_signal(symbol: str = "SBIN", strategy_name: str = "Gap & Go") -> FinalSignal:
    """Create a FinalSignal with configurable strategy name."""
    candidate = CandidateSignal(
        symbol=symbol,
        direction=SignalDirection.BUY,
        strategy_name=strategy_name,
        entry_price=100.0,
        stop_loss=97.0,
        target_1=105.0,
        target_2=107.0,
        gap_pct=4.0,
        volume_ratio=2.0,
        price_distance_from_open_pct=1.5,
        reason="test",
        generated_at=datetime(2025, 1, 6, 9, 35, 0, tzinfo=IST),
    )
    ranked = RankedSignal(
        candidate=candidate, composite_score=0.8, rank=1, signal_strength=4
    )
    return FinalSignal(
        ranked_signal=ranked,
        quantity=10,
        capital_required=1000.0,
        expires_at=datetime(2025, 1, 6, 10, 5, 0, tzinfo=IST),
    )


def _run_single_scan_iteration(app, signal, user_config):
    """Configure mocks and run exactly one scan loop iteration.

    Returns the SignalRecord that was passed to insert_signal.
    """
    mock_strategy = _make_mock_strategy(evaluate_return=["candidate1"])
    app._strategies = [mock_strategy]
    app._ranker.rank = MagicMock(return_value=["ranked1"])
    app._config_repo.get_user_config = AsyncMock(return_value=user_config)
    app._trade_repo.get_active_trade_count = AsyncMock(return_value=0)
    app._risk_manager.filter_and_size = MagicMock(return_value=[signal])
    app._signal_repo.insert_signal = AsyncMock(return_value=1)
    app._bot.send_signal = AsyncMock()
    app._exit_monitor.check_trade = AsyncMock()
    app._signal_repo.expire_stale_signals = AsyncMock(return_value=0)


# ---------------------------------------------------------------------------
# _is_paper_mode unit tests
# ---------------------------------------------------------------------------


class TestIsPaperMode:
    """Tests for SignalPilotApp._is_paper_mode static method."""

    def test_orb_signal_with_paper_mode_true(self):
        """ORB signal with orb_paper_mode=True should be paper."""
        signal = _make_final_signal(strategy_name="ORB")
        config = SimpleNamespace(orb_paper_mode=True, vwap_paper_mode=False)
        assert SignalPilotApp._is_paper_mode(signal, config) is True

    def test_orb_signal_with_paper_mode_false(self):
        """ORB signal with orb_paper_mode=False should not be paper."""
        signal = _make_final_signal(strategy_name="ORB")
        config = SimpleNamespace(orb_paper_mode=False, vwap_paper_mode=False)
        assert SignalPilotApp._is_paper_mode(signal, config) is False

    def test_vwap_signal_with_paper_mode_true(self):
        """VWAP Reversal signal with vwap_paper_mode=True should be paper."""
        signal = _make_final_signal(strategy_name="VWAP Reversal")
        config = SimpleNamespace(orb_paper_mode=False, vwap_paper_mode=True)
        assert SignalPilotApp._is_paper_mode(signal, config) is True

    def test_vwap_signal_with_paper_mode_false(self):
        """VWAP Reversal signal with vwap_paper_mode=False should not be paper."""
        signal = _make_final_signal(strategy_name="VWAP Reversal")
        config = SimpleNamespace(orb_paper_mode=False, vwap_paper_mode=False)
        assert SignalPilotApp._is_paper_mode(signal, config) is False

    def test_gap_and_go_never_paper(self):
        """Gap & Go signals should never be in paper mode."""
        signal = _make_final_signal(strategy_name="Gap & Go")
        config = SimpleNamespace(orb_paper_mode=True, vwap_paper_mode=True)
        assert SignalPilotApp._is_paper_mode(signal, config) is False

    def test_gap_and_go_not_paper_even_with_extra_attrs(self):
        """Gap & Go should not be paper regardless of other paper mode flags."""
        signal = _make_final_signal(strategy_name="Gap & Go")
        config = SimpleNamespace(orb_paper_mode=True, vwap_paper_mode=True)
        assert SignalPilotApp._is_paper_mode(signal, config) is False

    def test_unknown_strategy_not_paper(self):
        """Unknown strategy names should not be in paper mode."""
        signal = _make_final_signal(strategy_name="SomeNewStrategy")
        config = SimpleNamespace(orb_paper_mode=True, vwap_paper_mode=True)
        assert SignalPilotApp._is_paper_mode(signal, config) is False

    def test_none_app_config_defaults_to_not_paper(self):
        """When app_config is None, no strategy should be paper-traded."""
        signal = _make_final_signal(strategy_name="ORB")
        assert SignalPilotApp._is_paper_mode(signal, None) is False


# ---------------------------------------------------------------------------
# Scan loop integration with paper mode
# ---------------------------------------------------------------------------


class TestScanLoopPaperMode:
    """Tests verifying that paper mode integrates correctly in the scan loop."""

    async def test_orb_paper_signal_gets_paper_status(self):
        """ORB signal in paper mode should be saved with status='paper'."""
        signal = _make_final_signal(strategy_name="ORB")
        user_config = UserConfig(total_capital=50000.0, max_positions=8)

        app = _make_app(app_config=SimpleNamespace(orb_paper_mode=True, vwap_paper_mode=False))
        _run_single_scan_iteration(app, signal, user_config)

        call_count = 0
        original_sleep = asyncio.sleep

        async def mock_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                app._scanning = False
            await original_sleep(0)

        with patch(
            "signalpilot.scheduler.lifecycle.get_current_phase",
            return_value=StrategyPhase.OPENING,
        ), patch("asyncio.sleep", side_effect=mock_sleep):
            app._scanning = True
            app._accepting_signals = True
            await app._scan_loop()

        # Verify the record passed to insert_signal has status="paper"
        insert_call = app._signal_repo.insert_signal.call_args
        record = insert_call[0][0]
        assert record.status == "paper"

        # Verify send_signal was called with is_paper=True
        app._bot.send_signal.assert_awaited_once_with(
            signal, is_paper=True, signal_id=1,
            confirmation_level=None, confirmed_by=None, boosted_stars=None,
        )

    async def test_gap_go_signal_gets_sent_status(self):
        """Gap & Go signal should always be saved with status='sent'."""
        signal = _make_final_signal(strategy_name="Gap & Go")
        user_config = UserConfig(total_capital=50000.0, max_positions=8)

        app = _make_app(app_config=SimpleNamespace(orb_paper_mode=True, vwap_paper_mode=True))
        _run_single_scan_iteration(app, signal, user_config)

        call_count = 0
        original_sleep = asyncio.sleep

        async def mock_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                app._scanning = False
            await original_sleep(0)

        with patch(
            "signalpilot.scheduler.lifecycle.get_current_phase",
            return_value=StrategyPhase.OPENING,
        ), patch("asyncio.sleep", side_effect=mock_sleep):
            app._scanning = True
            app._accepting_signals = True
            await app._scan_loop()

        # Verify the record passed to insert_signal has status="sent"
        insert_call = app._signal_repo.insert_signal.call_args
        record = insert_call[0][0]
        assert record.status == "sent"

        # Verify send_signal was called with is_paper=False
        app._bot.send_signal.assert_awaited_once_with(
            signal, is_paper=False, signal_id=1,
            confirmation_level=None, confirmed_by=None, boosted_stars=None,
        )

    async def test_orb_paper_mode_false_gets_sent_status(self):
        """ORB signal with paper_mode=False should be saved with status='sent'."""
        signal = _make_final_signal(strategy_name="ORB")
        user_config = UserConfig(total_capital=50000.0, max_positions=8)

        app = _make_app(app_config=SimpleNamespace(orb_paper_mode=False, vwap_paper_mode=False))
        _run_single_scan_iteration(app, signal, user_config)

        call_count = 0
        original_sleep = asyncio.sleep

        async def mock_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                app._scanning = False
            await original_sleep(0)

        with patch(
            "signalpilot.scheduler.lifecycle.get_current_phase",
            return_value=StrategyPhase.OPENING,
        ), patch("asyncio.sleep", side_effect=mock_sleep):
            app._scanning = True
            app._accepting_signals = True
            await app._scan_loop()

        insert_call = app._signal_repo.insert_signal.call_args
        record = insert_call[0][0]
        assert record.status == "sent"
        app._bot.send_signal.assert_awaited_once_with(
            signal, is_paper=False, signal_id=1,
            confirmation_level=None, confirmed_by=None, boosted_stars=None,
        )

    async def test_vwap_paper_signal_gets_paper_status(self):
        """VWAP Reversal signal in paper mode should be saved with status='paper'."""
        signal = _make_final_signal(strategy_name="VWAP Reversal")
        user_config = UserConfig(total_capital=50000.0, max_positions=8)

        app = _make_app(app_config=SimpleNamespace(orb_paper_mode=False, vwap_paper_mode=True))
        _run_single_scan_iteration(app, signal, user_config)

        call_count = 0
        original_sleep = asyncio.sleep

        async def mock_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                app._scanning = False
            await original_sleep(0)

        with patch(
            "signalpilot.scheduler.lifecycle.get_current_phase",
            return_value=StrategyPhase.OPENING,
        ), patch("asyncio.sleep", side_effect=mock_sleep):
            app._scanning = True
            app._accepting_signals = True
            await app._scan_loop()

        insert_call = app._signal_repo.insert_signal.call_args
        record = insert_call[0][0]
        assert record.status == "paper"
        app._bot.send_signal.assert_awaited_once_with(
            signal, is_paper=True, signal_id=1,
            confirmation_level=None, confirmed_by=None, boosted_stars=None,
        )
