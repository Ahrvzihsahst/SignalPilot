"""Tests for logging configuration."""

import logging
from pathlib import Path

import pytest

from signalpilot.utils.logger import configure_logging


class TestConfigureLogging:
    def teardown_method(self):
        """Clean up logger handlers after each test."""
        logger = logging.getLogger("signalpilot")
        logger.handlers.clear()

    def test_creates_logger_with_specified_level(self):
        configure_logging(level="DEBUG", log_file=None)
        logger = logging.getLogger("signalpilot")
        assert logger.level == logging.DEBUG

    def test_creates_logger_with_info_level_by_default(self):
        configure_logging(log_file=None)
        logger = logging.getLogger("signalpilot")
        assert logger.level == logging.INFO

    def test_attaches_console_handler(self):
        configure_logging(log_file=None)
        logger = logging.getLogger("signalpilot")
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)

    def test_attaches_file_handler_when_log_file_specified(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        configure_logging(log_file=log_file)
        logger = logging.getLogger("signalpilot")
        assert len(logger.handlers) == 2
        handler_types = {type(h) for h in logger.handlers}
        from logging.handlers import RotatingFileHandler

        assert RotatingFileHandler in handler_types

    def test_no_file_handler_when_log_file_is_none(self):
        configure_logging(log_file=None)
        logger = logging.getLogger("signalpilot")
        assert len(logger.handlers) == 1

    def test_clears_existing_handlers_on_repeated_calls(self):
        configure_logging(log_file=None)
        configure_logging(log_file=None)
        logger = logging.getLogger("signalpilot")
        # Should have exactly 1 handler, not 2
        assert len(logger.handlers) == 1

    def test_invalid_level_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid log level"):
            configure_logging(level="VERBOSE")

    def test_creates_parent_directories_for_log_file(self, tmp_path):
        log_file = str(tmp_path / "subdir" / "nested" / "test.log")
        configure_logging(log_file=log_file)
        assert Path(log_file).parent.exists()

    def test_log_message_format(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        configure_logging(log_file=log_file)
        logger = logging.getLogger("signalpilot.test")
        logger.info("test message")

        content = Path(log_file).read_text()
        assert "| INFO     | signalpilot.test | test message" in content
