"""Async token-bucket rate limiter for API call throttling."""

import asyncio
import logging
import time

logger = logging.getLogger("signalpilot.utils.rate_limiter")


class TokenBucketRateLimiter:
    """Token-bucket rate limiter that enforces requests-per-second limits.

    Tokens refill continuously at ``rate`` tokens per second, up to a maximum
    of ``rate`` tokens (burst capacity equals the per-second limit).  Each
    :meth:`acquire` call consumes one token; if no tokens are available the
    caller sleeps until a token is refilled.

    Also enforces a per-minute cap when ``per_minute`` is provided.

    Args:
        rate: Maximum requests per second (also the burst capacity).
        per_minute: Maximum requests per minute.  ``0`` means unlimited.
    """

    def __init__(self, rate: int = 3, per_minute: int = 0) -> None:
        self._rate = rate
        self._tokens = float(rate)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

        # Per-minute tracking
        self._per_minute = per_minute
        self._minute_window_start = time.monotonic()
        self._minute_count = 0

    async def acquire(self) -> None:
        """Wait until a token is available, then consume it."""
        async with self._lock:
            await self._wait_for_token()
            await self._wait_for_minute_window()
            self._tokens -= 1
            self._minute_count += 1

    async def _wait_for_token(self) -> None:
        """Refill tokens and sleep if the bucket is empty."""
        self._refill()
        while self._tokens < 1:
            deficit = 1 - self._tokens
            sleep_time = deficit / self._rate
            await asyncio.sleep(sleep_time)
            self._refill()

    def _refill(self) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
        self._last_refill = now

    async def _wait_for_minute_window(self) -> None:
        """Enforce the per-minute cap if configured."""
        if self._per_minute <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._minute_window_start
        if elapsed >= 60:
            self._minute_window_start = now
            self._minute_count = 0
        elif self._minute_count >= self._per_minute:
            wait = 60 - elapsed
            logger.warning(
                "Per-minute rate limit reached (%d/%d), waiting %.1fs",
                self._minute_count,
                self._per_minute,
                wait,
            )
            await asyncio.sleep(wait)
            self._minute_window_start = time.monotonic()
            self._minute_count = 0
