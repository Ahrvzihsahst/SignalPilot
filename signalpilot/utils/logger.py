"""Logging configuration for SignalPilot."""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from signalpilot.utils.log_context import (
    get_command,
    get_cycle_id,
    get_job_name,
    get_phase,
    get_symbol,
)

# Noisy third-party loggers that should be suppressed to WARNING
_NOISY_LOGGERS = (
    "apscheduler",
    "telegram",
    "httpx",
    "SmartApi",
    "yfinance",
    "urllib3",
    "asyncio",
)


class SignalPilotFormatter(logging.Formatter):
    """Custom formatter that injects ContextVar fields into log records."""

    def format(self, record: logging.LogRecord) -> str:
        record.cycle_id = get_cycle_id() or "-"
        record.phase = get_phase() or "-"
        record.symbol = get_symbol() or "-"
        record.job_name = get_job_name() or "-"
        record.command = get_command() or "-"
        return super().format(record)


def configure_logging(
    level: str = "INFO",
    log_file: str | None = "signalpilot.log",
) -> None:
    """Configure application-wide logging with console and rotating file handlers.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Path to the rotating log file. Set to None to disable file logging.
    """
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level!r}")

    fmt = (
        "%(asctime)s [%(cycle_id)s] [%(phase)s] [%(symbol)s]"
        " [%(levelname)s] [%(name)s] %(message)s"
    )
    formatter = SignalPilotFormatter(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S")

    root = logging.getLogger("signalpilot")
    root.handlers.clear()
    root.setLevel(numeric_level)

    # Console handler — errors only
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.ERROR)
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler (timed rotating, optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            log_path,
            when="midnight",
            backupCount=7,
            utc=True,
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
