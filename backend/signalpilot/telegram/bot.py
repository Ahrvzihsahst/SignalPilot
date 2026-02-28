"""SignalPilot Telegram bot -- signal delivery and command handling."""

import asyncio
import logging
import time

from telegram import Update
from telegram.error import BadRequest, TimedOut
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from signalpilot.db.models import CallbackResult, ExitAlert, FinalSignal
from signalpilot.telegram.formatters import format_exit_alert, format_signal_message
from signalpilot.telegram.handlers import (
    handle_adapt,
    handle_allocate,
    handle_capital,
    handle_earnings_command,
    handle_exit_now_callback,
    handle_help,
    handle_hold_callback,
    handle_journal,
    handle_let_run_callback,
    handle_news_command,
    handle_override_circuit,
    handle_override_confirm,
    handle_partial_exit_callback,
    handle_pause,
    handle_rebalance,
    handle_resume,
    handle_score,
    handle_skip_callback,
    handle_skip_reason_callback,
    handle_status,
    handle_strategy,
    handle_take_profit_callback,
    handle_taken,
    handle_taken_callback,
    handle_unsuppress_command,
    handle_unwatch_command,
    handle_watch_callback,
    handle_watchlist_command,
)
from signalpilot.telegram.keyboards import (
    build_near_t2_keyboard,
    build_signal_keyboard,
    build_sl_approaching_keyboard,
    build_t1_keyboard,
    build_t2_keyboard,
)
from signalpilot.utils.log_context import log_context

logger = logging.getLogger(__name__)


