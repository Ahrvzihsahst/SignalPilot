"""Repository for signal records."""

from datetime import date, datetime

import aiosqlite

from signalpilot.db.models import SignalRecord

_VALID_STATUSES = frozenset({"sent", "taken", "expired"})


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
                 gap_pct, volume_ratio, reason, created_at, expires_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                signal.created_at.isoformat() if signal.created_at else datetime.now().isoformat(),
                signal.expires_at.isoformat() if signal.expires_at else datetime.now().isoformat(),
                signal.status,
            ),
        )
        await self._conn.commit()
        row_id = cursor.lastrowid
        assert row_id is not None, "INSERT did not return a row ID"
        return row_id

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
        now = now or datetime.now()
        cursor = await self._conn.execute(
            """
            SELECT * FROM signals
            WHERE date = ? AND status = 'sent'
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
        now = now or datetime.now()
        cursor = await self._conn.execute(
            """
            UPDATE signals
            SET status = 'expired'
            WHERE status = 'sent' AND expires_at <= ?
            """,
            (now.isoformat(),),
        )
        await self._conn.commit()
        return cursor.rowcount

    async def get_latest_active_signal(self, now: datetime | None = None) -> SignalRecord | None:
        """Return the most recent active signal (for TAKEN command)."""
        now = now or datetime.now()
        cursor = await self._conn.execute(
            """
            SELECT * FROM signals
            WHERE status = 'sent' AND expires_at > ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (now.isoformat(),),
        )
        row = await cursor.fetchone()
        return self._row_to_record(row) if row else None

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> SignalRecord:
        """Convert a database row to a SignalRecord."""
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
        )
