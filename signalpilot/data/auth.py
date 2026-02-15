"""Angel One SmartAPI authentication lifecycle manager."""

import asyncio
import logging

import pyotp
from SmartApi import SmartConnect

from signalpilot.config import AppConfig
from signalpilot.utils.retry import with_retry

logger = logging.getLogger("signalpilot.data.auth")


class AuthenticationError(Exception):
    """Raised when authentication fails after all retries."""


class SmartAPIAuthenticator:
    """Manages Angel One SmartAPI authentication lifecycle."""

    def __init__(self, config: AppConfig) -> None:
        self._api_key: str = config.angel_api_key
        self._client_id: str = config.angel_client_id
        self._mpin: str = config.angel_mpin
        self._totp_secret: str = config.angel_totp_secret
        self._smart_connect: SmartConnect | None = None
        self._auth_token: str | None = None
        self._feed_token: str | None = None
        self._refresh_token: str | None = None

    @property
    def api_key(self) -> str:
        """Angel One API key (needed by WebSocket client)."""
        return self._api_key

    @property
    def client_id(self) -> str:
        """Angel One client ID (needed by WebSocket client)."""
        return self._client_id

    @with_retry(max_retries=3, base_delay=2.0, exceptions=(Exception,))
    async def authenticate(self) -> bool:
        """Authenticate with Angel One SmartAPI.

        Generates a fresh TOTP, calls generateSession, and stores tokens.
        Retries up to 3 times with exponential backoff.
        Returns True on success, raises AuthenticationError on failure.
        """
        totp = pyotp.TOTP(self._totp_secret).now()
        smart_connect = SmartConnect(api_key=self._api_key)

        def _do_auth():
            return smart_connect.generateSession(self._client_id, self._mpin, totp)

        try:
            data = await asyncio.to_thread(_do_auth)
        except Exception as e:
            logger.error("SmartAPI authentication failed: %s", e)
            raise AuthenticationError(f"SmartAPI authentication failed: {e}") from e

        if data.get("status") is False:
            msg = data.get("message", "Unknown auth error")
            logger.error("SmartAPI auth rejected: %s", msg)
            raise AuthenticationError(f"SmartAPI auth rejected: {msg}")

        token_data = data.get("data", {})
        self._auth_token = token_data.get("jwtToken")
        self._feed_token = token_data.get("feedToken")
        self._refresh_token = token_data.get("refreshToken")
        self._smart_connect = smart_connect

        logger.info("SmartAPI authentication successful for client %s", self._client_id)
        return True

    async def refresh_session(self) -> bool:
        """Re-authenticate using stored credentials."""
        logger.info("Refreshing SmartAPI session")
        return await self.authenticate()

    @property
    def auth_token(self) -> str:
        """Current JWT auth token. Raises if not authenticated."""
        if self._auth_token is None:
            raise AuthenticationError("Not authenticated. Call authenticate() first.")
        return self._auth_token

    @property
    def feed_token(self) -> str:
        """Current feed token for WebSocket. Raises if not authenticated."""
        if self._feed_token is None:
            raise AuthenticationError("Not authenticated. Call authenticate() first.")
        return self._feed_token

    @property
    def smart_connect(self) -> SmartConnect:
        """The underlying SmartConnect instance."""
        if self._smart_connect is None:
            raise AuthenticationError("Not authenticated. Call authenticate() first.")
        return self._smart_connect

    @property
    def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        return self._auth_token is not None
