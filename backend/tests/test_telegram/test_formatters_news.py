"""Tests for news sentiment extensions to Telegram formatters."""

from datetime import datetime

import pytest

from signalpilot.db.models import (
    CandidateSignal,
    FinalSignal,
    RankedSignal,
    SignalDirection,
    SuppressedSignal,
)
from signalpilot.telegram.formatters import (
    format_signal_message,
    format_suppression_notification,
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
        reason="Gap up 4.0%",
        generated_at=datetime(2025, 1, 15, 9, 35, tzinfo=IST),
    )
    ranked = RankedSignal(
        candidate=candidate,
        composite_score=0.8,
        rank=1,
        signal_strength=4,
    )
    return FinalSignal(
        ranked_signal=ranked,
        quantity=15,
        capital_required=1500.0,
        expires_at=datetime(2025, 1, 15, 10, 5, tzinfo=IST),
    )


class TestFormatSuppressionNotification:
    """Tests for format_suppression_notification."""

    def test_includes_all_fields(self):
        suppressed = SuppressedSignal(
            symbol="SBIN",
            strategy="Gap & Go",
            original_stars=4,
            sentiment_score=-0.72,
            sentiment_label="STRONG_NEGATIVE",
            top_headline="SBIN reports massive fraud",
            reason="Strong negative sentiment (score: -0.72)",
            entry_price=104.50,
            stop_loss=100.0,
            target_1=109.73,
        )
        msg = format_suppression_notification(suppressed)
        assert "SIGNAL SUPPRESSED" in msg
        assert "SBIN" in msg
        assert "Gap & Go" in msg
        assert "-0.72" in msg
        assert "STRONG_NEGATIVE" in msg
        assert "SBIN reports massive fraud" in msg
        assert "104.50" in msg
        assert "100.00" in msg
        assert "109.73" in msg
        assert "NEWS SBIN" in msg

    def test_no_headline(self):
        suppressed = SuppressedSignal(
            symbol="TCS",
            strategy="ORB",
            original_stars=3,
            sentiment_score=-0.6,
            sentiment_label="STRONG_NEGATIVE",
            top_headline=None,
            reason="Test reason",
            entry_price=100.0,
            stop_loss=97.0,
            target_1=105.0,
        )
        msg = format_suppression_notification(suppressed)
        assert "TCS" in msg
        assert "NEWS TCS" in msg


class TestFormatSignalMessageNews:
    """Tests for news sentiment additions to format_signal_message."""

    def test_mild_negative_warning(self):
        signal = _make_final_signal()
        msg = format_signal_message(
            signal,
            news_sentiment_label="MILD_NEGATIVE",
            news_sentiment_score=-0.35,
            news_top_headline="SBIN faces regulatory scrutiny",
            original_star_rating=4,
        )
        assert "NEWS WARNING" in msg
        assert "-0.35" in msg
        assert "Downgraded from 4/5" in msg

    def test_positive_badge(self):
        signal = _make_final_signal()
        msg = format_signal_message(
            signal,
            news_sentiment_label="POSITIVE",
        )
        assert "Positive sentiment" in msg

    def test_no_news_note(self):
        signal = _make_final_signal()
        msg = format_signal_message(
            signal,
            news_sentiment_label="NO_NEWS",
        )
        assert "No recent news" in msg

    def test_neutral_no_change(self):
        signal = _make_final_signal()
        msg_neutral = format_signal_message(
            signal,
            news_sentiment_label="NEUTRAL",
        )
        msg_none = format_signal_message(signal)
        # NEUTRAL and None should produce same message (no news blocks)
        assert "NEWS WARNING" not in msg_neutral
        assert "Positive sentiment" not in msg_neutral
        assert "No recent news" not in msg_neutral

    def test_none_label_no_change(self):
        signal = _make_final_signal()
        msg = format_signal_message(signal, news_sentiment_label=None)
        assert "NEWS WARNING" not in msg
        assert "Positive sentiment" not in msg
        assert "No recent news" not in msg
