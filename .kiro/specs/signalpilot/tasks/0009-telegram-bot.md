# Task 9: Telegram Bot

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 21-27, 15.4)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 4.6)

---

## Subtasks

### 9.1 Implement `signalpilot/telegram/formatters.py` with message formatting functions

- [ ] `format_signal_message(signal: FinalSignal) -> str`:
  - Include all fields from the PRD signal format:
    - Signal direction (BUY)
    - Stock symbol/name
    - Entry price (formatted as INR)
    - Stop loss with risk % from entry
    - Target 1 with % from entry
    - Target 2 with % from entry
    - Quantity (number of shares)
    - Capital required (formatted as INR)
    - Signal strength (star rating display)
    - Strategy name
    - Reasoning text
    - Expiry time ("Valid Until: 30 mins from signal")
    - "Reply TAKEN to log this trade" instruction
  - Use visual separators and formatting for readability
- [ ] `star_rating(strength: int) -> str`:
  - Map 1-5 to filled/empty star display with label (Weak/Moderate/Good/Strong/Very Strong)
- [ ] `format_exit_alert(alert: ExitAlert) -> str`:
  - SL hit message: "Stop Loss hit on [STOCK] at [PRICE]. Exit immediately."
  - T1 hit message: "Target 1 hit! Consider booking partial profit."
  - T2 hit message: "Target 2 hit! Full exit recommended."
  - Trailing SL update: "Trailing SL updated to [PRICE]."
  - Include stock name, current price, P&L in all alerts
- [ ] `format_status_message(signals: list, trades: list, market_data: MarketDataStore) -> str`:
  - Active signals: symbol, entry, SL, targets
  - TAKEN trades: symbol, entry, current price, unrealized P&L (INR and %), current SL
  - Handle empty state: "No active signals or open trades."
- [ ] `format_journal_message(metrics: PerformanceMetrics) -> str`:
  - Period, signals sent, trades taken, win rate, total P&L, avg win, avg loss, risk-reward ratio, best trade, worst trade
  - Handle empty state: "No trades logged yet. Reply TAKEN to a signal to start tracking."
- [ ] `format_daily_summary(summary: DailySummary) -> str`:
  - Date, signals generated, signals taken, wins/losses, total P&L, cumulative P&L
  - Per-trade details with outcomes
  - Handle no-signals state: "No signals generated today."
- [ ] Write tests in `tests/test_telegram/test_formatters.py`:
  - Verify signal message contains all required fields
  - Verify star ratings for 1-5 display correctly
  - Verify exit alert messages for each exit type
  - Verify status message with data and empty state
  - Verify journal message with data and empty state
  - Verify daily summary with data and empty state

**Requirement coverage:** Req 21.1-21.3 (signal format), Req 23.2-23.4 (STATUS format), Req 24.1 (JOURNAL format), Req 31.2 (daily summary format)

---

### 9.2 Implement `signalpilot/telegram/handlers.py` with command handler logic

- [ ] `handle_taken(signal_repo, trade_repo, exit_monitor, update)`:
  - Find latest active (non-expired) signal via `signal_repo.get_latest_active_signal()`
  - If no active signal: respond "No active signal to log." (Req 22.4)
  - If signal expired: respond "Signal has expired and is no longer valid." (Req 15.4)
  - Create TradeRecord from signal data
  - Insert into trade_repo
  - Update signal status to "taken"
  - Start exit monitoring via `exit_monitor.start_monitoring(trade)`
  - Respond: "Trade logged. Tracking [STOCK]." (Req 22.2)
- [ ] `handle_status(signal_repo, trade_repo, market_data, update)`:
  - Query active signals for today
  - Query open trades (exited_at IS NULL)
  - For each open trade, get current price from market_data
  - Calculate live P&L for each
  - Format and respond with status message (Req 23.1-23.4)
- [ ] `handle_journal(metrics_calculator, update)`:
  - Calculate performance metrics
  - If no trades: respond with "No trades logged yet." (Req 24.3)
  - Otherwise respond with formatted journal (Req 24.1)
- [ ] `handle_capital(config_repo, update, text)`:
  - Parse amount from message text (e.g., "CAPITAL 50000" -> 50000)
  - If invalid or missing amount: respond with usage instructions (Req 25.4)
  - Update capital in config_repo
  - Respond: "Capital updated to [amount]. Per-trade allocation is now [amount/5]." (Req 25.2)
- [ ] `handle_help(update)`:
  - Respond with formatted list of commands and descriptions (Req 26.1)
- [ ] Write tests in `tests/test_telegram/test_handlers.py` with mocked repos and update context:
  - TAKEN with active signal -> trade created, confirmation sent
  - TAKEN with no signal -> error message
  - TAKEN with expired signal -> expiry message
  - STATUS with open trades -> formatted list
  - STATUS with no trades -> empty message
  - JOURNAL with trades -> metrics displayed
  - JOURNAL with no trades -> empty message
  - CAPITAL 50000 -> updated and confirmed
  - CAPITAL (no amount) -> usage message
  - HELP -> command list

**Requirement coverage:** Req 22 (TAKEN), Req 23 (STATUS), Req 24 (JOURNAL), Req 25 (CAPITAL), Req 26 (HELP), Req 15.4 (expired signal)

---

### 9.3 Implement `signalpilot/telegram/bot.py` with SignalPilotBot

- [ ] Implement `SignalPilotBot` class as specified in design (Section 4.6.1)
- [ ] `__init__(bot_token, chat_id, dependencies)`:
  - Store bot token, chat_id
  - Store references to repos, market_data, exit_monitor, metrics_calculator
- [ ] `start()`:
  - Build `Application` with `ApplicationBuilder().token(bot_token).build()`
  - Register message handlers with regex filters:
    - `r"(?i)^taken$"` -> handle_taken
    - `r"(?i)^status$"` -> handle_status
    - `r"(?i)^journal$"` -> handle_journal
    - `r"(?i)^capital\s+\d+"` -> handle_capital
    - `r"(?i)^help$"` -> handle_help
  - Initialize and start polling (Telegram polling mode, no webhook needed)
- [ ] `stop()`: gracefully stop updater, application, and shutdown
- [ ] `send_signal(signal: FinalSignal)`:
  - Format using `format_signal_message()`
  - Send to configured chat_id with HTML parse mode
  - Track delivery latency: `latency = time.time() - signal.generated_at.timestamp()`
  - If latency > 30 seconds, log warning (Req 21.4)
- [ ] `send_alert(text: str)`: send plain text alert to chat_id
- [ ] `send_exit_alert(alert: ExitAlert)`:
  - Format using `format_exit_alert()`
  - Send to chat_id
- [ ] Write tests in `tests/test_telegram/test_bot.py` with mocked Application:
  - Verify all 5 handlers are registered
  - Verify `send_signal` calls bot.send_message with correct chat_id and formatted text
  - Verify `send_alert` sends plain text
  - Verify latency warning logged when > 30s

**Requirement coverage:** Req 21 (signal delivery), Req 22-26 (command handling), Req 27 (scheduled alerts via send_alert)
