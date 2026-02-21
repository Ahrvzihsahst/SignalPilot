# Task 4: Data Engine

## Status: COMPLETED

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 1-5, 7)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 4.1)

---

## Subtasks

### 4.1 Implement `signalpilot/data/market_data_store.py` with MarketDataStore

- [x] Implement `MarketDataStore` class as specified in design (Section 4.1.5)
- [x] Use `asyncio.Lock` for async-safe access (docstring clarified: not raw thread-safe)
- [x] Implement all methods:
  - `update_tick(symbol: str, tick: TickData)` — update latest tick for symbol
  - `get_tick(symbol: str) -> TickData | None` — retrieve latest tick
  - `set_historical(symbol: str, ref: HistoricalReference)` — store prev day data
  - `get_historical(symbol: str) -> HistoricalReference | None` — retrieve prev day data
  - `accumulate_volume(symbol: str, volume: int)` — track cumulative day volume
  - `get_accumulated_volume(symbol: str) -> int` — retrieve cumulative volume
  - `get_all_ticks() -> dict[str, TickData]` — snapshot of all current ticks
- [x] Volume accumulation tracks cumulative day volume per symbol (no candle aggregation needed per design decision 10.8)
- [x] Write tests in `tests/test_data/test_market_data_store.py` (12 tests):
  - Verify tick updates and retrieval
  - Verify historical data storage and retrieval
  - Verify volume accumulation across multiple updates
  - Verify concurrent access safety (asyncio lock)
  - Verify snapshot returns copy (not reference)
  - Verify clear removes all data

**Requirement coverage:** Req 2.5 (update in-memory store within 1s), Req 3.4 (store historical data), Req 7 (volume accumulation)

---

### 4.2 Implement `signalpilot/data/instruments.py` with InstrumentManager

- [x] Implement `InstrumentManager` class as specified in design (Section 4.1.4)
- [x] `load()`:
  - Read Nifty 500 CSV from configured path
  - Fetch Angel One instrument master JSON (`OpenAPIScripMaster.json`)
  - Filter instrument master for NSE equity (`exch_seg == "NSE"`, symbol ends with `-EQ`)
  - Cross-reference CSV symbols with instrument master to obtain Angel One tokens
  - Build `_instruments` dict (symbol -> Instrument)
  - Build `_token_map` dict (angel_token -> symbol)
- [x] Log warnings for symbols not found in instrument master (Req 5.3)
- [x] Added `@with_retry(max_retries=3)` on `_fetch_instrument_master` for HTTP resilience
- [x] Validate instrument master response is a list
- [x] Implement accessor methods:
  - `get_all_tokens() -> list[str]` — all Angel One tokens for WebSocket subscription
  - `get_symbol_by_token(token: str) -> str | None` — reverse lookup
  - `get_instrument(symbol: str) -> Instrument | None`
  - `symbols` property — list of all loaded symbols
- [x] Write tests in `tests/test_data/test_instruments.py` (10 tests):
  - Verify cross-reference builds correct mappings
  - Verify token-to-symbol reverse lookup
  - Verify missing symbol logs warning and is excluded
  - Verify BSE and non-EQ instruments are filtered out
  - Verify alternative CSV column headers
  - Verify empty state before load

**Requirement coverage:** Req 5.1 (load instrument list), Req 5.2 (use for subscription), Req 5.3 (log missing instruments)

---

### 4.3 Implement `signalpilot/data/auth.py` with SmartAPIAuthenticator

- [x] Implement `SmartAPIAuthenticator` class as specified in design (Section 4.1.1)
- [x] Credentials stored as private attributes (`_mpin`, `_totp_secret`); `api_key` and `client_id` exposed via read-only properties
- [x] `authenticate()`:
  - Generate TOTP via `pyotp.TOTP(secret).now()`
  - Call `SmartConnect.generateSession(client_id, password, totp)`
  - Store tokens: auth_token, feed_token, refresh_token
  - Run in `asyncio.to_thread` since SmartConnect is synchronous
- [x] Apply `@with_retry(max_retries=3)` decorator for retry with exponential backoff
- [x] `refresh_session()`: re-authenticate using stored credentials when session expires
- [x] Properties for `auth_token`, `feed_token`, `smart_connect` that raise if not authenticated
- [x] Write tests in `tests/test_data/test_auth.py` (11 tests):
  - Verify successful auth stores all tokens
  - Verify TOTP generation and session call
  - Verify retry on failure (3 attempts)
  - Verify retry exhaustion raises
  - Verify API rejection raises
  - Verify re-auth flow works
  - Verify unauthenticated property access raises

