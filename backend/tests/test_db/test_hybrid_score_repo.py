"""Tests for HybridScoreRepository."""

from datetime import date, datetime, timedelta

from signalpilot.db.models import HybridScoreRecord, SignalRecord
from signalpilot.utils.constants import IST


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
    created_at = created_at or datetime(2026, 2, 16, 9, 35, 0, tzinfo=IST)
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


def _make_hybrid_score(
    signal_id=1,
    composite_score=0.85,
    created_at=None,
    confirmed_by=None,
    confirmation_level="single",
) -> HybridScoreRecord:
    """Helper to create a HybridScoreRecord with sensible defaults."""
    created_at = created_at or datetime(2026, 2, 16, 9, 36, 0, tzinfo=IST)
    return HybridScoreRecord(
        signal_id=signal_id,
        composite_score=composite_score,
        strategy_strength_score=0.30,
        win_rate_score=0.25,
        risk_reward_score=0.20,
        confirmation_bonus=0.10,
        confirmed_by=confirmed_by,
        confirmation_level=confirmation_level,
        position_size_multiplier=1.2,
        created_at=created_at,
    )


class TestHybridScoreRepository:
    async def test_insert_and_retrieve_by_signal_id(self, signal_repo, hybrid_score_repo):
        signal = _make_signal()
        signal_id = await signal_repo.insert_signal(signal)

        score = _make_hybrid_score(signal_id=signal_id)
        score_id = await hybrid_score_repo.insert_score(score)
        assert score_id is not None
        assert score_id > 0

        retrieved = await hybrid_score_repo.get_by_signal_id(signal_id)
        assert retrieved is not None
        assert retrieved.id == score_id
        assert retrieved.signal_id == signal_id
        assert retrieved.composite_score == 0.85
        assert retrieved.strategy_strength_score == 0.30
        assert retrieved.win_rate_score == 0.25
        assert retrieved.risk_reward_score == 0.20
        assert retrieved.confirmation_bonus == 0.10
        assert retrieved.confirmation_level == "single"
        assert retrieved.position_size_multiplier == 1.2

    async def test_get_latest_for_symbol(self, signal_repo, hybrid_score_repo):
        # Insert two signals for the same symbol
        signal1 = _make_signal(
            symbol="SBIN",
            created_at=datetime(2026, 2, 16, 9, 35, 0, tzinfo=IST),
        )
        signal1_id = await signal_repo.insert_signal(signal1)

        signal2 = _make_signal(
            symbol="SBIN",
            created_at=datetime(2026, 2, 16, 10, 0, 0, tzinfo=IST),
        )
        signal2_id = await signal_repo.insert_signal(signal2)

        # Insert hybrid scores with different timestamps
        score1 = _make_hybrid_score(
            signal_id=signal1_id,
            composite_score=0.70,
            created_at=datetime(2026, 2, 16, 9, 36, 0, tzinfo=IST),
        )
        await hybrid_score_repo.insert_score(score1)

        score2 = _make_hybrid_score(
            signal_id=signal2_id,
            composite_score=0.90,
            created_at=datetime(2026, 2, 16, 10, 1, 0, tzinfo=IST),
        )
        score2_id = await hybrid_score_repo.insert_score(score2)

        latest = await hybrid_score_repo.get_latest_for_symbol("SBIN")
        assert latest is not None
        assert latest.id == score2_id
        assert latest.composite_score == 0.90

    async def test_get_by_date_sorted_by_composite_score(self, signal_repo, hybrid_score_repo):
        # Insert three signals for the same date
        signal1 = _make_signal(
            symbol="SBIN",
            created_at=datetime(2026, 2, 16, 9, 35, 0, tzinfo=IST),
        )
        sid1 = await signal_repo.insert_signal(signal1)

        signal2 = _make_signal(
            symbol="TCS",
            created_at=datetime(2026, 2, 16, 9, 40, 0, tzinfo=IST),
        )
        sid2 = await signal_repo.insert_signal(signal2)

        signal3 = _make_signal(
            symbol="RELIANCE",
            created_at=datetime(2026, 2, 16, 9, 45, 0, tzinfo=IST),
        )
        sid3 = await signal_repo.insert_signal(signal3)

        # Insert scores with different composite values
        await hybrid_score_repo.insert_score(
            _make_hybrid_score(signal_id=sid1, composite_score=0.60,
                               created_at=datetime(2026, 2, 16, 9, 36, 0, tzinfo=IST)),
        )
        await hybrid_score_repo.insert_score(
            _make_hybrid_score(signal_id=sid2, composite_score=0.90,
                               created_at=datetime(2026, 2, 16, 9, 41, 0, tzinfo=IST)),
        )
        await hybrid_score_repo.insert_score(
            _make_hybrid_score(signal_id=sid3, composite_score=0.75,
                               created_at=datetime(2026, 2, 16, 9, 46, 0, tzinfo=IST)),
        )

        results = await hybrid_score_repo.get_by_date(date(2026, 2, 16))
        assert len(results) == 3
        # Should be sorted by composite_score descending
        assert results[0].composite_score == 0.90
        assert results[1].composite_score == 0.75
        assert results[2].composite_score == 0.60

    async def test_returns_none_for_nonexistent_symbol(self, hybrid_score_repo):
        result = await hybrid_score_repo.get_latest_for_symbol("NONEXISTENT")
        assert result is None

    async def test_returns_none_for_nonexistent_signal_id(self, hybrid_score_repo):
        result = await hybrid_score_repo.get_by_signal_id(99999)
        assert result is None
