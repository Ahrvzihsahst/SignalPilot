"""Pipeline stage for news sentiment filtering."""

from __future__ import annotations

import logging

from signalpilot.db.models import SuppressedSignal
from signalpilot.pipeline.context import ScanContext

logger = logging.getLogger(__name__)


class NewsSentimentStage:
    """Filter ranked signals based on news sentiment (stage between Ranking and RiskSizing).

    Action matrix:
    - STRONG_NEGATIVE -> suppress (remove from ranked_signals, add to suppressed_signals)
    - MILD_NEGATIVE -> downgrade (reduce star rating by 1, minimum 1)
    - NEUTRAL / POSITIVE / NO_NEWS -> pass through
    - Earnings blackout -> suppress regardless of sentiment
    - Unsuppress override -> pass through with UNSUPPRESSED action
    """

    def __init__(self, news_sentiment_service, earnings_repo, config) -> None:
        self._news_sentiment_service = news_sentiment_service
        self._earnings_repo = earnings_repo
        self._config = config

    @property
    def name(self) -> str:
        return "NewsSentiment"

    async def process(self, ctx: ScanContext) -> ScanContext:
        # Kill switch (also skip if config or service not wired)
        if self._config is None or self._news_sentiment_service is None:
            return ctx
        if not self._config.news_enabled:
            return ctx

        if not ctx.ranked_signals:
            return ctx

        # Batch fetch sentiment for all symbols
        symbols = [rs.candidate.symbol for rs in ctx.ranked_signals]
        sentiment_batch = await self._news_sentiment_service.get_sentiment_batch(symbols)
        ctx.sentiment_results = sentiment_batch

        passed = []
        suppressed = []

        for rs in ctx.ranked_signals:
            sym = rs.candidate.symbol

            # Check earnings blackout first (highest priority)
            if self._config.earnings_blackout_enabled and self._earnings_repo is not None:
                has_earnings = await self._earnings_repo.has_earnings_today(sym)
                if has_earnings:
                    # Check unsuppress override
                    if self._news_sentiment_service.is_unsuppressed(sym):
                        # Override: let it pass with UNSUPPRESSED action
                        sr = sentiment_batch.get(sym)
                        if sr is not None:
                            # Mutate action to UNSUPPRESSED
                            sentiment_batch[sym] = type(sr)(
                                score=sr.score, label=sr.label,
                                headline=sr.headline, action="UNSUPPRESSED",
                                headline_count=sr.headline_count,
                                top_negative_headline=sr.top_negative_headline,
                                model_used=sr.model_used,
                            )
                        passed.append(rs)
                        continue

                    suppressed.append(SuppressedSignal(
                        symbol=sym,
                        strategy=rs.candidate.strategy_name,
                        original_stars=rs.signal_strength,
                        sentiment_score=sentiment_batch[sym].score if sym in sentiment_batch else 0.0,
                        sentiment_label="EARNINGS_BLACKOUT",
                        top_headline=sentiment_batch[sym].headline if sym in sentiment_batch else None,
                        reason="Earnings day blackout",
                        entry_price=rs.candidate.entry_price,
                        stop_loss=rs.candidate.stop_loss,
                        target_1=rs.candidate.target_1,
                    ))
                    # Update sentiment result action
                    if sym in sentiment_batch:
                        sr = sentiment_batch[sym]
                        sentiment_batch[sym] = type(sr)(
                            score=sr.score, label=sr.label,
                            headline=sr.headline, action="EARNINGS_BLACKOUT",
                            headline_count=sr.headline_count,
                            top_negative_headline=sr.top_negative_headline,
                            model_used=sr.model_used,
                        )
                    continue

            # Get sentiment result
            sr = sentiment_batch.get(sym)
            if sr is None:
                # Cache miss: treat as NO_NEWS, pass through
                passed.append(rs)
                continue

            # Check unsuppress override
            if self._news_sentiment_service.is_unsuppressed(sym):
                sentiment_batch[sym] = type(sr)(
                    score=sr.score, label=sr.label,
                    headline=sr.headline, action="UNSUPPRESSED",
                    headline_count=sr.headline_count,
                    top_negative_headline=sr.top_negative_headline,
                    model_used=sr.model_used,
                )
                passed.append(rs)
                continue

            # Apply label-based action
            if sr.label == "STRONG_NEGATIVE":
                suppressed.append(SuppressedSignal(
                    symbol=sym,
                    strategy=rs.candidate.strategy_name,
                    original_stars=rs.signal_strength,
                    sentiment_score=sr.score,
                    sentiment_label=sr.label,
                    top_headline=sr.top_negative_headline or sr.headline,
                    reason=f"Strong negative sentiment (score: {sr.score:.2f})",
                    entry_price=rs.candidate.entry_price,
                    stop_loss=rs.candidate.stop_loss,
                    target_1=rs.candidate.target_1,
                ))
                continue

            if sr.label == "MILD_NEGATIVE":
                # Downgrade: reduce star rating by 1 (minimum 1)
                original_stars = rs.signal_strength
                new_stars = max(1, original_stars - 1)
                # Create a new ranked signal with reduced strength
                from signalpilot.db.models import RankedSignal
                downgraded = RankedSignal(
                    candidate=rs.candidate,
                    composite_score=rs.composite_score,
                    rank=rs.rank,
                    signal_strength=new_stars,
                )
                # Update action to DOWNGRADED
                sentiment_batch[sym] = type(sr)(
                    score=sr.score, label=sr.label,
                    headline=sr.headline, action="DOWNGRADED",
                    headline_count=sr.headline_count,
                    top_negative_headline=sr.top_negative_headline,
                    model_used=sr.model_used,
                )
                passed.append(downgraded)
                continue

            # NEUTRAL, POSITIVE, NO_NEWS: pass through
            passed.append(rs)

        ctx.ranked_signals = passed
        ctx.suppressed_signals = suppressed

        logger.info(
            "NewsSentiment: %d passed, %d suppressed",
            len(passed), len(suppressed),
        )

        return ctx
