"""Tests for AdaptationLogRepository."""

from datetime import date


class TestAdaptationLogRepository:
    async def test_insert_and_get_by_date(self, adaptation_log_repo):
        today = date(2026, 2, 16)
        log_id = await adaptation_log_repo.insert_log(
            today=today,
            strategy="gap_and_go",
            event_type="weight_change",
            details="Win rate improved, increasing weight",
            old_weight=0.33,
            new_weight=0.40,
        )
        assert log_id is not None
        assert log_id > 0

        results = await adaptation_log_repo.get_by_date(today)
        assert len(results) == 1
        record = results[0]
        assert record.id == log_id
        assert record.date == today
        assert record.strategy == "gap_and_go"
        assert record.event_type == "weight_change"
        assert record.details == "Win rate improved, increasing weight"
        assert record.old_weight == 0.33
        assert record.new_weight == 0.40
        assert record.created_at is not None

    async def test_get_by_strategy(self, adaptation_log_repo):
        today = date(2026, 2, 16)
        await adaptation_log_repo.insert_log(
            today=today, strategy="gap_and_go",
            event_type="weight_change", details="test 1",
            old_weight=0.33, new_weight=0.40,
        )
        await adaptation_log_repo.insert_log(
            today=today, strategy="orb",
            event_type="throttle", details="test 2",
            old_weight=0.33, new_weight=0.25,
        )
        await adaptation_log_repo.insert_log(
            today=today, strategy="gap_and_go",
            event_type="pause", details="test 3",
            old_weight=0.40, new_weight=0.0,
        )

        gap_go_results = await adaptation_log_repo.get_by_strategy("gap_and_go")
        assert len(gap_go_results) == 2
        assert all(r.strategy == "gap_and_go" for r in gap_go_results)

        orb_results = await adaptation_log_repo.get_by_strategy("orb")
        assert len(orb_results) == 1
        assert orb_results[0].strategy == "orb"

    async def test_get_by_event_type(self, adaptation_log_repo):
        today = date(2026, 2, 16)
        await adaptation_log_repo.insert_log(
            today=today, strategy="gap_and_go",
            event_type="weight_change", details="test 1",
            old_weight=0.33, new_weight=0.40,
        )
        await adaptation_log_repo.insert_log(
            today=today, strategy="orb",
            event_type="throttle", details="test 2",
            old_weight=None, new_weight=None,
        )
        await adaptation_log_repo.insert_log(
            today=today, strategy="vwap",
            event_type="weight_change", details="test 3",
            old_weight=0.20, new_weight=0.30,
        )

        results = await adaptation_log_repo.get_by_event_type("weight_change")
        assert len(results) == 2
        assert all(r.event_type == "weight_change" for r in results)

        throttle_results = await adaptation_log_repo.get_by_event_type("throttle")
        assert len(throttle_results) == 1

    async def test_get_recent(self, adaptation_log_repo):
        today = date(2026, 2, 16)
        for i in range(5):
            await adaptation_log_repo.insert_log(
                today=today, strategy=f"strategy_{i}",
                event_type="weight_change", details=f"test {i}",
                old_weight=0.30, new_weight=0.35,
            )

        results = await adaptation_log_repo.get_recent(limit=3)
        assert len(results) == 3
        # Should be ordered by created_at DESC (most recent first)

    async def test_empty_results(self, adaptation_log_repo):
        # No records inserted
        by_date = await adaptation_log_repo.get_by_date(date(2026, 2, 16))
        assert by_date == []

        by_strategy = await adaptation_log_repo.get_by_strategy("nonexistent")
        assert by_strategy == []

        by_event = await adaptation_log_repo.get_by_event_type("nonexistent")
        assert by_event == []

        recent = await adaptation_log_repo.get_recent()
        assert recent == []

    async def test_null_weights_round_trip(self, adaptation_log_repo):
        today = date(2026, 2, 16)
        log_id = await adaptation_log_repo.insert_log(
            today=today, strategy="orb",
            event_type="throttle", details="Throttled after consecutive losses",
            old_weight=None, new_weight=None,
        )

        results = await adaptation_log_repo.get_by_date(today)
        assert len(results) == 1
        assert results[0].old_weight is None
        assert results[0].new_weight is None
