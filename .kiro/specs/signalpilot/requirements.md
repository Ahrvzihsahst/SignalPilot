# Requirements Document

## Introduction

SignalPilot is a rule-based intraday signal generation tool for Indian equity markets (NSE). It scans Nifty 500 stocks during market hours, identifies high-probability Gap & Go trade setups, and delivers actionable buy signals via Telegram with entry price, stop loss, targets, and quantity. The tool is designed for beginner retail traders with small capital (INR 10K-1L) who execute trades manually on their broker platform. SignalPilot never places orders — it only generates and delivers signals.

This requirements document covers the Phase 1 MVP scope: Gap & Go strategy, real-time data ingestion, signal ranking, risk management, exit logic, Telegram delivery, trade journaling, and application lifecycle management.

---

## Requirements

### Requirement 1: Angel One SmartAPI Authentication

**User Story:** As a trader, I want the system to authenticate with Angel One SmartAPI on startup, so that it can access real-time and historical market data for signal generation.

#### Acceptance Criteria

1. WHEN the application starts THEN the system SHALL authenticate with Angel One SmartAPI using stored credentials (API key, client ID, password, TOTP secret).
2. IF authentication fails THEN the system SHALL retry up to 3 times with exponential backoff before reporting a failure via Telegram.
3. WHEN authentication succeeds THEN the system SHALL store the session token for subsequent API calls.
4. IF the session token expires during market hours THEN the system SHALL automatically re-authenticate without manual intervention.

---

### Requirement 2: Real-Time Market Data via WebSocket

**User Story:** As a trader, I want the system to receive real-time price and volume data for all Nifty 500 stocks, so that it can detect trading opportunities as they happen.

#### Acceptance Criteria

1. WHEN authentication succeeds THEN the system SHALL establish a WebSocket connection to Angel One SmartAPI and subscribe to tick data for all Nifty 500 instruments.
2. WHEN the WebSocket connection is established THEN the system SHALL receive real-time LTP (Last Traded Price), open price, high, low, close, and volume for each subscribed instrument.
3. IF the WebSocket connection drops THEN the system SHALL automatically reconnect within 10 seconds and resubscribe to all instruments.
4. IF the WebSocket connection fails to reconnect after 3 attempts THEN the system SHALL send an alert via Telegram notifying the user of data feed disruption.
5. WHEN tick data is received THEN the system SHALL update the in-memory data store for the corresponding instrument within 1 second.

---

### Requirement 3: Historical Data for Gap Detection

**User Story:** As a trader, I want the system to fetch previous day's OHLCV data for Nifty 500 stocks, so that it can calculate gap percentages and average daily volume for signal generation.

#### Acceptance Criteria

1. WHEN the application starts before market open THEN the system SHALL fetch previous trading day's close price and high price for all Nifty 500 instruments via Angel One SmartAPI.
2. WHEN the application starts THEN the system SHALL fetch average daily volume (ADV) data for at least the last 20 trading sessions for each Nifty 500 instrument.
3. IF historical data fetch fails for a specific instrument THEN the system SHALL exclude that instrument from scanning and log the failure.
4. WHEN historical data is successfully fetched THEN the system SHALL store it in memory for use by the strategy engine during the trading session.

---

### Requirement 4: yfinance Fallback for Data

**User Story:** As a trader, I want the system to fall back to yfinance for historical data if Angel One API is unavailable, so that gap detection can still function with slightly delayed data.

#### Acceptance Criteria

1. IF Angel One SmartAPI historical data request fails after retries THEN the system SHALL attempt to fetch the same data from yfinance as a fallback.
2. WHEN yfinance fallback is used THEN the system SHALL log a warning indicating that data may be delayed.
3. IF both Angel One SmartAPI and yfinance fail THEN the system SHALL send a Telegram alert to the user and skip signal generation for the affected instruments.

---

### Requirement 5: Nifty 500 Instrument List Management

**User Story:** As a trader, I want the system to maintain an up-to-date list of Nifty 500 instruments, so that scanning is limited to liquid, well-traded stocks.

#### Acceptance Criteria

1. WHEN the application starts THEN the system SHALL load the Nifty 500 instrument list with their Angel One instrument tokens.
2. WHEN the instrument list is loaded THEN the system SHALL use only these instruments for WebSocket subscription and strategy scanning.
3. IF an instrument from the Nifty 500 list is not found in Angel One's instrument master THEN the system SHALL log a warning and exclude it from scanning.

