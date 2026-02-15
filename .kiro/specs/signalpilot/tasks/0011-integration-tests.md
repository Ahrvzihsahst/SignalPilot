# Task 11: Integration Tests

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 6-20, 22, 29, 35)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 9)

---

## Subtasks

### 11.1 Write full signal pipeline integration test

- [ ] Create `tests/test_integration/test_signal_pipeline.py`
- [ ] **Test: Valid gap-up stock produces correct FinalSignal**
  - Set up MarketDataStore with historical data (prev_close=100, prev_high=101, adv=1000000)
  - Feed tick data: open=104 (4% gap), volume=600000 (60% of ADV), current_price=104.50
  - Run through pipeline: GapAndGoStrategy -> SignalRanker -> RiskManager
  - Verify FinalSignal has: entry=104.50, SL=104 (opening price), T1=109.73, T2=111.82, quantity>0, star_rating=1-5
- [ ] **Test: Stock failing gap condition produces no signal**
  - Same setup but open=102 (2% gap, below 3% threshold)
  - Verify no CandidateSignal produced
- [ ] **Test: Stock failing volume condition produces no signal**
  - Gap=4% but 15-min volume=400000 (40% of ADV, below 50% threshold)
  - Verify no CandidateSignal produced
- [ ] **Test: Stock failing price-hold condition produces no signal**
  - Gap=4%, volume passes, but current_price drops below opening price
  - Verify candidate is disqualified

**Requirement coverage:** Req 6-11 (full signal generation flow)

---

### 11.2 Write signal expiry integration test

- [ ] Create `tests/test_integration/test_signal_expiry.py`
- [ ] **Test: Signal expires after 30 minutes**
  - Generate a signal with `created_at = now`
  - Simulate 30 minutes passing (mock datetime)
  - Call `_expire_stale_signals()`
  - Verify signal status in DB changed to "expired"
  - Verify expiry notification was sent via Telegram
- [ ] **Test: TAKEN after expiry returns error**
  - Generate a signal, let it expire
  - Simulate user sending "TAKEN"
  - Verify response: "Signal has expired and is no longer valid."

**Requirement coverage:** Req 15 (signal expiry), Req 15.4 (TAKEN after expiry)

---

### 11.3 Write TAKEN-to-exit flow integration test

- [ ] Create `tests/test_integration/test_trade_lifecycle.py`
- [ ] **Test: TAKEN -> SL hit -> trade closed**
  - Generate signal (entry=100, SL=97)
  - Simulate TAKEN command -> verify trade record created in DB
  - Feed price ticks: 100, 99, 98, 97 (SL hit)
  - Verify trade record updated: exit_price=97, pnl_amount=-45 (for qty=15), exit_reason="sl_hit"
  - Verify SL alert was sent
- [ ] **Test: TAKEN -> T1 hit (advisory) -> T2 hit (exit)**
  - Generate signal (entry=100, T1=105, T2=107)
  - Simulate TAKEN command
  - Feed price ticks: 100, 103, 105 (T1 hit)
  - Verify T1 advisory alert sent, trade still open
  - Feed price ticks: 106, 107 (T2 hit)
  - Verify trade closed with exit_reason="t2_hit", P&L calculated correctly

**Requirement coverage:** Req 22 (TAKEN), Req 17 (target alerts), Req 18 (SL alert), Req 29.3-29.4 (trade logging)

---

### 11.4 Write trailing SL progression integration test

- [ ] Create `tests/test_integration/test_trailing_sl.py`
- [ ] **Test: Full trailing SL lifecycle**
  - Generate signal (entry=100, SL=97), simulate TAKEN
  - Feed price ticks in sequence:
    1. Price=100 -> SL stays at 97 (no change)
    2. Price=102 (+2%) -> SL moves to 100 (breakeven), notification sent
    3. Price=103 -> SL stays at 100 (between +2% and +4%)
    4. Price=104 (+4%) -> trailing SL activated at 101.92 (104*0.98), notification sent
    5. Price=106 (+6%) -> trailing SL moves up to 103.88 (106*0.98)
    6. Price=103 (retrace) -> trailing SL stays at 103.88 (never moves down)
    7. Price=103.88 -> trailing SL hit, exit triggered
  - Verify each notification was sent at the correct step
  - Verify final exit: exit_reason="trailing_sl", exit_price=103.88

**Requirement coverage:** Req 19.1-19.4 (trailing SL full lifecycle)

---

### 11.5 Write position limit enforcement integration test

- [ ] Create `tests/test_integration/test_position_limits.py`
- [ ] **Test: 6th signal is suppressed at max positions**
  - Generate 5 signals, simulate TAKEN for all 5
  - Attempt to generate 6th signal via RiskManager
  - Verify 6th signal is suppressed (empty result from filter_and_size)
- [ ] **Test: Signal allowed after closing a position**
  - With 5 active trades, close one trade (SL hit)
  - Verify active_trade_count drops to 4
  - Generate new signal via RiskManager
  - Verify signal passes through (1 slot available)

**Requirement coverage:** Req 14.1-14.3 (max position enforcement)

---

### 11.6 Write time-based exit integration test

- [ ] Create `tests/test_integration/test_time_exits.py`
- [ ] **Test: 3:00 PM exit reminder**
  - Have 2 open trades: one in profit (entry=100, current=103), one in loss (entry=100, current=99)
  - Simulate 3:00 PM trigger
  - Verify advisory alerts sent for both trades with current P&L
  - Verify trades are NOT closed (advisory only)
- [ ] **Test: 3:15 PM mandatory exit**
  - Have 2 open trades still open
  - Simulate 3:15 PM trigger
  - Verify both trades are closed with exit_reason="time_exit"
  - Verify mandatory exit alerts sent with final P&L

**Requirement coverage:** Req 16.2-16.5 (time-based restrictions), Req 20.1-20.3 (time exits)

---

### 11.7 Write crash recovery integration test

- [ ] Create `tests/test_integration/test_crash_recovery.py`
- [ ] **Test: Recovery reloads state and resumes monitoring**
  - Pre-populate SQLite DB with:
    - 3 signals sent today
    - 2 active trades (exited_at IS NULL)
  - Start app in recovery mode (`app.recover()`)
  - Verify:
    - Re-authentication was called
    - WebSocket reconnected
    - 2 active trades are being monitored by ExitMonitor
    - Recovery alert sent: "System recovered from interruption. Monitoring resumed."

**Requirement coverage:** Req 35.2-35.4 (crash recovery)
