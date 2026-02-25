"""Tests for SignalRepository."""

from datetime import date, datetime, timedelta

import pytest

from signalpilot.db.models import SignalRecord


def _make_signal(
    symbol="SBIN",
    strategy="gap_and_go",
    d=None,
    created_at=None,
    expires_at=None,
    status="sent",
) -> SignalRecord:
    """Helper to create a SignalRecord with sensible defaults."""
    d = d or date(2026, 2, 16)
    created_at = created_at or datetime(2026, 2, 16, 9, 35, 0)
    expires_at = expires_at or (created_at + timedelta(minutes=30))
    return SignalRecord(
        date=d,
        symbol=symbol,
        strategy=strategy,
        entry_price=770.0,
        stop_loss=745.0,
        target_1=808.5,
        target_2=823.9,
        quantity=13,
        capital_required=10010.0,
        signal_strength=4,
        gap_pct=4.05,
        volume_ratio=1.8,
        reason="Gap up 4.05%",
        created_at=created_at,
        expires_at=expires_at,
        status=status,
    )


class TestSignalRepository:
    async def test_insert_and_retrieve(self, signal_repo):
        signal = _make_signal()
        signal_id = await signal_repo.insert_signal(signal)
        assert signal_id is not None
        assert signal_id > 0

        signals = await signal_repo.get_signals_by_date(date(2026, 2, 16))
        assert len(signals) == 1
        assert signals[0].id == signal_id
        assert signals[0].symbol == "SBIN"
        assert signals[0].entry_price == 770.0

    async def test_update_status(self, signal_repo):
        signal = _make_signal()
        signal_id = await signal_repo.insert_signal(signal)

        await signal_repo.update_status(signal_id, "expired")

        signals = await signal_repo.get_signals_by_date(date(2026, 2, 16))
        assert signals[0].status == "expired"

    async def test_update_status_invalid_value_raises(self, signal_repo):
        signal = _make_signal()
        signal_id = await signal_repo.insert_signal(signal)

        with pytest.raises(ValueError, match="Invalid signal status"):
            await signal_repo.update_status(signal_id, "active")

    async def test_update_status_nonexistent_id_raises(self, signal_repo):
        with pytest.raises(ValueError, match="Signal 99999 not found"):
            await signal_repo.update_status(99999, "expired")

    async def test_get_active_signals_excludes_expired(self, signal_repo):
        active = _make_signal(
            symbol="SBIN",
            expires_at=datetime(2099, 12, 31, 23, 59, 59),
        )
        await signal_repo.insert_signal(active)

        expired = _make_signal(symbol="INFY", status="expired")
        await signal_repo.insert_signal(expired)

        # Pass a "now" that is before the far-future expiry
        result = await signal_repo.get_active_signals(
            date(2026, 2, 16), now=datetime(2026, 2, 16, 10, 0, 0)
        )
        symbols = [s.symbol for s in result]
        assert "SBIN" in symbols
        assert "INFY" not in symbols

    async def test_expire_stale_signals(self, signal_repo):
        past = _make_signal(
            created_at=datetime(2020, 1, 1, 9, 0, 0),
            expires_at=datetime(2020, 1, 1, 9, 30, 0),
        )
        signal_id = await signal_repo.insert_signal(past)

        count = await signal_repo.expire_stale_signals(now=datetime(2026, 2, 16, 12, 0, 0))
        assert count == 1

        signals = await signal_repo.get_signals_by_date(date(2026, 2, 16))
        for s in signals:
            if s.id == signal_id:
                assert s.status == "expired"

    async def test_date_filtering(self, signal_repo):
        today = _make_signal(d=date(2026, 2, 16))
        yesterday = _make_signal(
            d=date(2026, 2, 15),
            created_at=datetime(2026, 2, 15, 9, 35, 0),
        )
        await signal_repo.insert_signal(today)
        await signal_repo.insert_signal(yesterday)

        today_signals = await signal_repo.get_signals_by_date(date(2026, 2, 16))
        assert len(today_signals) == 1
        assert today_signals[0].date == date(2026, 2, 16)

    async def test_get_latest_active_signal(self, signal_repo):
        first = _make_signal(
            symbol="SBIN",
            created_at=datetime(2026, 2, 16, 9, 35, 0),
            expires_at=datetime(2099, 12, 31, 23, 59, 59),
        )
        second = _make_signal(
            symbol="INFY",
            created_at=datetime(2026, 2, 16, 9, 40, 0),
            expires_at=datetime(2099, 12, 31, 23, 59, 59),
        )
        await signal_repo.insert_signal(first)
        await signal_repo.insert_signal(second)

        latest = await signal_repo.get_latest_active_signal(
            now=datetime(2026, 2, 16, 10, 0, 0)
        )
        assert latest is not None
        assert latest.symbol == "INFY"

    async def test_get_latest_active_signal_returns_none_when_empty(self, signal_repo):
        result = await signal_repo.get_latest_active_signal(
            now=datetime(2026, 2, 16, 10, 0, 0)
        )
        assert result is None

    async def test_get_active_signal_by_id_valid(self, signal_repo):
        """get_active_signal_by_id returns the signal when active and not expired."""
        signal = _make_signal(
            symbol="SBIN",
            expires_at=datetime(2099, 12, 31, 23, 59, 59),
        )
        signal_id = await signal_repo.insert_signal(signal)

        result = await signal_repo.get_active_signal_by_id(
            signal_id, now=datetime(2026, 2, 16, 10, 0, 0)
        )
        assert result is not None
        assert result.id == signal_id
        assert result.symbol == "SBIN"

    async def test_get_active_signal_by_id_expired(self, signal_repo):
        """get_active_signal_by_id returns None for an expired signal."""
        signal = _make_signal(
            symbol="SBIN",
            expires_at=datetime(2026, 2, 16, 9, 50, 0),
        )
        signal_id = await signal_repo.insert_signal(signal)

        result = await signal_repo.get_active_signal_by_id(
            signal_id, now=datetime(2026, 2, 16, 10, 0, 0)
        )
        assert result is None

    async def test_get_active_signal_by_id_already_taken(self, signal_repo):
        """get_active_signal_by_id returns None for a signal with status='taken'."""
        signal = _make_signal(
            symbol="SBIN",
            status="taken",
            expires_at=datetime(2099, 12, 31, 23, 59, 59),
        )
        signal_id = await signal_repo.insert_signal(signal)

        result = await signal_repo.get_active_signal_by_id(
            signal_id, now=datetime(2026, 2, 16, 10, 0, 0)
        )
        assert result is None

    async def test_get_active_signal_by_id_nonexistent(self, signal_repo):
        """get_active_signal_by_id returns None for a nonexistent ID."""
        result = await signal_repo.get_active_signal_by_id(
            99999, now=datetime(2026, 2, 16, 10, 0, 0)
        )
        assert result is None

    async def test_get_active_signal_by_id_paper_status(self, signal_repo):
        """get_active_signal_by_id returns paper-mode signals too."""
        signal = _make_signal(
            symbol="INFY",
            status="paper",
            expires_at=datetime(2099, 12, 31, 23, 59, 59),
        )
        signal_id = await signal_repo.insert_signal(signal)

        result = await signal_repo.get_active_signal_by_id(
            signal_id, now=datetime(2026, 2, 16, 10, 0, 0)
        )
        assert result is not None
        assert result.symbol == "INFY"

    async def test_inserted_record_round_trips_all_fields(self, signal_repo):
        signal = _make_signal()
        signal_id = await signal_repo.insert_signal(signal)

        signals = await signal_repo.get_signals_by_date(date(2026, 2, 16))
        retrieved = signals[0]
        assert retrieved.id == signal_id
        assert retrieved.date == signal.date
        assert retrieved.symbol == signal.symbol
        assert retrieved.strategy == signal.strategy
        assert retrieved.entry_price == signal.entry_price
        assert retrieved.stop_loss == signal.stop_loss
        assert retrieved.target_1 == signal.target_1
        assert retrieved.target_2 == signal.target_2
        assert retrieved.quantity == signal.quantity
        assert retrieved.capital_required == signal.capital_required
        assert retrieved.signal_strength == signal.signal_strength
        assert retrieved.gap_pct == signal.gap_pct
        assert retrieved.volume_ratio == signal.volume_ratio
        assert retrieved.reason == signal.reason
        assert retrieved.status == signal.status
