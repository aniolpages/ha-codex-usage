"""Authentication helpers for OpenAI Codex."""

from __future__ import annotations

import base64
import binascii
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import aiohttp

from .const import (
    CODEX_OAUTH_CLIENT_ID,
    CODEX_OAUTH_ISSUER,
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_EMAIL,
    CONF_ACCOUNT_ID,
    CONF_EXPIRES_AT,
    CONF_ID_TOKEN,
    CONF_REFRESH_TOKEN,
    TOKEN_REFRESH_MARGIN,
)


class CodexAuthError(Exception):
    """Authentication failed."""


class CodexAuthPending(Exception):
    """The user has not completed device authorization yet."""


@dataclass
class CodexDeviceCode:
    """A pending Codex device-code login."""

    verification_url: str
    user_code: str
    device_auth_id: str
    interval: int


@dataclass
class CodexTokens:
    """OAuth tokens returned by Codex auth."""

    access_token: str | None
    refresh_token: str | None
    id_token: str | None


class CodexAuthClient:
    """Minimal client for the Codex device-code auth flow."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        issuer: str = CODEX_OAUTH_ISSUER,
        client_id: str = CODEX_OAUTH_CLIENT_ID,
    ) -> None:
        self._session = session
        self._issuer = issuer.rstrip("/")
        self._client_id = client_id

    async def async_request_device_code(self) -> CodexDeviceCode:
        """Start device-code login."""
        body = await self._post_json(
            f"{self._issuer}/api/accounts/deviceauth/usercode",
            {"client_id": self._client_id},
        )
        try:
            interval = int(body.get("interval", 5))
        except (TypeError, ValueError):
            interval = 5
        return CodexDeviceCode(
            verification_url=f"{self._issuer}/codex/device",
            user_code=str(body["user_code"]),
            device_auth_id=str(body["device_auth_id"]),
            interval=max(1, interval),
        )

    async def async_complete_device_code(self, device_code: CodexDeviceCode) -> CodexTokens:
        """Exchange a completed device-code login for tokens."""
        async with self._session.post(
            f"{self._issuer}/api/accounts/deviceauth/token",
            json={
                "device_auth_id": device_code.device_auth_id,
                "user_code": device_code.user_code,
            },
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status in {403, 404}:
                raise CodexAuthPending
            if not resp.ok:
                raise CodexAuthError(f"device auth failed ({resp.status})")
            body = await resp.json(content_type=None)

        return await self.async_exchange_code(
            code=str(body["authorization_code"]),
            code_verifier=str(body["code_verifier"]),
            redirect_uri=f"{self._issuer}/deviceauth/callback",
        )

    async def async_exchange_code(
        self, code: str, code_verifier: str, redirect_uri: str
    ) -> CodexTokens:
        """Exchange an authorization code for tokens."""
        payload = urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self._client_id,
                "code_verifier": code_verifier,
            }
        )
        async with self._session.post(
            f"{self._issuer}/oauth/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if not resp.ok:
                raise CodexAuthError(f"token exchange failed ({resp.status})")
            body = await resp.json(content_type=None)
        return _tokens_from_body(body)

    async def async_refresh_tokens(self, refresh_token: str) -> CodexTokens:
        """Refresh a Codex ChatGPT access token."""
        body = await self._post_json(
            f"{self._issuer}/oauth/token",
            {
                "client_id": self._client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        return _tokens_from_body(body)

    async def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status in {400, 401, 403}:
                raise CodexAuthError(f"authentication failed ({resp.status})")
            resp.raise_for_status()
            body = await resp.json(content_type=None)
        if not isinstance(body, dict):
            raise CodexAuthError("authentication response was not an object")
        return body


def token_config_data(tokens: CodexTokens, current: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return config-entry data for new or refreshed Codex tokens."""
    data = dict(current or {})
    if tokens.access_token:
        data[CONF_ACCESS_TOKEN] = tokens.access_token
        if expires_at := jwt_expires_at(tokens.access_token):
            data[CONF_EXPIRES_AT] = expires_at
    if tokens.refresh_token:
        data[CONF_REFRESH_TOKEN] = tokens.refresh_token
    if tokens.id_token:
        data[CONF_ID_TOKEN] = tokens.id_token
        claims = jwt_payload(tokens.id_token)
        profile = claims.get("https://api.openai.com/profile")
        auth = claims.get("https://api.openai.com/auth")
        if isinstance(profile, dict) and isinstance(profile.get("email"), str):
            data[CONF_ACCOUNT_EMAIL] = profile["email"]
        elif isinstance(claims.get("email"), str):
            data[CONF_ACCOUNT_EMAIL] = claims["email"]
        if isinstance(auth, dict):
            account_id = auth.get("chatgpt_account_id")
            if isinstance(account_id, str) and account_id:
                data[CONF_ACCOUNT_ID] = account_id
    return data


def needs_refresh(data: dict[str, Any]) -> bool:
    """Return True if the stored access token is missing or near expiry."""
    expires_at = data.get(CONF_EXPIRES_AT)
    if not isinstance(expires_at, int | float):
        expires_at = jwt_expires_at(str(data.get(CONF_ACCESS_TOKEN, "")))
    return expires_at is not None and time.time() >= expires_at - TOKEN_REFRESH_MARGIN


def jwt_expires_at(token: str) -> int | None:
    """Return a JWT exp claim."""
    exp = jwt_payload(token).get("exp")
    return exp if isinstance(exp, int) else None


def jwt_payload(token: str) -> dict[str, Any]:
    """Decode a JWT payload without verifying it."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        parsed = json.loads(decoded)
    except (binascii.Error, IndexError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _tokens_from_body(body: Any) -> CodexTokens:
    if not isinstance(body, dict):
        raise CodexAuthError("token response was not an object")
    return CodexTokens(
        access_token=_text(body.get("access_token")),
        refresh_token=_text(body.get("refresh_token")),
        id_token=_text(body.get("id_token")),
    )


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
