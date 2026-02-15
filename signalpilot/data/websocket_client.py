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

logger = logging.getLogger("signalpilot.data.websocket_client")


class WebSocketClient:
    """Manages the Angel One SmartAPI WebSocket connection."""

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

    async def connect(self) -> None:
        """Establish WebSocket connection and subscribe to all instruments."""
        self._loop = asyncio.get_running_loop()

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

        # Start WebSocket in a background thread (it runs its own event loop)
        await asyncio.to_thread(self._ws.connect)

    def _on_open(self, ws) -> None:
        """Callback when WebSocket connection is established."""
        logger.info("WebSocket connection established")
        self._connected = True

        # Subscribe to all instrument tokens
        token_list = self._instruments.get_all_tokens()
        # Mode 1 = LTP, Mode 2 = Quote, Mode 3 = Snap Quote
        self._ws.subscribe("abc123", 3, token_list)

        # Reset reconnect counter only after successful subscription (H5)
        self._reconnect_count = 0
        logger.info("Subscribed to %d token groups", len(token_list))

    def _on_data(self, ws, message) -> None:
        """Callback for incoming tick data.

        Parses the tick message and updates MarketDataStore.
        Bridges from the WebSocket thread into the asyncio event loop.
        """
        if self._loop is None:
            return

        try:
            token = str(message.get("token", ""))
            symbol = self._instruments.get_symbol_by_token(token)
            if symbol is None:
                return

            now = datetime.now()
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

    async def _update_store(self, symbol: str, tick: TickData) -> None:
        """Update the market data store with a new tick."""
        await self._store.update_tick(symbol, tick)
        await self._store.accumulate_volume(symbol, tick.volume)

    def _on_close(self, ws, code, reason) -> None:
        """Callback for connection close. Triggers reconnection."""
        self._connected = False
        logger.warning("WebSocket closed: code=%s reason=%s", code, reason)

        if self._reconnect_count < self._max_reconnect_attempts:
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
        await self.connect()

    def _on_error(self, ws, error) -> None:
        """Callback for WebSocket errors."""
        logger.error("WebSocket error: %s", error)

    async def disconnect(self) -> None:
        """Gracefully close the WebSocket connection."""
        if self._ws is not None:
            try:
                self._ws.close_connection()
            except Exception as e:
                logger.warning("Error closing WebSocket: %s", e)
            self._ws = None
            self._connected = False
            logger.info("WebSocket disconnected")

    @property
    def is_connected(self) -> bool:
        """Check if the WebSocket is currently connected."""
        return self._connected
