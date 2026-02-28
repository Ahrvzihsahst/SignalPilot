# SignalPilot — Explained Like a Story

> If the technical docs felt like reading a circuit diagram, this guide reads like a book.
> We follow one stock — **Reliance Industries** — through an entire trading day
> to show you exactly what SignalPilot does, why, and how every piece fits together.

---

## Chapter 1: What Is SignalPilot?

Imagine you hire a full-time assistant whose only job is to watch 500 stocks on the
Indian stock market (NSE) every single second between 9:15 AM and 3:30 PM, and send
you a Telegram message the moment something interesting happens — complete with
exactly what price to buy at, where to place your stop-loss, and where to take profit.

That assistant is SignalPilot.

It is **not** an auto-trading bot. It does **not** place orders for you. Think of it as
a very disciplined, very fast research analyst that never blinks, never gets distracted,
and never lets emotions cloud its judgment. You still make the final call.

**In one sentence:** SignalPilot scans all Nifty 500 stocks in real-time, identifies
high-probability intraday setups, scores and ranks them, and delivers actionable
signals to your phone via Telegram — all within seconds.

---

## Chapter 2: The Three Strategies (What It Looks For)

SignalPilot uses three battle-tested intraday strategies. Each one looks for a
different kind of price pattern. Let's understand them with our Reliance example.

### Strategy 1: Gap & Go (The Morning Rocket)

**The idea:** When a stock opens significantly higher than yesterday's close,
it often means big institutions bought it overnight. If the stock *holds* above
its opening price with strong volume, it tends to keep running upward.

**Real example with Reliance:**

```
Yesterday's close:  Rs 2,800
Today's open:       Rs 2,884  (a 3% gap up!)
Yesterday's high:   Rs 2,850

SignalPilot checks:
  1. Is the gap between 3% and 5%?     --> 3% gap, YES
  2. Did it open ABOVE yesterday's high? --> 2,884 > 2,850, YES
  3. Is volume strong?                   --> 55% of 20-day average already, YES
  4. (At 9:30) Is the price still
     above the opening price?            --> LTP is 2,890, YES

  SIGNAL GENERATED!
    Entry:     Rs 2,890
    Stop-Loss: Rs 2,884  (the opening price — if it falls below, the thesis is dead)
    Target 1:  Rs 3,035  (+5%)
    Target 2:  Rs 3,092  (+7%)
```

**When it runs:** 9:15 AM - 9:45 AM (first 30 minutes only)

**Why this window?** Gaps are a morning phenomenon. By 9:45, the initial momentum
is either confirmed or dead.

---

### Strategy 2: ORB — Opening Range Breakout (The Prison Break)

**The idea:** During the first 30 minutes (9:15-9:45), stocks trade in a range as
buyers and sellers fight. Once this "prison" range is established, a stock that
breaks above it with strong volume often makes a powerful move.

**Real example with Reliance:**

```
9:15 - 9:45 (Opening Range forms):
  Highest price in 30 min:  Rs 2,860  (range high)
  Lowest price in 30 min:   Rs 2,830  (range low)
  Range size:               1.05%  (within the 0.5%-3% sweet spot)

At 10:12 AM:
  Current price: Rs 2,862  (broke ABOVE range high!)
  Current candle volume: 1.8x the average  (volume surge confirms it!)

SignalPilot checks:
  1. Is the range locked?               --> YES (locked at 9:45)
  2. Is range size between 0.5% and 3%? --> 1.05%, YES
  3. Price above range high?            --> 2,862 > 2,860, YES
  4. Volume above 1.5x average?         --> 1.8x, YES
  5. Is it before 11:00 AM?             --> 10:12, YES
  6. Is this a gap stock?               --> NO (wasn't caught by Gap & Go)

  SIGNAL GENERATED!
    Entry:     Rs 2,862
    Stop-Loss: Rs 2,830  (the range low — below this, the breakout failed)
    Target 1:  Rs 2,905  (+1.5%)
    Target 2:  Rs 2,934  (+2.5%)
```

**When it runs:** 9:45 AM - 11:00 AM

**Why this window?** Breakouts after 11 AM are less reliable; the morning energy
has faded.

---

### Strategy 3: VWAP Reversal (The Rubber Band)

**The idea:** VWAP (Volume Weighted Average Price) acts like a magnet. When a stock
in an uptrend pulls back to touch this magnet and bounces, it's like a rubber band
snapping back — a high-probability buying opportunity.

VWAP Reversal has two setups:

**Setup A — Uptrend Pullback (the rubber band snap):**

```
Reliance has been trading above VWAP all morning (uptrend).

At 11:30 AM:
  VWAP:                   Rs 2,855
  Current candle low:     Rs 2,856  (touched VWAP within 0.3%!)
  Current candle close:   Rs 2,868  (bounced back above!)
  Volume on bounce:       1.2x average  (buyers stepped in)

  SIGNAL GENERATED!
    Entry:     Rs 2,868
    Stop-Loss: Rs 2,841  (0.5% below VWAP — if it breaks VWAP, thesis is dead)
    Target 1:  Rs 2,897  (+1.0%)
    Target 2:  Rs 2,911  (+1.5%)
```

**Setup B — VWAP Reclaim (the comeback):**

