"""Repository for trade records."""

from datetime import date, datetime

import aiosqlite

from signalpilot.db.models import ExitType, TradeRecord

_VALID_EXIT_REASONS = frozenset(e.value for e in ExitType)


class TradeRepository:
    """CRUD operations for the trades table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def insert_trade(self, trade: TradeRecord) -> int:
        """Insert a trade record and return the new row ID."""
        cursor = await self._conn.execute(
            """
            INSERT INTO trades
                (signal_id, date, symbol, strategy, entry_price, exit_price, stop_loss,
                 target_1, target_2, quantity, pnl_amount, pnl_pct,
                 exit_reason, taken_at, exited_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.signal_id,
                trade.date.isoformat(),
                trade.symbol,
                trade.strategy,
                trade.entry_price,
                trade.exit_price,
                trade.stop_loss,
                trade.target_1,
                trade.target_2,
                trade.quantity,
                trade.pnl_amount,
                trade.pnl_pct,
                trade.exit_reason,
                trade.taken_at.isoformat() if trade.taken_at else datetime.now().isoformat(),
                trade.exited_at.isoformat() if trade.exited_at else None,
            ),
        )
        await self._conn.commit()
        row_id = cursor.lastrowid
        assert row_id is not None, "INSERT did not return a row ID"
        return row_id

    async def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        pnl_amount: float,
        pnl_pct: float,
        exit_reason: str,
    ) -> None:
        """Close a trade by updating exit fields."""
        if exit_reason not in _VALID_EXIT_REASONS:
            raise ValueError(
                f"Invalid exit_reason: {exit_reason!r}. Must be one of {_VALID_EXIT_REASONS}"
            )
        cursor = await self._conn.execute(
            """
            UPDATE trades
            SET exit_price = ?, pnl_amount = ?, pnl_pct = ?,
                exit_reason = ?, exited_at = ?
            WHERE id = ?
            """,
            (exit_price, pnl_amount, pnl_pct, exit_reason, datetime.now().isoformat(), trade_id),
        )
        await self._conn.commit()
        if cursor.rowcount == 0:
            raise ValueError(f"Trade {trade_id} not found")

    async def get_active_trades(self) -> list[TradeRecord]:
        """Return all open trades (not yet exited)."""
        cursor = await self._conn.execute(
            """
            SELECT * FROM trades
            WHERE exited_at IS NULL
            ORDER BY taken_at DESC
            """,
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_active_trade_count(self) -> int:
        """Return the count of open trades (for position limit check)."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM trades WHERE exited_at IS NULL",
        )
        row = await cursor.fetchone()
        return row[0]

    async def get_trades_by_date(self, d: date) -> list[TradeRecord]:
        """Return all trades for the given date."""
        cursor = await self._conn.execute(
            "SELECT * FROM trades WHERE date = ? ORDER BY taken_at",
            (d.isoformat(),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_all_closed_trades(self) -> list[TradeRecord]:
        """Return all closed trades (for JOURNAL command)."""
        cursor = await self._conn.execute(
            """
            SELECT * FROM trades
            WHERE exited_at IS NOT NULL
            ORDER BY exited_at DESC
            """,
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_trades_by_strategy(self, strategy: str) -> list[TradeRecord]:
        """Return all trades for a given strategy."""
        cursor = await self._conn.execute(
            "SELECT * FROM trades WHERE strategy = ? ORDER BY taken_at",
            (strategy,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> TradeRecord:
        """Convert a database row to a TradeRecord."""
        return TradeRecord(
            id=row["id"],
            signal_id=row["signal_id"],
            date=date.fromisoformat(row["date"]),
            symbol=row["symbol"],
            strategy=row["strategy"] if "strategy" in row.keys() else "gap_go",
            entry_price=row["entry_price"],
            exit_price=row["exit_price"],
            stop_loss=row["stop_loss"],
            target_1=row["target_1"],
            target_2=row["target_2"],
            quantity=row["quantity"],
            pnl_amount=row["pnl_amount"],
            pnl_pct=row["pnl_pct"],
            exit_reason=row["exit_reason"],
            taken_at=datetime.fromisoformat(row["taken_at"]) if row["taken_at"] else None,
            exited_at=datetime.fromisoformat(row["exited_at"]) if row["exited_at"] else None,
        )
