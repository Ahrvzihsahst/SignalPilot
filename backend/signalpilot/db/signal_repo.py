"""Repository for signal records."""

from datetime import date, datetime

import aiosqlite

from signalpilot.db.models import SignalRecord
from signalpilot.utils.constants import IST

_VALID_STATUSES = frozenset({"sent", "taken", "expired", "paper", "position_full", "skipped"})


class SignalRepository:
    """CRUD operations for the signals table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def insert_signal(self, signal: SignalRecord) -> int:
        """Insert a signal record and return the new row ID."""
        cursor = await self._conn.execute(
            """
            INSERT INTO signals
                (date, symbol, strategy, entry_price, stop_loss, target_1,
                 target_2, quantity, capital_required, signal_strength,
                 gap_pct, volume_ratio, reason, created_at, expires_at, status,
                 setup_type, strategy_specific_score,
                 composite_score, confirmation_level, confirmed_by,
                 position_size_multiplier, adaptation_status,
                 news_sentiment_score, news_sentiment_label,
                 news_top_headline, news_action, original_star_rating,
                 market_regime, regime_confidence, regime_weight_modifier)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal.date.isoformat(),
                signal.symbol,
                signal.strategy,
                signal.entry_price,
                signal.stop_loss,
                signal.target_1,
                signal.target_2,
                signal.quantity,
                signal.capital_required,
                signal.signal_strength,
                signal.gap_pct,
                signal.volume_ratio,
                signal.reason,
                signal.created_at.isoformat() if signal.created_at else datetime.now(IST).isoformat(),
                signal.expires_at.isoformat() if signal.expires_at else datetime.now(IST).isoformat(),
                signal.status,
                signal.setup_type,
                signal.strategy_specific_score,
                signal.composite_score,
                signal.confirmation_level,
                signal.confirmed_by,
                signal.position_size_multiplier,
                signal.adaptation_status,
                signal.news_sentiment_score,
                signal.news_sentiment_label,
                signal.news_top_headline,
                signal.news_action,
                signal.original_star_rating,
                signal.market_regime,
                signal.regime_confidence,
                signal.regime_weight_modifier,
            ),
        )
        await self._conn.commit()
        row_id = cursor.lastrowid
        assert row_id is not None, "INSERT did not return a row ID"
        return row_id

    async def has_signal_for_stock_today(self, symbol: str, today: date) -> bool:
        """Check if a signal exists for a stock on a given date (any strategy, any status)."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM signals WHERE symbol = ? AND date = ?",
            (symbol, today.isoformat()),
        )
        row = await cursor.fetchone()
        return row[0] > 0

    async def update_status(self, signal_id: int, status: str) -> None:
        """Update the status of a signal (e.g., 'sent' -> 'expired')."""
        if status not in _VALID_STATUSES:
            raise ValueError(f"Invalid signal status: {status!r}. Must be one of {_VALID_STATUSES}")
        cursor = await self._conn.execute(
            "UPDATE signals SET status = ? WHERE id = ?",
            (status, signal_id),
        )
        await self._conn.commit()
        if cursor.rowcount == 0:
            raise ValueError(f"Signal {signal_id} not found")

    async def get_active_signals(self, d: date, now: datetime | None = None) -> list[SignalRecord]:
        """Return non-expired, active signals for the given date."""
        now = now or datetime.now(IST)
        cursor = await self._conn.execute(
            """
            SELECT * FROM signals
            WHERE date = ? AND status IN ('sent', 'paper')
              AND expires_at > ?
            ORDER BY created_at DESC
            """,
            (d.isoformat(), now.isoformat()),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_signals_by_date(self, d: date) -> list[SignalRecord]:
        """Return all signals for the given date."""
        cursor = await self._conn.execute(
            "SELECT * FROM signals WHERE date = ? ORDER BY created_at DESC",
            (d.isoformat(),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def expire_stale_signals(self, now: datetime | None = None) -> int:
        """Bulk-update stale signals to 'expired'. Return count of updated rows."""
        now = now or datetime.now(IST)
        cursor = await self._conn.execute(
            """
            UPDATE signals
            SET status = 'expired'
            WHERE status IN ('sent', 'paper') AND expires_at <= ?
            """,
            (now.isoformat(),),
        )
        await self._conn.commit()
        return cursor.rowcount

    async def get_active_signal_by_id(
        self, signal_id: int, now: datetime | None = None,
    ) -> SignalRecord | None:
        """Return an active signal by its DB id, or None if expired/taken/missing."""
        now = now or datetime.now(IST)
        cursor = await self._conn.execute(
            """
            SELECT * FROM signals
            WHERE id = ? AND status IN ('sent', 'paper') AND expires_at > ?
            """,
            (signal_id, now.isoformat()),
        )
        row = await cursor.fetchone()
        return self._row_to_record(row) if row else None

    async def get_latest_active_signal(self, now: datetime | None = None) -> SignalRecord | None:
        """Return the most recent active signal (for TAKEN command).

        Matches both 'sent' and 'paper' status signals so that paper-mode
        trades can also be logged via the TAKEN command.
        """
        now = now or datetime.now(IST)
        cursor = await self._conn.execute(
            """
            SELECT * FROM signals
            WHERE status IN ('sent', 'paper') AND expires_at > ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (now.isoformat(),),
        )
        row = await cursor.fetchone()
        return self._row_to_record(row) if row else None

    async def get_signal_status(self, signal_id: int) -> str | None:
        """Return the status of a signal by its ID, or None if not found."""
        cursor = await self._conn.execute(
            "SELECT status FROM signals WHERE id = ?",
            (signal_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def get_recent_signals_by_symbol(
        self, symbol: str, since: datetime,
    ) -> list[tuple[str, datetime]]:
        """Return (strategy_name, created_at) tuples for signals within the time window.

        Useful for multi-strategy confirmation: checks whether other strategies
        have recently generated signals for the same symbol.
        """
        cursor = await self._conn.execute(
            """
            SELECT strategy, created_at
            FROM signals
            WHERE symbol = ? AND created_at >= ?
            ORDER BY created_at DESC
            """,
            (symbol, since.isoformat()),
        )
        rows = await cursor.fetchall()
        return [(row["strategy"], datetime.fromisoformat(row["created_at"])) for row in rows]

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> SignalRecord:
        """Convert a database row to a SignalRecord."""
        keys = row.keys()
        return SignalRecord(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            symbol=row["symbol"],
            strategy=row["strategy"],
            entry_price=row["entry_price"],
            stop_loss=row["stop_loss"],
            target_1=row["target_1"],
            target_2=row["target_2"],
            quantity=row["quantity"],
            capital_required=row["capital_required"],
            signal_strength=row["signal_strength"],
            gap_pct=row["gap_pct"],
            volume_ratio=row["volume_ratio"],
            reason=row["reason"],
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            status=row["status"],
            setup_type=row["setup_type"],
            strategy_specific_score=row["strategy_specific_score"],
            # Phase 3 fields with safe defaults for pre-existing rows
            composite_score=row["composite_score"] if "composite_score" in keys else None,
            confirmation_level=row["confirmation_level"] if "confirmation_level" in keys else None,
            confirmed_by=row["confirmed_by"] if "confirmed_by" in keys else None,
            position_size_multiplier=(
                row["position_size_multiplier"]
                if "position_size_multiplier" in keys and row["position_size_multiplier"] is not None
                else 1.0
            ),
            adaptation_status=(
                row["adaptation_status"]
                if "adaptation_status" in keys and row["adaptation_status"] is not None
                else "normal"
            ),
            # Phase 4: News Sentiment Filter fields
            news_sentiment_score=row["news_sentiment_score"] if "news_sentiment_score" in keys else None,
            news_sentiment_label=row["news_sentiment_label"] if "news_sentiment_label" in keys else None,
            news_top_headline=row["news_top_headline"] if "news_top_headline" in keys else None,
            news_action=row["news_action"] if "news_action" in keys else None,
            original_star_rating=row["original_star_rating"] if "original_star_rating" in keys else None,
            # Phase 4: Market Regime Detection fields
            market_regime=row["market_regime"] if "market_regime" in keys else None,
            regime_confidence=row["regime_confidence"] if "regime_confidence" in keys else None,
            regime_weight_modifier=row["regime_weight_modifier"] if "regime_weight_modifier" in keys else None,
        )
