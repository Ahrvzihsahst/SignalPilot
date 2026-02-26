"""Repository for hybrid score records."""

from datetime import date, datetime

import aiosqlite

from signalpilot.db.models import HybridScoreRecord
from signalpilot.utils.constants import IST


class HybridScoreRepository:
    """CRUD operations for the hybrid_scores table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def insert_score(self, record: HybridScoreRecord) -> int:
        """Insert a hybrid score record and return the new row ID."""
        cursor = await self._conn.execute(
            """
            INSERT INTO hybrid_scores
                (signal_id, composite_score, strategy_strength_score,
                 win_rate_score, risk_reward_score, confirmation_bonus,
                 confirmed_by, confirmation_level, position_size_multiplier,
                 created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.signal_id,
                record.composite_score,
                record.strategy_strength_score,
                record.win_rate_score,
                record.risk_reward_score,
                record.confirmation_bonus,
                record.confirmed_by,
                record.confirmation_level,
                record.position_size_multiplier,
                record.created_at.isoformat() if record.created_at else datetime.now(IST).isoformat(),
            ),
        )
        await self._conn.commit()
        row_id = cursor.lastrowid
        assert row_id is not None, "INSERT did not return a row ID"
        return row_id

    async def get_latest_for_symbol(self, symbol: str) -> HybridScoreRecord | None:
        """Return the most recent hybrid score for a symbol (via signals JOIN)."""
        cursor = await self._conn.execute(
            """
            SELECT hs.id, hs.signal_id, hs.composite_score,
                   hs.strategy_strength_score, hs.win_rate_score,
                   hs.risk_reward_score, hs.confirmation_bonus,
                   hs.confirmed_by, hs.confirmation_level,
                   hs.position_size_multiplier, hs.created_at
            FROM hybrid_scores hs
            JOIN signals s ON hs.signal_id = s.id
            WHERE s.symbol = ?
            ORDER BY hs.created_at DESC
            LIMIT 1
            """,
            (symbol,),
        )
        row = await cursor.fetchone()
        return self._row_to_record(row) if row else None

    async def get_by_date(self, d: date) -> list[HybridScoreRecord]:
        """Return all hybrid scores for a given date, ordered by composite_score DESC."""
        cursor = await self._conn.execute(
            """
            SELECT id, signal_id, composite_score, strategy_strength_score,
                   win_rate_score, risk_reward_score, confirmation_bonus,
                   confirmed_by, confirmation_level, position_size_multiplier,
                   created_at
            FROM hybrid_scores
            WHERE DATE(created_at) = ?
            ORDER BY composite_score DESC
            """,
            (d.isoformat(),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_by_signal_id(self, signal_id: int) -> HybridScoreRecord | None:
        """Return the hybrid score for a specific signal ID."""
        cursor = await self._conn.execute(
            """
            SELECT id, signal_id, composite_score, strategy_strength_score,
                   win_rate_score, risk_reward_score, confirmation_bonus,
                   confirmed_by, confirmation_level, position_size_multiplier,
                   created_at
            FROM hybrid_scores
            WHERE signal_id = ?
            """,
            (signal_id,),
        )
        row = await cursor.fetchone()
        return self._row_to_record(row) if row else None

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> HybridScoreRecord:
        """Convert a database row to a HybridScoreRecord."""
        created_at_raw = row["created_at"]
        created_at = datetime.fromisoformat(created_at_raw) if created_at_raw else None
        # Ensure IST-aware datetime
        if created_at is not None and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=IST)
        return HybridScoreRecord(
            id=row["id"],
            signal_id=row["signal_id"],
            composite_score=row["composite_score"],
            strategy_strength_score=row["strategy_strength_score"],
            win_rate_score=row["win_rate_score"],
            risk_reward_score=row["risk_reward_score"],
            confirmation_bonus=row["confirmation_bonus"],
            confirmed_by=row["confirmed_by"],
            confirmation_level=row["confirmation_level"],
            position_size_multiplier=row["position_size_multiplier"],
            created_at=created_at,
        )
