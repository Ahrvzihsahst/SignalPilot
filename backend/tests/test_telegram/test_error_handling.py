"""Tests for graceful error handling in bot callback methods (Task 4.8)."""

from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import BadRequest, TimedOut

from signalpilot.db.models import CallbackResult
from signalpilot.telegram.bot import SignalPilotBot


def _make_bot(**overrides) -> SignalPilotBot:
    defaults = dict(
        bot_token="fake-token",
        chat_id="123456",
        signal_repo=AsyncMock(),
        trade_repo=AsyncMock(),
        config_repo=AsyncMock(),
        metrics_calculator=AsyncMock(),
        exit_monitor=MagicMock(),
        get_current_prices=AsyncMock(),
        signal_action_repo=AsyncMock(),
        watchlist_repo=AsyncMock(),
    )
    defaults.update(overrides)
    return SignalPilotBot(**defaults)


class TestBadRequestFallback:
    """BadRequest on message edit should fall back to a fresh message."""

    async def test_edit_message_bad_request_sends_fallback(self):
        """When edit_message_text raises BadRequest, bot sends a fresh message."""
        bot = _make_bot()
        bot._application = MagicMock()
        bot._application.bot.send_message = AsyncMock()

        result = CallbackResult(
            answer_text="Done",
            success=True,
            status_line="TAKEN -- Tracking SBIN",
        )

        query = MagicMock()
        query.answer = AsyncMock()
        query.message.text = "Signal message"
        query.edit_message_text = AsyncMock(
            side_effect=BadRequest("Message is not modified"),
        )

        await bot._apply_callback_result(query, result)

        # Answer should still succeed
        query.answer.assert_called_once_with("Done")

        # Fallback message should be sent
        bot._application.bot.send_message.assert_called_once()
        call_kwargs = bot._application.bot.send_message.call_args.kwargs
        assert call_kwargs["text"] == "TAKEN -- Tracking SBIN"
        assert call_kwargs["chat_id"] == "123456"

    async def test_edit_reply_markup_bad_request_no_fallback_without_status(self):
        """BadRequest on edit_message_reply_markup with no status_line: no fallback."""
        bot = _make_bot()
        bot._application = MagicMock()
        bot._application.bot.send_message = AsyncMock()

        result = CallbackResult(
            answer_text="Done",
            success=True,
            status_line=None,  # No status line
            new_keyboard=MagicMock(),
        )

        query = MagicMock()
        query.answer = AsyncMock()
        query.edit_message_reply_markup = AsyncMock(
            side_effect=BadRequest("Message is not modified"),
        )

        await bot._apply_callback_result(query, result)

        # No fallback since there's no status_line to send
        bot._application.bot.send_message.assert_not_called()

    async def test_fallback_send_message_failure_logged(self, caplog):
        """If fallback send_message also fails, it should be logged."""
        bot = _make_bot()
        bot._application = MagicMock()
        bot._application.bot.send_message = AsyncMock(
            side_effect=Exception("Network error"),
        )

        result = CallbackResult(
            answer_text="Done",
            success=True,
            status_line="EXITED -- SBIN",
        )

        query = MagicMock()
        query.answer = AsyncMock()
        query.message.text = "Signal"
        query.edit_message_text = AsyncMock(
            side_effect=BadRequest("Too old"),
        )

        with caplog.at_level("ERROR"):
            await bot._apply_callback_result(query, result)

        assert "fallback" in caplog.text.lower() or "Failed" in caplog.text


