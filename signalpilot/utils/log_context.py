"""Async-aware logging context using contextvars.

Provides ContextVar-backed fields (cycle_id, phase, symbol, job_name, command)
that are automatically injected into log records by SignalPilotFormatter.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token

_cycle_id: ContextVar[str | None] = ContextVar("cycle_id", default=None)
_phase: ContextVar[str | None] = ContextVar("phase", default=None)
_symbol: ContextVar[str | None] = ContextVar("symbol", default=None)
_job_name: ContextVar[str | None] = ContextVar("job_name", default=None)
_command: ContextVar[str | None] = ContextVar("command", default=None)

_ALL_VARS: dict[str, ContextVar[str | None]] = {
    "cycle_id": _cycle_id,
    "phase": _phase,
    "symbol": _symbol,
    "job_name": _job_name,
    "command": _command,
}


def set_context(**kwargs: str | None) -> None:
    """Set one or more context fields. Only non-None values are applied."""
    for key, value in kwargs.items():
        if value is not None:
            var = _ALL_VARS.get(key)
            if var is None:
                raise ValueError(f"Unknown context field: {key!r}")
            var.set(value)


def reset_context() -> None:
    """Reset all context fields to None."""
    for var in _ALL_VARS.values():
        var.set(None)


def get_cycle_id() -> str | None:
    return _cycle_id.get()


def get_phase() -> str | None:
    return _phase.get()


def get_symbol() -> str | None:
    return _symbol.get()


def get_job_name() -> str | None:
    return _job_name.get()


def get_command() -> str | None:
    return _command.get()


@asynccontextmanager
async def log_context(**kwargs: str | None) -> AsyncIterator[None]:
    """Async context manager that sets context fields and restores them on exit.

    Uses token-based reset so nested context managers only revert their own
    fields, preserving the outer context.
    """
    tokens: list[tuple[ContextVar[str | None], Token[str | None]]] = []
    for key, value in kwargs.items():
        var = _ALL_VARS.get(key)
        if var is None:
            raise ValueError(f"Unknown context field: {key!r}")
        tokens.append((var, var.set(value)))
    try:
        yield
    finally:
        for var, token in tokens:
            var.reset(token)
