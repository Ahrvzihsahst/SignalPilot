"""SignalPilot Telegram bot — signal delivery and command handling."""

import logging
import time

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

from signalpilot.db.models import ExitAlert, FinalSignal
from signalpilot.telegram.formatters import format_exit_alert, format_signal_message
from signalpilot.telegram.handlers import (
    handle_allocate,
    handle_capital,
    handle_help,
    handle_journal,
    handle_pause,
    handle_resume,
    handle_status,
    handle_strategy,
    handle_taken,
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
        self._application: Application | None = None

    async def start(self) -> None:
        """Initialize the bot, register handlers, and start polling."""
        self._application = ApplicationBuilder().token(self._bot_token).build()

        # Restrict all commands to the configured chat ID
        chat_filter = filters.Chat(chat_id=int(self._chat_id))

        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^/?taken$"),
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
        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^help$"),
                self._handle_help,
            )
        )

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

    async def send_signal(self, signal: FinalSignal, is_paper: bool = False) -> None:
        """Format and send a signal message to the user's chat."""
        message = format_signal_message(signal, is_paper=is_paper)
        await self._application.bot.send_message(
            chat_id=self._chat_id,
            text=message,
            parse_mode="HTML",
        )
        latency = time.time() - signal.ranked_signal.candidate.generated_at.timestamp()
        if latency > 30:
            logger.warning(
                "Signal delivery latency %.1fs exceeds 30s for %s",
                latency,
                signal.ranked_signal.candidate.symbol,
            )

    async def send_alert(self, text: str) -> None:
        """Send a plain text alert message."""
        await self._application.bot.send_message(
            chat_id=self._chat_id,
            text=text,
            parse_mode="HTML",
        )

    async def send_exit_alert(self, alert: ExitAlert) -> None:
        """Format and send an exit alert."""
        message = format_exit_alert(alert)
        await self.send_alert(message)

    # -- Internal handler wrappers that bridge telegram Update to handler logic

    async def _handle_taken(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="TAKEN"):
            response = await handle_taken(
                self._signal_repo, self._trade_repo, self._exit_monitor,
            )
            await update.message.reply_text(response)

    async def _handle_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="STATUS"):
            response = await handle_status(
                self._signal_repo, self._trade_repo, self._get_current_prices,
            )
            await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_journal(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="JOURNAL"):
            response = await handle_journal(self._metrics_calculator)
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
            response = await handle_strategy(self._strategy_performance_repo)
            await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_help(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        async with log_context(command="HELP"):
            response = await handle_help()
            await update.message.reply_text(response, parse_mode="HTML")