```
Reliance dipped below VWAP for a while, but just reclaimed above it
with high volume. Like a swimmer who went underwater and burst back to the surface.

  SIGNAL GENERATED with wider targets (+1.5%, +2.0%)
```

**When it runs:** 10:00 AM - 2:30 PM

**Rate limit:** Maximum 2 signals per stock per day, with at least 60 minutes
between them (to avoid over-trading one stock).

---

## Chapter 3: A Day in the Life of SignalPilot

Let's walk through an entire trading day, hour by hour.

### 8:30 AM — The News Desk

Before the market even opens, SignalPilot's intelligence layer gets to work. It
fetches the latest financial news headlines from RSS feeds for all 500 stocks and
runs them through VADER sentiment analysis — a natural language processing engine
tuned with a financial lexicon. Each headline gets a sentiment score, and the
results are cached so the pipeline can use them instantly when signals are
generated later.

It also checks the earnings calendar. Any stock reporting earnings today gets
flagged for automatic blackout — no signals will be generated for that stock,
no matter how good the setup looks. Earnings days are simply too unpredictable.

### 8:45 AM — The Morning Brief

Before the market opens, SignalPilot sends a pre-market briefing to your Telegram --
think of it as the "weather forecast" for the trading day. It collects global cues
(S&P 500, Nasdaq, Asian markets, SGX Nifty), checks India VIX (the market's fear gauge),
and looks at FII/DII flows (whether foreign and domestic institutions were buying or
selling). Using all of this, it predicts the likely **market regime** for the day --
TRENDING, RANGING, or VOLATILE -- and lists any watchlist alerts for stocks you're
tracking.

This is like a meteorologist giving you the morning forecast: "Sunny with clear skies
(TRENDING), expect momentum plays to do well" or "Storm clouds gathering (VOLATILE),
keep your umbrella ready and trade small." You start your day knowing what to expect.

### 8:50 AM — The Alarm Clock

SignalPilot wakes up. It loads all its settings from a configuration file (API keys,
risk limits, strategy parameters). Think of this as the analyst arriving at their
desk and reading their briefing notes.

### 9:00 AM — The Morning Briefing

SignalPilot sends you a Telegram message:

> "Good morning! Signals will start at 9:15. Market is open today."

Behind the scenes, it authenticates with Angel One (the broker) using a secure
two-factor login, downloads yesterday's closing prices and volume data for all
500 stocks, and loads the complete list of Nifty 500 instruments.

### 9:15 AM — The Market Opens (OPENING Phase)

The moment the market opens, SignalPilot connects to a real-time data feed
(WebSocket) and starts receiving live price updates — every tick, for all 500 stocks,
simultaneously.

It feeds these ticks into an in-memory data store that tracks:
- Latest price, high, low, volume for each stock
- The opening range (high and low) being built in these first 30 minutes
- VWAP (running calculation: total money traded / total shares traded)
- 15-minute candles (like mini price charts)

**The Gap & Go strategy is now active**, scanning for stocks that opened with a gap.

### 9:30 AM — Entry Window Opens & Regime Classification

Gap & Go candidates that passed the initial checks now get their final validation:
"Is the price still holding above where it opened?" If yes, signals are generated.

At the same time, SignalPilot classifies the market day. After observing the first
15 minutes of trading, it has enough data to "read the room." It looks at 4 key
inputs:

1. **India VIX** — How fearful is the market? (the barometer)
2. **Nifty gap %** — How far did the market jump at open? (the opening leap)
3. **First-15-min range %** — How wild were the first 15 minutes? (the temperature check)
4. **Directional alignment** — Are global markets (S&P 500, SGX Nifty) agreeing on
   direction? (the consensus reading)

From these four inputs, it labels the day as one of three regimes:

- **TRENDING** — A momentum day. Markets opened strong and global cues agree. SignalPilot
  favors Gap & Go (45% weight) and lets breakout strategies run. Like a tailwind --
  go with the flow.
- **RANGING** — A sideways day. Markets are indecisive. VWAP Reversal gets 50% weight
  (mean-reversion works best here), position sizes drop by 15%, and only 4-star or
  better signals pass. Like a calm lake -- fish carefully.
- **VOLATILE** — A chaotic day. VIX is high, swings are wide. All strategies get equal
  weight, position sizes are slashed by 35%, max positions drop to 4, and only 4-5
  star signals pass. Like a storm -- batten down the hatches and trade defensively.

This classification adjusts strategy weights, position sizes, and minimum signal
quality for the rest of the day.

### 9:45 AM — The Range Locks (CONTINUOUS Phase Begins)

The 30-minute opening range is now final. It's locked — no more updates.

**The ORB strategy activates.** It starts watching for breakouts above the range high.

### 10:00 AM — VWAP Strategy Joins

**VWAP Reversal activates.** Now all three strategies can potentially generate signals
at the same time.

### 10:00 AM - 2:30 PM — The Core Trading Session

This is where the magic happens. Every single second, SignalPilot runs a complete
**13-stage pipeline** (more on this in Chapter 4). It's like an assembly line in a
factory — each station does one specific job.

### 11:00 AM / 1:00 PM / 2:30 PM — Regime Re-checks

The market does not always behave the way the morning suggested. SignalPilot checks
three times during the day whether the regime should change -- like a pilot checking
the weather radar mid-flight.

Triggers for a re-classification include:
- **VIX spike** — India VIX jumps by 3 or more points from the morning reading
  (fear is rising fast)
- **Direction reversal** — Nifty reverses direction from the morning (opened bullish,
  now falling hard)
- **Round-trip** — Nifty does a "round-trip," coming back to where it opened after
  a big move (the momentum was a fake-out)

Important rules: the regime can only **upgrade in severity** (TRENDING can become
RANGING or VOLATILE, RANGING can become VOLATILE, but never backwards). And there's
a maximum of **2 re-classifications per day** to prevent flip-flopping. If the
morning said TRENDING but VIX spikes at 11:00 AM, SignalPilot upgrades to VOLATILE
and immediately tightens all the knobs -- higher quality bar, smaller positions,
fewer trades.

### 11:15 AM — Mid-Day News Refresh

The news sentiment cache gets a refresh. New headlines published since the pre-market
fetch are pulled in, analyzed, and scored. This ensures that breaking news during
the trading session is not missed — if a stock suddenly makes negative headlines,
SignalPilot will know about it before delivering any further signals.

### 1:15 PM — Afternoon News Refresh

One more cache refresh in the afternoon, catching any late-breaking stories. By
this point the day is winding down, but signals can still be generated until 2:30.

### 2:30 PM — No More New Signals

SignalPilot stops generating new signals but keeps monitoring your existing trades.

### 3:00 PM — Exit Reminder

If you still have open positions, you get a gentle nudge:

> "You have 2 open positions. Market closes in 30 minutes."

### 3:15 PM — Mandatory Exit

Any positions still open are force-closed. Intraday means intraday — no overnight risk.

### 3:30 PM — Daily Report Card

SignalPilot sends you a summary:

```
Daily Summary:
  Total signals: 5
  Taken: 3
  Winners: 2  |  Losers: 1
  Net P&L: +Rs 2,340
  Win rate: 66.7%

  Strategy Breakdown:
    Gap & Go: 1 signal, 1 win (+Rs 1,200)
    ORB:      2 signals, 1 win, 1 loss (+Rs 340)
    VWAP:     2 signals, skipped both
```

### 3:35 PM — Lights Out

SignalPilot disconnects from the data feed, closes the database, and stops the
Telegram bot. Good night.

---

## Chapter 4: The 13-Stage Pipeline (The Assembly Line)

Every second, each signal candidate passes through an assembly line of 13 stages.
Think of it like a car factory — the car (signal) moves from one station to the next,
and each station adds something or rejects defective ones.

Here is the complete journey of a Reliance signal:

### Stage 1: Circuit Breaker Gate (The Emergency Stop)

*"Has the market been too rough today?"*

If too many stop-losses have been hit today (default: 3), this gate slams shut
and no new signals are generated. It's like a fire alarm — when it goes off,
everyone stops working.

```
Today's SL hits: 2 (limit: 3)
--> Gate is OPEN, signal passes through
```

### Stage 2: Regime Context (The Weather Report)

*"What kind of day is the market having?"*

This stage is like checking the weather before deciding what to wear. Every second,
it reads the day's regime classification (a simple dictionary lookup -- takes less
than 1 millisecond) and sets the "conditions" for all downstream stages:

