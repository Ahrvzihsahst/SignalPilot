"""Tests for AdaptiveManager."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.monitor.adaptive_manager import (
    AdaptationLevel,
    AdaptiveManager,
)


class TestAdaptiveManager:
    @pytest.fixture
    def mock_log_repo(self):
        return AsyncMock()

    @pytest.fixture
    def mock_config_repo(self):
        repo = AsyncMock()
        repo.set_strategy_enabled = AsyncMock()
        return repo

    @pytest.fixture
    def mock_alert(self):
        return AsyncMock()

    @pytest.fixture
    def manager(self, mock_log_repo, mock_alert):
        return AdaptiveManager(
            adaptation_log_repo=mock_log_repo,
            alert_callback=mock_alert,
        )

    async def test_3_consecutive_losses_triggers_reduced(self, manager):
        today = date(2025, 1, 15)
        for _ in range(3):
            await manager.on_trade_exit("gap_go", is_loss=True, today=today)
        states = manager.get_all_states()
        assert states["gap_go"].level == AdaptationLevel.REDUCED

    async def test_5_consecutive_losses_triggers_paused(self, manager):
        today = date(2025, 1, 15)
        for _ in range(5):
            await manager.on_trade_exit("gap_go", is_loss=True, today=today)
        states = manager.get_all_states()
        assert states["gap_go"].level == AdaptationLevel.PAUSED

    async def test_win_resets_consecutive_losses(self, manager):
        today = date(2025, 1, 15)
        await manager.on_trade_exit("gap_go", is_loss=True, today=today)
        await manager.on_trade_exit("gap_go", is_loss=True, today=today)
        await manager.on_trade_exit("gap_go", is_loss=False, today=today)
        states = manager.get_all_states()
        assert states["gap_go"].consecutive_losses == 0
        assert states["gap_go"].consecutive_wins == 1

    async def test_should_allow_signal_paused_blocks_all(self, manager):
        today = date(2025, 1, 15)
        for _ in range(5):
            await manager.on_trade_exit("gap_go", is_loss=True, today=today)
        assert manager.should_allow_signal("gap_go", 5) is False
        assert manager.should_allow_signal("gap_go", 1) is False

    async def test_should_allow_signal_reduced_blocks_below_5(self, manager):
        today = date(2025, 1, 15)
        for _ in range(3):
            await manager.on_trade_exit("gap_go", is_loss=True, today=today)
        assert manager.should_allow_signal("gap_go", 4) is False
        assert manager.should_allow_signal("gap_go", 5) is True

    async def test_should_allow_signal_normal_allows_all(self, manager):
        assert manager.should_allow_signal("gap_go", 1) is True
        assert manager.should_allow_signal("gap_go", 5) is True

    async def test_should_allow_unknown_strategy(self, manager):
        assert manager.should_allow_signal("unknown", 1) is True

    async def test_reset_daily(self, manager):
        today = date(2025, 1, 15)
        for _ in range(3):
            await manager.on_trade_exit("gap_go", is_loss=True, today=today)
        manager.reset_daily()
        assert manager.get_all_states() == {}

    async def test_throttle_alert(self, manager, mock_alert):
        today = date(2025, 1, 15)
        for _ in range(3):
            await manager.on_trade_exit("gap_go", is_loss=True, today=today)
        assert mock_alert.call_count >= 1
        msg = mock_alert.call_args_list[0][0][0]
        assert "3 consecutive losses" in msg

    async def test_pause_alert(self, manager, mock_alert):
        today = date(2025, 1, 15)
        for _ in range(5):
            await manager.on_trade_exit("gap_go", is_loss=True, today=today)
        # Should have throttle alert at 3 and pause alert at 5
        assert mock_alert.call_count >= 2

    async def test_log_repo_called_on_state_change(self, manager, mock_log_repo):
        today = date(2025, 1, 15)
        for _ in range(3):
            await manager.on_trade_exit("gap_go", is_loss=True, today=today)
        mock_log_repo.insert_log.assert_called()

    async def test_one_strategy_doesnt_affect_another(self, manager):
        today = date(2025, 1, 15)
        for _ in range(5):
            await manager.on_trade_exit("gap_go", is_loss=True, today=today)
        assert manager.should_allow_signal("gap_go", 5) is False
        assert manager.should_allow_signal("ORB", 1) is True

    async def test_check_trailing_5d_warning(self, mock_log_repo, mock_alert):
        mock_perf_repo = AsyncMock()
        summary = MagicMock()
        summary.win_rate = 30.0
        mock_perf_repo.get_performance_summary = AsyncMock(return_value=summary)

        manager = AdaptiveManager(
            adaptation_log_repo=mock_log_repo,
            strategy_performance_repo=mock_perf_repo,
            alert_callback=mock_alert,
        )
        messages = await manager.check_trailing_performance(date(2025, 1, 15))
        # Should have warning messages for strategies with <35% 5d win rate
        assert any("5-day trailing" in m for m in messages)

    async def test_check_trailing_10d_auto_pause(self, mock_log_repo, mock_config_repo, mock_alert):
        mock_perf_repo = AsyncMock()
        summary = MagicMock()
        summary.win_rate = 25.0  # Below both thresholds
        mock_perf_repo.get_performance_summary = AsyncMock(return_value=summary)

        manager = AdaptiveManager(
            adaptation_log_repo=mock_log_repo,
            config_repo=mock_config_repo,
            strategy_performance_repo=mock_perf_repo,
            alert_callback=mock_alert,
        )
        messages = await manager.check_trailing_performance(date(2025, 1, 15))
        assert any("Auto-paused" in m for m in messages)
        mock_config_repo.set_strategy_enabled.assert_called()
