"""Tests for log context management using contextvars."""

import logging
from pathlib import Path

import pytest

from signalpilot.utils.log_context import (
    get_command,
    get_cycle_id,
    get_job_name,
    get_phase,
    get_symbol,
    log_context,
    reset_context,
    set_context,
)
from signalpilot.utils.logger import configure_logging


class TestSetAndGetContext:
    def teardown_method(self):
        reset_context()

    def test_defaults_are_none(self):
        reset_context()
        assert get_cycle_id() is None
        assert get_phase() is None
        assert get_symbol() is None
        assert get_job_name() is None
        assert get_command() is None

    def test_set_and_get_cycle_id(self):
        set_context(cycle_id="abc123")
        assert get_cycle_id() == "abc123"

    def test_set_and_get_phase(self):
        set_context(phase="OPENING")
        assert get_phase() == "OPENING"

    def test_set_and_get_symbol(self):
        set_context(symbol="RELIANCE")
        assert get_symbol() == "RELIANCE"

    def test_set_and_get_job_name(self):
        set_context(job_name="start_scanning")
        assert get_job_name() == "start_scanning"

    def test_set_and_get_command(self):
        set_context(command="TAKEN")
        assert get_command() == "TAKEN"

    def test_set_multiple_fields(self):
        set_context(cycle_id="abc", phase="ENTRY_WINDOW", symbol="TCS")
        assert get_cycle_id() == "abc"
        assert get_phase() == "ENTRY_WINDOW"
        assert get_symbol() == "TCS"

    def test_partial_update_preserves_other_fields(self):
        set_context(cycle_id="abc", phase="OPENING")
        set_context(symbol="INFY")
        assert get_cycle_id() == "abc"
        assert get_phase() == "OPENING"
        assert get_symbol() == "INFY"

    def test_none_values_are_skipped(self):
        set_context(cycle_id="abc")
        set_context(cycle_id=None)
        # None is skipped, so the value should remain
        assert get_cycle_id() == "abc"

    def test_reset_clears_all(self):
        set_context(cycle_id="abc", phase="OPENING", symbol="RELIANCE")
        reset_context()
        assert get_cycle_id() is None
        assert get_phase() is None
        assert get_symbol() is None

    def test_unknown_field_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown context field"):
            set_context(unknown_field="value")


class TestLogContext:
    def teardown_method(self):
        reset_context()

    async def test_sets_context_inside(self):
        async with log_context(symbol="RELIANCE"):
            assert get_symbol() == "RELIANCE"

    async def test_resets_after_exit(self):
        async with log_context(symbol="RELIANCE"):
            pass
        assert get_symbol() is None

    async def test_preserves_outer_context(self):
        set_context(cycle_id="outer")
        async with log_context(symbol="RELIANCE"):
            assert get_cycle_id() == "outer"
            assert get_symbol() == "RELIANCE"
        assert get_cycle_id() == "outer"
        assert get_symbol() is None

    async def test_nests_correctly(self):
        async with log_context(symbol="OUTER"):
            assert get_symbol() == "OUTER"
            async with log_context(symbol="INNER"):
                assert get_symbol() == "INNER"
            assert get_symbol() == "OUTER"

    async def test_resets_on_exception(self):
        with pytest.raises(RuntimeError):
            async with log_context(symbol="RELIANCE"):
                raise RuntimeError("test error")
        assert get_symbol() is None

    async def test_multiple_fields(self):
        async with log_context(cycle_id="abc", phase="OPENING"):
            assert get_cycle_id() == "abc"
            assert get_phase() == "OPENING"
        assert get_cycle_id() is None
        assert get_phase() is None

    async def test_unknown_field_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown context field"):
            async with log_context(bad_field="value"):
                pass


class TestFormatterIntegration:
    def teardown_method(self):
        reset_context()
        logger = logging.getLogger("signalpilot")
        logger.handlers.clear()

    def test_shows_dash_without_context(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        configure_logging(log_file=log_file)
        logger = logging.getLogger("signalpilot.test")
        logger.info("no context")

        content = Path(log_file).read_text()
        assert "[-] [-] [-] [INFO]" in content

    def test_shows_values_with_context(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        configure_logging(log_file=log_file)
        logger = logging.getLogger("signalpilot.test")
        set_context(cycle_id="deadbeef", phase="CONTINUOUS", symbol="TCS")
        logger.info("with context")

        content = Path(log_file).read_text()
        assert "[deadbeef] [CONTINUOUS] [TCS] [INFO]" in content
