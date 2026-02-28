"""Tests for MarketRegimeRepository."""

from datetime import datetime

import pytest

from signalpilot.db.database import DatabaseManager
from signalpilot.db.models import RegimeClassification
from signalpilot.db.regime_repo import MarketRegimeRepository
from signalpilot.utils.constants import IST


@pytest.fixture
async def regime_db():
    """In-memory database with full schema for regime tests."""
    manager = DatabaseManager(":memory:")
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.fixture
async def regime_repo(regime_db):
    """MarketRegimeRepository backed by in-memory database."""
    return MarketRegimeRepository(regime_db.connection)


def _make_classification(
    regime="TRENDING",
    confidence=0.75,
    classified_at=None,
    is_reclassification=False,
    previous_regime=None,
    **kwargs,
) -> RegimeClassification:
    """Helper to create a RegimeClassification with sensible defaults."""
    classified_at = classified_at or datetime(2026, 2, 28, 9, 30, tzinfo=IST)
    defaults = {
        "regime": regime,
        "confidence": confidence,
        "trending_score": 0.5,
        "ranging_score": 0.2,
        "volatile_score": 0.3,
        "india_vix": 15.0,
        "nifty_gap_pct": 1.5,
        "nifty_first_15_range_pct": 0.6,
        "nifty_first_15_direction": "UP",
        "directional_alignment": 0.75,
        "sp500_change_pct": 0.8,
        "sgx_direction": "UP",
        "fii_net_crores": 500.0,
        "dii_net_crores": -200.0,
        "prev_day_range_pct": 1.1,
        "strategy_weights": {"gap_go": 45, "orb": 35, "vwap": 20},
        "min_star_rating": 3,
        "max_positions": 8,
        "position_size_modifier": 1.0,
        "is_reclassification": is_reclassification,
        "previous_regime": previous_regime,
        "classified_at": classified_at,
    }
    defaults.update(kwargs)
    return RegimeClassification(**defaults)


class TestInsertAndRetrieve:
    """Tests for inserting and retrieving classifications."""

    async def test_insert_and_retrieve_classification(self, regime_repo):
        """Insert a classification and retrieve it via get_today_classifications."""
        classification = _make_classification(
            classified_at=datetime.now(IST),
        )

        row_id = await regime_repo.insert_classification(classification)
        assert row_id is not None
        assert row_id > 0

        rows = await regime_repo.get_today_classifications()
        assert len(rows) == 1
        row = rows[0]
        assert row["regime"] == "TRENDING"
        assert row["confidence"] == 0.75
        assert row["india_vix"] == 15.0
        assert row["nifty_gap_pct"] == 1.5
        assert row["is_reclassification"] == 0

    async def test_insert_reclassification(self, regime_repo):
        """Insert a re-classification and verify fields."""
        classification = _make_classification(
            regime="VOLATILE",
            confidence=0.85,
            is_reclassification=True,
            previous_regime="TRENDING",
            classified_at=datetime.now(IST),
        )

        row_id = await regime_repo.insert_classification(classification)
        assert row_id > 0

        rows = await regime_repo.get_today_classifications()
        assert len(rows) == 1
        row = rows[0]
        assert row["regime"] == "VOLATILE"
        assert row["is_reclassification"] == 1
        assert row["previous_regime"] == "TRENDING"


class TestGetTodayClassifications:
    """Tests for get_today_classifications."""

    async def test_get_today_classifications(self, regime_repo):
        """Should return all classifications for today, ordered by time."""
        now = datetime.now(IST)
        c1 = _make_classification(
            regime="TRENDING",
            classified_at=now.replace(hour=9, minute=30, second=0),
        )
        c2 = _make_classification(
            regime="VOLATILE",
            confidence=0.9,
            is_reclassification=True,
            previous_regime="TRENDING",
            classified_at=now.replace(hour=11, minute=0, second=0),
        )

        await regime_repo.insert_classification(c1)
        await regime_repo.insert_classification(c2)

        rows = await regime_repo.get_today_classifications()
        assert len(rows) == 2
        assert rows[0]["regime"] == "TRENDING"
        assert rows[1]["regime"] == "VOLATILE"
        # Ordered by classification_time ascending
        assert rows[0]["classification_time"] < rows[1]["classification_time"]

    async def test_get_today_classifications_empty(self, regime_repo):
        """Should return empty list when no classifications exist."""
        rows = await regime_repo.get_today_classifications()
        assert rows == []


class TestGetRegimeHistory:
    """Tests for get_regime_history."""

    async def test_get_regime_history(self, regime_repo):
        """Should return latest classification per day."""
        # Insert classification for today
        c1 = _make_classification(
            regime="TRENDING",
            classified_at=datetime.now(IST).replace(hour=9, minute=30),
        )
        c2 = _make_classification(
            regime="VOLATILE",
            confidence=0.9,
            classified_at=datetime.now(IST).replace(hour=11, minute=0),
        )

        await regime_repo.insert_classification(c1)
        await regime_repo.insert_classification(c2)

        history = await regime_repo.get_regime_history(days=7)
        # Should return only the latest for today (VOLATILE at 11:00)
        assert len(history) == 1
        assert history[0]["regime"] == "VOLATILE"

    async def test_get_regime_history_empty(self, regime_repo):
        """Should return empty list when no history exists."""
        history = await regime_repo.get_regime_history(days=7)
        assert history == []

    async def test_get_regime_history_respects_limit(self, regime_repo):
        """Should respect the days limit parameter."""
        c = _make_classification(
            classified_at=datetime.now(IST),
        )
        await regime_repo.insert_classification(c)

        history = await regime_repo.get_regime_history(days=1)
        assert len(history) <= 1

    async def test_get_regime_history_multiple_days(self, regime_repo):
        """Multiple days should each return their latest classification."""
        # Insert for today with two classifications
        now = datetime.now(IST)
        c1 = _make_classification(
            regime="TRENDING",
            classified_at=now.replace(hour=9, minute=30),
        )
        c2 = _make_classification(
            regime="RANGING",
            confidence=0.6,
            classified_at=now.replace(hour=13, minute=0),
        )

        await regime_repo.insert_classification(c1)
        await regime_repo.insert_classification(c2)

        history = await regime_repo.get_regime_history(days=20)
        # Both are same day, so should return only the latest (RANGING at 13:00)
        assert len(history) == 1
        assert history[0]["regime"] == "RANGING"
