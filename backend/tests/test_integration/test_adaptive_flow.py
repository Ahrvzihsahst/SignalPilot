"""Adaptive manager integration test: trade exits -> strategy throttle/pause."""

from datetime import date
from unittest.mock import AsyncMock

from signalpilot.monitor.adaptive_manager import AdaptationLevel, AdaptiveManager


class TestAdaptiveFlow:
    async def test_throttle_then_pause_flow(self):
        """3 losses -> REDUCED, 5 losses -> PAUSED."""
        log_repo = AsyncMock()
        alert = AsyncMock()
        manager = AdaptiveManager(adaptation_log_repo=log_repo, alert_callback=alert)
        today = date(2025, 1, 15)

        # 3 losses -> REDUCED
        for _ in range(3):
            await manager.on_trade_exit("gap_go", is_loss=True, today=today)

        assert manager.should_allow_signal("gap_go", 4) is False  # 4-star blocked
        assert manager.should_allow_signal("gap_go", 5) is True   # 5-star allowed

        # 2 more losses -> PAUSED
        for _ in range(2):
            await manager.on_trade_exit("gap_go", is_loss=True, today=today)

        assert manager.should_allow_signal("gap_go", 5) is False  # ALL blocked

        # Other strategies unaffected
        assert manager.should_allow_signal("ORB", 1) is True

    async def test_win_resets_counter(self):
        """A win after losses resets the consecutive loss counter."""
        log_repo = AsyncMock()
        manager = AdaptiveManager(adaptation_log_repo=log_repo)
        today = date(2025, 1, 15)

        await manager.on_trade_exit("gap_go", is_loss=True, today=today)
        await manager.on_trade_exit("gap_go", is_loss=True, today=today)
        await manager.on_trade_exit("gap_go", is_loss=False, today=today)

        states = manager.get_all_states()
        assert states["gap_go"].consecutive_losses == 0
        assert states["gap_go"].level == AdaptationLevel.NORMAL

    async def test_daily_reset_clears_all(self):
        """Daily reset returns all strategies to NORMAL."""
        log_repo = AsyncMock()
        manager = AdaptiveManager(adaptation_log_repo=log_repo)
        today = date(2025, 1, 15)

        for _ in range(5):
            await manager.on_trade_exit("gap_go", is_loss=True, today=today)

        manager.reset_daily()
        assert manager.get_all_states() == {}
        assert manager.should_allow_signal("gap_go", 1) is True

    async def test_adaptation_logs_persisted(self):
        """State changes are logged to the adaptation_log repository."""
        log_repo = AsyncMock()
        manager = AdaptiveManager(adaptation_log_repo=log_repo)
        today = date(2025, 1, 15)

        for _ in range(3):
            await manager.on_trade_exit("gap_go", is_loss=True, today=today)

        # Should have logged the throttle event
        log_repo.insert_log.assert_called()
        call_args = log_repo.insert_log.call_args
        assert call_args.kwargs.get("event_type") == "throttle"