---

### Requirement 6: Gap Detection

**User Story:** As a trader, I want the system to detect stocks that gap up 3-5% at market open, so that I can capitalize on momentum-driven intraday moves.

#### Acceptance Criteria

1. WHEN market opens at 9:15 AM THEN the system SHALL calculate the gap percentage for each Nifty 500 stock as: ((Open Price - Previous Close) / Previous Close) * 100.
2. WHEN a stock's gap percentage is between 3% and 5% (inclusive) THEN the system SHALL flag it as a gap candidate.
3. IF a stock's gap percentage is below 3% or above 5% THEN the system SHALL exclude it from Gap & Go signal generation.
4. WHEN a stock gaps up THEN the system SHALL verify that the opening price is above the previous day's high price; IF it is not above the previous day's high THEN the system SHALL exclude it from Gap & Go candidates.

---

### Requirement 7: Volume Condition Validation

**User Story:** As a trader, I want the system to confirm that a gapping stock has strong volume conviction in the first 15 minutes, so that I avoid false breakouts with weak participation.

#### Acceptance Criteria

1. WHEN the first 15 minutes of trading have elapsed (by 9:30 AM) THEN the system SHALL calculate the cumulative volume for each gap candidate during the 9:15-9:30 AM window.
2. WHEN the 15-minute volume for a gap candidate exceeds 50% of its 20-day average daily volume THEN the system SHALL mark the volume condition as met for that candidate.
3. IF the 15-minute volume for a gap candidate does not exceed 50% of ADV THEN the system SHALL exclude it from signal generation.

---

### Requirement 8: Entry Timing and Price Hold Validation

**User Story:** As a trader, I want signals to be generated only between 9:30-9:45 AM and only if the stock holds above its opening price, so that I enter after initial volatility settles and momentum is confirmed.

#### Acceptance Criteria

1. WHEN a gap candidate passes both gap percentage and volume conditions THEN the system SHALL monitor it between 9:30 AM and 9:45 AM for entry validation.
2. WHEN a qualifying candidate's current price is above its opening price during the 9:30-9:45 AM window THEN the system SHALL generate a BUY signal.
3. IF a qualifying candidate's price falls below its opening price at any point during the 9:30-9:45 AM window THEN the system SHALL disqualify it from signal generation.
4. IF it is after 9:45 AM and a Gap & Go candidate has not yet triggered THEN the system SHALL not generate a Gap & Go signal for that candidate.

---

### Requirement 9: Stop Loss and Target Calculation

**User Story:** As a trader, I want each signal to include a calculated stop loss and two target levels, so that I know my exact risk and reward before entering a trade.

#### Acceptance Criteria

1. WHEN a BUY signal is generated THEN the system SHALL set the stop loss at the stock's opening price (resulting in approximately 2-3% below entry price).
2. WHEN a BUY signal is generated THEN the system SHALL calculate Target 1 as entry price + 5%.
3. WHEN a BUY signal is generated THEN the system SHALL calculate Target 2 as entry price + 7%.
4. IF the calculated stop loss results in a risk greater than 3% from entry THEN the system SHALL adjust the stop loss to cap the risk at 3%.

---

### Requirement 10: Multi-Factor Signal Scoring

**User Story:** As a trader, I want signals to be scored and ranked by strength, so that I can focus on the highest-probability setups when multiple stocks qualify.

#### Acceptance Criteria

1. WHEN multiple stocks qualify for signal generation THEN the system SHALL calculate a composite score for each signal based on: gap percentage (weight: configurable), volume ratio relative to ADV (weight: configurable), and distance of current price from opening price as a percentage (weight: configurable).
2. WHEN composite scores are calculated THEN the system SHALL rank all qualifying signals in descending order of score.
3. WHEN signals are ranked THEN the system SHALL assign a signal strength rating from 1 to 5 stars based on the composite score distribution.

---

### Requirement 11: Top 5 Signal Selection

**User Story:** As a trader, I want to receive only the top 5 strongest signals, so that I am not overwhelmed and can focus my limited capital on the best setups.

#### Acceptance Criteria

1. WHEN signals are ranked THEN the system SHALL select only the top 5 signals for delivery to the user.
2. IF fewer than 5 stocks qualify THEN the system SHALL send all qualifying signals.
3. WHEN a signal is not in the top 5 THEN the system SHALL suppress it and not deliver it to Telegram.

---

