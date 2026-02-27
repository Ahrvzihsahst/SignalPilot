"""Tests for SignalActionRepository."""

from datetime import date, datetime, timedelta

import pytest

from signalpilot.db.models import SignalActionRecord, SignalRecord
from signalpilot.db.signal_action_repo import SignalActionRepository
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


class TestSignalActionRepository:
    async def test_insert_and_retrieve_action(self, db):
        signal_repo = SignalRepository(db.connection)
        action_repo = SignalActionRepository(db.connection)

        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        record = SignalActionRecord(
            signal_id=signal_id,
            action="taken",
            response_time_ms=3500,
            acted_at=now,
            message_id=12345,
        )
        action_id = await action_repo.insert_action(record)
        assert action_id > 0

        actions = await action_repo.get_actions_for_signal(signal_id)
        assert len(actions) == 1
        assert actions[0].action == "taken"
        assert actions[0].response_time_ms == 3500

    async def test_get_actions_for_signal(self, db):
        signal_repo = SignalRepository(db.connection)
        action_repo = SignalActionRepository(db.connection)

        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        for i, action in enumerate(["taken", "skip", "watch"]):
            await action_repo.insert_action(SignalActionRecord(
                signal_id=signal_id,
                action=action,
                acted_at=now + timedelta(seconds=i),
            ))

        actions = await action_repo.get_actions_for_signal(signal_id)
        assert len(actions) == 3
        assert [a.action for a in actions] == ["taken", "skip", "watch"]

    async def test_average_response_time(self, db):
        signal_repo = SignalRepository(db.connection)
        action_repo = SignalActionRepository(db.connection)

        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        for ms in [2000, 4000, 6000]:
            await action_repo.insert_action(SignalActionRecord(
                signal_id=signal_id,
                action="taken",
                response_time_ms=ms,
                acted_at=now,
            ))

        avg = await action_repo.get_average_response_time(days=30)
        assert avg == 4000.0

    async def test_average_response_time_empty(self, db):
        action_repo = SignalActionRepository(db.connection)
        avg = await action_repo.get_average_response_time(days=30)
        assert avg is None

    async def test_skip_reason_distribution(self, db):
        signal_repo = SignalRepository(db.connection)
        action_repo = SignalActionRepository(db.connection)

        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        reasons = ["no_capital", "no_capital", "low_confidence", "sector"]
        for reason in reasons:
            await action_repo.insert_action(SignalActionRecord(
                signal_id=signal_id,
                action="skip",
                reason=reason,
                acted_at=now,
            ))

        dist = await action_repo.get_skip_reason_distribution(days=30)
        assert dist["no_capital"] == 2
        assert dist["low_confidence"] == 1
        assert dist["sector"] == 1

    async def test_action_summary_by_date(self, db):
        signal_repo = SignalRepository(db.connection)
        action_repo = SignalActionRepository(db.connection)

        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        actions = ["taken", "taken", "skip", "watch"]
        for action in actions:
            await action_repo.insert_action(SignalActionRecord(
                signal_id=signal_id,
                action=action,
                acted_at=now,
            ))

        summary = await action_repo.get_action_summary(now.date())
        assert summary["taken"] == 2
        assert summary["skip"] == 1
        assert summary["watch"] == 1

    async def test_response_time_distribution(self, db):
        signal_repo = SignalRepository(db.connection)
        action_repo = SignalActionRepository(db.connection)

        now = datetime.now(IST)
        signal_id = await signal_repo.insert_signal(_make_signal(now))

        await action_repo.insert_action(SignalActionRecord(
            signal_id=signal_id,
            action="taken",
            response_time_ms=3000,
            acted_at=now,
        ))

        dist = await action_repo.get_response_time_distribution(days=30)
        assert len(dist) == 1
        assert dist[0][0] == 3000
        assert dist[0][1] == "taken"
