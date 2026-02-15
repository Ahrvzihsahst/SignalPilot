"""Tests for TradeRepository."""

from datetime import date, datetime
from unittest.mock import patch

import aiosqlite
import pytest

from signalpilot.db.models import SignalRecord, TradeRecord


async def _insert_parent_signal(signal_repo) -> int:
    """Insert a parent signal and return its ID (needed for FK constraint)."""
    signal = SignalRecord(
        date=date(2026, 2, 16),
        symbol="SBIN",
        strategy="gap_and_go",
        entry_price=770.0,
        stop_loss=745.0,
        target_1=808.5,
        target_2=823.9,
        quantity=13,
        capital_required=10010.0,
        signal_strength=4,
        gap_pct=4.05,
        volume_ratio=1.8,
        reason="Gap up",
        created_at=datetime(2026, 2, 16, 9, 35, 0),
        expires_at=datetime(2026, 2, 16, 10, 5, 0),
    )
    return await signal_repo.insert_signal(signal)


def _make_trade(signal_id: int, symbol="SBIN", d=None, taken_at=None) -> TradeRecord:
    d = d or date(2026, 2, 16)
    taken_at = taken_at or datetime(2026, 2, 16, 9, 36, 0)
    return TradeRecord(
        signal_id=signal_id,
        date=d,
        symbol=symbol,
        entry_price=770.0,
        stop_loss=745.0,
        target_1=808.5,
        target_2=823.9,
        quantity=13,
        taken_at=taken_at,
    )


class TestTradeRepository:
    async def test_insert_and_retrieve(self, trade_repo, signal_repo):
        signal_id = await _insert_parent_signal(signal_repo)
        trade = _make_trade(signal_id)
        trade_id = await trade_repo.insert_trade(trade)
        assert trade_id > 0

        trades = await trade_repo.get_trades_by_date(date(2026, 2, 16))
        assert len(trades) == 1
        assert trades[0].id == trade_id
        assert trades[0].symbol == "SBIN"
        assert trades[0].entry_price == 770.0

    async def test_close_trade(self, trade_repo, signal_repo):
        signal_id = await _insert_parent_signal(signal_repo)
        trade = _make_trade(signal_id)
        trade_id = await trade_repo.insert_trade(trade)

        fixed_now = "2026-02-16T15:00:00"
        with patch("signalpilot.db.trade_repo.datetime") as mock_dt:
            mock_dt.now.return_value.isoformat.return_value = fixed_now
            mock_dt.fromisoformat = datetime.fromisoformat
            await trade_repo.close_trade(
                trade_id=trade_id,
                exit_price=808.5,
                pnl_amount=500.5,
                pnl_pct=5.0,
                exit_reason="t1_hit",
            )

        trades = await trade_repo.get_trades_by_date(date(2026, 2, 16))
        closed = trades[0]
        assert closed.exit_price == 808.5
        assert closed.pnl_amount == 500.5
        assert closed.pnl_pct == 5.0
        assert closed.exit_reason == "t1_hit"
        assert closed.exited_at is not None

    async def test_close_trade_nonexistent_id_raises(self, trade_repo):
        with pytest.raises(ValueError, match="Trade 99999 not found"):
            await trade_repo.close_trade(99999, 808.5, 500.5, 5.0, "t1_hit")

    async def test_close_trade_invalid_exit_reason_raises(self, trade_repo, signal_repo):
        signal_id = await _insert_parent_signal(signal_repo)
        trade = _make_trade(signal_id)
        trade_id = await trade_repo.insert_trade(trade)

        with pytest.raises(ValueError, match="Invalid exit_reason"):
            await trade_repo.close_trade(trade_id, 808.5, 500.5, 5.0, "manual_exit")

    async def test_foreign_key_enforced(self, trade_repo):
        """Inserting a trade with a non-existent signal_id should raise."""
        trade = _make_trade(signal_id=99999)
        with pytest.raises(aiosqlite.IntegrityError):
            await trade_repo.insert_trade(trade)

    async def test_active_trade_count(self, trade_repo, signal_repo):
        signal_id = await _insert_parent_signal(signal_repo)

        assert await trade_repo.get_active_trade_count() == 0

        trade = _make_trade(signal_id)
        trade_id = await trade_repo.insert_trade(trade)
        assert await trade_repo.get_active_trade_count() == 1

        await trade_repo.close_trade(trade_id, 808.5, 500.5, 5.0, "t1_hit")
        assert await trade_repo.get_active_trade_count() == 0

    async def test_get_active_trades(self, trade_repo, signal_repo):
        signal_id = await _insert_parent_signal(signal_repo)

        trade1 = _make_trade(signal_id, taken_at=datetime(2026, 2, 16, 9, 36, 0))
        trade2 = _make_trade(signal_id, taken_at=datetime(2026, 2, 16, 9, 37, 0))
        id1 = await trade_repo.insert_trade(trade1)
        await trade_repo.insert_trade(trade2)

        await trade_repo.close_trade(id1, 808.5, 500.5, 5.0, "t1_hit")

        active = await trade_repo.get_active_trades()
        assert len(active) == 1
        assert active[0].exited_at is None

    async def test_date_filtering(self, trade_repo, signal_repo):
        signal_id = await _insert_parent_signal(signal_repo)

        today = _make_trade(signal_id, d=date(2026, 2, 16))
        yesterday = _make_trade(
            signal_id,
            d=date(2026, 2, 15),
            taken_at=datetime(2026, 2, 15, 9, 36, 0),
        )
        await trade_repo.insert_trade(today)
        await trade_repo.insert_trade(yesterday)

        trades = await trade_repo.get_trades_by_date(date(2026, 2, 16))
        assert len(trades) == 1

    async def test_get_all_closed_trades(self, trade_repo, signal_repo):
        signal_id = await _insert_parent_signal(signal_repo)

        trade1 = _make_trade(signal_id, taken_at=datetime(2026, 2, 16, 9, 36, 0))
        trade2 = _make_trade(signal_id, taken_at=datetime(2026, 2, 16, 9, 37, 0))
        id1 = await trade_repo.insert_trade(trade1)
        await trade_repo.insert_trade(trade2)

        await trade_repo.close_trade(id1, 808.5, 500.5, 5.0, "t1_hit")

        closed = await trade_repo.get_all_closed_trades()
        assert len(closed) == 1
        assert closed[0].id == id1

    async def test_round_trip_all_fields(self, trade_repo, signal_repo):
        signal_id = await _insert_parent_signal(signal_repo)
        trade = _make_trade(signal_id)
        trade_id = await trade_repo.insert_trade(trade)

        trades = await trade_repo.get_trades_by_date(date(2026, 2, 16))
        retrieved = trades[0]
        assert retrieved.id == trade_id
        assert retrieved.signal_id == signal_id
        assert retrieved.date == trade.date
        assert retrieved.symbol == trade.symbol
        assert retrieved.entry_price == trade.entry_price
        assert retrieved.exit_price is None
        assert retrieved.stop_loss == trade.stop_loss
        assert retrieved.target_1 == trade.target_1
        assert retrieved.target_2 == trade.target_2
        assert retrieved.quantity == trade.quantity
        assert retrieved.pnl_amount is None
        assert retrieved.exit_reason is None
        assert retrieved.exited_at is None