- **TRENDING day**: "It's sunny -- go full speed." Strategy weights favor Gap & Go
  (45%), position sizes stay normal, accept 3-star signals.
- **RANGING day**: "It's overcast -- proceed with caution." VWAP Reversal gets 50%
  weight, position sizes reduced by 15%, require 4-star signals.
- **VOLATILE day**: "Storm warning -- batten down the hatches." All strategies equally
  weighted, position sizes slashed by 35%, only accept 4-5 star signals, max 4 positions.

Before 9:30 AM (when the first classification happens), this stage uses neutral
defaults -- no modifications. The market has not spoken yet, so SignalPilot does not
make assumptions.

```
Today's regime: TRENDING (classified at 9:30 AM)
Confidence: 0.78
--> Downstream stages will use TRENDING modifiers
```

### Stage 3: Strategy Evaluation (The Talent Scout)

*"Which strategies are active right now, and what did they find?"*

This stage runs all enabled strategies (Gap & Go, ORB, VWAP) and collects their
candidates. Our Reliance ORB breakout signal is generated here.

```
Enabled: Gap & Go (past its window), ORB (active), VWAP (active)
ORB found: Reliance breakout above Rs 2,860
VWAP found: TCS pullback to VWAP
--> 2 candidates collected
```

### Stage 4: Gap Stock Marking (The Exclusion List)

*"Was this stock already flagged by Gap & Go?"*

If a stock had a gap in the morning, ORB and VWAP strategies skip it (to avoid
conflicting signals on the same stock from different angles).

```
Reliance was NOT a gap stock today
--> Passes through unchanged
```

### Stage 5: Deduplication (The Bouncer)

*"Have we already sent a signal for this stock today?"*

Checks two things:
1. Do you already have an active trade on this stock?
2. Was a signal already sent for this stock today?

```
No active Reliance trade, no prior Reliance signal today
--> Reliance passes through
```

### Stage 6: Confidence Detection (The Second Opinion)

*"Do multiple strategies agree on this stock?"*

When more than one strategy likes the same stock, that's a strong confirmation.
Like getting a second doctor's opinion.

```
Only ORB flagged Reliance today
--> Single confirmation (1x position size)

But if both ORB and VWAP flagged Reliance:
--> Double confirmation (1.5x position size, +1 star bonus!)
```

