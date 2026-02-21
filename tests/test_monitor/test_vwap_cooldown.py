"""Tests for VWAPCooldownTracker."""

from datetime import datetime, timedelta

import pytest

from signalpilot.monitor.vwap_cooldown import VWAPCooldownTracker
from signalpilot.utils.constants import IST

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tracker() -> VWAPCooldownTracker:
    return VWAPCooldownTracker(max_signals_per_stock=2, cooldown_minutes=60)


# ---------------------------------------------------------------------------
# can_signal — initially True
# ---------------------------------------------------------------------------


def test_can_signal_true_initially(tracker: VWAPCooldownTracker) -> None:
    """A stock with no prior signals should always be allowed."""
    now = datetime(2026, 2, 20, 10, 0, 0, tzinfo=IST)
    assert tracker.can_signal("SBIN", now) is True


def test_can_signal_true_for_different_symbols(tracker: VWAPCooldownTracker) -> None:
    """Cooldown for one symbol should not affect another."""
    now = datetime(2026, 2, 20, 10, 0, 0, tzinfo=IST)
    tracker.record_signal("SBIN", now)

    assert tracker.can_signal("TCS", now) is True


# ---------------------------------------------------------------------------
# can_signal — False after max signals (2)
# ---------------------------------------------------------------------------


def test_can_signal_false_after_max_signals(tracker: VWAPCooldownTracker) -> None:
    """After max_signals_per_stock (2) signals, further signals are blocked forever."""
    t1 = datetime(2026, 2, 20, 10, 0, 0, tzinfo=IST)
    t2 = t1 + timedelta(hours=2)  # well past cooldown
    t3 = t2 + timedelta(hours=2)

    tracker.record_signal("SBIN", t1)
    tracker.record_signal("SBIN", t2)

    # Even long after cooldown, blocked because count == max
    assert tracker.can_signal("SBIN", t3) is False


# ---------------------------------------------------------------------------
# can_signal — False within cooldown window (60 min)
# ---------------------------------------------------------------------------


def test_can_signal_false_within_cooldown(tracker: VWAPCooldownTracker) -> None:
    """Within 60 minutes of the last signal, new signals should be blocked."""
    t1 = datetime(2026, 2, 20, 10, 0, 0, tzinfo=IST)
    tracker.record_signal("SBIN", t1)

    # 30 minutes later -> still in cooldown
    t2 = t1 + timedelta(minutes=30)
    assert tracker.can_signal("SBIN", t2) is False

    # 59 minutes later -> still in cooldown
    t3 = t1 + timedelta(minutes=59)
    assert tracker.can_signal("SBIN", t3) is False


# ---------------------------------------------------------------------------
# can_signal — True after cooldown expires
# ---------------------------------------------------------------------------


def test_can_signal_true_after_cooldown_expires(tracker: VWAPCooldownTracker) -> None:
    """After cooldown period expires (>= 60 min), signals should be allowed again."""
    t1 = datetime(2026, 2, 20, 10, 0, 0, tzinfo=IST)
    tracker.record_signal("SBIN", t1)

    # Exactly 60 minutes later -> cooldown expired
    t2 = t1 + timedelta(minutes=60)
    assert tracker.can_signal("SBIN", t2) is True

    # 90 minutes later -> definitely past cooldown
    t3 = t1 + timedelta(minutes=90)
    assert tracker.can_signal("SBIN", t3) is True


# ---------------------------------------------------------------------------
# record_signal increments count
# ---------------------------------------------------------------------------


def test_record_signal_increments_count(tracker: VWAPCooldownTracker) -> None:
    """Each record_signal call should increment the signal count."""
    t1 = datetime(2026, 2, 20, 10, 0, 0, tzinfo=IST)
    tracker.record_signal("SBIN", t1)

    state = tracker.get_state()
    assert state["SBIN"][0] == 1  # count

    t2 = t1 + timedelta(hours=2)
    tracker.record_signal("SBIN", t2)

    state = tracker.get_state()
    assert state["SBIN"][0] == 2


# ---------------------------------------------------------------------------
# reset() clears all
# ---------------------------------------------------------------------------


def test_reset_clears_all(tracker: VWAPCooldownTracker) -> None:
    """reset() should clear all cooldown entries."""
    now = datetime(2026, 2, 20, 10, 0, 0, tzinfo=IST)
    tracker.record_signal("SBIN", now)
    tracker.record_signal("TCS", now)

    tracker.reset()

    # After reset, all symbols should be allowed
    assert tracker.can_signal("SBIN", now) is True
    assert tracker.can_signal("TCS", now) is True
    assert tracker.get_state() == {}


# ---------------------------------------------------------------------------
# get_state / restore_state round-trip
# ---------------------------------------------------------------------------


def test_get_state_restore_state_round_trip(tracker: VWAPCooldownTracker) -> None:
    """get_state -> restore_state should produce identical behavior."""
    t1 = datetime(2026, 2, 20, 10, 0, 0, tzinfo=IST)
    t2 = t1 + timedelta(minutes=30)

    tracker.record_signal("SBIN", t1)
    tracker.record_signal("TCS", t2)

    state = tracker.get_state()

    # Create a new tracker and restore
    new_tracker = VWAPCooldownTracker(max_signals_per_stock=2, cooldown_minutes=60)
    new_tracker.restore_state(state)

    # Check counts match
    new_state = new_tracker.get_state()
    assert new_state["SBIN"][0] == 1
    assert new_state["TCS"][0] == 1

    # Behavior should match: SBIN is in cooldown at t1+30min
    assert new_tracker.can_signal("SBIN", t2) is False
    # TCS just had a signal at t2, also in cooldown
    assert new_tracker.can_signal("TCS", t2 + timedelta(minutes=30)) is False


def test_get_state_serialization_format(tracker: VWAPCooldownTracker) -> None:
    """get_state should return dict with (count, iso_string) tuples."""
    t1 = datetime(2026, 2, 20, 10, 0, 0, tzinfo=IST)
    tracker.record_signal("SBIN", t1)

    state = tracker.get_state()
    assert "SBIN" in state
    count, iso_time = state["SBIN"]
    assert count == 1
    assert isinstance(iso_time, str)
    # Verify ISO string parses back to the same datetime
    parsed = datetime.fromisoformat(iso_time)
    assert parsed == t1


def test_restore_state_clears_previous_entries() -> None:
    """restore_state should replace all existing entries, not merge."""
    tracker = VWAPCooldownTracker(max_signals_per_stock=2, cooldown_minutes=60)
    t1 = datetime(2026, 2, 20, 10, 0, 0, tzinfo=IST)

    tracker.record_signal("SBIN", t1)
    tracker.record_signal("TCS", t1)

    # Restore with only one symbol
    state = {"RELIANCE": (1, t1.isoformat())}
    tracker.restore_state(state)

    new_state = tracker.get_state()
    assert "SBIN" not in new_state
    assert "TCS" not in new_state
    assert "RELIANCE" in new_state
