"""Tests for Phase 4 callback handlers."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.db.models import (
    CallbackResult,
    SignalRecord,
    TradeRecord,
    WatchlistRecord,
)
from signalpilot.db.signal_action_repo import SignalActionRepository
from signalpilot.db.signal_repo import SignalRepository
from signalpilot.db.trade_repo import TradeRepository
from signalpilot.db.watchlist_repo import WatchlistRepository
from signalpilot.telegram.handlers import (
    handle_exit_now_callback,
    handle_help,
    handle_hold_callback,
    handle_let_run_callback,
    handle_partial_exit_callback,
    handle_skip_callback,
    handle_skip_reason_callback,
    handle_take_profit_callback,
    handle_taken_callback,
    handle_unwatch_command,
    handle_watch_callback,
    handle_watchlist_command,
)
from signalpilot.utils.constants import IST


def _make_signal(now=None, status="sent"):
    now = now or datetime.now(IST)
    return SignalRecord(
        date=now.date(),
        symbol="SBIN",
        strategy="Gap & Go",
        entry_price=100.0,
        stop_loss=97.0,
        target_1=105.0,
        target_2=107.0,
        quantity=15,
        capital_required=1500.0,
        signal_strength=4,
        gap_pct=4.0,
        volume_ratio=2.0,
        reason="Test signal",
        created_at=now,
        expires_at=now + timedelta(minutes=30),
        status=status,
    )


class TestTakenCallback:
    async def test_taken_callback_success(self, db):
        signal_repo = SignalRepository(db.connection)
        trade_repo = TradeRepository(db.connection)
        action_repo = SignalActionRepository(db.connection)
        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        config_repo = AsyncMock()
        config_repo.get_user_config.return_value = MagicMock(max_positions=8)
        exit_monitor = MagicMock()

        result = await handle_taken_callback(
            signal_repo, trade_repo, config_repo, exit_monitor,
            action_repo, signal_id, now,
        )
        assert result.success is True
        assert "SBIN" in result.answer_text
        assert result.new_keyboard is not None
        exit_monitor.start_monitoring.assert_called_once()

    async def test_taken_callback_expired_signal(self, db):
        signal_repo = SignalRepository(db.connection)
        trade_repo = TradeRepository(db.connection)
        past = datetime.now(IST) - timedelta(hours=1)
        signal_id = await signal_repo.insert_signal(_make_signal(past))
        now = datetime.now(IST)

        config_repo = AsyncMock()
        exit_monitor = MagicMock()

        result = await handle_taken_callback(
            signal_repo, trade_repo, config_repo, exit_monitor,
            None, signal_id, now,
        )
        assert result.success is False
        assert "expired" in result.answer_text.lower()

    async def test_taken_callback_already_taken(self, db):
        signal_repo = SignalRepository(db.connection)
        trade_repo = TradeRepository(db.connection)
        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))
        await signal_repo.update_status(signal_id, "taken")

        config_repo = AsyncMock()
        exit_monitor = MagicMock()

        result = await handle_taken_callback(
            signal_repo, trade_repo, config_repo, exit_monitor,
            None, signal_id, now,
        )
        assert result.success is False
        assert "taken" in result.answer_text.lower()

    async def test_taken_callback_already_skipped(self, db):
        signal_repo = SignalRepository(db.connection)
        trade_repo = TradeRepository(db.connection)
        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))
        await signal_repo.update_status(signal_id, "skipped")

        config_repo = AsyncMock()
        exit_monitor = MagicMock()

        result = await handle_taken_callback(
            signal_repo, trade_repo, config_repo, exit_monitor,
            None, signal_id, now,
        )
        assert result.success is False
        assert "skipped" in result.answer_text.lower()

    async def test_taken_callback_position_limit(self, db):
        signal_repo = SignalRepository(db.connection)
        trade_repo = TradeRepository(db.connection)
        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        # Mock config with max 1 position, already 1 active trade
        config_repo = AsyncMock()
        config_repo.get_user_config.return_value = MagicMock(max_positions=1)

        # Insert one active trade
        trade = TradeRecord(
            signal_id=signal_id, date=now.date(), symbol="TCS",
            entry_price=3500.0, stop_loss=3400.0, target_1=3600.0, target_2=3700.0,
            quantity=3, taken_at=now, strategy="Gap & Go",
        )
        sig2 = await signal_repo.insert_signal(_make_signal(now))
        await signal_repo.update_status(sig2, "taken")
        trade.signal_id = sig2
        await trade_repo.insert_trade(trade)

        exit_monitor = MagicMock()

        result = await handle_taken_callback(
            signal_repo, trade_repo, config_repo, exit_monitor,
            None, signal_id, now,
        )
        assert result.success is False
        assert "limit" in result.answer_text.lower() or "Position" in result.answer_text

    async def test_taken_callback_response_time(self, db):
        signal_repo = SignalRepository(db.connection)
        trade_repo = TradeRepository(db.connection)
        action_repo = SignalActionRepository(db.connection)
        created = datetime.now(IST) - timedelta(seconds=5)
        signal_id = await signal_repo.insert_signal(_make_signal(created))
        now = created + timedelta(seconds=5)

        config_repo = AsyncMock()
        config_repo.get_user_config.return_value = MagicMock(max_positions=8)
        exit_monitor = MagicMock()

        await handle_taken_callback(
            signal_repo, trade_repo, config_repo, exit_monitor,
            action_repo, signal_id, now,
        )

        actions = await action_repo.get_actions_for_signal(signal_id)
        assert len(actions) == 1
        assert actions[0].response_time_ms is not None
        assert actions[0].response_time_ms >= 4000  # ~5 seconds


class TestSkipCallbacks:
    async def test_skip_callback_shows_reasons(self, db):
        signal_repo = SignalRepository(db.connection)
        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        result = await handle_skip_callback(
            signal_repo, None, signal_id, now,
        )
        assert result.success is True
        assert result.new_keyboard is not None

    async def test_skip_reason_callback_success(self, db):
        signal_repo = SignalRepository(db.connection)
        action_repo = SignalActionRepository(db.connection)
        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        result = await handle_skip_reason_callback(
            signal_repo, action_repo, signal_id, "no_capital", now,
        )
        assert result.success is True
        assert "No Capital" in result.status_line

        # Verify signal status changed
        cursor = await db.connection.execute(
            "SELECT status FROM signals WHERE id = ?", (signal_id,)
        )
        row = await cursor.fetchone()
        assert row["status"] == "skipped"

    @pytest.mark.parametrize("reason", ["no_capital", "low_confidence", "sector", "other"])
    async def test_skip_reason_callback_each_reason(self, db, reason):
        signal_repo = SignalRepository(db.connection)
        action_repo = SignalActionRepository(db.connection)
        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        result = await handle_skip_reason_callback(
            signal_repo, action_repo, signal_id, reason, now,
        )
        assert result.success is True

        actions = await action_repo.get_actions_for_signal(signal_id)
        assert len(actions) == 1
        assert actions[0].reason == reason


class TestWatchCallback:
    async def test_watch_callback_success(self, db):
        signal_repo = SignalRepository(db.connection)
        action_repo = SignalActionRepository(db.connection)
        watchlist_repo = WatchlistRepository(db.connection)
        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        result = await handle_watch_callback(
            signal_repo, action_repo, watchlist_repo, signal_id, now,
        )
        assert result.success is True
        assert "watchlist" in result.answer_text.lower()

        # Verify on watchlist
        assert await watchlist_repo.is_on_watchlist("SBIN", now)

    async def test_watch_callback_already_on_watchlist(self, db):
        signal_repo = SignalRepository(db.connection)
        action_repo = SignalActionRepository(db.connection)
        watchlist_repo = WatchlistRepository(db.connection)
        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        # Add first
        await handle_watch_callback(
            signal_repo, action_repo, watchlist_repo, signal_id, now,
        )
        # Try again
        result = await handle_watch_callback(
            signal_repo, action_repo, watchlist_repo, signal_id, now,
        )
        assert result.success is False
        assert "already" in result.answer_text.lower()

    async def test_watch_callback_expired_signal(self, db):
        signal_repo = SignalRepository(db.connection)
        watchlist_repo = WatchlistRepository(db.connection)
        past = datetime.now(IST) - timedelta(hours=1)
        signal_id = await signal_repo.insert_signal(_make_signal(past))
        now = datetime.now(IST)

        result = await handle_watch_callback(
            signal_repo, None, watchlist_repo, signal_id, now,
        )
        assert result.success is False
        assert "expired" in result.answer_text.lower()


class TestTradeManagementCallbacks:
    async def test_partial_exit_t1_success(self):
        trade_repo = AsyncMock()
        trade = TradeRecord(
            id=1, signal_id=1, symbol="SBIN", entry_price=100.0,
            stop_loss=97.0, target_1=105.0, target_2=107.0, quantity=15,
            taken_at=datetime.now(IST),
        )
        trade_repo.get_active_trades.return_value = [trade]

        result = await handle_partial_exit_callback(trade_repo, 1, "t1")
        assert result.success is True
        assert "T1" in result.status_line

    async def test_partial_exit_already_exited(self):
        trade_repo = AsyncMock()
        trade_repo.get_active_trades.return_value = []

        result = await handle_partial_exit_callback(trade_repo, 1, "t1")
        assert result.success is False
        assert "closed" in result.answer_text.lower()

    async def test_full_exit_t2_success(self):
        trade_repo = AsyncMock()
        trade = TradeRecord(
            id=2, signal_id=1, symbol="SBIN", entry_price=100.0,
            stop_loss=97.0, target_1=105.0, target_2=107.0, quantity=15,
            taken_at=datetime.now(IST),
        )
        trade_repo.get_active_trades.return_value = [trade]

        result = await handle_partial_exit_callback(trade_repo, 2, "t2")
        assert result.success is True
        assert "T2" in result.status_line

    async def test_exit_now_success(self):
        trade_repo = AsyncMock()
        trade = TradeRecord(
            id=1, signal_id=1, symbol="SBIN", entry_price=100.0,
            stop_loss=97.0, target_1=105.0, target_2=107.0, quantity=15,
            taken_at=datetime.now(IST),
        )
        trade_repo.get_active_trades.return_value = [trade]
        exit_monitor = MagicMock()
        get_prices = AsyncMock(return_value={"SBIN": 99.0})

        result = await handle_exit_now_callback(trade_repo, exit_monitor, get_prices, 1)
        assert result.success is True
        trade_repo.close_trade.assert_called_once()
        exit_monitor.stop_monitoring.assert_called_once_with(1)

    async def test_exit_now_no_price(self):
        trade_repo = AsyncMock()
        trade = TradeRecord(
            id=1, signal_id=1, symbol="SBIN", entry_price=100.0,
            stop_loss=97.0, target_1=105.0, target_2=107.0, quantity=15,
            taken_at=datetime.now(IST),
        )
        trade_repo.get_active_trades.return_value = [trade]
        exit_monitor = MagicMock()
        get_prices = AsyncMock(return_value={})

        result = await handle_exit_now_callback(trade_repo, exit_monitor, get_prices, 1)
        assert result.success is False
        assert "price" in result.answer_text.lower()

    async def test_take_profit_success(self):
        trade_repo = AsyncMock()
        trade = TradeRecord(
            id=1, signal_id=1, symbol="SBIN", entry_price=100.0,
            stop_loss=97.0, target_1=105.0, target_2=107.0, quantity=15,
            taken_at=datetime.now(IST),
        )
        trade_repo.get_active_trades.return_value = [trade]
        exit_monitor = MagicMock()
        get_prices = AsyncMock(return_value={"SBIN": 107.0})

        result = await handle_take_profit_callback(trade_repo, exit_monitor, get_prices, 1)
        assert result.success is True
        trade_repo.close_trade.assert_called_once()

    async def test_hold_dismisses(self):
        result = await handle_hold_callback(1)
        assert result.success is True

    async def test_let_run_dismisses(self):
        result = await handle_let_run_callback(1)
        assert result.success is True


class TestWatchlistTextCommands:
    async def test_watchlist_command_with_entries(self, db):
        watchlist_repo = WatchlistRepository(db.connection)
        now = datetime.now(IST)
        entry = WatchlistRecord(
            symbol="SBIN", signal_id=None, strategy="Gap & Go",
            entry_price=100.0, added_at=now,
            expires_at=now + timedelta(days=5),
        )
        await watchlist_repo.add_to_watchlist(entry)

        result = await handle_watchlist_command(watchlist_repo)
        assert "SBIN" in result
        assert "1 stocks" in result

    async def test_watchlist_command_empty(self):
        repo = AsyncMock()
        repo.get_active_watchlist.return_value = []

        result = await handle_watchlist_command(repo)
        assert "No stocks" in result

    async def test_unwatch_command_success(self, db):
        watchlist_repo = WatchlistRepository(db.connection)
        now = datetime.now(IST)
        entry = WatchlistRecord(
            symbol="SBIN", signal_id=None, strategy="Gap & Go",
            entry_price=100.0, added_at=now,
            expires_at=now + timedelta(days=5),
        )
        await watchlist_repo.add_to_watchlist(entry)

        result = await handle_unwatch_command(watchlist_repo, "UNWATCH SBIN")
        assert "removed" in result

    async def test_unwatch_command_not_found(self, db):
        watchlist_repo = WatchlistRepository(db.connection)
        result = await handle_unwatch_command(watchlist_repo, "UNWATCH TCS")
        assert "not on your watchlist" in result

    async def test_unwatch_command_invalid(self, db):
        watchlist_repo = WatchlistRepository(db.connection)
        result = await handle_unwatch_command(watchlist_repo, "UNWATCH")
        assert "Usage" in result

    async def test_help_includes_buttons_and_watchlist(self):
        result = await handle_help()
        assert "WATCHLIST" in result
        assert "UNWATCH" in result
        assert "Tap buttons" in result
