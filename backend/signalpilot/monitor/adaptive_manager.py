"""Adaptive strategy management for Phase 3 intraday risk control."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from signalpilot.events import EventBus

logger = logging.getLogger(__name__)


class AdaptationLevel(Enum):
    NORMAL = "normal"
    REDUCED = "reduced"
    PAUSED = "paused"


@dataclass
class StrategyAdaptationState:
    strategy_name: str = ""
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    level: AdaptationLevel = AdaptationLevel.NORMAL
    daily_wins: int = 0
    daily_losses: int = 0


class AdaptiveManager:
    CONSECUTIVE_LOSS_THROTTLE = 3
    CONSECUTIVE_LOSS_PAUSE = 5
    TRAILING_5D_WARN_THRESHOLD = 35.0
    TRAILING_10D_PAUSE_THRESHOLD = 30.0

    def __init__(
        self,
        adaptation_log_repo=None,
        config_repo=None,
        strategy_performance_repo=None,
        alert_callback=None,
        event_bus: EventBus | None = None,
    ):
        self._adaptation_log_repo = adaptation_log_repo
        self._config_repo = config_repo
        self._strategy_perf_repo = strategy_performance_repo
        self._alert_callback = alert_callback
        self._event_bus = event_bus
        self._states: dict[str, StrategyAdaptationState] = {}

    async def _send_alert(self, message: str) -> None:
        """Send alert via event bus or legacy callback."""
        if self._event_bus is not None:
            from signalpilot.events import AlertMessageEvent

            await self._event_bus.emit(AlertMessageEvent(message=message))
        elif self._alert_callback:
            await self._alert_callback(message)

    async def on_trade_exit(self, strategy_name: str, is_loss: bool, today: date) -> None:
        state = self._ensure_state(strategy_name)

        if is_loss:
            state.consecutive_losses += 1
            state.consecutive_wins = 0
            state.daily_losses += 1

            if (
                state.consecutive_losses >= self.CONSECUTIVE_LOSS_PAUSE
                and state.level != AdaptationLevel.PAUSED
            ):
                state.level = AdaptationLevel.PAUSED
                await self._log_adaptation(
                    today, strategy_name, "pause",
                    f"{state.consecutive_losses} consecutive losses",
                    None, None,
                )
                msg = (
                    f"\U0001f6ab {strategy_name} hit {state.consecutive_losses} consecutive losses today. "
                    f"Fully paused for rest of day."
                )
                await self._send_alert(msg)
            elif (
                state.consecutive_losses >= self.CONSECUTIVE_LOSS_THROTTLE
                and state.level == AdaptationLevel.NORMAL
            ):
                state.level = AdaptationLevel.REDUCED
                await self._log_adaptation(
                    today, strategy_name, "throttle",
                    f"{state.consecutive_losses} consecutive losses",
                    None, None,
                )
                msg = (
                    f"\u26a0\ufe0f {strategy_name} hit {state.consecutive_losses} consecutive losses today. "
                    f"Reduced to 5-star signals only for rest of day."
                )
                await self._send_alert(msg)
        else:
            state.consecutive_wins += 1
            state.consecutive_losses = 0
            state.daily_wins += 1

    def should_allow_signal(self, strategy_name: str, signal_strength: int) -> bool:
        if strategy_name not in self._states:
            return True
        state = self._states[strategy_name]
        if state.level == AdaptationLevel.PAUSED:
            return False
        if state.level == AdaptationLevel.REDUCED and signal_strength < 5:
            return False
        return True

    def reset_daily(self) -> None:
        self._states.clear()

    def get_all_states(self) -> dict[str, StrategyAdaptationState]:
        return dict(self._states)

    async def check_trailing_performance(self, today: date) -> list[str]:
        messages: list[str] = []
        strategies = ["Gap & Go", "ORB", "VWAP Reversal"]

        for strategy in strategies:
            if self._strategy_perf_repo is None:
                continue
            try:
                summary_5d = await self._strategy_perf_repo.get_performance_summary(
                    strategy, days=5
                )
                if summary_5d and hasattr(summary_5d, 'win_rate'):
                    if summary_5d.win_rate < self.TRAILING_5D_WARN_THRESHOLD:
                        msg = (
                            f"\u26a0\ufe0f {strategy}: 5-day trailing win rate "
                            f"{summary_5d.win_rate:.1f}% below {self.TRAILING_5D_WARN_THRESHOLD}% threshold"
                        )
                        messages.append(msg)

                summary_10d = await self._strategy_perf_repo.get_performance_summary(
                    strategy, days=10
                )
                if summary_10d and hasattr(summary_10d, 'win_rate'):
                    if summary_10d.win_rate < self.TRAILING_10D_PAUSE_THRESHOLD:
                        field_map = {
                            "Gap & Go": "gap_go_enabled",
                            "ORB": "orb_enabled",
                            "VWAP Reversal": "vwap_enabled",
                        }
                        field_name = field_map.get(strategy)
                        if field_name and self._config_repo:
                            await self._config_repo.set_strategy_enabled(field_name, False)

                        await self._log_adaptation(
                            today, strategy, "auto_pause",
                            f"10-day win rate {summary_10d.win_rate:.1f}% below threshold",
                            None, None,
                        )
                        msg = (
                            f"\U0001f6d1 {strategy}: 10-day trailing win rate "
                            f"{summary_10d.win_rate:.1f}% below {self.TRAILING_10D_PAUSE_THRESHOLD}% threshold. "
                            f"Auto-paused."
                        )
                        messages.append(msg)
            except Exception:
                logger.warning("Failed to check trailing performance for %s", strategy)

        return messages

    async def _log_adaptation(
        self, today: date, strategy: str, event_type: str,
        details: str, old_weight: float | None, new_weight: float | None,
    ) -> None:
        if self._adaptation_log_repo is not None:
            await self._adaptation_log_repo.insert_log(
                today=today, strategy=strategy, event_type=event_type,
                details=details, old_weight=old_weight, new_weight=new_weight,
            )

    def _ensure_state(self, strategy_name: str) -> StrategyAdaptationState:
        if strategy_name not in self._states:
            self._states[strategy_name] = StrategyAdaptationState(
                strategy_name=strategy_name,
            )
        return self._states[strategy_name]
