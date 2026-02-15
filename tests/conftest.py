"""Shared test fixtures for SignalPilot."""

import pytest


@pytest.fixture
def required_env(monkeypatch):
    """Set all required environment variables for AppConfig."""
    monkeypatch.setenv("ANGEL_API_KEY", "test_key")
    monkeypatch.setenv("ANGEL_CLIENT_ID", "test_client")
    monkeypatch.setenv("ANGEL_MPIN", "1234")
    monkeypatch.setenv("ANGEL_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