class SignalPilotBot:
    """Main Telegram bot manager.

    Registers command handlers, delivers signals and alerts, and manages
    the bot application lifecycle. All handlers are restricted to the
    configured chat_id for security.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        signal_repo,
        trade_repo,
        config_repo,
        metrics_calculator,
        exit_monitor,
        get_current_prices,
        capital_allocator=None,
        strategy_performance_repo=None,
        signal_action_repo=None,
        watchlist_repo=None,
        # Phase 3 components
        circuit_breaker=None,
        adaptive_manager=None,
        hybrid_score_repo=None,
        adaptation_log_repo=None,
        app=None,
        # Phase 4: News Sentiment Filter
        news_sentiment_service=None,
        earnings_repo=None,
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._signal_repo = signal_repo
        self._trade_repo = trade_repo
        self._config_repo = config_repo
        self._metrics_calculator = metrics_calculator
        self._exit_monitor = exit_monitor
        self._get_current_prices = get_current_prices
        self._capital_allocator = capital_allocator
        self._strategy_performance_repo = strategy_performance_repo
        self._signal_action_repo = signal_action_repo
        self._watchlist_repo = watchlist_repo
        # Phase 3
        self._circuit_breaker = circuit_breaker
        self._adaptive_manager = adaptive_manager
        self._hybrid_score_repo = hybrid_score_repo
        self._adaptation_log_repo = adaptation_log_repo
        self._app = app
        # Phase 4: News Sentiment Filter
        self._news_sentiment_service = news_sentiment_service
        self._earnings_repo = earnings_repo
        self._application: Application | None = None
        self._pending_entry_edits: dict[int, int] = {}  # chat_message_id -> signal_id
        self._awaiting_override_confirm = False

    def set_app(self, app) -> None:
        """Set the app reference after construction (breaks circular dep)."""
        self._app = app

    async def start(self) -> None:
        """Initialize the bot, register handlers, and start polling."""
        self._application = ApplicationBuilder().token(self._bot_token).build()

        # Restrict all commands to the configured chat ID
        chat_filter = filters.Chat(chat_id=int(self._chat_id))

        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT
                & filters.Regex(r"(?i)^/?taken(?:\s+force)?(?:\s+\d+)?$"),
                self._handle_taken,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^status$"),
                self._handle_status,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^journal$"),
                self._handle_journal,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^capital\s+\d+(?:\.\d+)?$"),
                self._handle_capital,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^pause\s+\w+$"),
                self._handle_pause,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^resume\s+\w+$"),
                self._handle_resume,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^allocate"),
                self._handle_allocate,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^strategy$"),
                self._handle_strategy,
            )
        )
        # Phase 3 handlers
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^override\s+circuit$"),
                self._handle_override_circuit,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^yes$"),
                self._handle_override_confirm,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^score\s+\S+$"),
                self._handle_score,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^adapt$"),
                self._handle_adapt,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^rebalance$"),
                self._handle_rebalance,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^help$"),
                self._handle_help,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^watchlist$"),
                self._handle_watchlist,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^unwatch\s+\w+$"),
                self._handle_unwatch,
            )
        )
        # Phase 4: News Sentiment Filter commands
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^news(?:\s+\S+)?$"),
                self._handle_news,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^earnings$"),
                self._handle_earnings,
            )
        )
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^unsuppress\s+\S+$"),
                self._handle_unsuppress,
            )
        )
        self._application.add_handler(CallbackQueryHandler(self._handle_callback))

        await self._application.initialize()
        await self._application.start()
        await self._application.updater.start_polling()
        logger.info("Telegram bot started polling")

    async def stop(self) -> None:
        """Gracefully stop the bot."""
        if self._application:
            await self._application.updater.stop()
            await self._application.stop()
            await self._application.shutdown()
            logger.info("Telegram bot stopped")

    async def send_signal(
        self, signal: FinalSignal, is_paper: bool = False,
        signal_id: int | None = None, is_watchlisted: bool = False,
        confirmation_level: str | None = None,
        confirmed_by: str | None = None,
        boosted_stars: int | None = None,
        news_sentiment_label: str | None = None,
        news_top_headline: str | None = None,
        news_sentiment_score: float | None = None,
        original_star_rating: int | None = None,
    ) -> int | None:
        """Format and send a signal message to the user's chat.

        Returns the sent message's message_id, or None on failure.
        """
        message = format_signal_message(
            signal, is_paper=is_paper, signal_id=signal_id,
            is_watchlisted=is_watchlisted,
            confirmation_level=confirmation_level,
            confirmed_by=confirmed_by,
            boosted_stars=boosted_stars,
            news_sentiment_label=news_sentiment_label,
            news_top_headline=news_top_headline,
            news_sentiment_score=news_sentiment_score,
            original_star_rating=original_star_rating,
        )
        keyboard = None
        if signal_id is not None:
            keyboard = build_signal_keyboard(signal_id)
        else:
            logger.warning("No signal_id for keyboard; sending without buttons")

        sent = await self._application.bot.send_message(
            chat_id=self._chat_id,
            text=message,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        latency = time.time() - signal.ranked_signal.candidate.generated_at.timestamp()
        if latency > 30:
            logger.warning(
                "Signal delivery latency %.1fs exceeds 30s for %s",
                latency,
                signal.ranked_signal.candidate.symbol,
            )
        return sent.message_id if sent else None

    async def send_alert(self, text: str) -> None:
        """Send a plain text alert message."""
        await self._application.bot.send_message(
            chat_id=self._chat_id,
            text=text,
            parse_mode="HTML",
        )

    async def send_exit_alert(self, alert: ExitAlert) -> None:
        """Format and send an exit alert, with keyboard if applicable."""
        message = format_exit_alert(alert)
        keyboard_type = getattr(alert, "keyboard_type", None)
        keyboard = None
        if keyboard_type and alert.trade and alert.trade.id:
            keyboard_map = {
                "t1": build_t1_keyboard,
                "t2": build_t2_keyboard,
                "sl_approaching": build_sl_approaching_keyboard,
                "near_t2": build_near_t2_keyboard,
            }
            builder = keyboard_map.get(keyboard_type)
            if builder:
                keyboard = builder(alert.trade.id)

        await self._application.bot.send_message(
            chat_id=self._chat_id,
            text=message,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    # -- Internal handler wrappers that bridge telegram Update to handler logic

    async def _handle_taken(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="TAKEN"):
            text = update.message.text.strip()
            response = await handle_taken(
                self._signal_repo, self._trade_repo, self._config_repo,
                self._exit_monitor, text=text,
                signal_action_repo=self._signal_action_repo,
            )
            await update.message.reply_text(response)

    async def _handle_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="STATUS"):
            response = await handle_status(
                self._signal_repo, self._trade_repo, self._get_current_prices,
                hybrid_score_repo=self._hybrid_score_repo,
            )
            await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_journal(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="JOURNAL"):
            response = await handle_journal(
                self._metrics_calculator,
                hybrid_score_repo=self._hybrid_score_repo,
            )
            await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_capital(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="CAPITAL"):
            response = await handle_capital(self._config_repo, update.message.text)
            await update.message.reply_text(response)

    async def _handle_pause(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="PAUSE"):
            response = await handle_pause(self._config_repo, update.message.text)
            await update.message.reply_text(response)

    async def _handle_resume(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="RESUME"):
            response = await handle_resume(self._config_repo, update.message.text)
            await update.message.reply_text(response)

    async def _handle_allocate(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="ALLOCATE"):
            response = await handle_allocate(
                self._capital_allocator, self._config_repo, update.message.text
            )
            await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_strategy(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="STRATEGY"):
            response = await handle_strategy(
                self._strategy_performance_repo,
                adaptive_manager=self._adaptive_manager,
            )
            await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_override_circuit(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="OVERRIDE_CIRCUIT"):
            response = await handle_override_circuit(
                self._circuit_breaker, app=self._app,
            )
            if "Reply YES" in response:
                self._awaiting_override_confirm = True
            await update.message.reply_text(response)

    async def _handle_override_confirm(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="OVERRIDE_CONFIRM"):
            if not self._awaiting_override_confirm:
                return  # Ignore stray YES messages
            self._awaiting_override_confirm = False
            response = await handle_override_confirm(
                self._circuit_breaker, app=self._app,
            )
            await update.message.reply_text(response)

    async def _handle_score(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="SCORE"):
            response = await handle_score(
                self._hybrid_score_repo, update.message.text,
            )
            await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_adapt(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="ADAPT"):
            response = await handle_adapt(self._adaptive_manager)
            await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_rebalance(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="REBALANCE"):
            response = await handle_rebalance(
                self._capital_allocator,
                self._config_repo,
                adaptation_log_repo=self._adaptation_log_repo,
            )
            await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_help(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="HELP"):
            response = await handle_help()
            await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_watchlist(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="WATCHLIST"):
            if self._watchlist_repo is None:
                await update.message.reply_text("Watchlist not configured.")
                return
            response = await handle_watchlist_command(self._watchlist_repo)
            await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_unwatch(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="UNWATCH"):
            if self._watchlist_repo is None:
                await update.message.reply_text("Watchlist not configured.")
                return
            response = await handle_unwatch_command(self._watchlist_repo, update.message.text)
            await update.message.reply_text(response)

    # -- Phase 4: News Sentiment Filter command wrappers

    async def _handle_news(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="NEWS"):
            if self._news_sentiment_service is None:
                await update.message.reply_text("News sentiment not configured.")
                return
            response = await handle_news_command(
                self._news_sentiment_service, update.message.text,
            )
            await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_earnings(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="EARNINGS"):
            if self._earnings_repo is None:
                await update.message.reply_text("Earnings calendar not configured.")
                return
            response = await handle_earnings_command(self._earnings_repo)
            await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_unsuppress(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="UNSUPPRESS"):
            if self._news_sentiment_service is None:
                await update.message.reply_text("News sentiment not configured.")
                return
            response = await handle_unsuppress_command(
                self._news_sentiment_service, update.message.text,
            )
            await update.message.reply_text(response)

    # -- Callback query handler (Phase 4: Quick Action Buttons)

    async def _handle_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Route inline keyboard callback queries to appropriate handlers."""
        query = update.callback_query
        if query is None:
            return

        # Security: ignore callbacks from non-configured chat_id
        if str(query.message.chat_id) != str(self._chat_id):
            logger.warning(
                "Callback from unauthorized chat_id: %s", query.message.chat_id
            )
            return

        data = query.data or ""
        try:
            result = await self._dispatch_callback(data, query)
            await self._apply_callback_result(query, result)
        except Exception:
            logger.exception("Error handling callback: %s", data)
            try:
                await query.answer("Something went wrong. Try again.")
            except Exception:
                logger.exception("Failed to answer callback after error")

    async def _dispatch_callback(self, data: str, query) -> CallbackResult:
        """Parse callback data and dispatch to the appropriate handler."""

        parts = data.split(":")
        prefix = parts[0]

        if prefix == "taken" and len(parts) >= 2:
            signal_id = int(parts[1])
            return await handle_taken_callback(
                self._signal_repo, self._trade_repo, self._config_repo,
                self._exit_monitor, self._signal_action_repo, signal_id,
            )

        if prefix == "skip" and len(parts) >= 2:
            signal_id = int(parts[1])
            return await handle_skip_callback(
                self._signal_repo, self._signal_action_repo, signal_id,
            )

        if prefix == "skip_reason" and len(parts) >= 3:
            signal_id = int(parts[1])
            reason = parts[2]
            return await handle_skip_reason_callback(
                self._signal_repo, self._signal_action_repo, signal_id, reason,
            )

        if prefix == "watch" and len(parts) >= 2:
            signal_id = int(parts[1])
            return await handle_watch_callback(
                self._signal_repo, self._signal_action_repo,
                self._watchlist_repo, signal_id,
            )

        if prefix == "edit_entry" and len(parts) >= 2:
            signal_id = int(parts[1])
            return await self._handle_edit_entry(signal_id, query)

        if prefix == "confirm_taken" and len(parts) >= 2:
            return CallbackResult(
                answer_text="Trade confirmed at signal price.",
                success=True,
                status_line="CONFIRMED -- Using signal entry price",
            )

        if prefix == "partial_exit" and len(parts) >= 3:
            trade_id = int(parts[1])
            level = parts[2]
            return await handle_partial_exit_callback(
                self._trade_repo, trade_id, level,
            )

        if prefix == "full_exit" and len(parts) >= 3:
            trade_id = int(parts[1])
            level = parts[2]
            return await handle_partial_exit_callback(
                self._trade_repo, trade_id, level,
            )

        if prefix == "exit_now" and len(parts) >= 2:
            trade_id = int(parts[1])
            return await handle_exit_now_callback(
                self._trade_repo, self._exit_monitor,
                self._get_current_prices, trade_id,
            )

        if prefix == "hold" and len(parts) >= 2:
            trade_id = int(parts[1])
            return await handle_hold_callback(trade_id)

        if prefix == "take_profit" and len(parts) >= 2:
            trade_id = int(parts[1])
            return await handle_take_profit_callback(
                self._trade_repo, self._exit_monitor,
                self._get_current_prices, trade_id,
            )

        if prefix == "let_run" and len(parts) >= 2:
            trade_id = int(parts[1])
            return await handle_let_run_callback(trade_id)

        logger.warning("Unknown callback data: %s", data)
        return CallbackResult(answer_text="Unknown action.", success=False)

    async def _handle_edit_entry(self, signal_id: int, query) -> CallbackResult:
        """Handle edit_entry callback — prompt user for new price."""

        # Fetch signal to get symbol
        cursor = await self._signal_repo._conn.execute(
            "SELECT symbol FROM signals WHERE id = ?", (signal_id,)
        )
        row = await cursor.fetchone()
        symbol = row["symbol"] if row else "unknown"

        prompt_msg = await self._application.bot.send_message(
            chat_id=self._chat_id,
            text=f"Reply with your actual entry price for {symbol}:",
        )

        # Store pending edit
        self._pending_entry_edits[signal_id] = prompt_msg.message_id

        # Wait for reply (up to 60 seconds)
        async def _wait_for_price():
            await asyncio.sleep(60)
            if signal_id in self._pending_entry_edits:
                del self._pending_entry_edits[signal_id]
                try:
                    await self._application.bot.send_message(
                        chat_id=self._chat_id,
                        text=f"Entry price edit timed out. Using signal price for {symbol}.",
                    )
                except Exception:
                    logger.exception("Failed to send timeout message")

        asyncio.create_task(_wait_for_price())

        return CallbackResult(
            answer_text=f"Enter price for {symbol}",
            success=True,
        )

    async def _apply_callback_result(self, query, result) -> None:
        """Apply a CallbackResult: answer query, update message."""
        # Answer the callback query
        try:
            await query.answer(result.answer_text)
        except TimedOut:
            try:
                await asyncio.sleep(1)
                await query.answer(result.answer_text)
            except Exception:
                logger.warning("Failed to answer callback after retry")

        # Update message
        try:
            if result.status_line:
                # Append status line to existing message
                current_text = query.message.text or ""
                new_text = f"{current_text}\n\n{result.status_line}"
                if result.new_keyboard:
                    await query.edit_message_text(
                        text=new_text, reply_markup=result.new_keyboard,
                    )
                else:
                    await query.edit_message_text(text=new_text)
            elif result.new_keyboard:
                await query.edit_message_reply_markup(
                    reply_markup=result.new_keyboard,
                )
            elif result.success:
                # Remove keyboard on success with no new keyboard
                await query.edit_message_reply_markup(reply_markup=None)
        except BadRequest as e:
            logger.warning("BadRequest editing message: %s", e)
            # Fallback: send fresh message
            if result.status_line:
                try:
                    await self._application.bot.send_message(
                        chat_id=self._chat_id,
                        text=result.status_line,
                    )
                except Exception:
                    logger.exception("Failed to send fallback message")
