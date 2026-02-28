EC2 Sizing Recommendation for SignalPilot

  TL;DR: t3.small (2 vCPU, 2 GB RAM) is the sweet spot. t3.micro works as a budget option
  but leaves little headroom once the dashboard frontend is served alongside the backend.

  Component Inventory (as of Phase 4)

  ┌────────────────────────┬────────────────────────────────────────────────────────┐
  │ Component              │ Details                                                │
  ├────────────────────────┼────────────────────────────────────────────────────────┤
  │ Backend (Python)       │ Async event loop, 12 pipeline stages, 3 strategies    │
  │ Frontend (React/Vite)  │ SPA dashboard — static files served via nginx         │
  │ Database               │ SQLite WAL, 10 tables, in-process                     │
  │ WebSocket              │ Angel One SmartAPI V2, 500 symbols, background thread  │
  │ Telegram Bot           │ 16 commands + 9 inline callback handlers              │
  │ FastAPI Dashboard API  │ 8 routers, runs in same process as backend            │
  │ Scheduler              │ APScheduler 3.x, 9 cron jobs                          │
  │ Event Bus              │ 4 event types, in-process dispatch                    │
  └────────────────────────┴────────────────────────────────────────────────────────┘

  Resource Usage Breakdown

  ┌────────────────────────┬──────────────────┬─────────────────────┬───────────────────┐
  │ Resource               │    Peak Usage    │ t3.small Capacity   │     Headroom      │
  ├────────────────────────┼──────────────────┼─────────────────────┼───────────────────┤
  │ CPU                    │ ~5-10% (2 cores) │ 2 vCPU (burstable)  │ ~90% spare        │
  ├────────────────────────┼──────────────────┼─────────────────────┼───────────────────┤
  │ Memory — Python app    │ ~400-600 MB      │                     │                   │
  │ Memory — nginx         │ ~50 MB           │ 2 GB                │ ~1 GB spare       │
  │ Memory — OS            │ ~200-300 MB      │                     │                   │
  ├────────────────────────┼──────────────────┼─────────────────────┼───────────────────┤
  │ Network                │ ~20 Mbps burst   │ Up to 5 Gbps burst  │ Massive spare     │
  ├────────────────────────┼──────────────────┼─────────────────────┼───────────────────┤
  │ Disk I/O               │ ~200-300 writes  │ 3000 IOPS (gp3)     │ Overkill          │
  ├────────────────────────┼──────────────────┼─────────────────────┼───────────────────┤
  │ Storage                │ ~50 MB/year (DB) │ 10 GB EBS            │ Years of headroom │
  └────────────────────────┴──────────────────┴─────────────────────┴───────────────────┘

  Why it's still lightweight

  - I/O-bound, not CPU-bound — the app mostly awaits WebSocket ticks, Telegram API, and broker
    API responses; actual computation (scoring, ranking, VWAP math) is simple O(N) arithmetic
  - Single asyncio event loop — 12 pipeline stages, 3 strategies, exit monitor, FastAPI
    dashboard, and Telegram bot all share one event loop with ~10-15 concurrent coroutines at peak
  - Modest in-memory data — ~1-2 MB for 500-symbol tick cache, VWAP accumulators, opening
    ranges, and 15-min candle aggregation
  - SQLite is in-process — no separate database server; WAL mode handles concurrent reads from
    the dashboard API alongside pipeline writes
  - No ML, no pandas at runtime — the 4-factor composite scoring, confidence detection, and
    adaptive filtering are all lightweight math
  - Runs only 6.5 hours/day — 9:15 AM to 3:35 PM IST, weekdays only, with NSE holiday skipping

  Load Timeline During Market Day

  08:00 AM  ██░░░  Startup + historical data fetch (heaviest: ~500 batched API calls at 3 req/sec)
  09:00 AM  █░░░░  Pre-market alert sent via Telegram
  09:15 AM  ███░░  OPENING — Gap & Go gap detection, WebSocket feed starts, volume accumulation
  09:30 AM  ████░  ENTRY_WINDOW — Gap & Go entry signals, scoring peak (~5-10% CPU)
  09:45 AM  ███░░  CONTINUOUS — ORB breakouts begin, opening ranges locked
  10:00 AM  ███░░  CONTINUOUS — VWAP Reversal activates, all 3 strategies running
  11:00 AM  ██░░░  CONTINUOUS — ORB window ends, VWAP + exit monitoring only
  02:30 PM  █░░░░  WIND_DOWN — no new signals, exit monitoring only
  03:15 PM  █░░░░  Mandatory exit reminders
  03:35 PM  ░░░░░  Shutdown, daily summary sent

  Pipeline Processing Per Scan Cycle (every 1 second)

  Each cycle runs these 12 stages over up to 500 symbols:

   1. CircuitBreakerGateStage  — check daily SL limit       (< 1 ms)
   2. StrategyEvalStage        — run 3 strategies            (1-5 ms)
   3. GapStockMarkingStage     — mark gap stocks             (< 1 ms)
   4. DeduplicationStage       — cross-strategy dedup        (< 1 ms)
   5. ConfidenceStage          — multi-strategy confirmation (< 1 ms)
   6. CompositeScoringStage    — 4-factor hybrid scoring     (< 1 ms)
   7. AdaptiveFilterStage      — check paused strategies     (< 1 ms)
   8. RankingStage             — top-N selection             (< 1 ms)
   9. RiskSizingStage          — position sizing             (< 1 ms)
  10. PersistAndDeliverStage   — DB write + Telegram send    (5-20 ms, I/O)
  11. DiagnosticStage          — heartbeat log               (< 1 ms)
  12. ExitMonitoringStage      — SL/target/trailing exits    (1-3 ms)

  Total per cycle: ~10-30 ms out of 1000 ms budget → ~1-3% CPU utilization

  Recommended Setup

  ┌─────────────────┬──────────────────────────────────────────┐
  │ Component       │ Recommendation                           │
  ├─────────────────┼──────────────────────────────────────────┤
  │ Instance        │ t3.small (2 vCPU, 2 GB RAM)              │
  │ CPU credits     │ Enable unlimited mode                    │
  │ EBS             │ 10 GB gp3 (3000 IOPS baseline)           │
  │ OS              │ Ubuntu 24.04 LTS                         │
  │ Python          │ 3.11+                                    │
  │ Web server      │ nginx (reverse proxy + static files)     │
  │ Process manager │ systemd service                          │
  └─────────────────┴──────────────────────────────────────────┘

  Deployment Architecture (single EC2)

  ┌──────────────────────────────────────────────────────┐
  │                    EC2 (t3.small)                     │
  │                                                      │
  │  ┌──────────┐    ┌──────────────────────────────┐    │
  │  │  nginx   │    │  Python backend (systemd)     │    │
  │  │  :80/443 │───▶│  ├─ Async event loop          │    │
  │  │          │    │  ├─ 12 pipeline stages         │    │
  │  │ static   │    │  ├─ FastAPI dashboard (:8000)  │    │
  │  │ files    │    │  ├─ Telegram bot (polling)     │    │
  │  │ (React   │    │  ├─ WebSocket (bg thread)      │    │
  │  │  dist/)  │    │  ├─ APScheduler (9 jobs)       │    │
  │  └──────────┘    │  └─ SQLite WAL (signalpilot.db)│    │
  │                  └──────────────────────────────────┘    │
  └──────────────────────────────────────────────────────┘

  nginx serves the React SPA from dist/ and proxies /api requests to the FastAPI
  backend on port 8000. Everything else runs in a single Python process.

  Cost Comparison

  ┌─────────────┬──────────┬─────────┬────────────────────────────────────┐
  │ Instance    │ RAM      │ $/month │ Notes                              │
  ├─────────────┼──────────┼─────────┼────────────────────────────────────┤
  │ t3.micro    │ 1 GB     │ ~$8     │ Budget option, tight on RAM        │
  │ t3.small    │ 2 GB     │ ~$15    │ Recommended — comfortable headroom │
  │ t3.medium   │ 4 GB     │ ~$30    │ Only if adding backtesting/ML      │
  └─────────────┴──────────┴─────────┴────────────────────────────────────┘

  Costs assume on-demand pricing in ap-south-1 (Mumbai). Add ~$1/month for 10 GB gp3 EBS.

  Cost-Saving Tips

  - Stop the instance on weekends and NSE holidays (no trading) — saves ~30% (~$4-5/month)
  - Automate start/stop with Lambda + EventBridge schedule or a simple cron on a free-tier
    nano instance
  - Use a 1-year Reserved Instance for ~40% savings ($9/month instead of $15)
  - Use Spot Instance for non-critical/testing environments (~70% savings)
  - Host frontend on S3 + CloudFront instead of nginx to offload static serving entirely

  t3.micro as Budget Option

  t3.micro (1 vCPU, 1 GB RAM) can work if:
  - You skip the nginx + React dashboard and use Telegram-only mode
  - Or you build the React SPA and serve it as static files (no Node.js process)
  - Python backend alone uses ~400-600 MB, leaving ~400-600 MB for OS + nginx

  It gets tight if the dashboard sees concurrent API requests alongside the scan loop,
  but for single-user operation it's viable.

  When to Upgrade to t3.medium (4 GB RAM)

  Only if you later add:
  - Backtesting with pandas/numpy running alongside the live scanner
  - Multiple broker account support (multiple WebSocket connections)
  - Heavy dashboard usage with concurrent users
  - Additional data sources (Options chain, F&O data)

  For the current production scanner + dashboard, t3.small handles everything comfortably
  at ~30-40% memory utilization and <10% CPU utilization.