**Requirement coverage:** Req 1.1 (authenticate on startup), Req 1.2 (retry 3x), Req 1.3 (store session), Req 1.4 (auto re-auth)

---

### 4.4 Implement `signalpilot/data/historical.py` with HistoricalDataFetcher

- [x] Implement `HistoricalDataFetcher` as specified in design (Section 4.1.3)
- [x] `fetch_previous_day_data()`:
  - Fetch previous close and previous high for all Nifty 500 via Angel One API
  - Batch requests with `asyncio.Semaphore` for rate limiting (~3 req/s)
- [x] `fetch_average_daily_volume(lookback_days=20)`:
  - Fetch 20-day ADV for each stock
- [x] `_fetch_from_angel_one()`: use `SmartConnect.getCandleData()`, validate candle structure
- [x] `_fetch_from_yfinance()`: use yfinance with `.NS` suffix as fallback, log warning (Req 4.2)
- [x] If both sources fail for an instrument, exclude it and log (Req 3.3, Req 4.3)
- [x] `build_historical_references()` logs warnings for partial data exclusions
- [x] Write tests in `tests/test_data/test_historical.py` (9 tests):
  - Mock Angel One API success — verify data is returned
  - Mock Angel One failure — verify fallback to yfinance
  - Mock both sources fail — verify instrument is excluded
  - Verify insufficient candles triggers fallback
  - Verify ADV calculation and fallback
  - Verify build_historical_references combines data
  - Verify API status=False triggers fallback

**Requirement coverage:** Req 3.1 (prev close/high), Req 3.2 (20-day ADV), Req 3.3 (exclude on failure), Req 4.1 (yfinance fallback), Req 4.2 (log warning), Req 4.3 (alert on both fail)

---

### 4.5 Implement `signalpilot/data/websocket_client.py` with WebSocketClient

- [x] Implement `WebSocketClient` as specified in design (Section 4.1.2)
- [x] `connect()`:
  - Create `SmartWebSocketV2` instance with auth_token and feed_token
  - Register callbacks: `_on_data`, `_on_close`, `_on_error`
  - Subscribe to all Nifty 500 tokens (single connection, up to 1000 tokens)
- [x] `_on_data()`:
  - Parse binary tick data from WebSocket
  - Bridge into asyncio loop via `loop.call_soon_threadsafe`
  - Update MarketDataStore with parsed tick
  - Use `logger.exception` with message payload for parse errors
- [x] `_on_close()`: trigger reconnection with exponential backoff delay (2s, 4s, 8s)
- [x] Reconnect counter reset only after successful subscription (prevents infinite loop)
- [x] `_on_error()`: log errors
- [x] `disconnect()`: gracefully close WebSocket with cleanup on error
- [x] Write tests in `tests/test_data/test_websocket_client.py` (16 tests):
  - Mock WebSocket, verify subscription call
  - Verify tick parsing updates MarketDataStore
  - Verify volume accumulation in _on_data flow
  - Verify malformed message handling
  - Verify reconnection attempts on close
  - Verify exponential backoff delay
  - Verify alert callback after retries exhausted
  - Verify disconnect cleanup and error handling

**Requirement coverage:** Req 2.1 (establish WebSocket), Req 2.2 (receive LTP/OHLCV), Req 2.3 (auto-reconnect), Req 2.4 (alert on failure), Req 2.5 (update store)

---

## Code Review Fixes Applied
- **C1 (Critical):** Made credentials private (`_mpin`, `_totp_secret`); added read-only `api_key`/`client_id` properties
- **H1 (High):** Changed tick parsing error handler to `logger.exception` with message payload
- **H2 (High):** Added candle structure validation (length check) before indexing
- **H3 (High):** Added `@with_retry(max_retries=3)` to `_fetch_instrument_master` with response type validation
- **H4 (High):** Added exponential backoff delay (`_reconnect_with_delay`) before WebSocket reconnection
- **H5 (High):** Moved reconnect counter reset after successful subscription
- **M1 (Medium):** Updated docstrings from "thread-safe" to "async-safe"
- **M3 (Medium):** Added logging for partial data exclusion in `build_historical_references`
