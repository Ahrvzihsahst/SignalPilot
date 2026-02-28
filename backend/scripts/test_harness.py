#!/usr/bin/env python3
"""SignalPilot Test Harness — simulate a full trading day outside market hours.

Replaces external dependencies (Angel One, WebSocket) with synthetic data
and simulates time progression through all market phases. The real pipeline,
strategies, database, and optionally Telegram bot run as in production.

Usage:
    cd backend
    python -m scripts.test_harness                     # Console mode, 60x speed
    python -m scripts.test_harness --speed 30          # Slower (day in ~13 min)
    python -m scripts.test_harness --speed 300         # Fast (day in ~1.3 min)
    python -m scripts.test_harness --with-telegram     # Send signals to real Telegram
    python -m scripts.test_harness --phase continuous  # Start at CONTINUOUS phase (9:45)
"""

import argparse
import asyncio
import importlib
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from datetime import datetime as _real_datetime
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Ensure backend/ is on sys.path
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from signalpilot.utils.constants import IST  # noqa: E402

# ===========================================================================
#  ANSI colours for terminal output
# ===========================================================================
_C_RESET = "\033[0m"
_C_BOLD = "\033[1m"
_C_GREEN = "\033[92m"
_C_YELLOW = "\033[93m"
_C_CYAN = "\033[96m"
_C_RED = "\033[91m"
_C_DIM = "\033[2m"
_C_MAGENTA = "\033[95m"


def _header(msg: str) -> str:
    return f"{_C_BOLD}{_C_CYAN}{msg}{_C_RESET}"


def _signal_line(msg: str) -> str:
    return f"{_C_BOLD}{_C_GREEN}{msg}{_C_RESET}"


def _phase_line(msg: str) -> str:
    return f"{_C_BOLD}{_C_YELLOW}{msg}{_C_RESET}"


def _warn(msg: str) -> str:
    return f"{_C_RED}{msg}{_C_RESET}"


def _dim(msg: str) -> str:
    return f"{_C_DIM}{msg}{_C_RESET}"


# ===========================================================================
#  Simulated Clock & FakeDatetime
# ===========================================================================

