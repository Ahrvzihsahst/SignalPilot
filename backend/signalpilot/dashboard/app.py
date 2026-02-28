"""FastAPI dashboard application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


def create_dashboard_app(
    db_path: str = "signalpilot.db",
    write_connection: aiosqlite.Connection | None = None,
) -> FastAPI:
    """Create and configure the FastAPI dashboard application.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  A **read-only** connection is
        opened automatically on startup.
    write_connection:
        Optional pre-existing writable connection shared with the main
        SignalPilot application (used for settings mutations).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        uri = f"file:{db_path}?mode=ro"
        app.state.read_conn = await aiosqlite.connect(uri, uri=True)
        app.state.read_conn.row_factory = aiosqlite.Row
        await app.state.read_conn.execute("PRAGMA journal_mode=WAL")
        app.state.write_conn = write_connection
        logger.info("Dashboard DB connections ready (read=%s)", db_path)
        yield
        await app.state.read_conn.close()
        logger.info("Dashboard DB connections closed")

    app = FastAPI(title="SignalPilot Dashboard", version="3.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from signalpilot.dashboard.routes import (
        adaptation,
        allocation,
        circuit_breaker,
        news,
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
    app.include_router(news.router, prefix="/api/news", tags=["news"])
    app.include_router(news.earnings_router, prefix="/api/earnings", tags=["earnings"])

    return app
