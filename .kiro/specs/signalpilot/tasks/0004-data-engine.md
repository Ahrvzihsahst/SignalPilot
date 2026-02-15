# Task 4: Data Engine

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 1-5, 7)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 4.1)

---

## Subtasks

### 4.1 Implement `signalpilot/data/market_data_store.py` with MarketDataStore

- [ ] Implement `MarketDataStore` class as specified in design (Section 4.1.5)
- [ ] Use `asyncio.Lock` for thread-safe access
- [ ] Implement all methods:
  - `update_tick(symbol: str, tick: TickData)` — update latest tick for symbol
  - `get_tick(symbol: str) -> TickData | None` — retrieve latest tick
  - `set_historical(symbol: str, ref: HistoricalReference)` — store prev day data
  - `get_historical(symbol: str) -> HistoricalReference | None` — retrieve prev day data
  - `accumulate_volume(symbol: str, volume: int)` — track cumulative day volume
  - `get_accumulated_volume(symbol: str) -> int` — retrieve cumulative volume
  - `get_all_ticks() -> dict[str, TickData]` — snapshot of all current ticks
- [ ] Volume accumulation tracks cumulative day volume per symbol (no candle aggregation needed per design decision 10.8)
- [ ] Write tests in `tests/test_data/test_market_data_store.py`:
  - Verify tick updates and retrieval
  - Verify historical data storage and retrieval
  - Verify volume accumulation across multiple updates
  - Verify concurrent access safety (asyncio lock)

**Requirement coverage:** Req 2.5 (update in-memory store within 1s), Req 3.4 (store historical data), Req 7 (volume accumulation)

---

### 4.2 Implement `signalpilot/data/instruments.py` with InstrumentManager

- [ ] Implement `InstrumentManager` class as specified in design (Section 4.1.4)
- [ ] `load()`:
  - Read Nifty 500 CSV from configured path
  - Fetch Angel One instrument master JSON (`OpenAPIScripMaster.json`)
  - Filter instrument master for NSE equity (`exch_seg == "NSE"`, symbol ends with `-EQ`)
  - Cross-reference CSV symbols with instrument master to obtain Angel One tokens
  - Build `_instruments` dict (symbol -> Instrument)
  - Build `_token_map` dict (angel_token -> symbol)
- [ ] Log warnings for symbols not found in instrument master (Req 5.3)
- [ ] Implement accessor methods:
  - `get_all_tokens() -> list[str]` — all Angel One tokens for WebSocket subscription
  - `get_symbol_by_token(token: str) -> str | None` — reverse lookup
  - `get_instrument(symbol: str) -> Instrument | None`
  - `symbols` property — list of all loaded symbols
- [ ] Write tests in `tests/test_data/test_instruments.py` with mock CSV and mock instrument master:
  - Verify cross-reference builds correct mappings
  - Verify token-to-symbol reverse lookup
  - Verify missing symbol logs warning and is excluded

**Requirement coverage:** Req 5.1 (load instrument list), Req 5.2 (use for subscription), Req 5.3 (log missing instruments)

---

### 4.3 Implement `signalpilot/data/auth.py` with SmartAPIAuthenticator

- [ ] Implement `SmartAPIAuthenticator` class as specified in design (Section 4.1.1)
- [ ] `authenticate()`:
  - Generate TOTP via `pyotp.TOTP(secret).now()`
  - Call `SmartConnect.generateSession(client_id, password, totp)`
  - Store tokens: auth_token, feed_token, refresh_token
  - Run in `asyncio.to_thread` since SmartConnect is synchronous
- [ ] Apply `@with_retry(max_retries=3)` decorator for retry with exponential backoff
- [ ] `refresh_session()`: re-authenticate using stored credentials when session expires
- [ ] Properties for `auth_token`, `feed_token`, `smart_connect` that raise if not authenticated
- [ ] Write tests in `tests/test_data/test_auth.py` with mocked SmartConnect:
  - Verify successful auth stores all tokens
  - Verify retry on failure (3 attempts)
  - Verify re-auth flow works

**Requirement coverage:** Req 1.1 (authenticate on startup), Req 1.2 (retry 3x), Req 1.3 (store session), Req 1.4 (auto re-auth)

---

### 4.4 Implement `signalpilot/data/historical.py` with HistoricalDataFetcher

- [ ] Implement `HistoricalDataFetcher` as specified in design (Section 4.1.3)
- [ ] `fetch_previous_day_data()`:
  - Fetch previous close and previous high for all Nifty 500 via Angel One API
  - Batch requests with `asyncio.Semaphore` for rate limiting (~3 req/s)
- [ ] `fetch_average_daily_volume(lookback_days=20)`:
  - Fetch 20-day ADV for each stock
- [ ] `_fetch_from_angel_one()`: use `SmartConnect.getCandleData()`
- [ ] `_fetch_from_yfinance()`: use yfinance with `.NS` suffix as fallback, log warning (Req 4.2)
- [ ] If both sources fail for an instrument, exclude it and log (Req 3.3, Req 4.3)
- [ ] Write tests in `tests/test_data/test_historical.py`:
  - Mock Angel One API success — verify data is returned
  - Mock Angel One failure — verify fallback to yfinance
  - Mock both sources fail — verify instrument is excluded

**Requirement coverage:** Req 3.1 (prev close/high), Req 3.2 (20-day ADV), Req 3.3 (exclude on failure), Req 4.1 (yfinance fallback), Req 4.2 (log warning), Req 4.3 (alert on both fail)

---

### 4.5 Implement `signalpilot/data/websocket_client.py` with WebSocketClient

- [ ] Implement `WebSocketClient` as specified in design (Section 4.1.2)
- [ ] `connect()`:
  - Create `SmartWebSocketV2` instance with auth_token and feed_token
  - Register callbacks: `_on_data`, `_on_close`, `_on_error`
  - Subscribe to all Nifty 500 tokens (single connection, up to 1000 tokens)
- [ ] `_on_data()`:
  - Parse binary tick data from WebSocket
  - Bridge into asyncio loop via `loop.call_soon_threadsafe`
  - Update MarketDataStore with parsed tick
- [ ] `_on_close()`: trigger reconnection logic with up to 3 retries
- [ ] `_on_error()`: log errors, trigger disconnect alert callback after retries exhausted
- [ ] `disconnect()`: gracefully close WebSocket
- [ ] Write tests in `tests/test_data/test_websocket_client.py`:
  - Mock WebSocket, verify subscription call
  - Verify tick parsing updates MarketDataStore
  - Verify reconnection attempts on close
  - Verify alert callback after retries exhausted

**Requirement coverage:** Req 2.1 (establish WebSocket), Req 2.2 (receive LTP/OHLCV), Req 2.3 (auto-reconnect), Req 2.4 (alert on failure), Req 2.5 (update store)
