"""Tests for WebSocketClient."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from signalpilot.data.auth import SmartAPIAuthenticator
from signalpilot.data.instruments import InstrumentManager
from signalpilot.data.market_data_store import MarketDataStore
from signalpilot.data.websocket_client import WebSocketClient


@pytest.fixture
def mock_auth() -> MagicMock:
    auth = MagicMock(spec=SmartAPIAuthenticator)
    auth.auth_token = "test_auth_token"
    auth.api_key = "test_api_key"
    auth.client_id = "TEST123"
    auth.feed_token = "test_feed_token"
    return auth


@pytest.fixture
def mock_instruments() -> MagicMock:
    mgr = MagicMock(spec=InstrumentManager)
    mgr.get_all_tokens.return_value = [{"exchangeType": 1, "tokens": ["3045", "2885"]}]
    mgr.get_symbol_by_token.side_effect = lambda t: {"3045": "SBIN", "2885": "RELIANCE"}.get(t)
    return mgr


@pytest.fixture
def store() -> MarketDataStore:
    return MarketDataStore()


@pytest.fixture
def mock_disconnect_alert() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(
    mock_auth: MagicMock,
    mock_instruments: MagicMock,
    store: MarketDataStore,
    mock_disconnect_alert: AsyncMock,
) -> WebSocketClient:
    return WebSocketClient(
        authenticator=mock_auth,
        instruments=mock_instruments,
        market_data_store=store,
        on_disconnect_alert=mock_disconnect_alert,
        max_reconnect_attempts=3,
    )


# ── Initialization ───────────────────────────────────────────────


def test_initial_state(client: WebSocketClient) -> None:
    assert client.is_connected is False
    assert client._ws is None
    assert client._reconnect_count == 0


# ── on_open subscribes ──────────────────────────────────────────


def test_on_open_subscribes_to_tokens(
    client: WebSocketClient, mock_instruments: MagicMock
) -> None:
    mock_ws = MagicMock()
    client._ws = mock_ws

    client._on_open(mock_ws)

    assert client.is_connected is True
    assert client._reconnect_count == 0
    mock_ws.subscribe.assert_called_once()
    call_args = mock_ws.subscribe.call_args
    # Verify token_list passed matches instruments
    assert call_args[0][2] == mock_instruments.get_all_tokens()


# ── on_data parses tick and updates store ────────────────────────


@pytest.mark.asyncio
async def test_on_data_updates_store(
    client: WebSocketClient,
    store: MarketDataStore,
) -> None:
    """Verify _on_data parses tick message and updates MarketDataStore."""
    loop = asyncio.get_running_loop()
    client._loop = loop

    message = {
        "token": "3045",
        "last_traded_price": 10500,   # 105.00 after /100
        "open_price_of_the_day": 10400,
        "high_price_of_the_day": 10600,
        "low_price_of_the_day": 10300,
        "closed_price": 10200,
        "volume_trade_for_the_day": 75000,
    }

    client._on_data(None, message)

    # Give the event loop a chance to process the scheduled coroutine
    await asyncio.sleep(0.1)

    tick = await store.get_tick("SBIN")
    assert tick is not None
    assert tick.ltp == pytest.approx(105.0)
    assert tick.open_price == pytest.approx(104.0)
    assert tick.high == pytest.approx(106.0)
    assert tick.low == pytest.approx(103.0)
    assert tick.close == pytest.approx(102.0)
    assert tick.volume == 75000


@pytest.mark.asyncio
async def test_on_data_ignores_unknown_token(
    client: WebSocketClient,
    store: MarketDataStore,
) -> None:
    """Unknown token should be silently ignored."""
    loop = asyncio.get_running_loop()
    client._loop = loop

    message = {
        "token": "9999",  # not in our instruments
        "last_traded_price": 10000,
    }

    client._on_data(None, message)
    await asyncio.sleep(0.1)

    snapshot = await store.get_all_ticks()
    assert len(snapshot) == 0


@pytest.mark.asyncio
async def test_on_data_accumulates_volume(
    client: WebSocketClient,
    store: MarketDataStore,
) -> None:
    """Verify _on_data also updates volume accumulator."""
    loop = asyncio.get_running_loop()
    client._loop = loop

    message = {
        "token": "3045",
        "last_traded_price": 10500,
        "open_price_of_the_day": 10400,
        "high_price_of_the_day": 10600,
        "low_price_of_the_day": 10300,
        "closed_price": 10200,
        "volume_trade_for_the_day": 75000,
    }

    client._on_data(None, message)
    await asyncio.sleep(0.1)

    vol = await store.get_accumulated_volume("SBIN")
    assert vol == 75000


@pytest.mark.asyncio
async def test_on_data_handles_malformed_message(
    client: WebSocketClient,
    store: MarketDataStore,
) -> None:
    """Malformed message should be logged, not crash the handler."""
    loop = asyncio.get_running_loop()
    client._loop = loop

    # Missing required fields entirely
    client._on_data(None, {})
    await asyncio.sleep(0.1)

    snapshot = await store.get_all_ticks()
    assert len(snapshot) == 0


@pytest.mark.asyncio
async def test_on_data_does_nothing_without_loop(client: WebSocketClient) -> None:
    """If _loop is None, _on_data should return without error."""
    client._loop = None
    # Should not raise
    client._on_data(None, {"token": "3045", "last_traded_price": 10000})


# ── on_close triggers reconnection ──────────────────────────────


@pytest.mark.asyncio
async def test_on_close_triggers_reconnection(client: WebSocketClient) -> None:
    """First close should trigger a reconnection attempt via _reconnect_with_delay."""
    loop = asyncio.get_running_loop()
    client._loop = loop
    client._connected = True

    with patch.object(client, "_reconnect_with_delay", new_callable=AsyncMock) as mock_reconnect:
        client._on_close(None, 1000, "normal")
        await asyncio.sleep(0.1)

    assert client.is_connected is False
    assert client._reconnect_count == 1
    mock_reconnect.assert_called_once()


@pytest.mark.asyncio
async def test_on_close_increments_reconnect_count(client: WebSocketClient) -> None:
    loop = asyncio.get_running_loop()
    client._loop = loop
    client._reconnect_count = 1  # Already 1 reconnect

    with patch.object(client, "_reconnect_with_delay", new_callable=AsyncMock):
        client._on_close(None, 1000, "disconnect")
        await asyncio.sleep(0.1)

    assert client._reconnect_count == 2


@pytest.mark.asyncio
async def test_reconnect_with_delay_applies_backoff(client: WebSocketClient) -> None:
    """Verify exponential backoff delay before reconnection."""
    client._reconnect_count = 1  # 2.0 * 2^(1-1) = 2.0s

    with patch.object(client, "connect", new_callable=AsyncMock) as mock_connect, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await client._reconnect_with_delay()

    mock_sleep.assert_called_once_with(2.0)
    mock_connect.assert_called_once()


@pytest.mark.asyncio
async def test_reconnect_with_delay_increases_backoff(client: WebSocketClient) -> None:
    """Second reconnect should have longer delay."""
    client._reconnect_count = 2  # 2.0 * 2^(2-1) = 4.0s

    with patch.object(client, "connect", new_callable=AsyncMock) as mock_connect, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await client._reconnect_with_delay()

    mock_sleep.assert_called_once_with(4.0)
    mock_connect.assert_called_once()


# ── on_close after max retries → disconnect alert ────────────────


@pytest.mark.asyncio
async def test_on_close_alert_after_max_retries(
    client: WebSocketClient,
    mock_disconnect_alert: AsyncMock,
) -> None:
    """After max reconnect attempts, the disconnect alert callback fires."""
    loop = asyncio.get_running_loop()
    client._loop = loop
    client._reconnect_count = 3  # Already at max

    client._on_close(None, 1000, "disconnect")
    await asyncio.sleep(0.1)

    mock_disconnect_alert.assert_called_once()
    call_msg = mock_disconnect_alert.call_args[0][0]
    assert "max retries" in call_msg.lower()


# ── on_error logs ────────────────────────────────────────────────


def test_on_error_does_not_raise(client: WebSocketClient) -> None:
    """_on_error should log but not raise."""
    client._on_error(None, RuntimeError("test error"))


# ── disconnect ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disconnect_closes_ws(client: WebSocketClient) -> None:
    mock_ws = MagicMock()
    client._ws = mock_ws
    client._connected = True

    await client.disconnect()

    mock_ws.close_connection.assert_called_once()
    assert client._ws is None
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_disconnect_handles_already_disconnected(client: WebSocketClient) -> None:
    """Disconnecting when already disconnected should be safe."""
    await client.disconnect()
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_disconnect_handles_close_error(client: WebSocketClient) -> None:
    """If close_connection raises, disconnect should still clean up."""
    mock_ws = MagicMock()
    mock_ws.close_connection.side_effect = RuntimeError("close failed")
    client._ws = mock_ws
    client._connected = True

    await client.disconnect()

    assert client._ws is None
    assert client.is_connected is False