### Stage 7: Composite Scoring (The Report Card)

*"How good is this signal really?"*

Every signal gets a composite score out of 100, calculated from four factors:

```
Reliance ORB Signal Score Breakdown:

  Strategy Strength (40%):  72/100  (good volume, clean breakout)
  Win Rate (30%):           65/100  (ORB has 65% win rate over 30 days)
  Risk-Reward (20%):        80/100  (R:R ratio of 2.2)
  Confirmation (10%):        0/100  (single strategy, no bonus)

  Composite Score = 72*0.4 + 65*0.3 + 80*0.2 + 0*0.1
                  = 28.8 + 19.5 + 16.0 + 0
                  = 64.3 / 100
```

### Stage 8: Adaptive Filter (The Performance Review)

*"Has this strategy been losing too much lately?"*

Each strategy has a status that changes based on recent performance:

```
NORMAL  -->  All signals pass (default)
REDUCED -->  Only 5-star signals pass (after 3 consecutive losses)
PAUSED  -->  No signals pass (after 5 consecutive losses)
```

```
ORB status: NORMAL (last 3 trades: Win, Win, Loss)
--> Reliance signal passes through
```

### Stage 9: Ranking (The Talent Show)

*"Which signals deserve to be sent?"*

All surviving signals are ranked by composite score. The top N (default: 8) make
the cut. Each signal gets a star rating:

```
Rank 1: Reliance ORB  (score: 64.3) --> 3 stars (Moderate)
Rank 2: TCS VWAP      (score: 58.1) --> 3 stars (Moderate)

Star Rating Scale:
  5 stars: Exceptional (score >= 80)
  4 stars: Strong      (score >= 65)
  3 stars: Moderate    (score >= 50)
  2 stars: Speculative (score >= 35)
  1 star:  Weak        (score < 35)
```

**Regime adjustment:** In VOLATILE or RANGING regimes, the admission bar is raised.
On a normal TRENDING day, 3-star signals pass. On a RANGING day, only 4-star or
better. On a VOLATILE day with high confidence, only 5-star signals make it through.
This is like raising the entrance requirements when conditions are tough -- only the
best candidates get through the door.

### Stage 10: News Sentiment Filter (The Intelligence Analyst)

*"What is the news saying about this stock right now?"*

Before sizing the position, SignalPilot checks the latest news sentiment for each
surviving signal. It uses a pre-built cache of headlines (fetched at 8:30 AM and
refreshed at 11:15 AM and 1:15 PM) so this check is nearly instant — no waiting
for web requests in the middle of a scan cycle.

Each stock gets a sentiment score (from -1.0 to +1.0) computed as a
recency-weighted average of all recent headlines. Recent news counts more than
older news (6-hour half-life decay). The score maps to a label, and the label
determines what happens:

```
Reliance ORB Signal — News Sentiment Check:

  Headlines in cache: 4 (within last 24 hours)
  Recency-weighted score: +0.12
  Label: NEUTRAL
  Action: PASS

  --> Signal passes through unchanged
```

Here is the full action matrix:

```
STRONG_NEGATIVE (score < -0.5):
  --> SUPPRESSED. Signal is removed entirely.
  --> You get a notification: "SIGNAL SUPPRESSED: RELIANCE (ORB) — Strong negative sentiment"

MILD_NEGATIVE (score between -0.5 and -0.2):
  --> DOWNGRADED. Star rating reduced by 1 (minimum 1 star).
  --> Signal shows warning: "NEWS WARNING: -0.35 (MILD_NEGATIVE) — Downgraded from 4/5 to 3/5"

NEUTRAL (score between -0.2 and +0.3):
  --> PASS. Signal goes through unchanged.

POSITIVE (score > +0.3):
  --> PASS with badge: "Positive sentiment"

NO_NEWS (no headlines found):
  --> PASS with note: "No recent news"

EARNINGS BLACKOUT:
  --> SUPPRESSED regardless of sentiment score.
  --> "SIGNAL SUPPRESSED: SBIN (Gap & Go) — Earnings day blackout"
```

If you disagree with a suppression, you can override it with the `UNSUPPRESS RELIANCE`
command, and the stock will be allowed through for the rest of the day.

### Stage 11: Risk Sizing (The Accountant)

*"How many shares can you afford, and how much to risk?"*

```
Your total capital:    Rs 50,000
Max positions:         8
Per-trade capital:     Rs 6,250 (50,000 / 8)
Confirmation:          1.0x (single, no boost)
Allocated capital:     Rs 6,250

Reliance entry price:  Rs 2,862
Quantity:              2 shares (floor of 6,250 / 2,862)
Actual capital used:   Rs 5,724
```

**Regime adjustment:** During RANGING days, all position sizes are reduced by 15%.
During VOLATILE days, positions are slashed by 35% and the maximum number of positions
drops from 8 to 4. This is SignalPilot being defensive -- smaller bets when the market
is unpredictable. If the accountant sees storm clouds on the regime weather report,
they tighten the budget.

### Stage 12: Persist & Deliver (The Messenger)

*"Save the record and tell the user!"*

The signal is saved to the database and delivered to your Telegram:

