"""Tests for skipped status in SignalRepository."""

from datetime import datetime, timedelta

import pytest

from signalpilot.db.models import SignalRecord
from signalpilot.db.signal_repo import SignalRepository
from signalpilot.utils.constants import IST


def _make_signal(now=None):
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
        status="sent",
    )


class TestSkippedStatus:
    async def test_update_status_to_skipped(self, db):
        repo = SignalRepository(db.connection)
        signal = _make_signal()
        signal_id = await repo.insert_signal(signal)
        await repo.update_status(signal_id, "skipped")
        # Verify status changed (re-fetch raw)
        cursor = await db.connection.execute(
            "SELECT status FROM signals WHERE id = ?", (signal_id,)
        )
        row = await cursor.fetchone()
        assert row["status"] == "skipped"

    async def test_skipped_signal_excluded_from_active(self, db):
        repo = SignalRepository(db.connection)
        now = datetime.now(IST)
        signal = _make_signal(now)
        signal_id = await repo.insert_signal(signal)
        await repo.update_status(signal_id, "skipped")

        active = await repo.get_active_signals(now.date(), now)
        assert len(active) == 0

        latest = await repo.get_latest_active_signal(now)
        assert latest is None

    async def test_skipped_signal_excluded_from_get_active_by_id(self, db):
        repo = SignalRepository(db.connection)
        now = datetime.now(IST)
        signal = _make_signal(now)
        signal_id = await repo.insert_signal(signal)
        await repo.update_status(signal_id, "skipped")

        result = await repo.get_active_signal_by_id(signal_id, now)
        assert result is None
