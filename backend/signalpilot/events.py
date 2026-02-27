"""Lightweight event bus for decoupled cross-component communication."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from signalpilot.db.models import ExitAlert

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain Events (frozen dataclasses)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExitAlertEvent:
    """ExitMonitor detected an exit condition and needs to notify the bot."""

    alert: ExitAlert


@dataclass(frozen=True)
class StopLossHitEvent:
    """A trade exited via stop loss -- used to feed the circuit breaker."""

    symbol: str
    strategy: str
    pnl_amount: float


@dataclass(frozen=True)
class TradeExitedEvent:
    """Any trade exit -- used to feed the adaptive manager."""

    strategy_name: str
    is_loss: bool


@dataclass(frozen=True)
class AlertMessageEvent:
    """A component needs to send a plain-text Telegram alert."""

    message: str


# ---------------------------------------------------------------------------
# Event Bus
# ---------------------------------------------------------------------------

# Type alias for async event handlers
EventHandler = Callable[..., Awaitable[None]]


class EventBus:
    """In-process async event bus with sequential dispatch and error isolation.

    No external dependencies, no persistence, no background tasks.
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        """Register *handler* to be called when *event_type* is emitted."""
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type, handler: EventHandler) -> None:
        """Remove *handler* from *event_type* subscribers."""
        try:
            self._handlers[event_type].remove(handler)
        except ValueError:
            pass  # not subscribed -- ignore

    async def emit(self, event: object) -> None:
        """Dispatch *event* to all subscribed handlers sequentially.

        Each handler is called in registration order.  If a handler raises,
        the error is logged but remaining handlers still run.
        """
        event_type = type(event)
        for handler in list(self._handlers.get(event_type, [])):
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Event handler %s failed for %s",
                    getattr(handler, "__name__", handler),
                    event_type.__name__,
                )

    def handler_count(self, event_type: type) -> int:
        """Return the number of handlers registered for *event_type*."""
        return len(self._handlers.get(event_type, []))