```
 BUY SIGNAL -- RELIANCE  ***-- (Moderate)
 Strategy:  ORB (Opening Range Breakout)
 Entry:     Rs 2,862
 Stop-Loss: Rs 2,830
 Target 1:  Rs 2,905 (+1.5%)
 Target 2:  Rs 2,934 (+2.5%)
 Quantity:  2 shares
 Risk:      Rs 64 (1.1%)

 [ TAKEN ]    [ SKIP ]    [ WATCH ]
```

Those three buttons are your response options (more on this in Chapter 6).

Each signal message now also includes a **regime badge** -- a small label like
"TRENDING DAY" or "VOLATILE -- reduced sizing" -- so you always know the market
context behind each signal. It is like a label on the package telling you the
weather conditions when it was shipped.

### Stage 13: Diagnostic (The Health Check)

Every 60 cycles (~1 minute), a heartbeat log confirms everything is healthy:

```
[HEARTBEAT] Phase: CONTINUOUS | Candidates: 2 | WebSocket: connected
```

### Always-On Stage: Exit Monitoring (The Bodyguard)

This runs every single cycle regardless of whether new signals are being generated.
It watches your active trades like a bodyguard.

```
Monitoring Reliance trade:
  Entry: Rs 2,862  |  Current: Rs 2,891  |  SL: Rs 2,830

  Priority exit checks (in order):
  1. SL hit?                 --> No (2,891 > 2,830)
  2. Target 2 hit?           --> No (2,891 < 2,934)
  3. Target 1 hit?           --> No (2,891 < 2,905)
  4. Should trailing SL move? --> Not yet (need +1.5% for breakeven move)
  5. SL approaching?         --> No
  6. Near T2?                --> No

  --> No action needed. Checking again in 1 second.
```

---

## Chapter 5: The Exit Monitor — Protecting Your Trades

Once you take a trade, SignalPilot watches it every second. It uses **trailing
stop-losses** that automatically adjust as the price moves in your favor.

### How Trailing Stops Work (ORB Example)

```
You took Reliance at Rs 2,862. Stop-loss is at Rs 2,830.

Phase 1 - Initial:
  Price moves to Rs 2,880 (+0.6%)
  SL stays at Rs 2,830 (no change yet)

Phase 2 - Breakeven Trigger (price reaches +1.5%):
  Price hits Rs 2,905 (+1.5%)
  SL moves UP to Rs 2,862 (your entry price!)
  --> You are now in a risk-free trade. Worst case: you break even.

Phase 3 - Trail Trigger (price reaches +2%):
  Price hits Rs 2,919 (+2%)
  SL now trails 1% below the highest price reached
  Peak so far: Rs 2,919
  New SL: Rs 2,919 * 0.99 = Rs 2,890

Phase 4 - SL keeps trailing up:
  Price runs to Rs 2,950 (new peak!)
  SL moves to: Rs 2,950 * 0.99 = Rs 2,921

Phase 5 - Price reverses:
  Price drops to Rs 2,921
  TRAILING SL HIT at Rs 2,921!
  --> Trade closed. Profit: Rs 2,921 - Rs 2,862 = Rs 59/share
```

Each strategy has different trailing stop settings:

| Strategy | Breakeven Trigger | Trail Trigger | Trail Distance |
|----------|-------------------|---------------|----------------|
| Gap & Go | +2% | +4% | 2% below peak |
| ORB | +1.5% | +2% | 1% below peak |
| VWAP | +1% to +1.5% | No trail | Breakeven only |

---

## Chapter 6: Telegram Interaction — Your Control Panel

### Signal Buttons

When a signal arrives, you see three buttons:

**[ TAKEN ]** — "I took this trade!"
- Creates a trade record in the database
- Starts the exit monitor for this stock
- Tracks your entry time and response speed

**[ SKIP ]** — "Not interested"
- Shows follow-up reasons: `No Capital | Low Confidence | Sector | Other`
- Helps SignalPilot understand why you skip signals (analytics)

**[ WATCH ]** — "Interesting, but not now"
- Adds to your watchlist (5-day expiry)
- If this stock generates another signal within 5 days, you'll be alerted again

### Exit Alert Buttons

As the price moves, you get contextual alerts:

**Target 1 Hit:**
> "Reliance hit Target 1 (Rs 2,905)!"
> `[ Book 50% at T1 ]`

**SL Approaching:**
> "Reliance is approaching your stop-loss..."
> `[ Exit Now ]  [ Hold ]`

**Near Target 2:**
> "Reliance is close to Target 2!"
> `[ Take Profit ]  [ Let Run ]`

### Text Commands

You can also type commands:

| Command | What it does |
|---------|-------------|
| `STATUS` | Shows all your active trades with current P&L |
| `JOURNAL` | Performance metrics (win rate, total P&L, average R:R) |
| `CAPITAL 100000` | Update your trading capital to Rs 1,00,000 |
| `PAUSE ORB` | Temporarily stop ORB signals |
| `RESUME ORB` | Re-enable ORB signals |
| `SCORE RELIANCE` | Show the composite score breakdown for a stock |
| `WATCHLIST` | View your current watchlist |
| `NEWS RELIANCE` | View the current sentiment score and label for Reliance |
| `NEWS ALL` | Summary of sentiment scores for all stocks in the cache |
| `EARNINGS` | Show upcoming earnings calendar (next 7 days) |
| `UNSUPPRESS SBIN` | Manually override a news suppression for SBIN (lasts until end of day) |
| `REGIME` | What kind of day is the market having? Shows the current classification (TRENDING/RANGING/VOLATILE), confidence score, and how it's affecting strategy weights and position sizing |
| `REGIME HISTORY` | Shows the last 7 days of market regimes. Useful for spotting patterns (e.g., "3 volatile days in a row -- market is unsettled") |
| `REGIME OVERRIDE TRENDING` | Manual override. If you disagree with SignalPilot's assessment, you can force a different regime (TRENDING, RANGING, or VOLATILE). Use with caution -- you're overriding the algorithm |
| `VIX` | Shows the current India VIX with an interpretation (very calm / normal / slightly elevated / high / very high -- defensive mode) |
| `MORNING` | Re-read today's morning brief. If you missed the 8:45 AM message, this shows it again |
| `HELP` | List all available commands |

