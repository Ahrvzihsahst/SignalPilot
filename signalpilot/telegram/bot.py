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
    handle_capital,
    handle_help,
    handle_journal,
    handle_status,
    handle_taken,
)

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
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._signal_repo = signal_repo
        self._trade_repo = trade_repo
        self._config_repo = config_repo
        self._metrics_calculator = metrics_calculator
        self._exit_monitor = exit_monitor
        self._get_current_prices = get_current_prices
        self._application: Application | None = None

    async def start(self) -> None:
        """Initialize the bot, register handlers, and start polling."""
        self._application = ApplicationBuilder().token(self._bot_token).build()

        # Restrict all commands to the configured chat ID
        chat_filter = filters.Chat(chat_id=int(self._chat_id))

        self._application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & filters.Regex(r"(?i)^taken$"),
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

    async def send_signal(self, signal: FinalSignal) -> None:
        """Format and send a signal message to the user's chat."""
        message = format_signal_message(signal)
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
        response = await handle_taken(
            self._signal_repo, self._trade_repo, self._exit_monitor,
        )
        await update.message.reply_text(response)

    async def _handle_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        response = await handle_status(
            self._signal_repo, self._trade_repo, self._get_current_prices,
        )
        await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_journal(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        response = await handle_journal(self._metrics_calculator)
        await update.message.reply_text(response, parse_mode="HTML")

    async def _handle_capital(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        response = await handle_capital(self._config_repo, update.message.text)
        await update.message.reply_text(response)

    async def _handle_help(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        response = await handle_help()
        await update.message.reply_text(response, parse_mode="HTML")
