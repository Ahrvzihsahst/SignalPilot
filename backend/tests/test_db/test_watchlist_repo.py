"""Tests for WatchlistRepository."""

from datetime import datetime, timedelta

import pytest

from signalpilot.db.models import WatchlistRecord
from signalpilot.db.watchlist_repo import WatchlistRepository
from signalpilot.utils.constants import IST


def _make_entry(symbol="SBIN", now=None, days=5):
    now = now or datetime.now(IST)
    return WatchlistRecord(
        symbol=symbol,
        signal_id=None,
        strategy="Gap & Go",
        entry_price=100.0,
        added_at=now,
        expires_at=now + timedelta(days=days),
    )


class TestWatchlistRepository:
    async def test_add_and_retrieve(self, db):
        repo = WatchlistRepository(db.connection)
        now = datetime.now(IST)
        entry = _make_entry(now=now)
        entry_id = await repo.add_to_watchlist(entry)
        assert entry_id > 0

        active = await repo.get_active_watchlist(now)
        assert len(active) == 1
        assert active[0].symbol == "SBIN"

    async def test_get_active_excludes_expired(self, db):
        repo = WatchlistRepository(db.connection)
        now = datetime.now(IST)

        # Add an entry that expires in 5 days
        entry = _make_entry(now=now)
        await repo.add_to_watchlist(entry)

        # Check at now+6 days (expired)
        future = now + timedelta(days=6)
        active = await repo.get_active_watchlist(future)
        assert len(active) == 0

    async def test_is_on_watchlist_active(self, db):
        repo = WatchlistRepository(db.connection)
        now = datetime.now(IST)
        await repo.add_to_watchlist(_make_entry(now=now))

        assert await repo.is_on_watchlist("SBIN", now) is True
        assert await repo.is_on_watchlist("TCS", now) is False

    async def test_is_on_watchlist_expired(self, db):
        repo = WatchlistRepository(db.connection)
        now = datetime.now(IST)
        await repo.add_to_watchlist(_make_entry(now=now))

        future = now + timedelta(days=6)
        assert await repo.is_on_watchlist("SBIN", future) is False

    async def test_remove_from_watchlist(self, db):
        repo = WatchlistRepository(db.connection)
        now = datetime.now(IST)
        await repo.add_to_watchlist(_make_entry(now=now))

        count = await repo.remove_from_watchlist("SBIN")
        assert count == 1

        active = await repo.get_active_watchlist(now)
        assert len(active) == 0

    async def test_remove_nonexistent_returns_zero(self, db):
        repo = WatchlistRepository(db.connection)
        count = await repo.remove_from_watchlist("NONEXISTENT")
        assert count == 0

    async def test_increment_trigger(self, db):
        repo = WatchlistRepository(db.connection)
        now = datetime.now(IST)
        await repo.add_to_watchlist(_make_entry(now=now))

        await repo.increment_trigger("SBIN", now)
        active = await repo.get_active_watchlist(now)
        assert active[0].triggered_count == 1
        assert active[0].last_triggered_at is not None

        await repo.increment_trigger("SBIN", now)
        active = await repo.get_active_watchlist(now)
        assert active[0].triggered_count == 2

    async def test_cleanup_expired(self, db):
        repo = WatchlistRepository(db.connection)
        now = datetime.now(IST)

        # Add expired entry
        expired = _make_entry(now=now - timedelta(days=10), days=5)
        await repo.add_to_watchlist(expired)

        # Add active entry
        active = _make_entry(symbol="TCS", now=now)
        await repo.add_to_watchlist(active)

        count = await repo.cleanup_expired(now)
        assert count == 1

        remaining = await repo.get_active_watchlist(now)
        assert len(remaining) == 1
        assert remaining[0].symbol == "TCS"

    async def test_cleanup_nothing_expired(self, db):
        repo = WatchlistRepository(db.connection)
        now = datetime.now(IST)
        await repo.add_to_watchlist(_make_entry(now=now))

        count = await repo.cleanup_expired(now)
        assert count == 0
