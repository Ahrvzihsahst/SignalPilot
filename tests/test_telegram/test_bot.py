"""Tests for SignalPilotBot.

These tests verify the bot's signal delivery and alert sending without
requiring a real Telegram connection. python-telegram-bot's Application
is mocked.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.db.models import (
    CandidateSignal,
    ExitAlert,
    ExitType,
    FinalSignal,
    RankedSignal,
    SignalDirection,
    TradeRecord,
)
from signalpilot.telegram.bot import SignalPilotBot
from signalpilot.utils.constants import IST


def _make_bot() -> SignalPilotBot:
    return SignalPilotBot(
        bot_token="fake-token",
        chat_id="123456",
        signal_repo=AsyncMock(),
        trade_repo=AsyncMock(),
        config_repo=AsyncMock(),
        metrics_calculator=AsyncMock(),
        exit_monitor=MagicMock(),
        get_current_prices=AsyncMock(),
    )


def _make_final_signal(generated_at: datetime | None = None) -> FinalSignal:
    if generated_at is None:
        generated_at = datetime.now(IST)
    candidate = CandidateSignal(
        symbol="SBIN",
        direction=SignalDirection.BUY,
        strategy_name="Gap & Go",
        entry_price=645.0,
        stop_loss=625.65,
        target_1=677.25,
        target_2=690.15,
        gap_pct=4.2,
        volume_ratio=2.1,
        price_distance_from_open_pct=1.5,
        reason="test",
        generated_at=generated_at,
    )
    ranked = RankedSignal(
        candidate=candidate,
        composite_score=0.75,
        rank=1,
        signal_strength=4,
    )
    return FinalSignal(
        ranked_signal=ranked,
        quantity=15,
        capital_required=9675.0,
        expires_at=datetime(2025, 1, 6, 10, 5, 0, tzinfo=IST),
    )


@pytest.mark.asyncio
async def test_send_signal_calls_bot() -> None:
    """send_signal should call bot.send_message with correct chat_id and HTML."""
    bot = _make_bot()
    mock_send = AsyncMock()
    bot._application = MagicMock()
    bot._application.bot.send_message = mock_send

    signal = _make_final_signal()
    await bot.send_signal(signal)

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args
    assert call_kwargs.kwargs["chat_id"] == "123456"
    assert call_kwargs.kwargs["parse_mode"] == "HTML"
    assert "BUY SIGNAL" in call_kwargs.kwargs["text"]


@pytest.mark.asyncio
async def test_send_alert_calls_bot() -> None:
    """send_alert should send plain text to chat_id."""
    bot = _make_bot()
    mock_send = AsyncMock()
    bot._application = MagicMock()
    bot._application.bot.send_message = mock_send

    await bot.send_alert("Test alert")

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["text"] == "Test alert"
    assert mock_send.call_args.kwargs["chat_id"] == "123456"


@pytest.mark.asyncio
async def test_send_exit_alert_formats_and_sends() -> None:
    """send_exit_alert should format the alert and send via send_alert."""
    bot = _make_bot()
    mock_send = AsyncMock()
    bot._application = MagicMock()
    bot._application.bot.send_message = mock_send

    trade = TradeRecord(id=1, symbol="SBIN", entry_price=100.0, stop_loss=97.0, quantity=10)
    alert = ExitAlert(
        trade=trade, exit_type=ExitType.SL_HIT,
        current_price=97.0, pnl_pct=-3.0, is_alert_only=False,
    )
    await bot.send_exit_alert(alert)

    mock_send.assert_called_once()
    text = mock_send.call_args.kwargs["text"]
    assert "STOP LOSS HIT" in text
    assert "SBIN" in text


@pytest.mark.asyncio
async def test_latency_warning_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Signal delivery > 30s should log a warning."""
    bot = _make_bot()
    mock_send = AsyncMock()
    bot._application = MagicMock()
    bot._application.bot.send_message = mock_send

    # Signal generated 60 seconds ago
    old_time = datetime.fromtimestamp(
        datetime.now(IST).timestamp() - 60, tz=IST
    )
    signal = _make_final_signal(generated_at=old_time)

    with caplog.at_level("WARNING"):
        await bot.send_signal(signal)

    assert "latency" in caplog.text.lower()
    assert "30s" in caplog.text


@pytest.mark.asyncio
async def test_no_latency_warning_when_fast(caplog: pytest.LogCaptureFixture) -> None:
    """Signal delivery < 30s should NOT log a warning."""
    bot = _make_bot()
    mock_send = AsyncMock()
    bot._application = MagicMock()
    bot._application.bot.send_message = mock_send

    # Signal generated just now
    signal = _make_final_signal(generated_at=datetime.now(IST))

    with caplog.at_level("WARNING"):
        await bot.send_signal(signal)

    assert "latency" not in caplog.text.lower()
