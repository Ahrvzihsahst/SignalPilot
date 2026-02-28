"""Tests for the lightweight event bus."""

from signalpilot.events import (
    AlertMessageEvent,
    EventBus,
    ExitAlertEvent,
    StopLossHitEvent,
    TradeExitedEvent,
)


async def test_subscribe_and_emit_single_handler():
    """A subscribed handler receives the emitted event."""
    bus = EventBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe(AlertMessageEvent, handler)
    event = AlertMessageEvent(message="hello")
    await bus.emit(event)

    assert received == [event]


async def test_subscribe_and_emit_multiple_handlers():
    """Multiple handlers for the same event type all get called."""
    bus = EventBus()
    results = []

    async def handler_a(event):
        results.append(("a", event.message))

    async def handler_b(event):
        results.append(("b", event.message))

    bus.subscribe(AlertMessageEvent, handler_a)
    bus.subscribe(AlertMessageEvent, handler_b)
    await bus.emit(AlertMessageEvent(message="test"))

    assert results == [("a", "test"), ("b", "test")]


async def test_emit_with_no_subscribers_is_noop():
    """Emitting an event with no subscribers should not raise."""
    bus = EventBus()
    await bus.emit(AlertMessageEvent(message="nobody listening"))


async def test_handler_error_does_not_block_other_handlers():
    """If one handler raises, others should still be called."""
    bus = EventBus()
    results = []

    async def failing_handler(event):
        raise RuntimeError("boom")

    async def ok_handler(event):
        results.append(event.message)

    bus.subscribe(AlertMessageEvent, failing_handler)
    bus.subscribe(AlertMessageEvent, ok_handler)
    await bus.emit(AlertMessageEvent(message="test"))

    assert results == ["test"]


async def test_unsubscribe_removes_handler():
    """After unsubscribe, the handler should no longer be called."""
    bus = EventBus()
    results = []

    async def handler(event):
        results.append(event)

    bus.subscribe(AlertMessageEvent, handler)
    bus.unsubscribe(AlertMessageEvent, handler)
    await bus.emit(AlertMessageEvent(message="ignored"))

    assert results == []


async def test_unsubscribe_nonexistent_handler_is_noop():
    """Unsubscribing a handler that was never subscribed should not raise."""
    bus = EventBus()

    async def handler(event):
        pass

    bus.unsubscribe(AlertMessageEvent, handler)


async def test_handler_count():
    """handler_count returns the number of registered handlers."""
    bus = EventBus()
    assert bus.handler_count(AlertMessageEvent) == 0

    async def h1(event):
        pass

    async def h2(event):
        pass

    bus.subscribe(AlertMessageEvent, h1)
    assert bus.handler_count(AlertMessageEvent) == 1

    bus.subscribe(AlertMessageEvent, h2)
    assert bus.handler_count(AlertMessageEvent) == 2

    bus.unsubscribe(AlertMessageEvent, h1)
    assert bus.handler_count(AlertMessageEvent) == 1


async def test_different_event_types_isolated():
    """Handlers for one event type don't receive events of another type."""
    bus = EventBus()
    alert_results = []
    sl_results = []

    async def alert_handler(event):
        alert_results.append(event)

    async def sl_handler(event):
        sl_results.append(event)

    bus.subscribe(AlertMessageEvent, alert_handler)
    bus.subscribe(StopLossHitEvent, sl_handler)

    await bus.emit(AlertMessageEvent(message="alert"))
    await bus.emit(StopLossHitEvent(symbol="SBIN", strategy="Gap & Go", pnl_amount=-100.0))

    assert len(alert_results) == 1
    assert len(sl_results) == 1
    assert isinstance(alert_results[0], AlertMessageEvent)
    assert isinstance(sl_results[0], StopLossHitEvent)


async def test_domain_events_are_frozen():
    """Domain events should be frozen dataclasses."""
    event = StopLossHitEvent(symbol="SBIN", strategy="Gap & Go", pnl_amount=-100.0)
    try:
        event.symbol = "TCS"
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        pass


async def test_trade_exited_event():
    """TradeExitedEvent carries strategy name and loss flag."""
    event = TradeExitedEvent(strategy_name="ORB", is_loss=True)
    assert event.strategy_name == "ORB"
    assert event.is_loss is True


async def test_exit_alert_event():
    """ExitAlertEvent wraps an ExitAlert."""
    from signalpilot.db.models import ExitAlert, ExitType, TradeRecord

    trade = TradeRecord(id=1, symbol="SBIN")
    alert = ExitAlert(
        trade=trade,
        exit_type=ExitType.SL_HIT,
        current_price=97.0,
        pnl_pct=-3.0,
        is_alert_only=False,
    )
    event = ExitAlertEvent(alert=alert)
    assert event.alert is alert
