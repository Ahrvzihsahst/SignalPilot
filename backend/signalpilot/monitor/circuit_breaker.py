"""Circuit breaker that halts signal generation after N stop-losses in a day."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

from signalpilot.utils.constants import IST

if TYPE_CHECKING:
    from signalpilot.events import EventBus

logger = logging.getLogger(__name__)


class CircuitBreaker:
    def __init__(
        self,
        circuit_breaker_repo=None,
        config_repo=None,
        on_circuit_break=None,
        sl_limit: int = 3,
        event_bus: EventBus | None = None,
    ):
        self._repo = circuit_breaker_repo
        self._config_repo = config_repo
        self._on_circuit_break = on_circuit_break
        self._sl_limit = sl_limit
        self._event_bus = event_bus
        self._daily_sl_count = 0
        self._is_active = False
        self._overridden = False
        self._current_date: date | None = None
        self._sl_details: list[dict] = []

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def daily_sl_count(self) -> int:
        return self._daily_sl_count

    @property
    def sl_limit(self) -> int:
        return self._sl_limit

    @property
    def is_overridden(self) -> bool:
        return self._overridden

    async def _send_alert(self, message: str) -> None:
        """Send alert via event bus or legacy callback."""
        if self._event_bus is not None:
            from signalpilot.events import AlertMessageEvent

            await self._event_bus.emit(AlertMessageEvent(message=message))
        elif self._on_circuit_break:
            await self._on_circuit_break(message)

    async def on_sl_hit(self, trade_symbol: str, trade_strategy: str, pnl_amount: float) -> None:
        self._daily_sl_count += 1
        self._sl_details.append({
            "symbol": trade_symbol,
            "strategy": trade_strategy,
            "pnl": pnl_amount,
        })

        if self._daily_sl_count == self._sl_limit - 1:
            msg = (
                f"\u26a0\ufe0f {self._daily_sl_count} stop losses hit today. "
                f"1 more triggers circuit breaker."
            )
            await self._send_alert(msg)

        if self._daily_sl_count >= self._sl_limit and not self._is_active and not self._overridden:
            await self._activate()

    async def _activate(self) -> None:
        self._is_active = True
        now = datetime.now(IST)

        if self._repo is not None:
            await self._repo.log_activation(
                today=now.date(),
                sl_count=self._daily_sl_count,
                triggered_at=now,
            )

        total_loss = sum(d["pnl"] for d in self._sl_details)
        details_lines = []
        for d in self._sl_details:
            details_lines.append(f"  \u2022 {d['symbol']} ({d['strategy']}): \u20b9{d['pnl']:.0f}")
        details_text = "\n".join(details_lines)

        msg = (
            f"\U0001f6d1 CIRCUIT BREAKER ACTIVATED\n"
            f"SL count: {self._daily_sl_count}/{self._sl_limit}\n"
            f"\nTrade details:\n{details_text}\n"
            f"\nTotal loss: \u20b9{total_loss:.0f}\n"
            f"No new signals until tomorrow 9:15 AM.\n"
            f"Use OVERRIDE CIRCUIT to resume."
        )
        await self._send_alert(msg)

    async def override(self) -> bool:
        if not self._is_active:
            return False
        self._overridden = True
        self._is_active = False

        if self._repo is not None:
            now = datetime.now(IST)
            await self._repo.log_override(today=now.date(), override_at=now)

        return True

    def reset_daily(self) -> None:
        self._daily_sl_count = 0
        self._is_active = False
        self._overridden = False
        self._sl_details.clear()
        self._current_date = datetime.now(IST).date()
