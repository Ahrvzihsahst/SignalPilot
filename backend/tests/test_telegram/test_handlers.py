"""Tests for Telegram command handlers."""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.db.models import SignalRecord, TradeRecord
from signalpilot.telegram.handlers import (
    handle_capital,
    handle_help,
    handle_journal,
    handle_status,
    handle_taken,
)
from signalpilot.utils.constants import IST


def _make_signal_record(
    signal_id: int = 1,
    symbol: str = "SBIN",
    entry_price: float = 645.0,
    expires_at: datetime | None = None,
) -> SignalRecord:
    now = datetime(2025, 1, 6, 9, 35, 0, tzinfo=IST)
    return SignalRecord(
        id=signal_id,
        date=now.date(),
        symbol=symbol,
        strategy="Gap & Go",
        entry_price=entry_price,
        stop_loss=625.65,
        target_1=677.25,
        target_2=690.15,
        quantity=15,
        capital_required=9675.0,
        signal_strength=4,
        gap_pct=4.2,
        volume_ratio=2.1,
        reason="test",
        created_at=now,
        expires_at=expires_at or (now + timedelta(minutes=30)),
        status="sent",
    )


# ── handle_taken ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_taken_with_active_signal() -> None:
    """TAKEN with active signal -> trade created, confirmation sent."""
    signal = _make_signal_record()
    signal_repo = AsyncMock()
    signal_repo.get_latest_active_signal.return_value = signal
    signal_repo.update_status = AsyncMock()

    trade_repo = AsyncMock()
    trade_repo.insert_trade.return_value = 42

    exit_monitor = MagicMock()

    now = datetime(2025, 1, 6, 9, 40, 0, tzinfo=IST)
    result = await handle_taken(signal_repo, trade_repo, exit_monitor, now=now)

    assert "Trade logged" in result
    assert "SBIN" in result
    trade_repo.insert_trade.assert_called_once()
    signal_repo.update_status.assert_called_once_with(signal.id, "taken")
    exit_monitor.start_monitoring.assert_called_once()


@pytest.mark.asyncio
async def test_taken_with_no_signal() -> None:
    """TAKEN with no active signal -> error message."""
    signal_repo = AsyncMock()
    signal_repo.get_latest_active_signal.return_value = None

    trade_repo = AsyncMock()
    exit_monitor = MagicMock()

    result = await handle_taken(signal_repo, trade_repo, exit_monitor)

    assert "No active signal" in result
    trade_repo.insert_trade.assert_not_called()


@pytest.mark.asyncio
async def test_taken_with_expired_signal() -> None:
    """TAKEN with expired signal -> expiry message."""
    expired_at = datetime(2025, 1, 6, 10, 0, 0, tzinfo=IST)
    signal = _make_signal_record(expires_at=expired_at)
    signal_repo = AsyncMock()
    signal_repo.get_latest_active_signal.return_value = signal

    trade_repo = AsyncMock()
    exit_monitor = MagicMock()

    now = datetime(2025, 1, 6, 10, 5, 0, tzinfo=IST)
    result = await handle_taken(signal_repo, trade_repo, exit_monitor, now=now)

    assert "expired" in result
    trade_repo.insert_trade.assert_not_called()


@pytest.mark.asyncio
async def test_taken_with_specific_id() -> None:
    """TAKEN 42 -> looks up signal by ID, creates trade."""
    signal = _make_signal_record(signal_id=42)
    signal_repo = AsyncMock()
    signal_repo.get_active_signal_by_id = AsyncMock(return_value=signal)
    signal_repo.update_status = AsyncMock()

    trade_repo = AsyncMock()
    trade_repo.insert_trade.return_value = 10

    exit_monitor = MagicMock()

    now = datetime(2025, 1, 6, 9, 40, 0, tzinfo=IST)
    result = await handle_taken(signal_repo, trade_repo, exit_monitor, now=now, text="TAKEN 42")

    assert "Trade logged" in result
    assert "SBIN" in result
    signal_repo.get_active_signal_by_id.assert_called_once_with(42, now)
    signal_repo.get_latest_active_signal.assert_not_called()


@pytest.mark.asyncio
async def test_taken_with_invalid_id() -> None:
    """TAKEN 999 with no matching signal -> error message with ID."""
    signal_repo = AsyncMock()
    signal_repo.get_active_signal_by_id = AsyncMock(return_value=None)

    trade_repo = AsyncMock()
    exit_monitor = MagicMock()

    now = datetime(2025, 1, 6, 9, 40, 0, tzinfo=IST)
    result = await handle_taken(signal_repo, trade_repo, exit_monitor, now=now, text="TAKEN 999")

    assert "No active signal with ID 999" in result
    trade_repo.insert_trade.assert_not_called()


@pytest.mark.asyncio
async def test_taken_with_slash_prefix_and_id() -> None:
    """/taken 42 -> same as TAKEN 42."""
    signal = _make_signal_record(signal_id=42)
    signal_repo = AsyncMock()
    signal_repo.get_active_signal_by_id = AsyncMock(return_value=signal)
    signal_repo.update_status = AsyncMock()

    trade_repo = AsyncMock()
    trade_repo.insert_trade.return_value = 10

    exit_monitor = MagicMock()

    now = datetime(2025, 1, 6, 9, 40, 0, tzinfo=IST)
    result = await handle_taken(signal_repo, trade_repo, exit_monitor, now=now, text="/taken 42")

    assert "Trade logged" in result
    signal_repo.get_active_signal_by_id.assert_called_once_with(42, now)