### Requirement 12: Auto-Skip Expensive Stocks

**User Story:** As a trader, I want the system to automatically skip stocks whose price exceeds my per-trade allocation, so that I don't receive signals I can't act on with my capital.

#### Acceptance Criteria

1. WHEN a signal is generated THEN the system SHALL check if the stock's entry price exceeds the user's per-trade capital allocation (total capital / max positions).
2. IF the stock's entry price exceeds the per-trade allocation THEN the system SHALL suppress the signal and not deliver it to the user.
3. WHEN a stock is skipped due to price THEN the system SHALL log the skip reason for debugging purposes.

---

### Requirement 13: Position Sizing

**User Story:** As a trader, I want the system to auto-calculate the number of shares to buy for each signal based on my capital, so that I deploy capital evenly and manage risk properly.

#### Acceptance Criteria

1. WHEN a signal is generated THEN the system SHALL calculate per-trade capital as: total capital / max open positions (default 5).
2. WHEN per-trade capital is calculated THEN the system SHALL calculate quantity as: floor(per-trade capital / entry price).
3. WHEN a signal is delivered THEN it SHALL include the calculated quantity and the total capital required (quantity * entry price).
4. IF the calculated quantity is zero (stock price exceeds per-trade capital) THEN the system SHALL suppress the signal.

---

### Requirement 14: Maximum Position Limits

**User Story:** As a trader, I want the system to enforce a maximum of 5 open positions at any time, so that my capital is not over-concentrated or over-leveraged.

#### Acceptance Criteria

1. WHEN the user has 5 active trades (marked as TAKEN) THEN the system SHALL not send new signals until an existing position is closed.
2. WHEN a position is closed (via SL hit, target hit, or time exit) THEN the system SHALL decrement the active position count and allow new signals if below the limit.
3. WHEN the position limit is reached THEN the system SHALL log the suppression and optionally inform the user that the maximum position limit is active.

---

### Requirement 15: Signal Expiry

**User Story:** As a trader, I want signals to expire automatically after 30 minutes, so that I don't act on stale signals where the setup may no longer be valid.

#### Acceptance Criteria

1. WHEN a signal is generated THEN the system SHALL set an expiry timestamp 30 minutes from the generation time.
2. WHEN a signal's expiry time is reached and the user has not replied TAKEN THEN the system SHALL mark the signal as expired in the database.
3. WHEN a signal expires THEN the system SHALL send a Telegram notification: the signal for [STOCK] has expired.
4. IF a user replies TAKEN after a signal has expired THEN the system SHALL inform the user that the signal is no longer valid.

---

### Requirement 16: Trading Time Restrictions

**User Story:** As a trader, I want no new signals after 2:30 PM and mandatory exit reminders by 3:15 PM, so that I don't get stuck in positions too close to market close.

#### Acceptance Criteria

1. WHEN the time is 2:30 PM THEN the system SHALL stop generating new signals and send a Telegram message: "No new signals. Monitoring existing positions only."
2. WHEN the time is 3:00 PM THEN the system SHALL send a Telegram alert: "Market closing in 15 mins. Exit all open intraday positions."
3. IF the time is between 2:30 PM and 3:15 PM AND a position is in profit but hasn't hit target THEN the system SHALL recommend exiting.
4. IF the time is between 2:30 PM and 3:15 PM AND a position is in minor loss (less than SL) THEN the system SHALL recommend exiting to avoid overnight risk.
5. WHEN the time is 3:15 PM THEN the system SHALL send a mandatory exit alert for any positions still marked as open.

---

### Requirement 17: Target Hit Alerts

**User Story:** As a trader, I want to be alerted in real-time when my trade hits Target 1 or Target 2, so that I can book profits at the right levels.

#### Acceptance Criteria

1. WHEN a TAKEN trade's current price reaches or exceeds Target 1 (entry + 5%) THEN the system SHALL send a Telegram alert: "Target 1 hit! Consider booking partial profit."
2. WHEN a TAKEN trade's current price reaches or exceeds Target 2 (entry + 7%) THEN the system SHALL send a Telegram alert: "Target 2 hit! Full exit recommended."
3. WHEN a target alert is sent THEN the system SHALL include the stock name, current price, and P&L percentage in the message.

---

### Requirement 18: Stop Loss Hit Alerts

**User Story:** As a trader, I want to be alerted immediately when a stock hits my stop loss, so that I can exit the trade and limit my loss.

