"""Position sizing based on capital allocation and entry price."""

from signalpilot.db.models import PositionSize


class PositionSizer:
    """Calculates position sizes based on user capital and constraints."""

    def calculate(
        self,
        entry_price: float,
        total_capital: float,
        max_positions: int,
        multiplier: float = 1.0,
    ) -> PositionSize:
        """Compute quantity and capital required for a single trade.

        Per-trade capital = total_capital / max_positions.
        When ``multiplier`` > 1.0, per-trade capital is scaled up with caps:
          - multiplier >= 2.0: cap at 25% of total_capital
          - multiplier > 1.0 but < 2.0: cap at 20% of total_capital
        Quantity = floor(per_trade_capital / entry_price).

        Raises:
            ValueError: If max_positions <= 0 or entry_price <= 0.
        """
        if max_positions <= 0:
            raise ValueError(f"max_positions must be positive, got {max_positions}")
        if entry_price <= 0:
            raise ValueError(f"entry_price must be positive, got {entry_price}")
        per_trade_capital = total_capital / max_positions

        if multiplier > 1.0:
            multiplied = per_trade_capital * multiplier
            if multiplier >= 2.0:
                cap = total_capital * 0.25
            else:
                cap = total_capital * 0.20
            per_trade_capital = min(multiplied, cap)

        quantity = int(per_trade_capital // entry_price)
        capital_required = quantity * entry_price
        return PositionSize(
            quantity=quantity,
            capital_required=capital_required,
            per_trade_capital=per_trade_capital,
        )
