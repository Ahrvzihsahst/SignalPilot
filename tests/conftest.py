"""Shared test fixtures for SignalPilot.

Provides database, configuration, sample model objects, and trade data
fixtures used across all test modules.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from signalpilot.config import AppConfig
from signalpilot.db.config_repo import ConfigRepository
from signalpilot.db.database import DatabaseManager
from signalpilot.db.metrics import MetricsCalculator
from signalpilot.db.models import (
    CandidateSignal,
    FinalSignal,
    HistoricalReference,
    Instrument,
    RankedSignal,
    SignalActionRecord,
    SignalDirection,
    TickData,
    TradeRecord,
    WatchlistRecord,
)
from signalpilot.db.signal_repo import SignalRepository
from signalpilot.db.trade_repo import TradeRepository
from signalpilot.utils.constants import IST

TEST_DATA_DIR = Path(__file__).parent / "test_data"


# ---------------------------------------------------------------------------
# Environment & Config
# ---------------------------------------------------------------------------


@pytest.fixture
def required_env(monkeypatch):
    """Set all required environment variables for AppConfig."""
    monkeypatch.setenv("ANGEL_API_KEY", "test_key")
    monkeypatch.setenv("ANGEL_CLIENT_ID", "test_client")
    monkeypatch.setenv("ANGEL_MPIN", "1234")
    monkeypatch.setenv("ANGEL_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")


@pytest.fixture
def app_config(required_env):
    """AppConfig with test-appropriate values (small capital, in-memory DB)."""
    return AppConfig(
        db_path=":memory:",
        default_capital=100000.0,
        default_max_positions=5,
        signal_expiry_minutes=30,
    )


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


@pytest.fixture
async def db():
    """In-memory SQLite database with full schema, auto-cleaned after test.

    Note: tests/test_integration/conftest.py defines its own ``db`` fixture.
    Pytest uses the most-local fixture, so integration tests keep using theirs.
    """
    manager = DatabaseManager(":memory:")
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.fixture
async def repos(db):
    """All four repositories backed by the in-memory database.

    Note: tests/test_integration/conftest.py defines its own ``repos`` fixture.
    Pytest uses the most-local fixture, so integration tests keep using theirs.
    """
    conn = db.connection
    return {
        "signal_repo": SignalRepository(conn),
        "trade_repo": TradeRepository(conn),
        "config_repo": ConfigRepository(conn),
        "metrics": MetricsCalculator(conn),
    }


# ---------------------------------------------------------------------------
# Sample Signal Objects
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_candidate():
    """A valid Gap & Go CandidateSignal (4% gap, 1.2x volume)."""
    return CandidateSignal(
        symbol="SBIN",
        direction=SignalDirection.BUY,
        strategy_name="Gap & Go",
        entry_price=104.50,
        stop_loss=100.0,
        target_1=109.73,
        target_2=111.82,
        gap_pct=4.0,
        volume_ratio=1.2,
        price_distance_from_open_pct=0.5,
        reason="Gap up 4.0%, volume 1.2x ADV",
        generated_at=datetime(2025, 1, 15, 9, 35, tzinfo=IST),
    )


@pytest.fixture
def sample_ranked(sample_candidate):
    """A RankedSignal with 4-star rating, rank 1."""
    return RankedSignal(
        candidate=sample_candidate,
        composite_score=0.82,
        rank=1,
        signal_strength=4,
    )


@pytest.fixture
def sample_final_signal(sample_ranked):
    """A fully sized FinalSignal ready for delivery."""
    return FinalSignal(
        ranked_signal=sample_ranked,
        quantity=15,
        capital_required=1567.50,
        expires_at=datetime(2025, 1, 15, 10, 5, tzinfo=IST),
    )


# ---------------------------------------------------------------------------
# Sample Market Data
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_instruments():
    """List of 5 Nifty 500 instruments for testing."""
    return [
        Instrument(
            symbol="SBIN", name="State Bank of India",
            angel_token="3045", exchange="NSE",
            nse_symbol="SBIN-EQ", yfinance_symbol="SBIN.NS",
        ),
        Instrument(
            symbol="TCS", name="Tata Consultancy Services",
            angel_token="11536", exchange="NSE",
            nse_symbol="TCS-EQ", yfinance_symbol="TCS.NS",
        ),
        Instrument(
            symbol="RELIANCE", name="Reliance Industries",
            angel_token="2885", exchange="NSE",
            nse_symbol="RELIANCE-EQ", yfinance_symbol="RELIANCE.NS",
        ),
        Instrument(
            symbol="INFY", name="Infosys",
            angel_token="1594", exchange="NSE",
            nse_symbol="INFY-EQ", yfinance_symbol="INFY.NS",
        ),
        Instrument(
            symbol="HDFCBANK", name="HDFC Bank",
            angel_token="1333", exchange="NSE",
            nse_symbol="HDFCBANK-EQ", yfinance_symbol="HDFCBANK.NS",
        ),
    ]


@pytest.fixture
def sample_historical_refs():
    """Dict of symbol -> HistoricalReference for gap/volume checks."""
    return {
        "SBIN": HistoricalReference(
            previous_close=500.0, previous_high=510.0, average_daily_volume=5_000_000,
        ),
        "TCS": HistoricalReference(
            previous_close=3500.0, previous_high=3550.0, average_daily_volume=1_500_000,
        ),
        "RELIANCE": HistoricalReference(
            previous_close=2500.0, previous_high=2530.0, average_daily_volume=3_000_000,
        ),
        "INFY": HistoricalReference(
            previous_close=1500.0, previous_high=1520.0, average_daily_volume=2_000_000,
        ),
        "HDFCBANK": HistoricalReference(
            previous_close=1500.0, previous_high=1510.0, average_daily_volume=4_000_000,
        ),
    }


@pytest.fixture
def sample_tick():
    """A single TickData sample for SBIN with 4% gap-up."""
    now = datetime(2025, 1, 15, 9, 35, tzinfo=IST)
    return TickData(
        symbol="SBIN",
        ltp=524.0,
        open_price=520.0,
        high=525.0,
        low=518.0,
        close=500.0,
        volume=3_200_000,
        last_traded_timestamp=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Sample Trade Data: 7 wins, 5 losses, total P&L = +2340.0
# ---------------------------------------------------------------------------

_TRADE_BASE_DATE = date(2025, 1, 15)
_TRADE_BASE_DT = datetime(2025, 1, 15, 9, 40, tzinfo=IST)

# fmt: off
_SAMPLE_TRADES = [
    # --- 7 Wins (total: +2740) ---
    {"sig": 1,  "sym": "SBIN",      "entry": 500.0,  "exit": 525.0,  "sl": 485.0,  "t1": 525.0,  "t2": 535.0,  "qty": 30,  "reason": "t1_hit"},
    {"sig": 2,  "sym": "TCS",       "entry": 3500.0, "exit": 3675.0, "sl": 3395.0, "t1": 3675.0, "t2": 3745.0, "qty": 3,   "reason": "t2_hit"},
    {"sig": 3,  "sym": "RELIANCE",  "entry": 2500.0, "exit": 2550.0, "sl": 2425.0, "t1": 2625.0, "t2": 2675.0, "qty": 4,   "reason": "trailing_sl"},
    {"sig": 4,  "sym": "INFY",      "entry": 1500.0, "exit": 1575.0, "sl": 1455.0, "t1": 1575.0, "t2": 1605.0, "qty": 5,   "reason": "t1_hit"},
    {"sig": 5,  "sym": "HDFC",      "entry": 1500.0, "exit": 1560.0, "sl": 1455.0, "t1": 1575.0, "t2": 1605.0, "qty": 5,   "reason": "trailing_sl"},
    {"sig": 6,  "sym": "ICICIBANK", "entry": 1000.0, "exit": 1010.0, "sl": 970.0,  "t1": 1050.0, "t2": 1070.0, "qty": 11,  "reason": "trailing_sl"},
    {"sig": 7,  "sym": "AXISBANK",  "entry": 800.0,  "exit": 860.0,  "sl": 776.0,  "t1": 840.0,  "t2": 856.0,  "qty": 8,   "reason": "t2_hit"},
    # --- 5 Losses (total: -400) ---
    {"sig": 8,  "sym": "WIPRO",     "entry": 450.0,  "exit": 441.0,  "sl": 441.0,  "t1": 472.5,  "t2": 481.5,  "qty": 10,  "reason": "sl_hit"},
    {"sig": 9,  "sym": "HCLTECH",   "entry": 1400.0, "exit": 1372.0, "sl": 1372.0, "t1": 1470.0, "t2": 1498.0, "qty": 5,   "reason": "sl_hit"},
    {"sig": 10, "sym": "BAJFINANCE","entry": 7000.0, "exit": 6930.0, "sl": 6930.0, "t1": 7350.0, "t2": 7490.0, "qty": 1,   "reason": "sl_hit"},
    {"sig": 11, "sym": "MARUTI",    "entry": 10000.0,"exit": 9940.0, "sl": 9700.0, "t1":10500.0, "t2":10700.0, "qty": 1,   "reason": "time_exit"},
    {"sig": 12, "sym": "TATAMOTORS","entry": 600.0,  "exit": 596.0,  "sl": 582.0,  "t1": 630.0,  "t2": 642.0,  "qty": 10,  "reason": "sl_hit"},
]
# fmt: on

# Verify all docstring claims at import time
_wins = [t for t in _SAMPLE_TRADES if (t["exit"] - t["entry"]) * t["qty"] > 0]
_losses = [t for t in _SAMPLE_TRADES if (t["exit"] - t["entry"]) * t["qty"] < 0]
assert len(_wins) == 7
assert len(_losses) == 5
assert sum((t["exit"] - t["entry"]) * t["qty"] for t in _SAMPLE_TRADES) == 2340.0
_win_total = sum((t["exit"] - t["entry"]) * t["qty"] for t in _wins)
_loss_total = sum((t["exit"] - t["entry"]) * t["qty"] for t in _losses)
assert round(_win_total / 7, 2) == 391.43  # avg_win
assert round(_loss_total / 5, 2) == -80.0   # avg_loss
_best = max(_SAMPLE_TRADES, key=lambda t: (t["exit"] - t["entry"]) * t["qty"])
_worst = min(_SAMPLE_TRADES, key=lambda t: (t["exit"] - t["entry"]) * t["qty"])
assert _best["sym"] == "SBIN" and ((_best["exit"] - _best["entry"]) * _best["qty"]) == 750.0
assert _worst["sym"] == "HCLTECH" and ((_worst["exit"] - _worst["entry"]) * _worst["qty"]) == -140.0


@pytest.fixture
def sample_trades():
    """12 completed TradeRecords: 7 wins, 5 losses, total P&L = +2340.0.

    Known aggregates for verification:
        wins=7, losses=5, win_rate=58.33%
        total_pnl=+2340.0, avg_win=+391.43, avg_loss=-80.0
        best_trade=SBIN (+750.0), worst_trade=HCLTECH (-140.0)
    """
    records = []
    for i, t in enumerate(_SAMPLE_TRADES):
        pnl = (t["exit"] - t["entry"]) * t["qty"]
        pnl_pct = ((t["exit"] - t["entry"]) / t["entry"]) * 100
        taken_at = _TRADE_BASE_DT + timedelta(minutes=i * 5)
        exited_at = taken_at + timedelta(minutes=30 + i * 3)
        records.append(
            TradeRecord(
                signal_id=t["sig"],
                date=_TRADE_BASE_DATE,
                symbol=t["sym"],
                entry_price=t["entry"],
                exit_price=t["exit"],
                stop_loss=t["sl"],
                target_1=t["t1"],
                target_2=t["t2"],
                quantity=t["qty"],
                pnl_amount=pnl,
                pnl_pct=round(pnl_pct, 2),
                exit_reason=t["reason"],
                taken_at=taken_at,
                exited_at=exited_at,
            )
        )
    return records


# ---------------------------------------------------------------------------
# Test Data File Loader
# ---------------------------------------------------------------------------


def load_test_data(filename: str) -> dict | list:
    """Load a JSON file from tests/test_data/.

    Keys prefixed with ``_`` (e.g. ``_description``, ``_note``) are
    documentation-only; filter them with ``if not key.startswith("_")``.
    """
    path = TEST_DATA_DIR / filename
    if not path.exists():
        available = sorted(f.name for f in TEST_DATA_DIR.glob("*.json"))
        raise FileNotFoundError(
            f"Test data file not found: {path}. Available: {available}"
        )
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Phase 2 Sample Signal Objects
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_orb_candidate():
    """A valid ORB CandidateSignal with breakout data."""
    return CandidateSignal(
        symbol="TCS",
        direction=SignalDirection.BUY,
        strategy_name="ORB",
        entry_price=3550.0,
        stop_loss=3500.0,
        target_1=3603.25,
        target_2=3638.75,
        gap_pct=0.0,
        volume_ratio=2.0,
        reason="ORB breakout: range 3500-3550, volume 2.0x",
        generated_at=datetime(2025, 1, 15, 10, 0, tzinfo=IST),
    )


@pytest.fixture
def sample_vwap_candidate():
    """A VWAP Uptrend Pullback CandidateSignal."""
    return CandidateSignal(
        symbol="RELIANCE",
        direction=SignalDirection.BUY,
        strategy_name="VWAP Reversal",
        entry_price=2520.0,
        stop_loss=2507.4,
        target_1=2545.2,
        target_2=2557.8,
        gap_pct=0.0,
        volume_ratio=1.5,
        reason="VWAP Reversal: uptrend pullback to VWAP",
        generated_at=datetime(2025, 1, 15, 10, 30, tzinfo=IST),
        setup_type="uptrend_pullback",
    )


@pytest.fixture
def sample_vwap_reclaim_candidate():
    """A VWAP Reclaim CandidateSignal (Higher Risk)."""
    return CandidateSignal(
        symbol="INFY",
        direction=SignalDirection.BUY,
        strategy_name="VWAP Reversal",
        entry_price=1510.0,
        stop_loss=1495.0,
        target_1=1525.1,
        target_2=1532.65,
        gap_pct=0.0,
        volume_ratio=1.8,
        reason="VWAP Reversal: reclaim (Higher Risk)",
        generated_at=datetime(2025, 1, 15, 11, 0, tzinfo=IST),
        setup_type="vwap_reclaim",
    )


# ---------------------------------------------------------------------------
# Phase 4 Sample Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_signal_action():
    """A SignalActionRecord with realistic values."""
    return SignalActionRecord(
        signal_id=1,
        action="taken",
        reason=None,
        response_time_ms=3500,
        acted_at=datetime(2025, 1, 15, 9, 40, tzinfo=IST),
        message_id=12345,
    )


@pytest.fixture
def sample_watchlist_entry():
    """A WatchlistRecord with 5-day expiry."""
    added = datetime(2025, 1, 15, 9, 40, tzinfo=IST)
    return WatchlistRecord(
        symbol="SBIN",
        signal_id=None,
        strategy="Gap & Go",
        entry_price=104.50,
        added_at=added,
        expires_at=added + timedelta(days=5),
        triggered_count=0,
        last_triggered_at=None,
    )