#### Acceptance Criteria

1. WHEN a TAKEN trade's current price falls to or below the stop loss price THEN the system SHALL send a Telegram alert: "Stop Loss hit on [STOCK] at [PRICE]. Exit immediately."
2. WHEN a stop loss alert is sent THEN the system SHALL log the trade outcome as SL hit in the database with the exit price and P&L.
3. WHEN a stop loss is hit THEN the system SHALL send the alert within 30 seconds of detection.

---

### Requirement 19: Trailing Stop Loss

**User Story:** As a trader, I want the system to tighten my stop loss as the trade moves in my favor, so that I can lock in profits while giving the trade room to run.

#### Acceptance Criteria

1. WHEN a TAKEN trade's current price moves 2% or more above the entry price THEN the system SHALL update the trailing stop loss to the entry price (breakeven) and notify the user via Telegram.
2. WHEN a TAKEN trade's current price moves 4% or more above the entry price THEN the system SHALL set a trailing stop at 2% below the current price and notify the user via Telegram.
3. WHEN the trailing stop is active at the 4%+ level THEN the system SHALL continuously update the trailing stop as the price moves higher (trail at current price - 2%), but SHALL NOT lower the trailing stop if the price retraces.
4. IF the price hits the trailing stop loss THEN the system SHALL send an alert and log the exit as a trailing SL hit.

---

### Requirement 20: Time-Based Exit

**User Story:** As a trader, I want a reminder at 3:00 PM to close all open positions, so that I don't accidentally hold intraday trades overnight.

#### Acceptance Criteria

1. WHEN the time is 3:00 PM THEN the system SHALL send a Telegram alert listing all TAKEN trades that are still open, with their current P&L.
2. FOR EACH open trade at 3:00 PM the system SHALL recommend "Exit" with the current price and unrealized P&L.
3. WHEN the time is 3:15 PM THEN the system SHALL mark all remaining open trades as requiring mandatory exit and send a final alert.

---

### Requirement 21: Signal Formatting and Delivery via Telegram

**User Story:** As a trader, I want signals delivered to my Telegram in a clear, actionable format, so that I can quickly understand and act on them without any confusion.

#### Acceptance Criteria

1. WHEN a signal is generated and passes all filters THEN the system SHALL send a Telegram message containing: signal direction (BUY), stock name, entry price, stop loss with risk percentage, Target 1 with percentage, Target 2 with percentage, quantity, capital required, signal strength rating (1-5 stars), strategy name, reasoning text, and expiry time.
2. WHEN a signal is sent THEN the system SHALL format it using the predefined template with clear labels and visual separators.
3. WHEN a signal is sent THEN it SHALL include the instruction "Reply TAKEN to log this trade."
4. WHEN the signal delivery latency exceeds 30 seconds from condition trigger THEN the system SHALL log a performance warning.

---

### Requirement 22: TAKEN Command

**User Story:** As a trader, I want to reply TAKEN to a signal to log that I've entered the trade, so that the system can track my position and send me exit alerts.

#### Acceptance Criteria

1. WHEN the user sends "TAKEN" in response to an active (non-expired) signal THEN the system SHALL log the trade as taken in the trades table with the signal's entry price, stop loss, targets, and quantity.
2. WHEN a trade is logged as TAKEN THEN the system SHALL respond with a confirmation: "Trade logged. Tracking [STOCK]."
3. WHEN a trade is logged as TAKEN THEN the system SHALL begin monitoring the stock for SL hit, target hit, and trailing SL conditions.
4. IF the user sends "TAKEN" when no active signal exists THEN the system SHALL respond with a helpful message indicating no active signal to log.

---

### Requirement 23: STATUS Command

**User Story:** As a trader, I want to check the status of all my active signals and trades, so that I can see my current positions and their live P&L at a glance.

#### Acceptance Criteria

1. WHEN the user sends "STATUS" THEN the system SHALL respond with a list of all active (non-expired) signals sent today and all TAKEN trades that are still open.
2. FOR EACH active signal in the STATUS response the system SHALL show: stock name, entry price, current price, current P&L percentage, stop loss, and targets.
3. FOR EACH TAKEN trade in the STATUS response the system SHALL show: stock name, entry price, current price, unrealized P&L in rupees and percentage, and current stop loss (including any trailing SL updates).
4. IF there are no active signals or open trades THEN the system SHALL respond with "No active signals or open trades."

---