---

## Chapter 7: The Safety Systems

SignalPilot has five layers of protection to prevent catastrophic losses.

### Layer 1: Circuit Breaker (The Fire Alarm)

If 3 stop-losses are hit in a single day, the circuit breaker activates
and **halts all signal generation** for the rest of the day.

```
Trade 1: Reliance  SL hit  --> Counter: 1/3
Trade 2: TCS      SL hit  --> Counter: 2/3
Trade 3: HDFC     SL hit  --> Counter: 3/3

 CIRCUIT BREAKER ACTIVATED!
No more signals will be generated today.

You receive a Telegram alert:
"Circuit breaker activated: 3 stop-losses hit today. Signal generation halted."
```

**Why?** Bad days happen. When the market is hostile, the best strategy is to
stop trading and preserve capital.

### Layer 2: Adaptive Strategy Manager (The Performance Coach)

Each strategy is independently monitored. If one keeps losing:

```
ORB results this week:
  Monday:    Win
  Tuesday:   Loss
  Wednesday: Loss
  Thursday:  Loss   --> 3 consecutive losses!

  ORB status: NORMAL --> REDUCED
  (Only 5-star ORB signals will be sent now)

  Friday:    Loss
  Saturday:  Loss   --> 5 consecutive losses!

  ORB status: REDUCED --> PAUSED
  (No ORB signals at all until the streak breaks)
```

Meanwhile, Gap & Go and VWAP continue operating normally. The bad student gets
detention; the good students keep going to class.

### Layer 3: Capital Allocator (The Budget Manager)

Every Sunday at 6 PM, SignalPilot rebalances how much capital each strategy gets,
based on their track record:

```
Weekly Rebalance:
  Gap & Go:  65% win rate, expectancy +1.2  --> 45% of capital
  ORB:       55% win rate, expectancy +0.8  --> 35% of capital
  VWAP:      40% win rate, expectancy +0.3  --> 20% of capital

  If any strategy drops below 40% win rate after 10+ trades:
  --> Auto-paused until performance improves
```

**20% Reserve:** SignalPilot always keeps 20% of capital in reserve for
exceptional (double/triple confirmed) signals.

### Layer 4: News Sentiment Filter (The Intelligence Analyst)

The newest safety layer looks beyond price and volume — it reads the news. Before
any signal reaches your phone, SignalPilot checks whether the stock is in the
headlines for the wrong reasons.

```
Scenario: ORB detects a beautiful breakout in SBIN at 10:15 AM.

But at 8:30 AM, headlines came in:
  "RBI imposes penalty on SBI for compliance failures"
  "SBI faces regulatory scrutiny over loan disbursement"

  Recency-weighted sentiment score: -0.62  (STRONG_NEGATIVE)

  --> Signal SUPPRESSED. You never see it.
  --> Instead you get: "SIGNAL SUPPRESSED: SBIN (ORB) — Strong negative sentiment"
```

Even if the chart looks perfect, trading against negative news flow is risky.
This layer catches that risk before you are exposed to it.

For stocks reporting earnings today, signals are automatically suppressed
regardless of sentiment — earnings announcements can cause wild, unpredictable
swings in either direction.

If you review the news and disagree with the suppression (maybe the headline
is about a different entity or old news), you can type `UNSUPPRESS SBIN` to
override it for the rest of the day.

### Layer 5: Market Regime Detection (The Weather Station)

The regime detection system is SignalPilot's "macro awareness." While the other
safety systems react to individual trades (circuit breaker) or strategy performance
(adaptive manager), the regime detector looks at the whole market environment. It is
like having a weather station on the roof of the factory -- the assembly line workers
(pipeline stages) can check the conditions before deciding how aggressively to work.

On a VOLATILE day (high VIX, wild swings), SignalPilot automatically:
- Raises the quality bar (only 4-5 star signals)
- Cuts position sizes by 35%
- Limits to 4 positions maximum
- Weights all strategies equally (no favorites)

This prevents SignalPilot from being overly aggressive when the market is
unpredictable. On RANGING days, the adjustments are milder but still meaningful:
position sizes drop by 15% and the minimum star rating is raised to 4. On TRENDING
days, the system runs at full speed -- conditions are favorable.

And if you disagree with the classification, the `REGIME OVERRIDE` command lets you
set your own assessment. Maybe you see something the algorithm missed, or you have
conviction that the market is about to break out of its range. You are still in
control.

