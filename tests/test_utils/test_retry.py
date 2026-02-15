"""Tests for the retry decorator."""

import asyncio
from unittest.mock import patch

import pytest

from signalpilot.utils.retry import with_retry


class TestWithRetry:
    async def test_succeeds_on_first_attempt(self):
        call_count = 0

        @with_retry(max_retries=3)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    async def test_retries_on_failure_then_succeeds(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        async def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"Attempt {call_count}")
            return "ok"

        result = await fail_twice()
        assert result == "ok"
        assert call_count == 3

    async def test_raises_after_all_retries_exhausted(self):
        call_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("always fails")

        with pytest.raises(RuntimeError, match="always fails"):
            await always_fail()

        # 1 initial + 2 retries = 3 total
        assert call_count == 3

    async def test_only_catches_specified_exceptions(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01, exceptions=(ValueError,))
        async def type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("not caught")

        with pytest.raises(TypeError, match="not caught"):
            await type_error()

        # Should fail on first attempt without retrying
        assert call_count == 1

    async def test_exponential_backoff_delays(self):
        delays: list[float] = []

        async def mock_sleep(delay: float) -> None:
            delays.append(delay)

        @with_retry(max_retries=3, base_delay=1.0, exponential=True)
        async def always_fail():
            raise ValueError("fail")

        with patch("signalpilot.utils.retry.asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(ValueError):
                await always_fail()

        # Delays should be: 1.0, 2.0, 4.0 (exponential backoff)
        assert len(delays) == 3
        assert delays[0] == pytest.approx(1.0)
        assert delays[1] == pytest.approx(2.0)
        assert delays[2] == pytest.approx(4.0)

    async def test_constant_delay_when_not_exponential(self):
        delays: list[float] = []

        async def mock_sleep(delay: float) -> None:
            delays.append(delay)

        @with_retry(max_retries=3, base_delay=0.5, exponential=False)
        async def always_fail():
            raise ValueError("fail")

        with patch("signalpilot.utils.retry.asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(ValueError):
                await always_fail()

        assert all(d == pytest.approx(0.5) for d in delays)

    async def test_max_delay_caps_backoff(self):
        delays: list[float] = []

        async def mock_sleep(delay: float) -> None:
            delays.append(delay)

        @with_retry(max_retries=5, base_delay=1.0, max_delay=5.0, exponential=True)
        async def always_fail():
            raise ValueError("fail")

        with patch("signalpilot.utils.retry.asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(ValueError):
                await always_fail()

        assert len(delays) == 5
        assert delays[0] == pytest.approx(1.0)
        assert delays[1] == pytest.approx(2.0)
        assert delays[2] == pytest.approx(4.0)
        assert delays[3] == pytest.approx(5.0)  # capped
        assert delays[4] == pytest.approx(5.0)  # capped

    async def test_preserves_function_name(self):
        @with_retry()
        async def my_function():
            pass

        assert my_function.__name__ == "my_function"

    async def test_zero_retries_means_single_attempt(self):
        call_count = 0

        @with_retry(max_retries=0, base_delay=0.01)
        async def fail_once():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await fail_once()

        assert call_count == 1

    def test_rejects_sync_function(self):
        with pytest.raises(TypeError, match="can only decorate async functions"):

            @with_retry()
            def sync_func():
                pass
