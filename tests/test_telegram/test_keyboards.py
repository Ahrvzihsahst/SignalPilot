"""Tests for keyboard builder functions (Phase 4)."""

import pytest

from signalpilot.telegram.keyboards import (
    build_near_t2_keyboard,
    build_signal_keyboard,
    build_skip_reason_keyboard,
    build_sl_approaching_keyboard,
    build_t1_keyboard,
    build_t2_keyboard,
    build_taken_followup_keyboard,
)


class TestSignalKeyboard:
    def test_signal_keyboard_structure(self):
        kb = build_signal_keyboard(42)
        rows = kb.inline_keyboard
        assert len(rows) == 1
        assert len(rows[0]) == 3
        assert rows[0][0].text == "TAKEN"
        assert rows[0][1].text == "SKIP"
        assert rows[0][2].text == "WATCH"
        assert rows[0][0].callback_data == "taken:42"
        assert rows[0][1].callback_data == "skip:42"
        assert rows[0][2].callback_data == "watch:42"


class TestTakenFollowupKeyboard:
    def test_taken_followup_keyboard(self):
        kb = build_taken_followup_keyboard(7)
        rows = kb.inline_keyboard
        assert len(rows) == 1
        assert len(rows[0]) == 2
        assert rows[0][0].text == "Edit Entry Price"
        assert rows[0][0].callback_data == "edit_entry:7"
        assert rows[0][1].text == "Confirm"
        assert rows[0][1].callback_data == "confirm_taken:7"


class TestSkipReasonKeyboard:
    def test_skip_reason_keyboard(self):
        kb = build_skip_reason_keyboard(10)
        rows = kb.inline_keyboard
        assert len(rows) == 2
        assert len(rows[0]) == 2
        assert len(rows[1]) == 2
        assert "no_capital" in rows[0][0].callback_data
        assert "low_confidence" in rows[0][1].callback_data
        assert "sector" in rows[1][0].callback_data
        assert "other" in rows[1][1].callback_data


class TestT1Keyboard:
    def test_t1_keyboard(self):
        kb = build_t1_keyboard(5)
        rows = kb.inline_keyboard
        assert len(rows) == 1
        assert len(rows[0]) == 1
        assert rows[0][0].text == "Book 50% at T1"
        assert rows[0][0].callback_data == "partial_exit:5:t1"


class TestT2Keyboard:
    def test_t2_keyboard(self):
        kb = build_t2_keyboard(5)
        rows = kb.inline_keyboard
        assert len(rows) == 1
        assert len(rows[0]) == 1
        assert rows[0][0].text == "Exit Remaining at T2"
        assert rows[0][0].callback_data == "full_exit:5:t2"


class TestSLApproachingKeyboard:
    def test_sl_approaching_keyboard(self):
        kb = build_sl_approaching_keyboard(3)
        rows = kb.inline_keyboard
        assert len(rows) == 1
        assert len(rows[0]) == 2
        assert rows[0][0].text == "Exit Now"
        assert rows[0][0].callback_data == "exit_now:3"
        assert rows[0][1].text == "Hold"
        assert rows[0][1].callback_data == "hold:3"


class TestNearT2Keyboard:
    def test_near_t2_keyboard(self):
        kb = build_near_t2_keyboard(8)
        rows = kb.inline_keyboard
        assert len(rows) == 1
        assert len(rows[0]) == 2
        assert rows[0][0].text == "Take Profit"
        assert rows[0][0].callback_data == "take_profit:8"
        assert rows[0][1].text == "Let It Run"
        assert rows[0][1].callback_data == "let_run:8"


class TestCallbackDataSize:
    """Verify all callback data fits within Telegram's 64-byte limit."""

    @pytest.mark.parametrize("builder,args", [
        (build_signal_keyboard, (999999,)),
        (build_taken_followup_keyboard, (999999,)),
        (build_skip_reason_keyboard, (999999,)),
        (build_t1_keyboard, (999999,)),
        (build_t2_keyboard, (999999,)),
        (build_sl_approaching_keyboard, (999999,)),
        (build_near_t2_keyboard, (999999,)),
    ])
    def test_callback_data_under_64_bytes(self, builder, args):
        kb = builder(*args)
        for row in kb.inline_keyboard:
            for button in row:
                data = button.callback_data
                assert len(data.encode("utf-8")) <= 64, (
                    f"Callback data too long ({len(data.encode('utf-8'))} bytes): {data}"
                )