The system starts in **shadow mode** by default -- it classifies and logs the regime
but does not actually change trading behavior. This lets you observe how it works
and validate its accuracy for a couple of weeks before enabling active mode. Think of
it as a trial run: the weather station is installed and reporting, but the factory
workers are not yet checking it. Once you trust the readings, you flip the switch.

---

## Chapter 8: Multi-Strategy Confirmation (The Second Opinion)

When two or three strategies independently identify the same stock within a
15-minute window, that's a powerful confirmation signal.

```
Example:
  10:05 AM  ORB detects Reliance breakout above range high
  10:12 AM  VWAP detects Reliance bouncing off VWAP line

  Both strategies, using completely different logic, agree: Reliance looks strong.

  Confirmation: DOUBLE (ORB + VWAP)
    --> Position size boosted by 1.5x
    --> Star rating gets +1 bonus
    --> Signal message shows: "DOUBLE CONFIRMED by ORB + VWAP Reversal"
```

| Confirmation | Strategies Agree | Position Boost | Star Bonus |
|--------------|------------------|----------------|------------|
| Single | 1 | 1.0x (normal) | +0 |
| Double | 2 | 1.5x | +1 star |
| Triple | 3 (rare!) | 2.0x | +2 stars |

---

## Chapter 9: The Database — SignalPilot's Memory

Everything is stored in a local SQLite database (a single file). Here's what's
tracked:

| Table | What it stores | Example |
|-------|---------------|---------|
| `signals` | Every signal ever generated (now includes `market_regime`, `regime_confidence`, and `regime_weight_modifier` columns so every signal is tagged with the market context when it was generated) | Reliance BUY at 2,862, ORB, 3 stars, TRENDING day |
| `trades` | Trades you actually took | Reliance, entry 2,862, exit 2,921, +Rs 118 |
| `user_config` | Your personal settings | Capital: 50K, max positions: 8 |
| `strategy_performance` | Win/loss record per strategy | ORB: 45 wins, 23 losses |
| `signal_actions` | How you responded to each signal | Reliance: TAKEN in 12 seconds |
| `watchlist` | Stocks you're watching | TCS, added Feb 27, expires Mar 4 |
| `hybrid_scores` | Composite score breakdowns | Reliance: 64.3 (40+19.5+16+0) |
| `circuit_breaker_log` | When circuit breaker fired | Feb 27, activated at 11:30 |
| `adaptation_log` | Strategy status changes | ORB: NORMAL -> REDUCED, Feb 25 |
| `news_sentiment` | Cached headlines with sentiment scores | SBIN: -0.62, STRONG_NEGATIVE, 4 headlines |
| `earnings_calendar` | Upcoming earnings dates per stock | RELIANCE: earnings on Mar 5 |
| `market_regimes` | Every regime classification: the scores, the inputs, the resulting modifiers. Creates an audit trail and enables backtesting | Feb 28: TRENDING, confidence 0.78, VIX 13.2, gap +0.8% |
| `regime_performance` | Daily performance broken down by regime type. Over time, tells you which strategies work best on which types of days | TRENDING days: Gap & Go 72% win rate, ORB 61% |

That is **14 tables** in total -- a complete audit trail of every decision SignalPilot
makes, from signal generation to regime classification to your response.

---

## Chapter 10: Crash Recovery — What If Something Goes Wrong?

Computers crash. Internet goes down. SignalPilot is designed to handle this.

**Scenario:** It's 11:00 AM. You have 2 active trades. SignalPilot crashes.

**What happens when it restarts:**

```
1. Detects it's during market hours (11 AM is in CONTINUOUS phase)
2. Re-authenticates with Angel One
3. Reconnects WebSocket for live data
4. Loads your 2 active trades from the database
5. Resumes exit monitoring immediately
6. Resumes signal generation (ORB and VWAP are still in their windows)
7. Sends you a Telegram alert: "Recovered from crash. Monitoring 2 active trades."
```

Your trades were never at risk because the entries are saved in the database,
and the exit monitor picks right back up.

---

## Chapter 11: The Complete Picture — One Second in SignalPilot

Here is everything that happens in a single 1-second scan cycle at 10:30 AM
on a normal trading day:

```
10:30:00.000  Scan cycle #4500 begins

  [Stage 1]  Circuit Breaker: OFF (1 SL today, limit is 3) .............. PASS
  [Stage 2]  Regime Context: TRENDING (confidence 0.78) ................. modifiers set
  [Stage 3]  Strategy Eval: ORB evaluates 500 stocks, finds 1 breakout .. 1 candidate
             VWAP evaluates 500 stocks, finds 0 setups .................. 0 candidates
  [Stage 4]  Gap Stock Marking: no overlap ............................... 1 candidate
  [Stage 5]  Dedup: no prior signal for this stock ....................... 1 candidate
  [Stage 6]  Confidence: single strategy only ............................ 1x multiplier
  [Stage 7]  Composite Score: 64.3/100 ................................... scored
  [Stage 8]  Adaptive Filter: ORB is NORMAL .............................. PASS
  [Stage 9]  Ranking: rank #1 of 1, 3 stars (min 3 for TRENDING) ....... ranked
  [Stage 10] News Sentiment: NEUTRAL (+0.12), no earnings ............... PASS
  [Stage 11] Risk Sizing: 2 shares, Rs 5,724 capital (no regime cut) ... sized
  [Stage 12] Persist & Deliver: saved to DB, sent to Telegram ........... DELIVERED
  [Stage 13] Diagnostic: healthy .......................................... logged

  [Always]   Exit Monitor: checking 1 active trade (HDFC Bank) .......... no exits

10:30:00.850  Scan cycle #4500 complete (850ms)
10:30:01.000  Scan cycle #4501 begins...
```