### Requirement 24: JOURNAL Command

**User Story:** As a trader, I want to view my trading performance summary, so that I can track my progress and evaluate whether the system is working for me.

#### Acceptance Criteria

1. WHEN the user sends "JOURNAL" THEN the system SHALL respond with a performance summary including: date range, total signals sent, trades taken, win rate (wins / total), total P&L in rupees, average win amount, average loss amount, risk-reward ratio, best trade, and worst trade.
2. WHEN the JOURNAL summary is generated THEN the system SHALL calculate metrics from all trades logged in the trades table.
3. IF no trades have been logged yet THEN the system SHALL respond with "No trades logged yet. Reply TAKEN to a signal to start tracking."

---

### Requirement 25: CAPITAL Command

**User Story:** As a trader, I want to update my trading capital at any time, so that position sizing adjusts to reflect my current account balance.

#### Acceptance Criteria

1. WHEN the user sends "CAPITAL [amount]" (e.g., "CAPITAL 50000") THEN the system SHALL update the user's total capital in the user_config table.
2. WHEN capital is updated THEN the system SHALL respond with confirmation: "Capital updated to [amount]. Per-trade allocation is now [amount/5]."
3. WHEN capital is updated THEN all subsequent signals SHALL use the new capital for position sizing calculations.
4. IF the user sends "CAPITAL" without an amount or with an invalid value THEN the system SHALL respond with usage instructions: "Usage: CAPITAL [amount]. Example: CAPITAL 50000."

---

### Requirement 26: HELP Command

**User Story:** As a trader, I want a list of all available commands, so that I know how to interact with the bot.

#### Acceptance Criteria

1. WHEN the user sends "HELP" THEN the system SHALL respond with a formatted list of all available commands: TAKEN, STATUS, JOURNAL, CAPITAL, and HELP, each with a brief description.

---

### Requirement 27: Scheduled Telegram Alerts

**User Story:** As a trader, I want automated alerts at key times during the trading day, so that I stay informed about the system's status and don't miss important actions.

#### Acceptance Criteria

1. WHEN the time is 9:00 AM on a trading day THEN the system SHALL send a pre-market alert: "Pre-market scan running. Signals coming shortly."
2. WHEN the time is 2:30 PM THEN the system SHALL send: "No new signals. Monitoring existing positions only."
3. WHEN the time is 3:00 PM THEN the system SHALL send: "Close all intraday positions in the next 15 minutes."
4. WHEN the time is 3:30 PM THEN the system SHALL send a daily summary including: total signals sent today, trades taken, trades won/lost, total P&L, and a list of each trade with its outcome.

---

### Requirement 28: SQLite Database Schema

**User Story:** As a developer, I want a well-structured SQLite database to persist signals, trades, and user configuration, so that all data is reliably stored for journaling and analytics.

#### Acceptance Criteria

1. WHEN the application starts for the first time THEN the system SHALL create a SQLite database with three tables: signals, trades, and user_config.
2. WHEN the signals table is created THEN it SHALL contain columns: id (primary key), date, symbol, strategy, entry_price, stop_loss, target_1, target_2, quantity, capital_required, signal_strength, gap_pct, volume_ratio, reason, created_at, expires_at, and status (sent/expired).
3. WHEN the trades table is created THEN it SHALL contain columns: id (primary key), signal_id (foreign key to signals), date, symbol, entry_price, exit_price, stop_loss, quantity, pnl_amount, pnl_pct, exit_reason (sl_hit/t1_hit/t2_hit/trailing_sl/time_exit), taken_at, and exited_at.
4. WHEN the user_config table is created THEN it SHALL contain columns: id (primary key), telegram_chat_id, total_capital, max_positions, created_at, and updated_at.

---

### Requirement 29: Signal and Trade Logging

**User Story:** As a trader, I want every signal generated and every trade taken to be persisted, so that I have a complete audit trail of the system's recommendations and my actions.

#### Acceptance Criteria

1. WHEN a signal is generated THEN the system SHALL insert a record into the signals table with all signal details and status set to "sent."
2. WHEN a signal expires THEN the system SHALL update the signal's status to "expired" in the signals table.
3. WHEN a user replies TAKEN THEN the system SHALL insert a record into the trades table linked to the corresponding signal via signal_id.
4. WHEN a trade exits (via SL, target, trailing SL, or time) THEN the system SHALL update the trades record with exit_price, pnl_amount, pnl_pct, exit_reason, and exited_at.

