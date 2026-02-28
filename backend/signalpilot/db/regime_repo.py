"""Repository for the market_regimes table."""

from __future__ import annotations

import json
import logging
from datetime import datetime

import aiosqlite

from signalpilot.utils.constants import IST

logger = logging.getLogger(__name__)


class MarketRegimeRepository:
    """Repository for the market_regimes table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def insert_classification(self, classification) -> int:
        """Insert a regime classification record. Returns the inserted row id."""
        cursor = await self._conn.execute(
            """
            INSERT INTO market_regimes (
                regime_date, classification_time, regime, confidence,
                trending_score, ranging_score, volatile_score,
                india_vix, nifty_gap_pct, nifty_first_15_range_pct,
                nifty_first_15_direction, directional_alignment,
                sp500_change_pct, sgx_direction, fii_net_crores, dii_net_crores,
                is_reclassification, previous_regime,
                strategy_weights_json, min_star_rating, max_positions,
                position_size_modifier, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                classification.classified_at.date().isoformat(),
                classification.classified_at.strftime("%H:%M:%S"),
                classification.regime,
                classification.confidence,
                classification.trending_score,
                classification.ranging_score,
                classification.volatile_score,
                classification.india_vix,
                classification.nifty_gap_pct,
                classification.nifty_first_15_range_pct,
                classification.nifty_first_15_direction,
                classification.directional_alignment,
                classification.sp500_change_pct,
                classification.sgx_direction,
                classification.fii_net_crores,
                classification.dii_net_crores,
                1 if classification.is_reclassification else 0,
                classification.previous_regime,
                json.dumps(classification.strategy_weights),
                classification.min_star_rating,
                classification.max_positions,
                classification.position_size_modifier,
                classification.classified_at.isoformat(),
            ),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_today_classifications(self) -> list[dict]:
        """Return all classifications for today, ordered by time ascending."""
        today = datetime.now(IST).date().isoformat()
        cursor = await self._conn.execute(
            "SELECT * FROM market_regimes WHERE regime_date = ? ORDER BY classification_time ASC",
            (today,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_regime_history(self, days: int = 20) -> list[dict]:
        """Return the latest classification per day for the last N days."""
        cursor = await self._conn.execute(
            """
            SELECT m.* FROM market_regimes m
            INNER JOIN (
                SELECT regime_date, MAX(classification_time) as max_time
                FROM market_regimes
                GROUP BY regime_date
            ) latest ON m.regime_date = latest.regime_date
                    AND m.classification_time = latest.max_time
            ORDER BY m.regime_date DESC
            LIMIT ?
            """,
            (days,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
