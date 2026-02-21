"""Integration tests for signal expiry through real DB and real handlers."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from signalpilot.telegram.handlers import handle_taken
from signalpilot.utils.constants import IST
from tests.test_integration.conftest import make_signal_record


async def test_signal_expires_after_30_minutes(db, repos):
    """Signal with expires_at in the past should be marked expired."""
    now = datetime.now(IST)
    past = now - timedelta(minutes=31)
    signal = make_signal_record(
        created_at=past, expires_at=past + timedelta(minutes=30),
    )

    await repos["signal_repo"].insert_signal(signal)

    # Expire stale signals
    count = await repos["signal_repo"].expire_stale_signals(now)
    assert count == 1

    # Verify status changed
    all_signals = await repos["signal_repo"].get_signals_by_date(past.date())
    assert all_signals[0].status == "expired"


async def test_taken_after_expiry_returns_error(db, repos):
    """TAKEN command after signal expiry should return error message."""
    now = datetime.now(IST)
    past = now - timedelta(minutes=31)
    signal = make_signal_record(
        created_at=past, expires_at=past + timedelta(minutes=30),
    )

    await repos["signal_repo"].insert_signal(signal)

    # Expire the signal first (mirrors real lifecycle behavior)
    count = await repos["signal_repo"].expire_stale_signals(now)
    assert count == 1

    # Try TAKEN - signal is expired
    mock_exit_monitor = MagicMock()
    response = await handle_taken(
        repos["signal_repo"], repos["trade_repo"], mock_exit_monitor, now=now,
    )

    # get_latest_active_signal filters by expires_at > now, so returns None
    assert "no active signal" in response.lower()


async def test_active_signal_not_expired(db, repos):
    """A signal within its expiry window should remain active."""
    now = datetime.now(IST)
    signal = make_signal_record(
        created_at=now, expires_at=now + timedelta(minutes=30),
    )

    await repos["signal_repo"].insert_signal(signal)

    count = await repos["signal_repo"].expire_stale_signals(now)
    assert count == 0

    # Signal should still be retrievable
    active = await repos["signal_repo"].get_latest_active_signal(now)
    assert active is not None
    assert active.status == "sent"
