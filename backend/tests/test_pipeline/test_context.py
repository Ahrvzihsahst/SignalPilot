"""Tests for ScanContext."""

from signalpilot.pipeline.context import ScanContext
from signalpilot.utils.market_calendar import StrategyPhase


def test_scan_context_defaults():
    """ScanContext should have sensible defaults."""
    ctx = ScanContext()
    assert ctx.cycle_id == ""
    assert ctx.now is None
    assert ctx.phase == StrategyPhase.OPENING
    assert ctx.accepting_signals is True
    assert ctx.user_config is None
    assert ctx.enabled_strategies == []
    assert ctx.all_candidates == []
    assert ctx.confirmation_map is None
    assert ctx.composite_scores is None
    assert ctx.ranked_signals == []
    assert ctx.final_signals == []
    assert ctx.active_trade_count == 0


def test_scan_context_is_mutable():
    """ScanContext fields should be writable."""
    ctx = ScanContext()
    ctx.accepting_signals = False
    ctx.cycle_id = "abc123"
    assert ctx.accepting_signals is False
    assert ctx.cycle_id == "abc123"
