"""Position sizing based on capital allocation and entry price."""

from signalpilot.db.models import PositionSize


class PositionSizer:
    """Calculates position sizes based on user capital and constraints."""

    def calculate(
        self,
        entry_price: float,
        total_capital: float,
        max_positions: int,
    ) -> PositionSize:
        """Compute quantity and capital required for a single trade.

        Per-trade capital = total_capital / max_positions.
        Quantity = floor(per_trade_capital / entry_price).

        Raises:
            ValueError: If max_positions <= 0 or entry_price <= 0.
        """
        if max_positions <= 0:
            raise ValueError(f"max_positions must be positive, got {max_positions}")
        if entry_price <= 0:
            raise ValueError(f"entry_price must be positive, got {entry_price}")
        per_trade_capital = total_capital / max_positions
        quantity = int(per_trade_capital // entry_price)
        capital_required = quantity * entry_price
        return PositionSize(
            quantity=quantity,
            capital_required=capital_required,
            per_trade_capital=per_trade_capital,
        )