class SimulatedClock:
    """Mutable clock that tracks simulated IST time."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    @property
    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta

    def set(self, dt: datetime) -> None:
        self._now = dt


# Global clock instance — set before patching modules
_clock = SimulatedClock(datetime(2026, 3, 2, 9, 10, tzinfo=IST))


class FakeDatetime(_real_datetime):
    """datetime subclass that returns simulated time from ``now()``."""

    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return _clock.now.astimezone(tz)
        return _clock.now.replace(tzinfo=None)


# ===========================================================================
#  Patch datetime.now(IST) in all modules that call it inline
# ===========================================================================

_MODULES_TO_PATCH = [
    "signalpilot.strategy.gap_and_go",
    "signalpilot.strategy.orb",
    "signalpilot.strategy.vwap_reversal",
    "signalpilot.scheduler.lifecycle",
    "signalpilot.scheduler.scheduler",
    "signalpilot.pipeline.stages.exit_monitoring",
    "signalpilot.monitor.circuit_breaker",
    "signalpilot.main",
    "signalpilot.db.signal_repo",
    "signalpilot.db.trade_repo",
    "signalpilot.db.config_repo",
    "signalpilot.db.metrics",
    "signalpilot.db.signal_action_repo",
    "signalpilot.db.watchlist_repo",
    "signalpilot.db.adaptation_log_repo",
    "signalpilot.db.hybrid_score_repo",
    "signalpilot.db.regime_repo",
    "signalpilot.db.regime_performance_repo",
    "signalpilot.telegram.handlers",
    "signalpilot.intelligence.regime_data",
    "signalpilot.intelligence.regime_classifier",
    "signalpilot.intelligence.morning_brief",
    "signalpilot.pipeline.stages.regime_context",
    "signalpilot.intelligence.news_sentiment",
    "signalpilot.intelligence.news_fetcher",
    "signalpilot.db.news_sentiment_repo",
    "signalpilot.db.earnings_repo",
    "signalpilot.pipeline.stages.news_sentiment",
]


def _patch_datetime_modules() -> None:
    """Replace ``datetime`` reference in each module with FakeDatetime."""
    for mod_path in _MODULES_TO_PATCH:
        try:
            mod = importlib.import_module(mod_path)
            if hasattr(mod, "datetime"):
                mod.datetime = FakeDatetime  # type: ignore[attr-defined]
        except ImportError:
            pass  # module may not exist in all configs


# ===========================================================================
#  Stock Scenarios — deterministic price / volume paths
# ===========================================================================

@dataclass
class StockScenario:
    """Defines a simulated stock with deterministic price and volume."""

    symbol: str
    prev_close: float
    prev_high: float
    adv: int              # average daily volume
    open_price: float
    description: str      # what this stock is designed to test

    def state_at(self, t: int) -> tuple[float, int]:
        """Return (ltp, cumulative_volume) at *t* seconds since 9:15 AM."""
        raise NotImplementedError


class SBINScenario(StockScenario):
    """Gap & Go target: 3.5% gap up, strong volume, holds above open."""

    def __init__(self):
        super().__init__(
            symbol="SBIN", prev_close=800.0, prev_high=795.0,
            adv=10_000_000, open_price=828.0,
            description="Gap & Go (3.5% gap up, vol > 50% ADV)",
        )

    def state_at(self, t: int) -> tuple[float, int]:
        if t < 900:          # 9:15-9:30: drift up
            ltp = 828 + (t / 900) * 6
        elif t < 1800:       # 9:30-9:45: hold above open
            ltp = 834 + ((t - 900) / 900) * 2
        elif t < 5400:       # 9:45-10:45: climb toward T1
            ltp = 836 + ((t - 1800) / 3600) * 14
        else:                # after 10:45: slow grind
            ltp = 850 + ((t - 5400) / 14400) * 10
        volume = min(t * 7000, 50_000_000)
        return round(ltp, 2), volume


class INFYScenario(StockScenario):
    """Gap & Go target: 4.0% gap up."""

    def __init__(self):
        super().__init__(
            symbol="INFY", prev_close=1500.0, prev_high=1490.0,
            adv=6_000_000, open_price=1560.0,
            description="Gap & Go (4.0% gap up)",
        )

    def state_at(self, t: int) -> tuple[float, int]:
        if t < 900:
            ltp = 1560 + (t / 900) * 10
        elif t < 1800:
            ltp = 1570 + ((t - 900) / 900) * 5
        else:
            ltp = 1575 + ((t - 1800) / 18000) * 20
        volume = min(t * 5000, 30_000_000)
        return round(ltp, 2), volume


class TATAMOTORSScenario(StockScenario):
    """ORB target: tight range 9:15-9:45, breakout at 9:50 with volume surge."""

    def __init__(self):
        super().__init__(
            symbol="TATAMOTORS", prev_close=950.0, prev_high=955.0,
            adv=5_000_000, open_price=952.0,
            description="ORB (1% range, breakout with volume)",
        )

    def state_at(self, t: int) -> tuple[float, int]:
        import math
        if t < 1800:         # 9:15-9:45: oscillate in range 948-958
            ltp = 953 + 5 * math.sin(t * math.pi / 300)
        elif t < 2100:       # 9:45-9:50: breakout above range
            ltp = 958 + ((t - 1800) / 300) * 7  # 958 → 965
        else:                # after 9:50: hold above range
            ltp = 965 + ((t - 2100) / 17700) * 8
        # Volume: normal, then surge during breakout
        if t < 1800:
            volume = t * 2000
        elif t < 2400:       # surge during breakout window
            volume = 3_600_000 + (t - 1800) * 15000
        else:
            volume = 12_600_000 + (t - 2400) * 2500
        return round(ltp, 2), min(volume, 40_000_000)


class HDFCBANKScenario(StockScenario):
    """ORB target: range breakout (backup ORB stock)."""

    def __init__(self):
        super().__init__(
            symbol="HDFCBANK", prev_close=1600.0, prev_high=1610.0,
            adv=4_000_000, open_price=1605.0,
            description="ORB (1.2% range, breakout)",
        )

    def state_at(self, t: int) -> tuple[float, int]:
        import math
        if t < 1800:
            ltp = 1605 + 10 * math.sin(t * math.pi / 400)
        elif t < 2400:
            ltp = 1615 + ((t - 1800) / 600) * 8
        else:
            ltp = 1623 + ((t - 2400) / 17400) * 5
        if t < 1800:
            volume = t * 1800
        elif t < 2700:
            volume = 3_240_000 + (t - 1800) * 12000
        else:
            volume = 14_040_000 + (t - 2700) * 2000
        return round(ltp, 2), min(volume, 30_000_000)


class RELIANCEScenario(StockScenario):
    """VWAP Reversal target: uptrend then pullback to VWAP with bounce."""

    def __init__(self):
        super().__init__(
            symbol="RELIANCE", prev_close=2800.0, prev_high=2810.0,
            adv=8_000_000, open_price=2812.0,
            description="VWAP Reversal (uptrend pullback to VWAP)",
        )

    def state_at(self, t: int) -> tuple[float, int]:
        if t < 1800:         # 9:15-9:45: steady uptrend
            ltp = 2812 + (t / 1800) * 20  # → 2832
        elif t < 2700:       # 9:45-10:00: continue up
            ltp = 2832 + ((t - 1800) / 900) * 6  # → 2838
        elif t < 3300:       # 10:00-10:10: pullback toward VWAP
            ltp = 2838 - ((t - 2700) / 600) * 18  # → 2820
        elif t < 3600:       # 10:10-10:15: bounce from VWAP
            ltp = 2820 + ((t - 3300) / 300) * 14  # → 2834
        else:                # after 10:15: continue up
            ltp = 2834 + ((t - 3600) / 16200) * 10
        volume = min(t * 3500, 35_000_000)
        return round(ltp, 2), volume


class TCSScenario(StockScenario):
    """Noise: flat, no triggers."""

    def __init__(self):
        super().__init__(
            symbol="TCS", prev_close=4000.0, prev_high=4010.0,
            adv=3_000_000, open_price=4005.0,
            description="Noise (flat, no signals expected)",
        )

    def state_at(self, t: int) -> tuple[float, int]:
        import math
        ltp = 4005 + 3 * math.sin(t * math.pi / 1000)  # tiny oscillation
        volume = t * 1200
        return round(ltp, 2), min(volume, 15_000_000)


class ITCScenario(StockScenario):
    """Noise: slight downtrend."""

    def __init__(self):
        super().__init__(
            symbol="ITC", prev_close=450.0, prev_high=455.0,
            adv=12_000_000, open_price=448.0,
            description="Noise (slight down, no signals expected)",
        )

    def state_at(self, t: int) -> tuple[float, int]:
        ltp = 448 - (t / 19200) * 5  # slow drift down
        volume = t * 4000
        return round(ltp, 2), min(volume, 40_000_000)


class WIPROScenario(StockScenario):
    """Noise: low volume, no triggers."""

    def __init__(self):
        super().__init__(
            symbol="WIPRO", prev_close=520.0, prev_high=525.0,
            adv=5_000_000, open_price=521.0,
            description="Noise (low volume, no signals expected)",
        )

    def state_at(self, t: int) -> tuple[float, int]:
        import math
        ltp = 521 + 2 * math.sin(t * math.pi / 800)
        volume = t * 400  # very low volume
        return round(ltp, 2), min(volume, 5_000_000)


class Nifty50Scenario(StockScenario):
    """Nifty 50 index (not traded): provides data for regime classification."""

    def __init__(self):
        super().__init__(
            symbol="Nifty 50", prev_close=22500.0, prev_high=22600.0,
            adv=0, open_price=22610.0,
            description="Index (regime classification input, not traded)",
        )

    def state_at(self, t: int) -> tuple[float, int]:
        import math
        if t < 900:          # 9:15-9:30: gap up, first 15-min range ~0.5%
            ltp = 22610 + (t / 900) * 50 + 15 * math.sin(t * math.pi / 200)
        elif t < 1800:       # 9:30-9:45: consolidate
            ltp = 22660 + ((t - 900) / 900) * 10
        elif t < 7200:       # 9:45-11:15: uptrend
            ltp = 22670 + ((t - 1800) / 5400) * 80
        elif t < 13500:      # 11:15-12:45: range-bound
            ltp = 22750 + 20 * math.sin((t - 7200) * math.pi / 3000)
        else:                # 12:45 onward: slow drift
            ltp = 22750 + ((t - 13500) / 6300) * 30
        return round(ltp, 2), 0  # volume not meaningful for index


ALL_SCENARIOS: list[StockScenario] = [
    SBINScenario(),
    INFYScenario(),
    TATAMOTORSScenario(),
    HDFCBANKScenario(),
    RELIANCEScenario(),
    TCSScenario(),
    ITCScenario(),
    WIPROScenario(),
]

# Nifty 50 scenario for regime classification (separate from tradeable stocks)
_NIFTY_SCENARIO = Nifty50Scenario()


# ===========================================================================
#  Fake News Fetcher — synthetic headlines for NSF testing
# ===========================================================================

# Synthetic headlines: some positive, some negative, to exercise the NSF pipeline
_SYNTHETIC_HEADLINES: dict[str, list[dict]] = {
    "SBIN": [
        {"title": "SBI reports strong Q3 earnings, NII grows 18% YoY",
         "source": "Moneycontrol", "sentiment": "positive"},
        {"title": "SBI bad loan ratio declines to 4-year low",
         "source": "Economic Times", "sentiment": "positive"},
    ],
    "INFY": [
        {"title": "Infosys faces US visa scrutiny, may impact margins",
         "source": "Livemint", "sentiment": "negative"},
        {"title": "Infosys wins $500M deal from European bank",
         "source": "Business Standard", "sentiment": "positive"},
    ],
    "TATAMOTORS": [
        {"title": "Tata Motors JLR sales disappoint in February, miss estimates",
         "source": "NDTV Profit", "sentiment": "negative"},
        {"title": "Tata Motors EV division reports heavy losses, cash burn concerns",
         "source": "Reuters", "sentiment": "strong_negative"},
    ],
    "RELIANCE": [
        {"title": "Reliance Jio adds 12M subscribers in January",
         "source": "Moneycontrol", "sentiment": "positive"},
    ],
}


class FakeNewsFetcher:
    """Drop-in replacement for NewsFetcher that returns synthetic headlines."""

    def __init__(self, headlines: dict[str, list[dict]]) -> None:
        self._headlines = headlines
        self._symbol_index: dict[str, str] = {}

    def initialize(self, symbols: list[str]) -> None:
        for sym in symbols:
            self._symbol_index[sym.lower()] = sym

    async def fetch_all_stocks(self) -> dict:
        from signalpilot.intelligence.news_fetcher import RawHeadline
        result: dict[str, list] = {}
        for stock, entries in self._headlines.items():
            result[stock] = [
                RawHeadline(
                    title=e["title"],
                    source=e["source"],
                    published_at=_clock.now,
                    link="",
                    stock_codes=[stock],
                )
                for e in entries
            ]
        return result

    async def fetch_stocks(self, symbols: list[str]) -> dict:
        from signalpilot.intelligence.news_fetcher import RawHeadline
        result: dict[str, list] = {}
        for sym in symbols:
            entries = self._headlines.get(sym, [])
            if entries:
                result[sym] = [
                    RawHeadline(
                        title=e["title"],
                        source=e["source"],
                        published_at=_clock.now,
                        link="",
                        stock_codes=[sym],
                    )
                    for e in entries
                ]
        return result

    async def close(self) -> None:
        pass


# ===========================================================================
#  Console Bot — prints signals to terminal instead of Telegram
# ===========================================================================

class ConsolBot:
    """Drop-in replacement for SignalPilotBot that prints to the terminal."""

    def __init__(self):
        self._signal_count = 0
        self._alert_count = 0

    def set_app(self, app) -> None:
        pass

    async def start(self) -> None:
        print(_header("  Console Bot started (no Telegram)"))

    async def stop(self) -> None:
        print(_dim("  Console Bot stopped"))

    async def send_signal(
        self, signal, is_paper=False, signal_id=None,
        is_watchlisted=False, confirmation_level=None,
        confirmed_by=None, boosted_stars=None, **kwargs,
    ) -> int | None:
        self._signal_count += 1
        c = signal.ranked_signal.candidate
        mode = " [PAPER]" if is_paper else ""
        stars = signal.ranked_signal.signal_strength
        conf = f" [{confirmation_level}]" if confirmation_level else ""
        regime = kwargs.get("market_regime")
        regime_tag = f"  Regime: {regime}\n" if regime else ""
        print(_signal_line(
            f"\n  {'='*60}\n"
            f"  SIGNAL #{signal_id}{mode}{conf}  {'*' * stars}\n"
            f"  {c.strategy_name} | {c.symbol}\n"
            f"  Entry: {c.entry_price:.2f}  SL: {c.stop_loss:.2f}\n"
            f"  T1: {c.target_1:.2f}  T2: {c.target_2:.2f}\n"
            f"  Qty: {signal.quantity}  Capital: Rs {signal.capital_required:,.0f}\n"
            f"  Reason: {c.reason}\n"
            f"{regime_tag}"
            f"  {'='*60}"
        ))
        return signal_id

    async def send_alert(self, message: str) -> None:
        self._alert_count += 1
        print(f"  {_C_MAGENTA}ALERT:{_C_RESET} {message}")

    async def send_exit_alert(self, alert) -> None:
        t = alert.trade
        print(_warn(
            f"\n  EXIT ALERT: {t.symbol} | "
            f"Exit: {alert.exit_type.value if alert.exit_type else 'N/A'} | "
            f"P&L: {alert.pnl_pct:+.1f}%"
        ))


# ===========================================================================
#  Tick Feeder — populates MarketDataStore from scenarios
# ===========================================================================

async def feed_ticks(
    market_data,
    scenarios: list[StockScenario],
    now: datetime,
    prev_volumes: dict[str, int],
) -> None:
    """Feed one round of ticks into the MarketDataStore for all stocks."""
    from signalpilot.db.models import TickData

    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    elapsed = max(0, int((now - market_open).total_seconds()))

    for scenario in scenarios:
        ltp, cum_volume = scenario.state_at(elapsed)
        # Track high/low across the day
        if not hasattr(scenario, "_day_high"):
            scenario._day_high = ltp  # type: ignore[attr-defined]
            scenario._day_low = ltp   # type: ignore[attr-defined]
        scenario._day_high = max(scenario._day_high, ltp)  # type: ignore[attr-defined]
        scenario._day_low = min(scenario._day_low, ltp)    # type: ignore[attr-defined]

        tick = TickData(
            symbol=scenario.symbol,
            ltp=ltp,
            open_price=scenario.open_price,
            high=scenario._day_high,   # type: ignore[attr-defined]
            low=scenario._day_low,     # type: ignore[attr-defined]
            close=scenario.prev_close,
            volume=cum_volume,
            last_traded_timestamp=now,
            updated_at=now,
        )

        await market_data.update_tick(scenario.symbol, tick)
        await market_data.accumulate_volume(scenario.symbol, cum_volume)

        # Compute volume delta for VWAP and candle
        prev_vol = prev_volumes.get(scenario.symbol, 0)
        delta_vol = max(0, cum_volume - prev_vol)
        prev_volumes[scenario.symbol] = cum_volume

        if delta_vol > 0:
            await market_data.update_vwap(scenario.symbol, ltp, float(delta_vol))
            await market_data.update_candle(scenario.symbol, ltp, float(delta_vol), now)

        # Opening range (store ignores after lock)
        await market_data.update_opening_range(scenario.symbol, tick.high, tick.low)


# ===========================================================================
#  Component Wiring — replicate create_app() with fakes
# ===========================================================================

async def create_test_app(
    use_telegram: bool = False,
    db_path: str = ":memory:",
):
    """Wire all real components except external APIs (auth, websocket, historical)."""
    # Load .env from backend/ directory (where it lives in production)
    from dotenv import load_dotenv
    env_path = os.path.join(_BACKEND_DIR, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path, override=False)

    # Set dummy env vars for Angel One (not used in harness) so AppConfig
    # doesn't fail on required fields.  Telegram creds come from .env.
    os.environ.setdefault("ANGEL_API_KEY", "HARNESS_DUMMY")
    os.environ.setdefault("ANGEL_CLIENT_ID", "HARNESS_DUMMY")
    os.environ.setdefault("ANGEL_MPIN", "0000")
    os.environ.setdefault("ANGEL_TOTP_SECRET", "A" * 32)
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "DUMMY:TOKEN")
    os.environ.setdefault("TELEGRAM_CHAT_ID", "0")

    from signalpilot.config import AppConfig
    from signalpilot.data.market_data_store import MarketDataStore
    from signalpilot.db.adaptation_log_repo import AdaptationLogRepository
    from signalpilot.db.circuit_breaker_repo import CircuitBreakerRepository
    from signalpilot.db.config_repo import ConfigRepository
    from signalpilot.db.database import DatabaseManager
    from signalpilot.db.earnings_repo import EarningsCalendarRepository
    from signalpilot.db.hybrid_score_repo import HybridScoreRepository
    from signalpilot.db.metrics import MetricsCalculator
    from signalpilot.db.models import HistoricalReference, ScoringWeights
    from signalpilot.db.news_sentiment_repo import NewsSentimentRepository
    from signalpilot.db.regime_performance_repo import RegimePerformanceRepository
    from signalpilot.db.regime_repo import MarketRegimeRepository
    from signalpilot.db.signal_action_repo import SignalActionRepository
    from signalpilot.db.signal_repo import SignalRepository
    from signalpilot.db.strategy_performance_repo import StrategyPerformanceRepository
    from signalpilot.db.trade_repo import TradeRepository
    from signalpilot.db.watchlist_repo import WatchlistRepository
    from signalpilot.events import (
        AlertMessageEvent, EventBus, ExitAlertEvent,
        StopLossHitEvent, TradeExitedEvent,
    )
    from signalpilot.monitor.adaptive_manager import AdaptiveManager
    from signalpilot.monitor.circuit_breaker import CircuitBreaker
    from signalpilot.monitor.duplicate_checker import DuplicateChecker
    from signalpilot.monitor.exit_monitor import ExitMonitor, TrailingStopConfig
    from signalpilot.monitor.vwap_cooldown import VWAPCooldownTracker
    from signalpilot.pipeline.context import ScanContext
    from signalpilot.pipeline.stage import ScanPipeline
    from signalpilot.pipeline.stages.adaptive_filter import AdaptiveFilterStage
    from signalpilot.pipeline.stages.circuit_breaker_gate import CircuitBreakerGateStage
    from signalpilot.pipeline.stages.composite_scoring import CompositeScoringStage
    from signalpilot.pipeline.stages.confidence import ConfidenceStage
    from signalpilot.pipeline.stages.deduplication import DeduplicationStage
    from signalpilot.pipeline.stages.diagnostic import DiagnosticStage
    from signalpilot.pipeline.stages.exit_monitoring import ExitMonitoringStage
    from signalpilot.pipeline.stages.gap_stock_marking import GapStockMarkingStage
    from signalpilot.pipeline.stages.persist_and_deliver import PersistAndDeliverStage
    from signalpilot.pipeline.stages.ranking import RankingStage
    from signalpilot.pipeline.stages.news_sentiment import NewsSentimentStage
    from signalpilot.pipeline.stages.regime_context import RegimeContextStage
    from signalpilot.pipeline.stages.risk_sizing import RiskSizingStage
    from signalpilot.pipeline.stages.strategy_eval import StrategyEvalStage
    from signalpilot.intelligence.earnings import EarningsCalendar
    from signalpilot.intelligence.news_sentiment import NewsSentimentService
    from signalpilot.intelligence.regime_data import RegimeDataCollector
    from signalpilot.intelligence.regime_classifier import MarketRegimeClassifier
    from signalpilot.intelligence.morning_brief import MorningBriefGenerator
    from signalpilot.intelligence.sentiment_engine import VADERSentimentEngine
    from signalpilot.ranking.composite_scorer import CompositeScorer
    from signalpilot.ranking.confidence import ConfidenceDetector
    from signalpilot.ranking.orb_scorer import ORBScorer
    from signalpilot.ranking.ranker import SignalRanker
    from signalpilot.ranking.scorer import SignalScorer
    from signalpilot.ranking.vwap_scorer import VWAPScorer
    from signalpilot.risk.position_sizer import PositionSizer
    from signalpilot.risk.risk_manager import RiskManager
    from signalpilot.strategy.gap_and_go import GapAndGoStrategy
    from signalpilot.strategy.orb import ORBStrategy
    from signalpilot.strategy.vwap_reversal import VWAPReversalStrategy

    config = AppConfig()
    # Force paper mode off so signals get status="sent" for testing
    config.orb_paper_mode = False
    config.vwap_paper_mode = False
    # Enable regime detection (shadow mode off so modifiers apply)
    if hasattr(config, "regime_enabled"):
        config.regime_enabled = True
    if hasattr(config, "regime_shadow_mode"):
        config.regime_shadow_mode = False
    # Enable news sentiment filter
    if hasattr(config, "news_enabled"):
        config.news_enabled = True
    if hasattr(config, "earnings_blackout_enabled"):
        config.earnings_blackout_enabled = True

    # --- Database ---
    db = DatabaseManager(db_path)
    await db.initialize()
    conn = db.connection

    # --- Repositories ---
    signal_repo = SignalRepository(conn)
    trade_repo = TradeRepository(conn)
    config_repo = ConfigRepository(conn)
    metrics = MetricsCalculator(conn)
    signal_action_repo = SignalActionRepository(conn)
    watchlist_repo = WatchlistRepository(conn)
    hybrid_score_repo = HybridScoreRepository(conn)
    circuit_breaker_repo = CircuitBreakerRepository(conn)
    adaptation_log_repo = AdaptationLogRepository(conn)
    strategy_performance_repo = StrategyPerformanceRepository(conn)

    regime_repo = MarketRegimeRepository(conn)
    regime_performance_repo = RegimePerformanceRepository(conn)
    news_sentiment_repo = NewsSentimentRepository(conn)
    earnings_repo = EarningsCalendarRepository(conn)

    await config_repo.initialize_default(telegram_chat_id="test_harness")

    # --- Market data store ---
    market_data = MarketDataStore()

    # Load historical references for all scenarios
    for s in ALL_SCENARIOS:
        ref = HistoricalReference(
            previous_close=s.prev_close,
            previous_high=s.prev_high,
            average_daily_volume=float(s.adv),
        )
        await market_data.set_historical(s.symbol, ref)

    # Load Nifty 50 historical reference for regime classification
    nifty_ref = HistoricalReference(
        previous_close=_NIFTY_SCENARIO.prev_close,
        previous_high=_NIFTY_SCENARIO.prev_high,
        average_daily_volume=0.0,
    )
    await market_data.set_historical(_NIFTY_SCENARIO.symbol, nifty_ref)

    # --- Regime Detection Intelligence ---
    regime_data_collector = RegimeDataCollector(market_data, config)
    # Pre-populate synthetic global cues and VIX
    regime_data_collector.set_global_cues({
        "sgx_direction": "UP",
        "sgx_change_pct": 0.5,
        "sp500_change_pct": 0.8,
        "nasdaq_change_pct": 1.2,
        "nikkei_change_pct": 0.3,
        "hang_seng_change_pct": -0.2,
    })
    regime_data_collector._session_cache["india_vix"] = 15.5  # slightly elevated
    regime_data_collector.set_prev_day_data({
        "high": 22650.0, "low": 22350.0, "close": 22500.0,
    })

    regime_classifier = MarketRegimeClassifier(
        regime_data_collector, regime_repo, config,
    )
    morning_brief_generator = MorningBriefGenerator(
        data_collector=regime_data_collector,
        watchlist_repo=watchlist_repo,
        config=config,
    )

    # --- News Sentiment Filter ---
    fake_news_fetcher = FakeNewsFetcher(_SYNTHETIC_HEADLINES)
    fake_news_fetcher.initialize([s.symbol for s in ALL_SCENARIOS])
    sentiment_engine = VADERSentimentEngine(
        lexicon_path=getattr(config, "news_financial_lexicon_path", None),
    )
    news_sentiment_service = NewsSentimentService(
        news_fetcher=fake_news_fetcher,
        sentiment_engine=sentiment_engine,
        news_sentiment_repo=news_sentiment_repo,
        earnings_repo=earnings_repo,
        config=config,
    )
    earnings_calendar = EarningsCalendar(earnings_repo, config)

    # Pre-populate an earnings entry for TATAMOTORS on simulation day to test blackout
    from datetime import date as _date_cls
    try:
        await earnings_repo.upsert_earnings(
            stock_code="TATAMOTORS",
            earnings_date=_date_cls(2026, 3, 2),  # simulation day
            quarter="Q3FY26",
            source="harness",
            is_confirmed=True,
        )
    except Exception:
        pass  # table may not support upsert_earnings signature

    # --- Strategies ---
    gap_and_go = GapAndGoStrategy(config)
    orb = ORBStrategy(config, market_data)
    cooldown = VWAPCooldownTracker(
        max_signals_per_stock=config.vwap_max_signals_per_stock,
        cooldown_minutes=config.vwap_cooldown_minutes,
    )
    vwap = VWAPReversalStrategy(config, market_data, cooldown)
    strategies = [gap_and_go, orb, vwap]

    # --- Deduplication ---
    duplicate_checker = DuplicateChecker(signal_repo, trade_repo)

    # --- Ranking ---
    weights = ScoringWeights(
        gap_pct_weight=config.scoring_gap_weight,
        volume_ratio_weight=config.scoring_volume_weight,
        price_distance_weight=config.scoring_price_distance_weight,
    )
    orb_scorer = ORBScorer(
        volume_weight=config.orb_scoring_volume_weight,
        range_weight=config.orb_scoring_range_weight,
        distance_weight=config.orb_scoring_distance_weight,
    )
    vwap_scorer = VWAPScorer(
        volume_weight=config.vwap_scoring_volume_weight,
        touch_weight=config.vwap_scoring_touch_weight,
        trend_weight=config.vwap_scoring_trend_weight,
    )
    scorer = SignalScorer(weights, orb_scorer=orb_scorer, vwap_scorer=vwap_scorer)
    ranker = SignalRanker(scorer, max_signals=config.default_max_positions)

    # --- Phase 3: Confidence & composite ---
    confidence_detector = ConfidenceDetector(signal_repo=signal_repo)
    composite_scorer = CompositeScorer(
        signal_scorer=scorer,
        strategy_performance_repo=strategy_performance_repo,
    )
    capital_allocator = None  # Not needed for harness
    try:
        from signalpilot.risk.capital_allocator import CapitalAllocator
        capital_allocator = CapitalAllocator(
            strategy_performance_repo, config_repo,
            adaptation_log_repo=adaptation_log_repo,
        )
    except ImportError:
        pass

    # --- Risk ---
    position_sizer = PositionSizer()
    risk_manager = RiskManager(position_sizer)

    # --- Event bus ---
    event_bus = EventBus()

    trailing_configs = {
        "Gap & Go": TrailingStopConfig(
            breakeven_trigger_pct=config.trailing_sl_breakeven_trigger_pct,
            trail_trigger_pct=config.trailing_sl_trail_trigger_pct,
            trail_distance_pct=config.trailing_sl_trail_distance_pct,
        ),
        "gap_go": TrailingStopConfig(
            breakeven_trigger_pct=config.trailing_sl_breakeven_trigger_pct,
            trail_trigger_pct=config.trailing_sl_trail_trigger_pct,
            trail_distance_pct=config.trailing_sl_trail_distance_pct,
        ),
        "ORB": TrailingStopConfig(
            breakeven_trigger_pct=config.orb_breakeven_trigger_pct,
            trail_trigger_pct=config.orb_trail_trigger_pct,
            trail_distance_pct=config.orb_trail_distance_pct,
        ),
        "VWAP Reversal": TrailingStopConfig(
            breakeven_trigger_pct=config.vwap_setup1_breakeven_trigger_pct,
            trail_trigger_pct=None, trail_distance_pct=None,
        ),
    }

    async def _noop_alert(alert):
        pass

    exit_monitor = ExitMonitor(
        get_tick=market_data.get_tick,
        alert_callback=_noop_alert,
        breakeven_trigger_pct=config.trailing_sl_breakeven_trigger_pct,
        trail_trigger_pct=config.trailing_sl_trail_trigger_pct,
        trail_distance_pct=config.trailing_sl_trail_distance_pct,
        trailing_configs=trailing_configs,
        close_trade=trade_repo.close_trade,
        event_bus=event_bus,
    )

    # --- Circuit breaker ---
    circuit_breaker = CircuitBreaker(
        circuit_breaker_repo=circuit_breaker_repo,
        config_repo=config_repo,
        sl_limit=config.circuit_breaker_sl_limit,
        event_bus=event_bus,
    )

    # --- Adaptive manager ---
    adaptive_manager = AdaptiveManager(
        adaptation_log_repo=adaptation_log_repo,
        config_repo=config_repo,
        strategy_performance_repo=strategy_performance_repo,
        event_bus=event_bus,
    )

    # --- Bot ---
    console_bot = ConsolBot()  # always print to console for visibility

    if use_telegram:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or token == "DUMMY:TOKEN" or not chat_id or chat_id == "0":
            print(_warn("  --with-telegram requires TELEGRAM_BOT_TOKEN and "
                        "TELEGRAM_CHAT_ID in .env"))
            print(_warn("  Falling back to console mode."))
            use_telegram = False

    if use_telegram:
        from signalpilot.telegram.bot import SignalPilotBot

        async def _get_current_prices(symbols):
            prices = {}
            for sym in symbols:
                tick = await market_data.get_tick(sym)
                if tick:
                    prices[sym] = tick.ltp
            return prices

        real_bot = SignalPilotBot(
            bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            chat_id=os.environ["TELEGRAM_CHAT_ID"],
            signal_repo=signal_repo, trade_repo=trade_repo,
            config_repo=config_repo, metrics_calculator=metrics,
            exit_monitor=exit_monitor, get_current_prices=_get_current_prices,
            signal_action_repo=signal_action_repo, watchlist_repo=watchlist_repo,
            capital_allocator=capital_allocator,
            strategy_performance_repo=strategy_performance_repo,
            circuit_breaker=circuit_breaker, adaptive_manager=adaptive_manager,
            hybrid_score_repo=hybrid_score_repo,
            adaptation_log_repo=adaptation_log_repo,
            regime_classifier=regime_classifier,
            regime_data_collector=regime_data_collector,
            regime_repo=regime_repo,
            morning_brief_generator=morning_brief_generator,
            news_sentiment_service=news_sentiment_service,
            earnings_repo=earnings_repo,
        )

        # Wrap real bot so signals also print to console
        class TelegramWithConsole:
            """Delegates to real Telegram bot AND prints to console."""

            def __init__(self, tg_bot, con_bot):
                self._tg = tg_bot
                self._con = con_bot

            def set_app(self, app):
                self._tg.set_app(app)

            async def start(self):
                await self._tg.start()
                print(_header("  Telegram Bot started (signals go to Telegram + console)"))

            async def stop(self):
                await self._tg.stop()

            async def send_signal(self, signal, **kwargs):
                await self._con.send_signal(signal, **kwargs)
                return await self._tg.send_signal(signal, **kwargs)

            async def send_alert(self, message):
                await self._con.send_alert(message)
                await self._tg.send_alert(message)

            async def send_exit_alert(self, alert):
                await self._con.send_exit_alert(alert)
                await self._tg.send_exit_alert(alert)

        bot = TelegramWithConsole(real_bot, console_bot)
    else:
        bot = console_bot

    # --- Event bus subscriptions ---
    async def _on_exit_alert(event: ExitAlertEvent):
        await bot.send_exit_alert(event.alert)

    async def _on_sl_hit(event: StopLossHitEvent):
        await circuit_breaker.on_sl_hit(event.symbol, event.strategy, event.pnl_amount)

    async def _on_trade_exit(event: TradeExitedEvent):
        today = _clock.now.date()
        await adaptive_manager.on_trade_exit(event.strategy_name, event.is_loss, today)

    async def _on_alert_message(event: AlertMessageEvent):
        await bot.send_alert(event.message)

    event_bus.subscribe(ExitAlertEvent, _on_exit_alert)
    event_bus.subscribe(StopLossHitEvent, _on_sl_hit)
    event_bus.subscribe(TradeExitedEvent, _on_trade_exit)
    event_bus.subscribe(AlertMessageEvent, _on_alert_message)

    # --- Build pipeline ---
    # Use a fake websocket stub for DiagnosticStage
    class _FakeWS:
        is_connected = True
    fake_ws = _FakeWS()

    signal_stages = [
        CircuitBreakerGateStage(circuit_breaker),
        RegimeContextStage(regime_classifier, config),
        StrategyEvalStage(strategies, config_repo, market_data),
        GapStockMarkingStage(),
        DeduplicationStage(duplicate_checker),
        ConfidenceStage(confidence_detector),
        CompositeScoringStage(composite_scorer),
        AdaptiveFilterStage(adaptive_manager),
        RankingStage(ranker),
        NewsSentimentStage(news_sentiment_service, earnings_repo, config),
        RiskSizingStage(risk_manager, trade_repo),
        PersistAndDeliverStage(signal_repo, hybrid_score_repo, bot, adaptive_manager, config),
        DiagnosticStage(fake_ws),
    ]
    always_stages = [
        ExitMonitoringStage(trade_repo, exit_monitor, signal_repo),
    ]
    pipeline = ScanPipeline(signal_stages=signal_stages, always_stages=always_stages)

    return {
        "pipeline": pipeline,
        "market_data": market_data,
        "bot": bot,
        "db": db,
        "signal_repo": signal_repo,
        "trade_repo": trade_repo,
        "config": config,
        "use_telegram": use_telegram,
        "exit_monitor": exit_monitor,
        "circuit_breaker": circuit_breaker,
        "strategies": strategies,
        "regime_classifier": regime_classifier,
        "regime_data_collector": regime_data_collector,
        "regime_repo": regime_repo,
        "morning_brief_generator": morning_brief_generator,
        "news_sentiment_service": news_sentiment_service,
        "earnings_repo": earnings_repo,
        "earnings_calendar": earnings_calendar,
    }


# ===========================================================================
#  Simulation Loop
# ===========================================================================

PHASE_START_TIMES = {
    "pre_market": time(8, 40),
    "opening": time(9, 15),
    "entry_window": time(9, 30),
    "continuous": time(9, 45),
    "wind_down": time(14, 30),
}


async def run_simulation(args):
    """Main simulation entry point."""
    from signalpilot.pipeline.context import ScanContext
    from signalpilot.utils.market_calendar import StrategyPhase, get_current_phase

    # Patch datetime in all modules
    _patch_datetime_modules()

    # Determine start time
    start_phase = args.phase
    if start_phase and start_phase in PHASE_START_TIMES:
        start_time = PHASE_START_TIMES[start_phase]
        start_dt = datetime(2026, 3, 2, start_time.hour, start_time.minute, tzinfo=IST)
    else:
        start_dt = datetime(2026, 3, 2, 9, 10, tzinfo=IST)

    _clock.set(start_dt)
    speed = args.speed  # simulated seconds per real second

    print(_header(f"\n{'='*64}"))
    print(_header(f"  SignalPilot Test Harness"))
    print(_header(f"  Simulated date: Monday, 2 March 2026"))
    print(_header(f"  Start time: {start_dt.strftime('%H:%M:%S')} IST"))
    print(_header(f"  Speed: {speed}x (1 real second = {speed} sim seconds)"))
    print(_header(f"  Mode: {'Telegram + Console' if args.with_telegram else 'Console only'}"))
    print(_header(f"  Database: {args.db_path}"))
    est_duration = (19200 - max(0, (start_dt.hour * 3600 + start_dt.minute * 60 - 9 * 3600 - 10 * 60))) / speed
    print(_header(f"  Estimated duration: {est_duration / 60:.1f} minutes"))
    if args.with_telegram:
        print(_header(f"  Signal expiry: 30 sim min = {30 * 60 / speed:.0f} real seconds"))
        print(_header(f"  Click TAKEN/SKIP/WATCH on Telegram within that window!"))
    print(_header(f"{'='*64}\n"))

    # Create app
    components = await create_test_app(
        use_telegram=args.with_telegram,
        db_path=args.db_path,
    )
    pipeline = components["pipeline"]
    market_data = components["market_data"]
    bot = components["bot"]
    signal_repo = components["signal_repo"]
    trade_repo = components["trade_repo"]
    strategies = components["strategies"]
    regime_classifier = components["regime_classifier"]
    regime_data_collector = components["regime_data_collector"]
    morning_brief_generator = components["morning_brief_generator"]
    news_sentiment_service = components["news_sentiment_service"]

    if components["use_telegram"]:
        await bot.start()

    # Pre-populate ticks if starting after 9:15
    prev_volumes: dict[str, int] = {}
    market_open = start_dt.replace(hour=9, minute=15, second=0, microsecond=0)
    if start_dt > market_open:
        print(_dim("  Pre-populating market data up to start time..."))
        warmup_time = market_open
        warmup_step = timedelta(seconds=30)
        while warmup_time <= start_dt:
            _clock.set(warmup_time)
            await feed_ticks(market_data, ALL_SCENARIOS, warmup_time, prev_volumes)
            await feed_ticks(market_data, [_NIFTY_SCENARIO], warmup_time, prev_volumes)
            warmup_time += warmup_step
        # Lock opening ranges if starting at or after 9:45
        if start_dt >= start_dt.replace(hour=9, minute=45, second=0):
            await market_data.lock_opening_ranges()
            print(_dim("  Opening ranges pre-locked"))
        _clock.set(start_dt)
        print(_dim(f"  Warmed up to {start_dt.strftime('%H:%M')}"))

    # Reset strategies for fresh start
    for strat in strategies:
        if hasattr(strat, "reset"):
            strat.reset()

    # State
    accepting_signals = True
    prev_phase = None
    signals_generated = 0
    ranges_locked = start_dt >= start_dt.replace(hour=9, minute=45, second=0)
    signals_stopped = False
    sim_end = start_dt.replace(hour=15, minute=35, second=0, microsecond=0)
    cycle_count = 0
    last_status_time = start_dt

    # Regime lifecycle event flags
    morning_brief_sent = start_dt.time() >= time(8, 50)
    regime_classified = start_dt.time() >= time(9, 35)
    regime_reclass_11_done = start_dt.time() >= time(11, 5)
    regime_reclass_13_done = start_dt.time() >= time(13, 5)
    regime_reclass_1430_done = False  # always check (combines with wind_down)
    regime_classifier.reset_daily()

    # News Sentiment Filter lifecycle event flags
    news_pre_market_done = start_dt.time() >= time(8, 35)
    news_refresh_11_done = start_dt.time() >= time(11, 20)
    news_refresh_13_done = start_dt.time() >= time(13, 20)

    print(_header("  Simulation started. Press Ctrl+C to abort.\n"))

    try:
        while _clock.now < sim_end:
            now = _clock.now
            phase = get_current_phase(now)

            # Phase transition logging
            if phase != prev_phase:
                print(_phase_line(
                    f"\n  --- Phase: {phase.value.upper()} "
                    f"({now.strftime('%H:%M:%S')} IST) ---"
                ))
                prev_phase = phase

            # Lifecycle events at key times
            if not ranges_locked and now.time() >= time(9, 45):
                await market_data.lock_opening_ranges()
                ranges_locked = True
                print(_phase_line("  Opening ranges locked for ORB detection"))

            if not signals_stopped and now.time() >= time(14, 30):
                accepting_signals = False
                signals_stopped = True
                await bot.send_alert(
                    "No new signals after 2:30 PM. Monitoring existing positions only."
                )

            # --- News Sentiment lifecycle events ---
            if not news_pre_market_done and now.time() >= time(8, 30):
                news_pre_market_done = True
                try:
                    count = await news_sentiment_service.fetch_and_analyze_all()
                    print(_phase_line(
                        f"\n  --- PRE-MARKET NEWS FETCH (8:30 AM): "
                        f"{count} headlines analyzed ---"
                    ))
                except Exception as e:
                    print(_warn(f"  Pre-market news fetch failed: {e}"))

            if not news_refresh_11_done and now.time() >= time(11, 15):
                news_refresh_11_done = True
                try:
                    count = await news_sentiment_service.fetch_and_analyze_stocks()
                    print(_dim(f"    News cache refreshed (11:15): {count} headlines"))
                except Exception as e:
                    print(_warn(f"  News refresh (11:15) failed: {e}"))

            if not news_refresh_13_done and now.time() >= time(13, 15):
                news_refresh_13_done = True
                try:
                    count = await news_sentiment_service.fetch_and_analyze_stocks()
                    print(_dim(f"    News cache refreshed (13:15): {count} headlines"))
                except Exception as e:
                    print(_warn(f"  News refresh (13:15) failed: {e}"))

            # --- Regime lifecycle events ---
            if not morning_brief_sent and now.time() >= time(8, 45):
                morning_brief_sent = True
                try:
                    brief = await morning_brief_generator.generate()
                    # Strip HTML tags for console
                    import re as _re
                    clean = _re.sub(r"<[^>]+>", "", brief)
                    print(_phase_line(f"\n  --- MORNING BRIEF (8:45 AM) ---"))
                    for line in clean.split("\n"):
                        print(f"  {line}")
                    if components["use_telegram"]:
                        await bot.send_alert(brief)
                except Exception as e:
                    print(_warn(f"  Morning brief failed: {e}"))

            if not regime_classified and now.time() >= time(9, 30):
                regime_classified = True
                try:
                    classification = await regime_classifier.classify()
                    print(_phase_line(
                        f"\n  --- REGIME CLASSIFIED (9:30 AM): "
                        f"{classification.regime} "
                        f"(confidence={classification.confidence:.2f}) ---"
                    ))
                    print(_dim(
                        f"    Scores: trending={classification.trending_score:.3f}"
                        f" ranging={classification.ranging_score:.3f}"
                        f" volatile={classification.volatile_score:.3f}"
                    ))
                    if classification.strategy_weights:
                        print(_dim(f"    Weights: {classification.strategy_weights}"))
                    if components["use_telegram"]:
                        from signalpilot.telegram.formatters import format_classification_notification
                        msg = format_classification_notification(classification)
                        await bot.send_alert(msg)
                except Exception as e:
                    print(_warn(f"  Regime classification failed: {e}"))

            if not regime_reclass_11_done and now.time() >= time(11, 0):
                regime_reclass_11_done = True
                # Simulate VIX spike for potential reclassification
                regime_data_collector._session_cache["india_vix"] = 18.5
                print(_dim("    (Simulated VIX spike: 15.5 -> 18.5)"))
                try:
                    reclass = await regime_classifier.check_reclassify("11:00")
                    if reclass:
                        print(_phase_line(
                            f"\n  --- REGIME RE-CLASSIFIED (11:00): "
                            f"{reclass.previous_regime} -> {reclass.regime} ---"
                        ))
                    else:
                        print(_dim("    No re-classification triggered at 11:00"))
                except Exception as e:
                    print(_warn(f"  Regime re-classification (11:00) failed: {e}"))

            if not regime_reclass_13_done and now.time() >= time(13, 0):
                regime_reclass_13_done = True
                try:
                    reclass = await regime_classifier.check_reclassify("13:00")
                    if reclass:
                        print(_phase_line(
                            f"\n  --- REGIME RE-CLASSIFIED (13:00): "
                            f"{reclass.previous_regime} -> {reclass.regime} ---"
                        ))
                    else:
                        print(_dim("    No re-classification triggered at 13:00"))
                except Exception as e:
                    print(_warn(f"  Regime re-classification (13:00) failed: {e}"))

            if not regime_reclass_1430_done and now.time() >= time(14, 30):
                regime_reclass_1430_done = True
                try:
                    reclass = await regime_classifier.check_reclassify("14:30")
                    if reclass:
                        print(_phase_line(
                            f"\n  --- REGIME RE-CLASSIFIED (14:30): "
                            f"{reclass.previous_regime} -> {reclass.regime} ---"
                        ))
                    else:
                        print(_dim("    No re-classification triggered at 14:30"))
                except Exception as e:
                    print(_warn(f"  Regime re-classification (14:30) failed: {e}"))

            # Feed ticks (only during market hours)
            if now.time() >= time(9, 15):
                await feed_ticks(market_data, ALL_SCENARIOS, now, prev_volumes)
                await feed_ticks(market_data, [_NIFTY_SCENARIO], now, prev_volumes)

            # Run pipeline
            if now.time() >= time(9, 15) and phase != StrategyPhase.PRE_MARKET:
                cycle_id = uuid.uuid4().hex[:8]
                ctx = ScanContext(
                    cycle_id=cycle_id,
                    now=now,
                    phase=phase,
                    accepting_signals=accepting_signals,
                )
                ctx = await pipeline.run(ctx)
                accepting_signals = ctx.accepting_signals
                cycle_count += 1

                # Print suppressed signals from NSF
                if hasattr(ctx, "suppressed_signals") and ctx.suppressed_signals:
                    for ss in ctx.suppressed_signals:
                        print(_warn(
                            f"  SUPPRESSED: {ss.symbol} ({ss.strategy}) "
                            f"| {ss.sentiment_label} (score={ss.sentiment_score:.2f})"
                            f" | {ss.reason}"
                        ))

                if ctx.final_signals:
                    signals_generated += len(ctx.final_signals)
                    # In Telegram mode, pause to give user time to interact
                    if components["use_telegram"]:
                        pause_secs = 15
                        print(_phase_line(
                            f"  Pausing {pause_secs}s for Telegram interaction "
                            f"(click TAKEN/SKIP/WATCH)..."
                        ))
                        await asyncio.sleep(pause_secs)

            # Check for new trades (user clicked TAKEN)
            try:
                active_trades = await trade_repo.get_active_trades()
                if active_trades and cycle_count % 5 == 0:
                    trade_syms = [t.symbol for t in active_trades]
                    print(_dim(
                        f"  Active trades ({len(active_trades)}): "
                        f"{', '.join(trade_syms)}"
                    ))
            except Exception:
                pass

            # Periodic status every 15 simulated minutes
            if (now - last_status_time).total_seconds() >= 900:
                tick_summary = []
                for s in ALL_SCENARIOS[:5]:
                    ltp, vol = s.state_at(
                        max(0, int((now - market_open).total_seconds()))
                    )
                    tick_summary.append(f"{s.symbol}={ltp:.0f}")
                regime_tag = ""
                cr = regime_classifier.get_cached_regime()
                if cr:
                    regime_tag = f" | regime={cr.regime}"
                print(_dim(
                    f"  [{now.strftime('%H:%M')}] "
                    f"cycle={cycle_count} signals={signals_generated}"
                    f"{regime_tag} | {', '.join(tick_summary)}"
                ))
                last_status_time = now

            # Advance clock
            _clock.advance(timedelta(seconds=speed))
            await asyncio.sleep(1.0)

    except KeyboardInterrupt:
        print(_warn("\n\n  Simulation interrupted by user."))
    except Exception as e:
        print(_warn(f"\n  Simulation error: {e}"))
        logging.exception("Harness error")

    # --- Summary ---
    now = _clock.now
    print(_header(f"\n{'='*64}"))
    print(_header(f"  Simulation Complete"))
    print(_header(f"  Ended at: {now.strftime('%H:%M:%S')} IST"))
    print(_header(f"  Cycles run: {cycle_count}"))
    print(_header(f"  Signals generated: {signals_generated}"))

    # Regime summary
    cached_regime = regime_classifier.get_cached_regime()
    if cached_regime:
        print(_header(
            f"  Regime: {cached_regime.regime} "
            f"(confidence={cached_regime.confidence:.2f})"
        ))
        if cached_regime.is_reclassification:
            print(_header(f"  Re-classified from: {cached_regime.previous_regime}"))
    else:
        print(_header(f"  Regime: not classified"))

    # Query DB for results
    try:
        all_signals = await signal_repo.get_signals_by_date(start_dt.date())
        all_trades = await trade_repo.get_trades_by_date(start_dt.date())
        print(_header(f"  Signals in DB: {len(all_signals)}"))
        print(_header(f"  Trades in DB: {len(all_trades)}"))

        if all_signals:
            print(_header(f"\n  Signal Details:"))
            for sig in all_signals:
                regime_tag = ""
                if hasattr(sig, "market_regime") and sig.market_regime:
                    regime_tag = f" | Regime={sig.market_regime}"
                print(f"    {sig.strategy:15s} | {sig.symbol:12s} | "
                      f"Entry={sig.entry_price:.2f} | "
                      f"SL={sig.stop_loss:.2f} | "
                      f"T1={sig.target_1:.2f} | "
                      f"Status={sig.status}{regime_tag}")
        if all_trades:
            print(_header(f"\n  Trade Details:"))
            for tr in all_trades:
                exit_info = (
                    f"Exit={tr.exit_price:.2f} ({tr.exit_reason}) "
                    f"P&L={tr.pnl_pct:+.1f}%"
                    if tr.exit_price else "OPEN"
                )
                print(f"    {tr.strategy:15s} | {tr.symbol:12s} | "
                      f"Entry={tr.entry_price:.2f} | {exit_info}")
    except Exception as e:
        print(_dim(f"  (Could not query DB: {e})"))

    print(_header(f"{'='*64}\n"))

    # Cleanup
    try:
        news_sentiment_service.clear_unsuppress_overrides()
        await news_sentiment_service.purge_old_entries(48)
    except Exception:
        pass
    if components["use_telegram"]:
        await bot.stop()
    await components["db"].close()


# ===========================================================================
#  Entry Point
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="SignalPilot Test Harness — simulate a full trading day",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 -m scripts.test_harness                     # Console only, 60x speed
  python3 -m scripts.test_harness --speed 300         # Fast (day in ~1.3 min)
  python3 -m scripts.test_harness --with-telegram     # Telegram + DB, 20x speed
  python3 -m scripts.test_harness --with-telegram --speed 10  # Slower for clicking
  python3 -m scripts.test_harness --phase continuous  # Start at 9:45 AM
  python3 -m scripts.test_harness --db-path test.db   # Persist DB to file

With --with-telegram:
  - Signals are sent to Telegram with [TAKEN] [SKIP] [WATCH] buttons
  - Click TAKEN to create a trade (tracked in DB + exit monitor)
  - Exit alerts sent when SL/T1/T2 hit
  - DB saved to harness.db (inspect with: sqlite3 harness.db "SELECT * FROM signals")
  - Speed defaults to 20x so you have ~90 real seconds to click before expiry
        """,
    )
    parser.add_argument(
        "--speed", type=int, default=None,
        help="Time multiplier: 1 real second = N simulated seconds "
             "(default: 20 with --with-telegram, 60 without)",
    )
    parser.add_argument(
        "--with-telegram", action="store_true",
        help="Send signals to real Telegram with inline buttons "
             "(requires TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env)",
    )
    parser.add_argument(
        "--phase",
        choices=["pre_market", "opening", "entry_window", "continuous", "wind_down"],
        help="Start simulation at a specific phase (pre_market starts at 8:40 for morning brief)",
    )
    parser.add_argument(
        "--db-path", default=None,
        help="SQLite database path (default: harness.db with --with-telegram, "
             ":memory: without)",
    )
    parser.add_argument(
        "--log-level", default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level for SignalPilot internals (default: WARNING)",
    )
    args = parser.parse_args()

    # Smart defaults for Telegram mode
    if args.with_telegram:
        if args.speed is None:
            args.speed = 20  # slower so user can click buttons
        if args.db_path is None:
            args.db_path = "harness.db"
    else:
        if args.speed is None:
            args.speed = 60
        if args.db_path is None:
            args.db_path = ":memory:"

    # Configure logging — keep harness output clean, suppress library noise
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    asyncio.run(run_simulation(args))


if __name__ == "__main__":
    main()
