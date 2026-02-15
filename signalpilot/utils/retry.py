"""Retry decorator with exponential backoff for async functions."""

import asyncio
import functools
import inspect
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger("signalpilot.utils.retry")

T = TypeVar("T")


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential: bool = True,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[..., Any]:
    """
    Decorator for async functions that should be retried on failure.

    Uses exponential backoff by default. On each failed attempt, logs a warning
    and sleeps before retrying. After all retries are exhausted, raises the last
    exception.

    Args:
        max_retries: Maximum number of retry attempts (total calls = max_retries + 1).
        base_delay: Base delay in seconds between retries.
        max_delay: Maximum delay in seconds (caps exponential growth).
        exponential: If True, uses exponential backoff; otherwise, constant delay.
        exceptions: Tuple of exception types to catch and retry on.

    Raises:
        TypeError: If applied to a synchronous (non-async) function.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if not inspect.iscoroutinefunction(func):
            raise TypeError(
                f"@with_retry can only decorate async functions, "
                f"but {func.__name__!r} is synchronous"
            )

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: BaseException | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = base_delay * (2**attempt) if exponential else base_delay
                        delay = min(delay, max_delay)
                        logger.warning(
                            "%s failed (attempt %d/%d): %s. Retrying in %.1fs...",
                            func.__name__,
                            attempt + 1,
                            max_retries + 1,
                            e,
                            delay,
                        )
                        await asyncio.sleep(delay)
            raise last_exception  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