---

### Requirement 30: Performance Metrics Calculation

**User Story:** As a trader, I want the system to calculate and present performance metrics from my trade history, so that I can evaluate the strategy's effectiveness over time.

#### Acceptance Criteria

1. WHEN the JOURNAL command is invoked THEN the system SHALL query the trades table and calculate: win rate, total P&L, average win, average loss, risk-reward ratio, best trade, and worst trade.
2. WHEN a daily summary is generated at 3:30 PM THEN the system SHALL calculate the day's metrics from trades with today's date.
3. WHEN performance metrics are calculated THEN a "win" SHALL be defined as a trade where pnl_amount > 0 and a "loss" as pnl_amount <= 0.

---

### Requirement 31: Daily Summary Generation

**User Story:** As a trader, I want an end-of-day summary of all signals and trades, so that I can review the day's activity in one place.

#### Acceptance Criteria

1. WHEN the time is 3:30 PM THEN the system SHALL generate a daily summary from the database containing: total signals generated, total signals taken, outcomes of each trade (SL hit, T1, T2, time exit), total day P&L, and cumulative P&L.
2. WHEN the daily summary is generated THEN the system SHALL send it to Telegram in a formatted template.
3. IF no signals were generated today THEN the daily summary SHALL state "No signals generated today" with a note about market conditions.

---

### Requirement 32: Application Auto-Start

**User Story:** As a trader, I want the application to start automatically before market open, so that I don't need to remember to launch it manually every trading day.

#### Acceptance Criteria

1. WHEN the system clock reaches 8:50 AM on a weekday THEN the application SHALL start automatically via the configured scheduler (APScheduler or OS-level task scheduler).
2. WHEN the application auto-starts THEN it SHALL execute the full startup sequence: authenticate with Angel One, load instrument list, fetch historical data, and establish WebSocket connection.
3. IF the application fails to start at 8:50 AM THEN the scheduler SHALL retry at 8:55 AM and 9:00 AM before giving up.

---

### Requirement 33: Continuous Market Scanning

**User Story:** As a trader, I want the system to scan continuously from market open to close, so that the architecture supports Phase 1 signals and is ready for future intraday strategies without redesign.

#### Acceptance Criteria

1. WHEN the WebSocket connection is established THEN the system SHALL continuously process incoming tick data from 9:15 AM to 3:30 PM.
2. WHEN the system is in the 9:15-9:30 AM window THEN it SHALL accumulate volume data for gap candidates.
3. WHEN the system is in the 9:30-9:45 AM window THEN it SHALL evaluate Gap & Go entry conditions and generate signals.
4. WHEN the system is in the 9:45 AM-2:30 PM window THEN it SHALL continue monitoring TAKEN trades for exit conditions (SL, targets, trailing SL) while the scanning loop remains active for future strategy integration.
5. WHEN the system is in the 2:30-3:30 PM window THEN it SHALL only monitor existing positions for exit conditions and not generate new signals.

---

### Requirement 34: Application Auto-Shutdown

**User Story:** As a trader, I want the application to shut down gracefully after market close, so that it doesn't consume resources unnecessarily overnight.

#### Acceptance Criteria

1. WHEN the time is 3:35 PM THEN the system SHALL initiate a graceful shutdown sequence.
2. WHEN shutdown is initiated THEN the system SHALL: disconnect the WebSocket connection, save any pending journal data to SQLite, and send the daily summary if not already sent.
3. WHEN all shutdown steps are complete THEN the system SHALL terminate the process cleanly.

---

### Requirement 35: Crash Recovery

**User Story:** As a trader, I want the system to recover from unexpected crashes during market hours, so that I don't miss signals or exit alerts due to a transient failure.

#### Acceptance Criteria

1. IF the application process terminates unexpectedly during market hours (9:15 AM - 3:30 PM) THEN the OS-level scheduler or watchdog process SHALL restart it within 2 minutes.
2. WHEN the application restarts after a crash THEN it SHALL re-authenticate, re-establish the WebSocket connection, and reload today's signals and active trades from the SQLite database.
3. WHEN the application recovers THEN it SHALL resume monitoring all TAKEN trades that have not been exited.
4. WHEN the application recovers THEN it SHALL send a Telegram alert: "System recovered from interruption. Monitoring resumed."
5. IF the application crashes more than 3 times in a single trading session THEN it SHALL send a Telegram alert and not attempt further restarts.
