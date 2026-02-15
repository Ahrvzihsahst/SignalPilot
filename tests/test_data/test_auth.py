"""Tests for SmartAPIAuthenticator."""

from unittest.mock import MagicMock, patch

import pytest

from signalpilot.config import AppConfig
from signalpilot.data.auth import AuthenticationError, SmartAPIAuthenticator


def _make_config() -> AppConfig:
    """Build an AppConfig with minimal test values."""
    return AppConfig(
        angel_api_key="test_api_key",
        angel_client_id="TEST123",
        angel_mpin="1234",
        angel_totp_secret="JBSWY3DPEHPK3PXP",  # valid base32 for pyotp
        telegram_bot_token="000:AAA",
        telegram_chat_id="12345",
    )


# ── Successful authentication ────────────────────────────────────


@pytest.mark.asyncio
async def test_authenticate_stores_tokens() -> None:
    config = _make_config()
    auth = SmartAPIAuthenticator(config)

    mock_sc = MagicMock()
    mock_sc.generateSession.return_value = {
        "status": True,
        "data": {
            "jwtToken": "jwt_test_token",
            "feedToken": "feed_test_token",
            "refreshToken": "refresh_test_token",
        },
    }

    with patch("signalpilot.data.auth.SmartConnect", return_value=mock_sc):
        result = await auth.authenticate()

    assert result is True
    assert auth.auth_token == "jwt_test_token"
    assert auth.feed_token == "feed_test_token"
    assert auth.smart_connect is mock_sc
    assert auth.is_authenticated is True


@pytest.mark.asyncio
async def test_authenticate_calls_generate_session_with_totp() -> None:
    config = _make_config()
    auth = SmartAPIAuthenticator(config)

    mock_sc = MagicMock()
    mock_sc.generateSession.return_value = {
        "status": True,
        "data": {"jwtToken": "j", "feedToken": "f", "refreshToken": "r"},
    }

    with patch("signalpilot.data.auth.SmartConnect", return_value=mock_sc), \
         patch("signalpilot.data.auth.pyotp.TOTP") as mock_totp_cls:
        mock_totp_cls.return_value.now.return_value = "123456"
        await auth.authenticate()

    mock_sc.generateSession.assert_called_once_with("TEST123", "1234", "123456")


# ── Authentication failure ───────────────────────────────────────


@pytest.mark.asyncio
async def test_authenticate_raises_on_api_rejection() -> None:
    config = _make_config()
    auth = SmartAPIAuthenticator(config)

    mock_sc = MagicMock()
    mock_sc.generateSession.return_value = {
        "status": False,
        "message": "Invalid credentials",
    }

    with patch("signalpilot.data.auth.SmartConnect", return_value=mock_sc), \
         patch("signalpilot.data.auth.asyncio.sleep", return_value=None):
        with pytest.raises(AuthenticationError, match="auth rejected"):
            await auth.authenticate()


@pytest.mark.asyncio
async def test_authenticate_raises_on_exception() -> None:
    config = _make_config()
    auth = SmartAPIAuthenticator(config)

    mock_sc = MagicMock()
    mock_sc.generateSession.side_effect = ConnectionError("network down")

    with patch("signalpilot.data.auth.SmartConnect", return_value=mock_sc), \
         patch("signalpilot.data.auth.asyncio.sleep", return_value=None):
        with pytest.raises(AuthenticationError, match="authentication failed"):
            await auth.authenticate()


# ── Retry behavior ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_authenticate_retries_on_failure() -> None:
    """Verify that authentication retries up to 3 times before raising."""
    config = _make_config()
    auth = SmartAPIAuthenticator(config)

    mock_sc = MagicMock()
    # Fail 3 times, succeed on 4th
    mock_sc.generateSession.side_effect = [
        ConnectionError("fail 1"),
        ConnectionError("fail 2"),
        ConnectionError("fail 3"),
        {
            "status": True,
            "data": {"jwtToken": "j", "feedToken": "f", "refreshToken": "r"},
        },
    ]

    with patch("signalpilot.data.auth.SmartConnect", return_value=mock_sc), \
         patch("signalpilot.data.auth.asyncio.sleep", return_value=None):
        result = await auth.authenticate()

    assert result is True
    assert mock_sc.generateSession.call_count == 4


@pytest.mark.asyncio
async def test_authenticate_exhausts_retries() -> None:
    """After max_retries+1 failures, the last exception propagates."""
    config = _make_config()
    auth = SmartAPIAuthenticator(config)

    mock_sc = MagicMock()
    mock_sc.generateSession.side_effect = ConnectionError("persistent failure")

    with patch("signalpilot.data.auth.SmartConnect", return_value=mock_sc), \
         patch("signalpilot.data.auth.asyncio.sleep", return_value=None):
        with pytest.raises(AuthenticationError):
            await auth.authenticate()

    # max_retries=3 → 4 attempts total
    assert mock_sc.generateSession.call_count == 4


# ── Properties raise when not authenticated ──────────────────────


def test_auth_token_raises_when_not_authenticated() -> None:
    config = _make_config()
    auth = SmartAPIAuthenticator(config)
    with pytest.raises(AuthenticationError, match="Not authenticated"):
        _ = auth.auth_token


def test_feed_token_raises_when_not_authenticated() -> None:
    config = _make_config()
    auth = SmartAPIAuthenticator(config)
    with pytest.raises(AuthenticationError, match="Not authenticated"):
        _ = auth.feed_token


def test_smart_connect_raises_when_not_authenticated() -> None:
    config = _make_config()
    auth = SmartAPIAuthenticator(config)
    with pytest.raises(AuthenticationError, match="Not authenticated"):
        _ = auth.smart_connect


def test_is_authenticated_false_by_default() -> None:
    config = _make_config()
    auth = SmartAPIAuthenticator(config)
    assert auth.is_authenticated is False


# ── Refresh session ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_session_re_authenticates() -> None:
    config = _make_config()
    auth = SmartAPIAuthenticator(config)

    mock_sc = MagicMock()
    mock_sc.generateSession.return_value = {
        "status": True,
        "data": {"jwtToken": "new_jwt", "feedToken": "new_feed", "refreshToken": "new_refresh"},
    }

    with patch("signalpilot.data.auth.SmartConnect", return_value=mock_sc):
        result = await auth.refresh_session()

    assert result is True
    assert auth.auth_token == "new_jwt"