class TestTimeoutRetry:
    """TimedOut on query.answer should retry once after 1 second."""

    async def test_answer_callback_timeout_retries(self):
        """TimedOut on first answer attempt should retry after 1s sleep."""
        bot = _make_bot()
        bot._application = MagicMock()

        result = CallbackResult(
            answer_text="Trade logged",
            success=True,
        )

        query = MagicMock()
        # First call raises TimedOut, second succeeds
        query.answer = AsyncMock(
            side_effect=[TimedOut(), None],
        )
        query.edit_message_reply_markup = AsyncMock()

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await bot._apply_callback_result(query, result)

        # Should have called answer twice
        assert query.answer.call_count == 2
        # Should have slept 1 second between retries
        mock_sleep.assert_called_once_with(1)

    async def test_answer_callback_timeout_retry_also_fails(self, caplog):
        """If retry also fails, warning should be logged."""
        bot = _make_bot()
        bot._application = MagicMock()

        result = CallbackResult(
            answer_text="Trade logged",
            success=True,
        )

        query = MagicMock()
        # Both calls fail
        query.answer = AsyncMock(
            side_effect=[TimedOut(), Exception("Still failing")],
        )
        query.edit_message_reply_markup = AsyncMock()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with caplog.at_level("WARNING"):
                await bot._apply_callback_result(query, result)

        assert "failed to answer" in caplog.text.lower()


class TestExceptionHandling:
    """_handle_callback should catch unhandled exceptions."""

    async def test_unhandled_exception_answers_error(self):
        """Unhandled exception in dispatch should answer 'Something went wrong'."""
        bot = _make_bot()
        bot._application = MagicMock()

        # Make dispatch raise an unexpected error
        bot._dispatch_callback = AsyncMock(
            side_effect=RuntimeError("Unexpected"),
        )

        query = MagicMock()
        query.data = "taken:1"
        query.message.chat_id = 123456
        query.answer = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        await bot._handle_callback(update, MagicMock())

        query.answer.assert_called_once_with("Something went wrong. Try again.")

    async def test_unhandled_exception_logged(self, caplog):
        """Unhandled exception should be logged."""
        bot = _make_bot()
        bot._application = MagicMock()

        bot._dispatch_callback = AsyncMock(
            side_effect=ValueError("Bad data"),
        )

        query = MagicMock()
        query.data = "invalid:data"
        query.message.chat_id = 123456
        query.answer = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        with caplog.at_level("ERROR"):
            await bot._handle_callback(update, MagicMock())

        assert "error handling callback" in caplog.text.lower()

    async def test_exception_in_answer_after_error_also_caught(self, caplog):
        """If answering 'Something went wrong' also fails, it should be caught."""
        bot = _make_bot()
        bot._application = MagicMock()

        bot._dispatch_callback = AsyncMock(
            side_effect=RuntimeError("Dispatch failed"),
        )

        query = MagicMock()
        query.data = "taken:1"
        query.message.chat_id = 123456
        # answer also fails
        query.answer = AsyncMock(side_effect=Exception("Network down"))

        update = MagicMock()
        update.callback_query = query

        with caplog.at_level("ERROR"):
            # Should not raise
            await bot._handle_callback(update, MagicMock())

        assert "failed to answer callback after error" in caplog.text.lower()

    async def test_db_failure_still_answers_callback(self):
        """DB write failure in handler shouldn't prevent callback answer."""
        bot = _make_bot()
        bot._application = MagicMock()

        # Simulate a handler that partially fails (DB error in action recording)
        # but still returns a CallbackResult
        result = CallbackResult(
            answer_text="Trade logged: SBIN",
            success=True,
            status_line="TAKEN -- Tracking SBIN",
        )

        query = MagicMock()
        query.answer = AsyncMock()
        query.message.text = "Signal"
        query.edit_message_text = AsyncMock()

        await bot._apply_callback_result(query, result)

        # Answer must have been called regardless
        query.answer.assert_called_once_with("Trade logged: SBIN")
        # Message update should also proceed
        query.edit_message_text.assert_called_once()


class TestSecurityCheck:
    """Callback from wrong chat_id should be silently ignored."""

    async def test_unauthorized_chat_id_ignored(self, caplog):
        """Callback from non-configured chat_id should be ignored."""
        bot = _make_bot()
        bot._application = MagicMock()

        query = MagicMock()
        query.data = "taken:1"
        query.message.chat_id = 999999  # Wrong chat_id
        query.answer = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        with caplog.at_level("WARNING"):
            await bot._handle_callback(update, MagicMock())

        # Should not call answer (silently ignored)
        query.answer.assert_not_called()
        assert "unauthorized" in caplog.text.lower()
