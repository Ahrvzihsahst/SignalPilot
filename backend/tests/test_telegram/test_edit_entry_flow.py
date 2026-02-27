"""Tests for Edit Entry Price flow and confirm_taken callback (Task 4.6)."""

from unittest.mock import AsyncMock, MagicMock, patch

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


class TestEditEntryFlow:
    """Tests for _handle_edit_entry (edit_entry:{signal_id} callback)."""

    async def test_edit_entry_sends_prompt_and_stores_pending(self):
        """edit_entry callback should send price prompt and store pending edit."""
        bot = _make_bot()
        bot._application = MagicMock()

        # Mock signal lookup
        mock_cursor = AsyncMock()
        mock_cursor.fetchone.return_value = {"symbol": "SBIN"}
        bot._signal_repo._conn.execute = AsyncMock(return_value=mock_cursor)

        # Mock send_message returning a message with message_id
        prompt_msg = MagicMock()
        prompt_msg.message_id = 999
        bot._application.bot.send_message = AsyncMock(return_value=prompt_msg)

        query = MagicMock()

        with patch("asyncio.create_task") as mock_create_task:
            result = await bot._handle_edit_entry(signal_id=42, query=query)

        assert result.success is True
        assert "SBIN" in result.answer_text
        assert 42 in bot._pending_entry_edits
        assert bot._pending_entry_edits[42] == 999

        # Verify prompt message sent
        bot._application.bot.send_message.assert_called_once()
        call_kwargs = bot._application.bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == "123456"
        assert "entry price" in call_kwargs["text"].lower()
        assert "SBIN" in call_kwargs["text"]

        # Verify timeout task was created
        mock_create_task.assert_called_once()

    async def test_edit_entry_unknown_signal_uses_unknown_symbol(self):
        """edit_entry with missing signal should use 'unknown' as symbol."""
        bot = _make_bot()
        bot._application = MagicMock()

        mock_cursor = AsyncMock()
        mock_cursor.fetchone.return_value = None
        bot._signal_repo._conn.execute = AsyncMock(return_value=mock_cursor)

        prompt_msg = MagicMock()
        prompt_msg.message_id = 100
        bot._application.bot.send_message = AsyncMock(return_value=prompt_msg)

        query = MagicMock()

        with patch("asyncio.create_task"):
            result = await bot._handle_edit_entry(signal_id=999, query=query)

        assert result.success is True
        assert "unknown" in result.answer_text.lower()

    async def test_edit_entry_timeout_sends_message_and_clears_pending(self):
        """After 60s timeout, pending edit should be cleared and timeout message sent."""
        bot = _make_bot()
        bot._application = MagicMock()

        mock_cursor = AsyncMock()
        mock_cursor.fetchone.return_value = {"symbol": "SBIN"}
        bot._signal_repo._conn.execute = AsyncMock(return_value=mock_cursor)

        prompt_msg = MagicMock()
        prompt_msg.message_id = 999
        bot._application.bot.send_message = AsyncMock(return_value=prompt_msg)

        query = MagicMock()

        # Capture the coroutine passed to create_task
        captured_coro = None

        def capture_task(coro):
            nonlocal captured_coro
            captured_coro = coro
            return MagicMock()  # return a mock task

        with patch("asyncio.create_task", side_effect=capture_task):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await bot._handle_edit_entry(signal_id=42, query=query)

        assert 42 in bot._pending_entry_edits

        # Now run the timeout coroutine (patching sleep to be instant)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await captured_coro

        # Pending edit should be cleared
        assert 42 not in bot._pending_entry_edits

        # Timeout message should have been sent (2nd call)
        calls = bot._application.bot.send_message.call_args_list
        timeout_call = calls[-1]
        assert "timed out" in timeout_call.kwargs["text"].lower()
        assert "SBIN" in timeout_call.kwargs["text"]

    async def test_edit_entry_no_timeout_if_already_resolved(self):
        """If pending edit was resolved before timeout, no timeout message sent."""
        bot = _make_bot()
        bot._application = MagicMock()

        mock_cursor = AsyncMock()
        mock_cursor.fetchone.return_value = {"symbol": "TCS"}
        bot._signal_repo._conn.execute = AsyncMock(return_value=mock_cursor)

        prompt_msg = MagicMock()
        prompt_msg.message_id = 500
        bot._application.bot.send_message = AsyncMock(return_value=prompt_msg)

        query = MagicMock()

        captured_coro = None

        def capture_task(coro):
            nonlocal captured_coro
            captured_coro = coro
            return MagicMock()

        with patch("asyncio.create_task", side_effect=capture_task):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await bot._handle_edit_entry(signal_id=10, query=query)

        # Simulate: user already replied, so pending edit was cleared
        del bot._pending_entry_edits[10]

        # Run timeout coroutine — should be a no-op
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await captured_coro

        # Only the initial prompt should have been sent (1 call)
        assert bot._application.bot.send_message.call_count == 1


class TestConfirmTakenCallback:
    """Tests for confirm_taken:{signal_id} callback via _dispatch_callback."""

    async def test_confirm_taken_returns_success(self):
        """confirm_taken callback should return success with status line."""
        bot = _make_bot()
        bot._application = MagicMock()

        result = await bot._dispatch_callback("confirm_taken:42", MagicMock())

        assert result.success is True
        assert "confirmed" in result.answer_text.lower()
        assert "signal price" in result.answer_text.lower()
        assert result.status_line is not None
        assert "CONFIRMED" in result.status_line

    async def test_confirm_taken_removes_keyboard_via_apply(self):
        """_apply_callback_result with confirm_taken result should edit message."""
        bot = _make_bot()
        bot._application = MagicMock()

        result = CallbackResult(
            answer_text="Trade confirmed at signal price.",
            success=True,
            status_line="CONFIRMED -- Using signal entry price",
        )

        query = MagicMock()
        query.answer = AsyncMock()
        query.message.text = "Original signal message"
        query.edit_message_text = AsyncMock()

        await bot._apply_callback_result(query, result)

        query.answer.assert_called_once_with("Trade confirmed at signal price.")
        query.edit_message_text.assert_called_once()
        edited_text = query.edit_message_text.call_args.kwargs["text"]
        assert "CONFIRMED" in edited_text
        assert "Original signal message" in edited_text
