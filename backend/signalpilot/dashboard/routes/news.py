"""Dashboard API routes for news sentiment and earnings calendar."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Query, Request

from signalpilot.db.earnings_repo import EarningsCalendarRepository
from signalpilot.db.news_sentiment_repo import NewsSentimentRepository
from signalpilot.utils.constants import IST

router = APIRouter()
earnings_router = APIRouter()


@router.get("/{stock_code}")
async def get_stock_sentiment(request: Request, stock_code: str):
    """Get news sentiment for a specific stock."""
    conn = request.app.state.read_conn
    repo = NewsSentimentRepository(conn)
    result = await repo.get_composite_score(stock_code)

    if result is None:
        return {
            "stock_code": stock_code,
            "label": "NO_NEWS",
            "composite_score": 0.0,
            "headline_count": 0,
            "headlines": [],
        }

    composite_score, label, count = result
    headlines = await repo.get_stock_sentiment(stock_code, lookback_hours=24)

    return {
        "stock_code": stock_code,
        "label": label,
        "composite_score": round(composite_score, 4),
        "headline_count": count,
        "headlines": [
            {
                "headline": h.headline,
                "source": h.source,
                "score": round(h.composite_score, 4),
                "label": h.sentiment_label,
                "published_at": h.published_at.isoformat() if h.published_at else None,
                "model": h.model_used,
            }
            for h in headlines[:10]
        ],
    }


@router.get("/suppressed/list")
async def get_suppressed_signals(
    request: Request,
    date_filter: str | None = Query(None, alias="date"),
    limit: int = Query(50, ge=1, le=200),
):
    """Get signals that were suppressed by news sentiment."""
    conn = request.app.state.read_conn
    query = """
        SELECT * FROM signals
        WHERE news_action IN ('SUPPRESSED', 'EARNINGS_BLACKOUT')
    """
    params: list = []

    if date_filter:
        query += " AND date = ?"
        params.append(date_filter)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor = await conn.execute(query, params)
    rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "symbol": row["symbol"],
            "strategy": row["strategy"],
            "date": row["date"],
            "news_action": row["news_action"],
            "news_sentiment_score": row["news_sentiment_score"],
            "news_sentiment_label": row["news_sentiment_label"],
            "news_top_headline": row["news_top_headline"],
            "original_star_rating": row["original_star_rating"],
            "entry_price": row["entry_price"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


@earnings_router.get("/upcoming")
async def get_upcoming_earnings(
    request: Request,
    days: int = Query(14, ge=1, le=90),
):
    """Get upcoming earnings within the specified number of days."""
    conn = request.app.state.read_conn
    repo = EarningsCalendarRepository(conn)
    upcoming = await repo.get_upcoming_earnings(days)

    return [
        {
            "stock_code": e.stock_code,
            "earnings_date": e.earnings_date.isoformat() if e.earnings_date else None,
            "quarter": e.quarter,
            "source": e.source,
            "is_confirmed": e.is_confirmed,
        }
        for e in upcoming
    ]
