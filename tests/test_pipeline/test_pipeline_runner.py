"""Tests for ScanPipeline runner."""

from datetime import datetime

from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stage import ScanPipeline
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase


class _DummyStage:
    """A simple stage that appends its name to a shared list."""

    def __init__(self, stage_name: str, tracker: list):
        self._name = stage_name
        self._tracker = tracker

    @property
    def name(self) -> str:
        return self._name

    async def process(self, ctx: ScanContext) -> ScanContext:
        self._tracker.append(self._name)
        return ctx


async def test_signal_stages_run_during_active_phase():
    """Signal stages should run during OPENING/ENTRY_WINDOW/CONTINUOUS."""
    tracker = []
    pipeline = ScanPipeline(
        signal_stages=[_DummyStage("sig1", tracker), _DummyStage("sig2", tracker)],
        always_stages=[_DummyStage("always1", tracker)],
    )
    ctx = ScanContext(
        now=datetime.now(IST),
        phase=StrategyPhase.ENTRY_WINDOW,
        accepting_signals=True,
    )
    await pipeline.run(ctx)
    assert tracker == ["sig1", "sig2", "always1"]


async def test_signal_stages_skipped_during_wind_down():
    """Signal stages should NOT run during WIND_DOWN."""
    tracker = []
    pipeline = ScanPipeline(
        signal_stages=[_DummyStage("sig1", tracker)],
        always_stages=[_DummyStage("always1", tracker)],
    )
    ctx = ScanContext(
        now=datetime.now(IST),
        phase=StrategyPhase.WIND_DOWN,
        accepting_signals=True,
    )
    await pipeline.run(ctx)
    assert tracker == ["always1"]


async def test_signal_stages_skipped_when_not_accepting():
    """Signal stages should NOT run when accepting_signals is False."""
    tracker = []
    pipeline = ScanPipeline(
        signal_stages=[_DummyStage("sig1", tracker)],
        always_stages=[_DummyStage("always1", tracker)],
    )
    ctx = ScanContext(
        now=datetime.now(IST),
        phase=StrategyPhase.OPENING,
        accepting_signals=False,
    )
    await pipeline.run(ctx)
    assert tracker == ["always1"]


async def test_always_stages_run_every_cycle():
    """Always stages run regardless of phase or accepting_signals."""
    for phase in StrategyPhase:
        for accepting in (True, False):
            tracker = []
            pipeline = ScanPipeline(
                signal_stages=[_DummyStage("sig", tracker)],
                always_stages=[_DummyStage("always", tracker)],
            )
            ctx = ScanContext(
                now=datetime.now(IST),
                phase=phase,
                accepting_signals=accepting,
            )
            await pipeline.run(ctx)
            assert "always" in tracker, (
                f"always stage should run for phase={phase}, accepting={accepting}"
            )


async def test_empty_pipeline():
    """Pipeline with no stages should return context unchanged."""
    pipeline = ScanPipeline(signal_stages=[], always_stages=[])
    ctx = ScanContext(now=datetime.now(IST), phase=StrategyPhase.OPENING)
    result = await pipeline.run(ctx)
    assert result is ctx
