"""Tests for TokenBucketRateLimiter."""

import asyncio
import time

import pytest

from signalpilot.utils.rate_limiter import TokenBucketRateLimiter


@pytest.mark.asyncio
async def test_acquire_respects_rate_limit() -> None:
    """Acquiring more tokens than the rate should introduce delay."""
    limiter = TokenBucketRateLimiter(rate=5, per_minute=0)

    # Drain the bucket (5 tokens)
    for _ in range(5):
        await limiter.acquire()

    # Next acquire should wait ~0.2s (1 token / 5 tokens-per-sec)
    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start

    assert elapsed >= 0.15  # allow small tolerance


@pytest.mark.asyncio
async def test_burst_within_rate_is_instant() -> None:
    """Acquiring up to rate tokens should be near-instant."""
    limiter = TokenBucketRateLimiter(rate=10, per_minute=0)

    start = time.monotonic()
    for _ in range(10):
        await limiter.acquire()
    elapsed = time.monotonic() - start

    assert elapsed < 0.1


@pytest.mark.asyncio
async def test_per_minute_cap() -> None:
    """Per-minute cap triggers a wait when exhausted."""
    # Use high per-second rate but low per-minute cap
    limiter = TokenBucketRateLimiter(rate=100, per_minute=3)

    for _ in range(3):
        await limiter.acquire()

    # Manually advance the minute counter to simulate near-limit
    # The 4th acquire should trigger the per-minute wait.
    # We set the window start to 59.5s ago so the wait is ~0.5s
    limiter._minute_window_start = time.monotonic() - 59.5

    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start

    assert elapsed >= 0.3  # waited for the minute window to roll over


@pytest.mark.asyncio
async def test_concurrent_acquires_are_serialised() -> None:
    """Multiple concurrent acquires don't exceed the rate."""
    limiter = TokenBucketRateLimiter(rate=3, per_minute=0)
    timestamps: list[float] = []

    async def worker():
        await limiter.acquire()
        timestamps.append(time.monotonic())

    # Launch 6 workers concurrently (rate=3, so 2nd batch waits)
    await asyncio.gather(*[worker() for _ in range(6)])

    assert len(timestamps) == 6
    # First 3 should be fast, last 3 should be delayed
    first_batch = timestamps[:3]
    assert max(first_batch) - min(first_batch) < 0.1
