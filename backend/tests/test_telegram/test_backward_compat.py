"""Tests for backward compatibility (Phase 4)."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.db.models import SignalRecord
from signalpilot.db.signal_action_repo import SignalActionRepository
from signalpilot.db.signal_repo import SignalRepository
from signalpilot.db.trade_repo import TradeRepository
from signalpilot.telegram.handlers import handle_taken
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


class TestBackwardCompatibility:
    async def test_text_taken_still_works(self, db):
        """Text TAKEN command creates trade (unchanged behavior)."""
        signal_repo = SignalRepository(db.connection)
        trade_repo = TradeRepository(db.connection)
        config_repo = AsyncMock()
        config_repo.get_user_config.return_value = MagicMock(max_positions=8)
        exit_monitor = MagicMock()

        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        result = await handle_taken(
            signal_repo, trade_repo, config_repo, exit_monitor,
            now=now, text="TAKEN",
        )
        assert "Trade logged" in result

    async def test_text_taken_records_action(self, db):
        """Signal action record created when repo provided."""
        signal_repo = SignalRepository(db.connection)
        trade_repo = TradeRepository(db.connection)
        action_repo = SignalActionRepository(db.connection)
        config_repo = AsyncMock()
        config_repo.get_user_config.return_value = MagicMock(max_positions=8)
        exit_monitor = MagicMock()

        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        await handle_taken(
            signal_repo, trade_repo, config_repo, exit_monitor,
            now=now, text="TAKEN",
            signal_action_repo=action_repo,
        )

        actions = await action_repo.get_actions_for_signal(signal_id)
        assert len(actions) == 1
        assert actions[0].action == "taken"

    async def test_text_taken_already_skipped_via_button(self, db):
        """Returns 'already skipped' when signal status is skipped."""
        signal_repo = SignalRepository(db.connection)
        trade_repo = TradeRepository(db.connection)
        config_repo = AsyncMock()
        config_repo.get_user_config.return_value = MagicMock(max_positions=8)
        exit_monitor = MagicMock()

        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))
        await signal_repo.update_status(signal_id, "skipped")

        result = await handle_taken(
            signal_repo, trade_repo, config_repo, exit_monitor,
            now=now, text=f"TAKEN {signal_id}",
        )
        assert "skipped" in result.lower()

    async def test_text_taken_without_action_repo(self, db):
        """Works when signal_action_repo is None (backward compat)."""
        signal_repo = SignalRepository(db.connection)
        trade_repo = TradeRepository(db.connection)
        config_repo = AsyncMock()
        config_repo.get_user_config.return_value = MagicMock(max_positions=8)
        exit_monitor = MagicMock()

        now = datetime.now(IST)
        await signal_repo.insert_signal(_make_signal(now))

        result = await handle_taken(
            signal_repo, trade_repo, config_repo, exit_monitor,
            now=now, text="TAKEN",
            signal_action_repo=None,
        )
        assert "Trade logged" in result
