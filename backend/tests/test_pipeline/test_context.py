"""Tests for ScanContext."""

from signalpilot.db.models import SentimentResult, SuppressedSignal
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
    assert ctx.sentiment_results == {}
    assert ctx.suppressed_signals == []
    assert ctx.final_signals == []
    assert ctx.active_trade_count == 0


def test_scan_context_is_mutable():
    """ScanContext fields should be writable."""
    ctx = ScanContext()
    ctx.accepting_signals = False
    ctx.cycle_id = "abc123"
    assert ctx.accepting_signals is False
    assert ctx.cycle_id == "abc123"


def test_scan_context_sentiment_defaults_not_shared():
    """Each ScanContext gets independent sentiment_results and suppressed_signals."""
    ctx1 = ScanContext()
    ctx2 = ScanContext()
    assert ctx1.sentiment_results is not ctx2.sentiment_results
    assert ctx1.suppressed_signals is not ctx2.suppressed_signals
    # Mutating one does not affect the other
    ctx1.sentiment_results["SBIN"] = SentimentResult(
        score=-0.5, label="STRONG_NEGATIVE", headline=None,
        action="SUPPRESS", headline_count=0,
        top_negative_headline=None, model_used="vader",
    )
    assert "SBIN" not in ctx2.sentiment_results


def test_scan_context_sentiment_fields_writable():
    """ScanContext sentiment fields should be writable."""
    ctx = ScanContext()
    result = SentimentResult(
        score=0.5, label="POSITIVE", headline="Good news",
        action="PASS", headline_count=1,
        top_negative_headline=None, model_used="vader",
    )
    ctx.sentiment_results["SBIN"] = result
    assert ctx.sentiment_results["SBIN"] is result

    suppressed = SuppressedSignal(
        symbol="INFY", strategy="orb", original_stars=3,
        sentiment_score=-0.8, sentiment_label="STRONG_NEGATIVE",
        top_headline=None, reason="STRONG_NEGATIVE",
        entry_price=1500.0, stop_loss=1470.0, target_1=1545.0,
    )
    ctx.suppressed_signals.append(suppressed)
    assert len(ctx.suppressed_signals) == 1
    assert ctx.suppressed_signals[0] is suppressed
