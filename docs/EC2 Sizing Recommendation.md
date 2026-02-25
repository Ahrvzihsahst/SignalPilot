EC2 Sizing Recommendation for SignalPilot                                                                         
                                
  TL;DR: t3.micro (1 vCPU, 1 GB RAM) is sufficient. Anything larger wastes money.                                   
                                      
  Why it's enough                                                                                                   
                                                                                                                    
  ┌──────────┬──────────────────┬────────────────────┬───────────────────┐
  │ Resource │    Peak Usage    │ t3.micro Capacity  │     Headroom                                                
  ├──────────┼──────────────────┼────────────────────┼───────────────────┤                                         
  │ CPU      │ <5% single core  │ 1 vCPU (burstable) │ ~95% spare        │
  ├──────────┼──────────────────┼────────────────────┼───────────────────┤
  │ Memory   │ ~300-400 MB      │ 1 GB               │ ~600-700 MB spare │
  ├──────────┼──────────────────┼────────────────────┼───────────────────┤
  │ Network  │ ~20 Mbps burst   │ 5 Gbps burst       │ Massive spare     │
  ├──────────┼──────────────────┼────────────────────┼───────────────────┤
  │ Disk I/O │ ~100 writes/day  │ 3000 IOPS (gp3)    │ Overkill          │
  ├──────────┼──────────────────┼────────────────────┼───────────────────┤
  │ Storage  │ ~5 MB/day growth │ 5 GB EBS           │ Lasts 10+ years   │
  └──────────┴──────────────────┴────────────────────┴───────────────────┘

  Key reasons it's lightweight

  - I/O-bound, not CPU-bound — the app mostly awaits WebSocket ticks and API responses
  - Single asyncio event loop with ~5-10 concurrent coroutines at peak
  - ~800 KB - 1.2 MB of in-memory market data for all 500 symbols
  - SQLite WAL with ~50-100 writes/day (not a database-heavy workload)
  - No ML, no pandas at runtime — scoring/ranking is simple O(N) math
  - Runs only 6.5 hours/day (9:15 AM - 3:35 PM IST, weekdays only)

  Load timeline during market day

  08:00 AM  ██░░░  Startup + historical data fetch (heaviest: ~1000 API calls over 3-5 min)
  09:15 AM  ███░░  OPENING phase — gap detection, WebSocket feed starts
  09:30 AM  ████░  ENTRY_WINDOW — signal scoring peak (~5% CPU)
  09:45 AM  █░░░░  CONTINUOUS — exit monitoring only (idle)
  03:35 PM  ░░░░░  Shutdown

  Recommended setup

  Instance:    t3.micro (enable unlimited CPU credit mode)
  EBS:         5 GB gp3
  OS:          Ubuntu 22.04 LTS
  Cost:        ~$10-15/month

  Cost-saving tip

  Stop the instance on weekends and NSE holidays (no trading). This saves ~$2-3/week (~$100/year). You can automate
  this with a simple Lambda + EventBridge schedule.

  When to upgrade to t3.small (2 GB RAM)

  Only if you later add:
  - Backtesting with pandas/numpy running alongside the live scanner
  - Multiple broker account support
  - A local web dashboard

  For the current production scanner, t3.micro handles everything comfortably at ~20% utilization.