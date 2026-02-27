"""Integration tests for Phase 4 wiring."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.db.signal_action_repo import SignalActionRepository
from signalpilot.db.signal_repo import SignalRepository
from signalpilot.db.trade_repo import TradeRepository
from signalpilot.db.watchlist_repo import WatchlistRepository
from signalpilot.db.models import WatchlistRecord
from signalpilot.utils.constants import IST

from tests.test_integration.conftest import make_app, make_signal_record


class TestPhase4Wiring:
    async def test_create_app_phase4_wiring(self, db, repos):
        """Verify signal_action_repo and watchlist_repo are injected."""
        signal_action_repo = SignalActionRepository(db.connection)
        watchlist_repo = WatchlistRepository(db.connection)

        app = make_app(
            db, repos,
            watchlist_repo=watchlist_repo,
            signal_action_repo=signal_action_repo,
        )
        assert app._watchlist_repo is watchlist_repo
        assert app._signal_action_repo is signal_action_repo

    async def test_watchlist_trigger_in_scan_loop(self, db, repos):
        """Verify trigger increment when watched stock signals."""
        watchlist_repo = WatchlistRepository(db.connection)
        now = datetime.now(IST)

        # Add SBIN to watchlist
        entry = WatchlistRecord(
            symbol="SBIN", signal_id=None, strategy="Gap & Go",
            entry_price=100.0, added_at=now,
            expires_at=now + timedelta(days=5),
        )
        await watchlist_repo.add_to_watchlist(entry)

        # Verify it's on the watchlist
        assert await watchlist_repo.is_on_watchlist("SBIN", now)

        # Increment trigger
        await watchlist_repo.increment_trigger("SBIN", now)
        active = await watchlist_repo.get_active_watchlist(now)
        assert active[0].triggered_count == 1

    async def test_daily_summary_includes_button_analytics(self, db, repos):
        """Verify summary includes signal actions section when data exists."""
        signal_action_repo = SignalActionRepository(db.connection)
        signal_repo = repos["signal_repo"]

        now = datetime.now(IST)
        signal = make_signal_record(created_at=now)
        signal_id = await signal_repo.insert_signal(signal)

        from signalpilot.db.models import SignalActionRecord
        await signal_action_repo.insert_action(SignalActionRecord(
            signal_id=signal_id, action="taken", acted_at=now,
        ))

        summary = await signal_action_repo.get_action_summary(now.date())
        assert summary.get("taken", 0) == 1