@pytest.mark.asyncio
async def test_taken_plain_text_falls_through_to_latest() -> None:
    """TAKEN (no ID) with text param -> falls through to get_latest_active_signal."""
    signal = _make_signal_record()
    signal_repo = AsyncMock()
    signal_repo.get_latest_active_signal = AsyncMock(return_value=signal)
    signal_repo.update_status = AsyncMock()

    trade_repo = AsyncMock()
    trade_repo.insert_trade.return_value = 5

    exit_monitor = MagicMock()

    now = datetime(2025, 1, 6, 9, 40, 0, tzinfo=IST)
    result = await handle_taken(signal_repo, trade_repo, exit_monitor, now=now, text="TAKEN")

    assert "Trade logged" in result
    signal_repo.get_latest_active_signal.assert_called_once_with(now)


@pytest.mark.asyncio
async def test_taken_none_text_falls_through_to_latest() -> None:
    """handle_taken with text=None -> falls through to get_latest_active_signal."""
    signal = _make_signal_record()
    signal_repo = AsyncMock()
    signal_repo.get_latest_active_signal = AsyncMock(return_value=signal)
    signal_repo.update_status = AsyncMock()

    trade_repo = AsyncMock()
    trade_repo.insert_trade.return_value = 5

    exit_monitor = MagicMock()

    now = datetime(2025, 1, 6, 9, 40, 0, tzinfo=IST)
    result = await handle_taken(signal_repo, trade_repo, exit_monitor, now=now)

    assert "Trade logged" in result
    signal_repo.get_latest_active_signal.assert_called_once_with(now)


# ── handle_status ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_with_open_trades() -> None:
    """STATUS with open trades -> formatted list with P&L."""
    signal_repo = AsyncMock()
    signal_repo.get_active_signals.return_value = []

    trade = TradeRecord(
        id=1, symbol="SBIN", entry_price=100.0,
        stop_loss=97.0, quantity=10,
    )
    trade_repo = AsyncMock()
    trade_repo.get_active_trades.return_value = [trade]

    async def get_prices(symbols):
        return {"SBIN": 105.0}

    now = datetime(2025, 1, 6, 10, 0, 0, tzinfo=IST)
    result = await handle_status(signal_repo, trade_repo, get_prices, now=now)

    assert "Open Trades" in result
    assert "SBIN" in result
    assert "+5.0%" in result


@pytest.mark.asyncio
async def test_status_with_no_data() -> None:
    """STATUS with no signals or trades -> empty message."""
    signal_repo = AsyncMock()
    signal_repo.get_active_signals.return_value = []

    trade_repo = AsyncMock()
    trade_repo.get_active_trades.return_value = []

    async def get_prices(symbols):
        return {}

    result = await handle_status(signal_repo, trade_repo, get_prices)

    assert "No active signals" in result


# ── handle_journal ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_journal_with_trades() -> None:
    """JOURNAL with trades -> metrics displayed."""
    from signalpilot.db.models import PerformanceMetrics

    metrics = PerformanceMetrics(
        date_range_start=date(2025, 1, 1),
        date_range_end=date(2025, 1, 6),
        total_signals=10,
        trades_taken=8,
        wins=6,
        losses=2,
        win_rate=75.0,
        total_pnl=3000.0,
        avg_win=600.0,
        avg_loss=-150.0,
        risk_reward_ratio=4.0,
        best_trade_symbol="RELIANCE",
        best_trade_pnl=1500.0,
        worst_trade_symbol="TCS",
        worst_trade_pnl=-200.0,
    )
    metrics_calc = AsyncMock()
    metrics_calc.calculate_performance_metrics.return_value = metrics

    result = await handle_journal(metrics_calc)

    assert "Trade Journal" in result
    assert "75.0%" in result
    assert "RELIANCE" in result


@pytest.mark.asyncio
async def test_journal_no_trades() -> None:
    """JOURNAL with no trades -> empty message."""
    metrics_calc = AsyncMock()
    metrics_calc.calculate_performance_metrics.return_value = None

    result = await handle_journal(metrics_calc)

    assert "No trades logged yet" in result


# ── handle_capital ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_capital_valid_amount() -> None:
    """CAPITAL 50000 -> updated and confirmed using actual max_positions from config."""
    config_repo = AsyncMock()
    config_repo.get_user_config.return_value = MagicMock(max_positions=8)

    result = await handle_capital(config_repo, "CAPITAL 50000")

    assert "Capital updated to 50,000" in result
    assert "Per-trade allocation" in result
    assert "6,250" in result  # 50000 / 8 positions
    config_repo.update_capital.assert_called_once_with(50000.0)


@pytest.mark.asyncio
async def test_capital_case_insensitive() -> None:
    """CAPITAL command should be case insensitive."""
    config_repo = AsyncMock()
    config_repo.get_user_config.return_value = MagicMock(max_positions=8)

    result = await handle_capital(config_repo, "capital 75000")

    assert "Capital updated to 75,000" in result


@pytest.mark.asyncio
async def test_capital_no_amount() -> None:
    """CAPITAL (no amount) -> usage message."""
    config_repo = AsyncMock()

    result = await handle_capital(config_repo, "CAPITAL")

    assert "Usage:" in result
    config_repo.update_capital.assert_not_called()


@pytest.mark.asyncio
async def test_capital_invalid_text() -> None:
    """CAPITAL with non-numeric -> usage message."""
    config_repo = AsyncMock()

    result = await handle_capital(config_repo, "CAPITAL abc")

    assert "Usage:" in result


# ── handle_help ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_help_lists_commands() -> None:
    """HELP -> command list with all commands."""
    result = await handle_help()

    assert "TAKEN [id]" in result
    assert "STATUS" in result
    assert "JOURNAL" in result
    assert "CAPITAL" in result
    assert "HELP" in result
