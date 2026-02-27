"""Tests for Phase 4 formatter updates."""

from datetime import datetime, timedelta

import pytest

from signalpilot.db.models import (
    CandidateSignal,
    FinalSignal,
    RankedSignal,
    SignalDirection,
)
from signalpilot.telegram.formatters import (
    format_signal_actions_summary,
    format_signal_message,
)
from signalpilot.utils.constants import IST


def _make_final_signal():
    candidate = CandidateSignal(
        symbol="SBIN",
        direction=SignalDirection.BUY,
        strategy_name="Gap & Go",
        entry_price=100.0,
        stop_loss=97.0,
        target_1=105.0,
        target_2=107.0,
        gap_pct=4.0,
        volume_ratio=2.0,
        reason="Test",
        generated_at=datetime(2025, 1, 15, 9, 35, tzinfo=IST),
    )
    ranked = RankedSignal(candidate=candidate, composite_score=0.8, rank=1, signal_strength=4)
    return FinalSignal(
        ranked_signal=ranked, quantity=15, capital_required=1500.0,
        expires_at=datetime(2025, 1, 15, 10, 5, tzinfo=IST),
    )


class TestSignalMessageUpdated:
    def test_signal_message_footer_updated(self):
        msg = format_signal_message(_make_final_signal(), signal_id=42)
        assert "Tap a button below" in msg
        assert "TAKEN 42" in msg

    def test_signal_message_watchlisted_indicator(self):
        msg = format_signal_message(
            _make_final_signal(), signal_id=42, is_watchlisted=True,
        )
        assert "(Watchlisted)" in msg

    def test_signal_message_no_watchlisted_by_default(self):
        msg = format_signal_message(_make_final_signal(), signal_id=42)
        assert "(Watchlisted)" not in msg


class TestSignalActionsSummary:
    def test_signal_actions_summary_full(self):
        result = format_signal_actions_summary(
            taken_count=5, skipped_count=3, watched_count=2, no_action_count=1,
            avg_response_time_s=3.5,
            skip_reasons={"no_capital": 2, "low_confidence": 1},
        )
        assert "Signal Actions" in result
        assert "Taken: 5" in result
        assert "Skipped: 3" in result
        assert "Watched: 2" in result
        assert "No Action: 1" in result
        assert "Avg Response: 3.5s" in result
        assert "No Capital: 2" in result

    def test_signal_actions_summary_no_data(self):
        result = format_signal_actions_summary(
            taken_count=0, skipped_count=0, watched_count=0, no_action_count=0,
            avg_response_time_s=None,
        )
        assert result == ""
