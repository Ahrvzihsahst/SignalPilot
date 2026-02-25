"""Angel One SmartAPI WebSocket client for real-time tick data."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from SmartApi.smartWebSocketV2 import SmartWebSocketV2

from signalpilot.data.auth import SmartAPIAuthenticator
from signalpilot.data.instruments import InstrumentManager
from signalpilot.data.market_data_store import MarketDataStore
from signalpilot.db.models import TickData
from signalpilot.utils.constants import IST

logger = logging.getLogger("signalpilot.data.websocket_client")


class WebSocketClient:
    """Manages the Angel One SmartAPI WebSocket connection.

    The SmartWebSocketV2.connect() call is blocking (runs ``run_forever``
    internally), so it is launched in a background thread via
    ``loop.run_in_executor``.  The ``connect`` coroutine returns as soon as
    ``_on_open`` fires, allowing the caller to proceed immediately.
    """

    def __init__(
        self,
        authenticator: SmartAPIAuthenticator,
        instruments: InstrumentManager,
        market_data_store: MarketDataStore,
        on_disconnect_alert: Callable[[str], Awaitable[None]],
        max_reconnect_attempts: int = 3,
    ) -> None:
        self._auth = authenticator
        self._instruments = instruments
        self._store = market_data_store
        self._on_disconnect_alert = on_disconnect_alert
        self._max_reconnect_attempts = max_reconnect_attempts
        self._ws: SmartWebSocketV2 | None = None
        self._reconnect_count = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connected = False
        self._connected_event: asyncio.Event | None = None
        self._reconnecting = False  # guard against double reconnection
        # Track cumulative volume per symbol so we can derive per-tick deltas
        # for VWAP and candle aggregation.
        self._prev_volume: dict[str, int] = {}

    async def connect(self) -> None:
        """Establish WebSocket connection and subscribe to all instruments.

        Launches the blocking ``SmartWebSocketV2.connect()`` in a background
        thread and waits (with timeout) for the ``_on_open`` callback to fire,
        signalling that the connection is ready and subscriptions are in place.
        Returns promptly so the caller can proceed (e.g. start the scan loop).
        """
        self._loop = asyncio.get_running_loop()
        self._connected_event = asyncio.Event()

        # Close any lingering previous WebSocket before creating a new one
        # (prevents duplicate threads / callbacks on reconnection).
        if self._ws is not None:
            try:
                self._ws.close_connection()
            except Exception:
                pass
            self._ws = None

        self._ws = SmartWebSocketV2(
            self._auth.auth_token,
            self._auth.api_key,
            self._auth.client_id,
            self._auth.feed_token,
        )

        self._ws.on_data = self._on_data
        self._ws.on_close = self._on_close
        self._ws.on_error = self._on_error
        self._ws.on_open = self._on_open

        # Start WebSocket in a background thread.  ``SmartWebSocketV2.connect``
        # is blocking (calls ``run_forever``), so we must NOT await the future —
        # it only resolves when the WebSocket disconnects.
        self._loop.run_in_executor(None, self._ws.connect)

        # Wait until ``_on_open`` fires (or timeout after 30 s).
        try:
            await asyncio.wait_for(self._connected_event.wait(), timeout=30)
        except asyncio.TimeoutError:
            logger.error("WebSocket connection timed out after 30 s")
            raise

    # -- WebSocket callbacks (run in the WS background thread) ---------------

    def _on_open(self, ws) -> None:
        """Called when the WebSocket connection is established."""
        logger.info("WebSocket connection established")

        # Guard: if disconnect() was called before this callback fired,
        # self._ws will be None — skip subscription to avoid AttributeError.
        if self._ws is None:
            logger.warning("_on_open fired but WebSocket already torn down, skipping subscription")
            return

        self._connected = True

        # Subscribe to all instrument tokens
        token_list = self._instruments.get_all_tokens()
        try:
            # Mode 1 = LTP, Mode 2 = Quote, Mode 3 = Snap Quote
            self._ws.subscribe("abc123", 3, token_list)
        except Exception:
            logger.exception("Failed to subscribe to instrument tokens")

        # Reset reconnect counter and reconnecting guard after successful subscription.
        self._reconnect_count = 0
        self._reconnecting = False
        logger.info("Subscribed to %d token groups", len(token_list))

        # Signal the asyncio side that connection + subscription is ready.
        if self._loop is not None and self._connected_event is not None:
            self._loop.call_soon_threadsafe(self._connected_event.set)

    def _on_data(self, ws, message) -> None:
        """Parse incoming tick and bridge into the asyncio event loop."""
        if self._loop is None or not self._connected:
            return

        try:
            token = str(message.get("token", ""))
            symbol = self._instruments.get_symbol_by_token(token)
            if symbol is None:
                return

            now = datetime.now(IST)
            tick = TickData(
                symbol=symbol,
                ltp=float(message.get("last_traded_price", 0)) / 100,
                open_price=float(message.get("open_price_of_the_day", 0)) / 100,
                high=float(message.get("high_price_of_the_day", 0)) / 100,
                low=float(message.get("low_price_of_the_day", 0)) / 100,
                close=float(message.get("closed_price", 0)) / 100,
                volume=int(message.get("volume_trade_for_the_day", 0)),
                last_traded_timestamp=now,
                updated_at=now,
            )

            self._loop.call_soon_threadsafe(
                asyncio.ensure_future,
                self._update_store(symbol, tick),
            )
        except Exception:
            logger.exception("Error parsing tick data from message: %s", message)

    def _on_close(self, ws, code=None, reason=None) -> None:
        """Handle connection close — schedule reconnection if retries remain.

        Signature uses defaults because the upstream websocket-client library
        may call on_close with (ws,) or (ws, code, reason) depending on version.
        """
        self._connected = False
        logger.warning("WebSocket closed: code=%s reason=%s", code, reason)

        # Guard: if _on_error already triggered a reconnection, skip here.
        if self._reconnecting:
            return

        if self._reconnect_count < self._max_reconnect_attempts:
            self._reconnecting = True
            self._reconnect_count += 1
            logger.info(
                "Reconnection attempt %d/%d",
                self._reconnect_count,
                self._max_reconnect_attempts,
            )
            if self._loop is not None:
                self._loop.call_soon_threadsafe(
                    asyncio.ensure_future,
                    self._reconnect_with_delay(),
                )
        else:
            logger.error("Max reconnection attempts exhausted")
            if self._loop is not None:
                self._loop.call_soon_threadsafe(
                    asyncio.ensure_future,
                    self._on_disconnect_alert(
                        "WebSocket disconnected after max retries exhausted"
                    ),
                )

    def _on_error(self, ws, error) -> None:
        """Handle WebSocket errors — log and schedule reconnection."""
        logger.error("WebSocket error: %s", error)
        # Errors often precede an _on_close callback. Use _reconnecting guard
        # so only one of _on_error / _on_close triggers a reconnect attempt.
        if self._connected and not self._reconnecting:
            self._connected = False
            if (
                self._reconnect_count < self._max_reconnect_attempts
                and self._loop is not None
            ):
                self._reconnecting = True
                self._reconnect_count += 1
                self._loop.call_soon_threadsafe(
                    asyncio.ensure_future,
                    self._reconnect_with_delay(),
                )

    # -- Internal helpers ----------------------------------------------------

    async def _update_store(self, symbol: str, tick: TickData) -> None:
        """Update all market data aggregations from a single tick."""
        await self._store.update_tick(symbol, tick)
        await self._store.accumulate_volume(symbol, tick.volume)

        # Compute incremental volume (tick.volume is cumulative for the day).
        prev_vol = self._prev_volume.get(symbol, 0)
        delta_vol = max(0, tick.volume - prev_vol)
        self._prev_volume[symbol] = tick.volume

        if delta_vol > 0:
            # Running VWAP
            await self._store.update_vwap(symbol, tick.ltp, float(delta_vol))
            # 15-minute candle aggregation
            await self._store.update_candle(
                symbol, tick.ltp, float(delta_vol), tick.updated_at
            )

        # Opening range (store ignores updates after range is locked)
        await self._store.update_opening_range(symbol, tick.high, tick.low)

    async def _reconnect_with_delay(self) -> None:
        """Reconnect after an exponential backoff delay."""
        delay = 2.0 * (2 ** (self._reconnect_count - 1))
        logger.info(
            "Waiting %.1fs before reconnection attempt %d/%d",
            delay,
            self._reconnect_count,
            self._max_reconnect_attempts,
        )
        await asyncio.sleep(delay)
        try:
            await self.connect()
        except Exception:
            logger.exception("Reconnection attempt %d failed", self._reconnect_count)

    async def disconnect(self) -> None:
        """Gracefully close the WebSocket connection."""
        # Mark as disconnected first to prevent callbacks from firing
        self._connected = False
        # Exhaust retries so no in-flight reconnection attempts proceed
        self._reconnect_count = self._max_reconnect_attempts
        if self._ws is not None:
            try:
                self._ws.close_connection()
            except Exception as e:
                logger.warning("Error closing WebSocket: %s", e)
            self._ws = None
            logger.info("WebSocket disconnected")

    def reset_volume_tracking(self) -> None:
        """Clear per-tick volume deltas (call at session start)."""
        self._prev_volume.clear()

    @property
    def is_connected(self) -> bool:
        """Check if the WebSocket is currently connected."""
        return self._connected
