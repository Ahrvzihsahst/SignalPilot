"""Dashboard API test fixtures."""

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient

from signalpilot.db.database import DatabaseManager
from signalpilot.utils.constants import IST


def _build_test_app() -> FastAPI:
    """Build a FastAPI app without lifespan (state set by fixture)."""
    app = FastAPI(title="SignalPilot Dashboard Test", version="3.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from signalpilot.dashboard.routes import (
        adaptation,
        allocation,
        circuit_breaker,
        performance,
        settings,
        signals,
        strategies,
        trades,
    )

    app.include_router(signals.router, prefix="/api/signals", tags=["signals"])
    app.include_router(trades.router, prefix="/api/trades", tags=["trades"])
    app.include_router(performance.router, prefix="/api/performance", tags=["performance"])
    app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
    app.include_router(allocation.router, prefix="/api/allocation", tags=["allocation"])
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
    app.include_router(
        circuit_breaker.router, prefix="/api/circuit-breaker", tags=["circuit-breaker"]
    )
    app.include_router(adaptation.router, prefix="/api/adaptation", tags=["adaptation"])

    return app


@pytest.fixture
async def dashboard_db(tmp_path):
    """Create a temp database with full schema."""
    db_path = str(tmp_path / "test.db")
    manager = DatabaseManager(db_path)
    await manager.initialize()
    conn = manager.connection
    yield conn, db_path
    await manager.close()


@pytest.fixture
async def api_client(dashboard_db):
    """Create an httpx AsyncClient wired to a fresh dashboard app.

    Returns (client, connection) so tests can seed data directly.
    State is set directly on the app, bypassing lifespan for testing.
    """
    conn, db_path = dashboard_db
    app = _build_test_app()
    # Set state directly -- the same connection serves as both read and write
    app.state.read_conn = conn
    app.state.write_conn = conn
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, conn


@pytest.fixture
async def seeded_client(api_client):
    """Client backed by a database pre-loaded with representative data."""
    client, conn = api_client
    now = datetime.now(IST)
    today = now.date().isoformat()

    # Seed user_config
    await conn.execute(
        """INSERT INTO user_config
               (telegram_chat_id, total_capital, max_positions, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        ("123456", 100000.0, 8, now.isoformat(), now.isoformat()),
    )

    # Seed signals
    for i, (sym, strat, score, status) in enumerate([
        ("RELIANCE", "gap_go", 85.0, "sent"),
        ("TCS", "ORB", 72.0, "taken"),
        ("INFY", "VWAP Reversal", 65.0, "expired"),
    ]):
        await conn.execute(
            """INSERT INTO signals
                   (symbol, strategy, entry_price, stop_loss, target_1, target_2,
                    quantity, capital_required, signal_strength, gap_pct, volume_ratio,
                    status, reason, date, created_at, expires_at,
                    composite_score, confirmation_level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sym, strat,
                100.0 + i * 50, 95.0 + i * 50, 105.0 + i * 50, 110.0 + i * 50,
                10, 1000.0 + i * 500, 3, 2.5, 1.8,
                status, "test", today, now.isoformat(), now.isoformat(),
                score, "single",
            ),
        )

    # Seed trades
    for i, (sym, strat, pnl, exited) in enumerate([
        ("HDFC", "gap_go", 500.0, True),
        ("WIPRO", "ORB", -200.0, True),
        ("SBIN", "VWAP Reversal", 300.0, False),
    ]):
        exited_at = now.isoformat() if exited else None
        exit_reason = ("t2_hit" if pnl > 0 else "sl_hit") if exited else None
        await conn.execute(
            """INSERT INTO trades
                   (signal_id, symbol, strategy, entry_price, stop_loss, target_1, target_2,
                    quantity, pnl_amount, pnl_pct,
                    date, taken_at, exited_at, exit_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                i + 1, sym, strat, 100.0, 95.0, 105.0, 110.0,
                10, pnl, pnl / 100.0,
                today, now.isoformat(), exited_at, exit_reason,
            ),
        )

    # Seed strategy_performance
    for strat, weight in [("gap_go", 40.0), ("ORB", 35.0), ("VWAP Reversal", 25.0)]:
        await conn.execute(
            """INSERT INTO strategy_performance
                   (strategy, date, signals_generated, signals_taken, wins, losses,
                    total_pnl, win_rate, avg_win, avg_loss, expectancy, capital_weight_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (strat, today, 5, 3, 2, 1, 300.0, 66.67, 250.0, -100.0, 133.33, weight),
        )

    # Seed circuit_breaker_log
    await conn.execute(
        """INSERT INTO circuit_breaker_log (date, sl_count, triggered_at)
           VALUES (?, ?, ?)""",
        (today, 3, now.isoformat()),
    )

    # Seed adaptation_log
    await conn.execute(
        """INSERT INTO adaptation_log
               (date, strategy, event_type, details, old_weight, new_weight, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (today, "gap_go", "rebalance", "Weekly rebalance", 33.33, 40.0, now.isoformat()),
    )

    await conn.commit()
    yield client
