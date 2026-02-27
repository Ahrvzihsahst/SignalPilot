"""Inline keyboard builders for Telegram quick action buttons (Phase 4)."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_signal_keyboard(signal_id: int) -> InlineKeyboardMarkup:
    """Build the primary signal action keyboard: [TAKEN] [SKIP] [WATCH]."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("TAKEN", callback_data=f"taken:{signal_id}"),
                InlineKeyboardButton("SKIP", callback_data=f"skip:{signal_id}"),
                InlineKeyboardButton("WATCH", callback_data=f"watch:{signal_id}"),
            ]
        ]
    )


def build_taken_followup_keyboard(signal_id: int) -> InlineKeyboardMarkup:
    """Build the TAKEN followup keyboard: [Edit Entry Price] [Confirm]."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Edit Entry Price",
                    callback_data=f"edit_entry:{signal_id}",
                ),
                InlineKeyboardButton(
                    "Confirm",
                    callback_data=f"confirm_taken:{signal_id}",
                ),
            ]
        ]
    )


def build_skip_reason_keyboard(signal_id: int) -> InlineKeyboardMarkup:
    """Build the skip reason keyboard (2x2 grid)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "No Capital",
                    callback_data=f"skip_reason:{signal_id}:no_capital",
                ),
                InlineKeyboardButton(
                    "Low Confidence",
                    callback_data=f"skip_reason:{signal_id}:low_confidence",
                ),
            ],
            [
                InlineKeyboardButton(
                    "Already In Sector",
                    callback_data=f"skip_reason:{signal_id}:sector",
                ),
                InlineKeyboardButton(
                    "Other",
                    callback_data=f"skip_reason:{signal_id}:other",
                ),
            ],
        ]
    )


def build_t1_keyboard(trade_id: int) -> InlineKeyboardMarkup:
    """Build the T1 hit keyboard: [Book 50% at T1]."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Book 50% at T1",
                    callback_data=f"partial_exit:{trade_id}:t1",
                ),
            ]
        ]
    )


def build_t2_keyboard(trade_id: int) -> InlineKeyboardMarkup:
    """Build the T2 hit keyboard: [Exit Remaining at T2]."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Exit Remaining at T2",
                    callback_data=f"full_exit:{trade_id}:t2",
                ),
            ]
        ]
    )


def build_sl_approaching_keyboard(trade_id: int) -> InlineKeyboardMarkup:
    """Build the SL approaching keyboard: [Exit Now] [Hold]."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Exit Now",
                    callback_data=f"exit_now:{trade_id}",
                ),
                InlineKeyboardButton(
                    "Hold",
                    callback_data=f"hold:{trade_id}",
                ),
            ]
        ]
    )


def build_near_t2_keyboard(trade_id: int) -> InlineKeyboardMarkup:
    """Build the near-T2 keyboard: [Take Profit] [Let It Run]."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Take Profit",
                    callback_data=f"take_profit:{trade_id}",
                ),
                InlineKeyboardButton(
                    "Let It Run",
                    callback_data=f"let_run:{trade_id}",
                ),
            ]
        ]
    )
