"""Persist and deliver — saves signals to DB and sends via Telegram."""

from __future__ import annotations

import logging

from signalpilot.db.models import FinalSignal, HybridScoreRecord, SignalRecord
from signalpilot.pipeline.context import ScanContext
from signalpilot.telegram.formatters import format_suppression_notification
from signalpilot.utils.log_context import set_context

logger = logging.getLogger(__name__)


class PersistAndDeliverStage:
    """Persist final signals to the database and send them via Telegram."""

    def __init__(
        self,
        signal_repo,
        hybrid_score_repo,
        bot,
        adaptive_manager,
        app_config,
    ) -> None:
        self._signal_repo = signal_repo
        self._hybrid_score_repo = hybrid_score_repo
        self._bot = bot
        self._adaptive_manager = adaptive_manager
        self._app_config = app_config

    @property
    def name(self) -> str:
        return "persist_and_deliver"

    async def process(self, ctx: ScanContext) -> ScanContext:
        if not ctx.final_signals and not ctx.suppressed_signals:
            return ctx

        # Phase 4: Send suppression notifications
        for suppressed in ctx.suppressed_signals:
            try:
                msg = format_suppression_notification(suppressed)
                await self._bot.send_alert(msg)
            except Exception:
                logger.warning(
                    "Failed to send suppression notification for %s",
                    suppressed.symbol,
                )

        if not ctx.final_signals:
            return ctx

        for signal in ctx.final_signals:
            record = self._signal_to_record(signal, ctx.now)
            is_paper = self._is_paper_mode(signal, self._app_config)
            if is_paper:
                record.status = "paper"

            # Phase 4: Persist news sentiment metadata
            sym = signal.ranked_signal.candidate.symbol
            news_sentiment_label = None
            news_sentiment_score = None
            news_top_headline = None
            news_action = None
            original_star_rating = None
            if ctx.sentiment_results and sym in ctx.sentiment_results:
                sr = ctx.sentiment_results[sym]
                record.news_sentiment_score = sr.score
                record.news_sentiment_label = sr.label
                record.news_top_headline = sr.top_negative_headline or sr.headline
                record.news_action = sr.action
                news_sentiment_label = sr.label
                news_sentiment_score = sr.score
                news_top_headline = sr.top_negative_headline or sr.headline
                news_action = sr.action
                # Track original star rating for downgraded signals
                if sr.action == "DOWNGRADED":
                    record.original_star_rating = signal.ranked_signal.signal_strength + 1
                    original_star_rating = record.original_star_rating

            # Phase 3: Persist composite score and confirmation fields
            conf_level = None
            conf_by = None
            boosted_stars = None

            if ctx.composite_scores and sym in ctx.composite_scores:
                cs = ctx.composite_scores[sym]
                record.composite_score = cs.composite_score
                set_context(
                    cycle_id=ctx.cycle_id,
                    phase=ctx.phase.value,
                    symbol=sym,
                )

            if ctx.confirmation_map and sym in ctx.confirmation_map:
                conf = ctx.confirmation_map[sym]
                record.confirmation_level = conf.confirmation_level
                record.confirmed_by = ",".join(conf.confirmed_by)
                record.position_size_multiplier = conf.position_size_multiplier
                conf_level = conf.confirmation_level
                conf_by = ",".join(conf.confirmed_by)
                if conf.star_boost > 0:
                    boosted_stars = min(
                        signal.ranked_signal.signal_strength + conf.star_boost, 5
                    )

            if self._adaptive_manager is not None:
                state = self._adaptive_manager.get_all_states().get(
                    signal.ranked_signal.candidate.strategy_name
                )
                if state is not None:
                    record.adaptation_status = state.level.value

            signal_id = await self._signal_repo.insert_signal(record)
            record.id = signal_id

            # Phase 3: Persist hybrid score record
            if (
                self._hybrid_score_repo is not None
                and ctx.composite_scores
                and sym in ctx.composite_scores
            ):
                cs = ctx.composite_scores[sym]
                hs_record = HybridScoreRecord(
                    signal_id=signal_id,
                    composite_score=cs.composite_score,
                    strategy_strength_score=cs.strategy_strength_score,
                    win_rate_score=cs.win_rate_score,
                    risk_reward_score=cs.risk_reward_score,
                    confirmation_bonus=cs.confirmation_bonus,
                    confirmed_by=conf_by,
                    confirmation_level=conf_level or "single",
                    position_size_multiplier=(
                        ctx.confirmation_map[sym].position_size_multiplier
                        if ctx.confirmation_map and sym in ctx.confirmation_map
                        else 1.0
                    ),
                    created_at=ctx.now,
                )
                try:
                    await self._hybrid_score_repo.insert_score(hs_record)
                except Exception:
                    logger.warning(
                        "Failed to persist hybrid score for signal %d",
                        signal_id,
                    )

            await self._bot.send_signal(
                signal,
                is_paper=is_paper,
                signal_id=signal_id,
                confirmation_level=conf_level,
                confirmed_by=conf_by,
                boosted_stars=boosted_stars,
                news_sentiment_label=news_sentiment_label,
                news_top_headline=news_top_headline,
                news_sentiment_score=news_sentiment_score,
                original_star_rating=original_star_rating,
            )
            logger.info(
                "Signal %s for %s (id=%d, composite_score=%s, confirmation=%s)",
                "paper-sent" if is_paper else "sent",
                record.symbol,
                signal_id,
                record.composite_score,
                record.confirmation_level or "single",
            )

        return ctx

    @staticmethod
    def _is_paper_mode(signal: FinalSignal, app_config) -> bool:
        """Check if the signal's strategy is in paper trading mode."""
        strategy_name = signal.ranked_signal.candidate.strategy_name
        if strategy_name == "ORB" and getattr(app_config, "orb_paper_mode", False):
            return True
        if strategy_name == "VWAP Reversal" and getattr(app_config, "vwap_paper_mode", False):
            return True
        return False

    @staticmethod
    def _signal_to_record(signal: FinalSignal, now) -> SignalRecord:
        """Convert a FinalSignal to a SignalRecord for database storage."""
        c = signal.ranked_signal.candidate
        return SignalRecord(
            date=now.date(),
            symbol=c.symbol,
            strategy=c.strategy_name,
            entry_price=c.entry_price,
            stop_loss=c.stop_loss,
            target_1=c.target_1,
            target_2=c.target_2,
            quantity=signal.quantity,
            capital_required=signal.capital_required,
            signal_strength=signal.ranked_signal.signal_strength,
            gap_pct=c.gap_pct,
            volume_ratio=c.volume_ratio,
            reason=c.reason,
            created_at=c.generated_at,
            expires_at=signal.expires_at,
            status="sent",
            setup_type=c.setup_type,
            strategy_specific_score=c.strategy_specific_score,
        )