---

## Chapter 12: Glossary

| Term | Plain English |
|------|--------------|
| **LTP** | Last Traded Price — the most recent price at which a stock was bought/sold |
| **VWAP** | Volume Weighted Average Price — the "fair price" of a stock for the day, weighted by how much was traded at each price |
| **ADV** | Average Daily Volume — how many shares are typically traded in a day (20-day average) |
| **SL / Stop-Loss** | The price at which you exit a losing trade to limit your loss |
| **T1 / Target 1** | First profit target — many traders book partial profits here |
| **T2 / Target 2** | Second profit target — the full exit point |
| **Opening Range** | The highest and lowest prices in the first 30 minutes of trading |
| **Breakout** | When a price moves above a key resistance level (like the opening range high) |
| **Trailing Stop** | A stop-loss that automatically moves up as the price rises, locking in profits |
| **Gap** | When a stock opens at a significantly different price than yesterday's close |
| **IST** | Indian Standard Time (UTC+5:30) — all market times are in IST |
| **NSE** | National Stock Exchange of India |
| **Nifty 500** | The top 500 companies listed on NSE by market capitalization |
| **WebSocket** | A persistent connection that delivers real-time price data (instead of asking for it repeatedly) |
| **R:R / Risk-Reward** | The ratio of potential profit to potential loss. An R:R of 2:1 means you could make Rs 2 for every Rs 1 you risk |
| **Paper Mode** | Signals are generated and tracked but not intended for real trading — used to test new strategies |
| **Composite Score** | A 0-100 score combining strategy strength, win rate, risk-reward, and confirmation |
| **Circuit Breaker** | An automatic safety system that stops trading after too many losses in one day |
| **Confirmation** | When multiple strategies independently agree on the same stock — a stronger signal |
| **VADER** | Valence Aware Dictionary and sEntiment Reasoner — a rule-based sentiment analysis tool, enhanced here with a financial lexicon for stock market terminology |
| **Sentiment Score** | A number from -1.0 (extremely negative) to +1.0 (extremely positive) representing the overall news tone for a stock, computed as a recency-weighted average of headline scores |
| **Earnings Blackout** | Automatic suppression of signals for any stock reporting earnings on the current day — earnings announcements cause unpredictable price swings |
| **Suppression** | When the News Sentiment Filter blocks a signal from being delivered due to strong negative news or an earnings blackout |
| **Unsuppress** | A manual override command that lets you bypass a news suppression for a specific stock for the rest of the trading day |
| **RSS** | Really Simple Syndication — a standard format for publishing news feeds that SignalPilot reads to gather financial headlines |
| **Market Regime** | The overall market characterization for the day: TRENDING (strong directional movement), RANGING (sideways, mean-reverting), or VOLATILE (high uncertainty, wide swings) |
| **India VIX** | The India Volatility Index, derived from Nifty option prices. High VIX (>18) suggests fear and uncertainty; low VIX (<14) suggests calm markets |
| **Regime Classification** | The act of labeling the market day at 9:30 AM using VIX, gap, range, and alignment data |
| **Shadow Mode** | A deployment mode where the regime is classified and logged but does not affect actual trading decisions. Useful for validation before going live |
| **Directional Alignment** | A score from -1 to +1 measuring whether global markets (S&P 500, SGX Nifty) agree on direction. High alignment suggests trending; low alignment suggests ranging |

---

## Summary: Why SignalPilot Works the Way It Does

| Design Choice | Why |
|--------------|-----|
| Three different strategies | Different market conditions favor different setups. Diversification of approaches. |
| Strict time windows | Each strategy has a proven optimal window. Running them outside that window adds noise, not signal. |
| 13-stage pipeline | Each stage does one thing well. Easy to test, easy to modify, easy to understand. |
| Market regime detection | The market environment matters. TRENDING, RANGING, and VOLATILE days need different approaches. Regime detection adjusts strategy weights, position sizes, and quality thresholds based on the overall market conditions -- macro awareness, not just individual signals. |
| News sentiment filter | Price and volume alone do not tell the full story. Checking news before delivery avoids trading into known bad situations. |
| 5 layers of safety | Circuit Breaker, Adaptive Manager, Capital Allocator, News Sentiment Filter, and Market Regime Detection. Each layer protects at a different level -- individual trades, strategy streaks, capital allocation, news risk, and macro environment. |
| Multi-strategy confirmation | When independent methods agree, probability of success increases significantly. |
| Trailing stops | Lets winners run while mechanically locking in profits. Removes the hardest decision in trading. |
| Telegram delivery with buttons | You get actionable intel on your phone with one-tap responses. No need to watch charts all day. |
| Everything in a database | Full audit trail. You can analyze your performance, learn from mistakes, and improve over time. |
| No auto-trading | You stay in control. SignalPilot finds the opportunities; you decide which ones to take. |

---

*This guide covers the "what" and "why" of SignalPilot. For the technical "how"
(code structure, API references, configuration details), see
[how-it-works.md](how-it-works.md) and [system-flow.md](system-flow.md).*
