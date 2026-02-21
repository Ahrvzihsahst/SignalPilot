"""Tests for DuplicateChecker."""

from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

from signalpilot.db.models import CandidateSignal, SignalDirection, TradeRecord
from signalpilot.monitor.duplicate_checker import DuplicateChecker
from signalpilot.utils.constants import IST

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate(symbol: str) -> CandidateSignal:
    """Build a minimal CandidateSignal for the given symbol."""
    return CandidateSignal(
        symbol=symbol,
        direction=SignalDirection.BUY,
        strategy_name="ORB",
        entry_price=100.0,
        stop_loss=97.0,
        target_1=103.0,
        target_2=105.0,
        reason=f"Test candidate for {symbol}",
        generated_at=datetime(2026, 2, 20, 10, 0, 0, tzinfo=IST),
    )


def _make_active_trade(symbol: str) -> TradeRecord:
    """Build a TradeRecord representing an active (un-exited) trade."""
    return TradeRecord(
        signal_id=1,
        date=date(2026, 2, 20),
        symbol=symbol,
        entry_price=100.0,
        stop_loss=97.0,
        target_1=103.0,
        target_2=105.0,
        quantity=10,
        taken_at=datetime(2026, 2, 20, 9, 45, 0, tzinfo=IST),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def signal_repo() -> AsyncMock:
    """Mock signal repository."""
    mock = AsyncMock()
    mock.has_signal_for_stock_today = AsyncMock(return_value=False)
    return mock


@pytest.fixture
def trade_repo() -> AsyncMock:
    """Mock trade repository."""
    mock = AsyncMock()
    mock.get_active_trades = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def checker(signal_repo: AsyncMock, trade_repo: AsyncMock) -> DuplicateChecker:
    return DuplicateChecker(signal_repo, trade_repo)


# ---------------------------------------------------------------------------
# Existing signal blocks new candidate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_existing_signal_blocks_candidate(
    checker: DuplicateChecker, signal_repo: AsyncMock, trade_repo: AsyncMock
) -> None:
    """A stock that already has a signal today should be filtered out."""
    candidates = [_make_candidate("SBIN"), _make_candidate("TCS")]

    # SBIN already has a signal today
    async def has_signal(symbol: str, today: date) -> bool:
        return symbol == "SBIN"

    signal_repo.has_signal_for_stock_today = AsyncMock(side_effect=has_signal)

    today = date(2026, 2, 20)
    filtered = await checker.filter_duplicates(candidates, today)

    assert len(filtered) == 1
    assert filtered[0].symbol == "TCS"


# ---------------------------------------------------------------------------
# Active trade blocks new candidate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_trade_blocks_candidate(
    checker: DuplicateChecker, trade_repo: AsyncMock
) -> None:
    """A stock with an active (open) trade should be filtered out."""
    candidates = [_make_candidate("SBIN"), _make_candidate("TCS")]

    # SBIN has an active trade
    trade_repo.get_active_trades = AsyncMock(
        return_value=[_make_active_trade("SBIN")]
    )

    today = date(2026, 2, 20)
    filtered = await checker.filter_duplicates(candidates, today)

    assert len(filtered) == 1
    assert filtered[0].symbol == "TCS"


# ---------------------------------------------------------------------------
# Different stock passes through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_different_stock_passes_through(
    checker: DuplicateChecker, signal_repo: AsyncMock, trade_repo: AsyncMock
) -> None:
    """Candidates for stocks without existing signals or trades should pass."""
    candidates = [_make_candidate("SBIN"), _make_candidate("TCS"), _make_candidate("RELIANCE")]

    # No active trades, no existing signals
    trade_repo.get_active_trades = AsyncMock(return_value=[])
    signal_repo.has_signal_for_stock_today = AsyncMock(return_value=False)

    today = date(2026, 2, 20)
    filtered = await checker.filter_duplicates(candidates, today)

    assert len(filtered) == 3
    symbols = {c.symbol for c in filtered}
    assert symbols == {"SBIN", "TCS", "RELIANCE"}


# ---------------------------------------------------------------------------
# Empty input returns empty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_input_returns_empty(checker: DuplicateChecker) -> None:
    """Empty candidate list should return empty without calling repos."""
    today = date(2026, 2, 20)
    filtered = await checker.filter_duplicates([], today)

    assert filtered == []


# ---------------------------------------------------------------------------
# Both signal and trade blocking combined
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signal_and_trade_both_block(
    checker: DuplicateChecker, signal_repo: AsyncMock, trade_repo: AsyncMock
) -> None:
    """Both existing signals and active trades should independently block candidates."""
    candidates = [
        _make_candidate("SBIN"),     # blocked by active trade
        _make_candidate("TCS"),      # blocked by existing signal
        _make_candidate("RELIANCE"), # passes through
    ]

    trade_repo.get_active_trades = AsyncMock(
        return_value=[_make_active_trade("SBIN")]
    )

    async def has_signal(symbol: str, today: date) -> bool:
        return symbol == "TCS"

    signal_repo.has_signal_for_stock_today = AsyncMock(side_effect=has_signal)

    today = date(2026, 2, 20)
    filtered = await checker.filter_duplicates(candidates, today)

    assert len(filtered) == 1
    assert filtered[0].symbol == "RELIANCE"


# ---------------------------------------------------------------------------
# Single candidate blocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_candidate_all_blocked(
    checker: DuplicateChecker, trade_repo: AsyncMock
) -> None:
    """When the only candidate is blocked, result should be empty."""
    candidates = [_make_candidate("SBIN")]
    trade_repo.get_active_trades = AsyncMock(
        return_value=[_make_active_trade("SBIN")]
    )

    today = date(2026, 2, 20)
    filtered = await checker.filter_duplicates(candidates, today)

    assert filtered == []
