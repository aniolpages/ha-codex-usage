"""HTTP client for OpenAI Codex usage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import aiohttp

from .parser import (
    parse_reset_credits_response,
    parse_usage_response,
    retry_after_to_datetime,
)


class CodexUsageAuthError(Exception):
    """Authentication failed."""


class CodexUsageRateLimited(Exception):
    """The usage endpoint asked us to wait."""

    def __init__(self, retry_at: datetime) -> None:
        super().__init__("rate limited")
        self.retry_at = retry_at


class CodexUsageClient:
    """Minimal async client for Codex usage."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str,
        account_id: str | None,
        base_url: str,
    ) -> None:
        self._session = session
        self._token = token
        self._account_id = account_id
        self._base_url = _normalize_base_url(base_url)

    async def async_get_usage(self) -> dict[str, Any]:
        """Fetch and parse usage from the Codex backend."""
        body, response_headers, status = await self._get_json("/wham/usage", required=True)
        data = parse_usage_response(body, response_headers)
        reset_body, _, _ = await self._get_json("/wham/rate-limit-reset-credits", required=False)
        data.update(parse_reset_credits_response(reset_body))
        data["last_http_status"] = status
        data["api_error"] = 0
        return data

    async def _get_json(
        self, path: str, required: bool
    ) -> tuple[dict[str, Any], dict[str, str], int]:
        url = f"{self._base_url}{path}"
        async with self._session.get(
            url,
            headers=self._headers(),
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            response_headers = {key.lower(): value for key, value in resp.headers.items()}
            if resp.status in {401, 403}:
                if required:
                    raise CodexUsageAuthError(f"authentication failed ({resp.status})")
                return {}, response_headers, resp.status
            if resp.status == 429:
                retry_at = retry_after_to_datetime(
                    response_headers.get("retry-after"), datetime.now(UTC)
                ) or datetime.now(UTC)
                raise CodexUsageRateLimited(retry_at)
            if not required and resp.status >= 400:
                return {}, response_headers, resp.status
            resp.raise_for_status()
            try:
                body = await resp.json(content_type=None)
            except ValueError:
                if required:
                    raise
                body = {}
        return body if isinstance(body, dict) else {}, response_headers, resp.status

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "OpenAI-Beta": "codex-1",
            "originator": "Codex Desktop",
            "User-Agent": "codex-usage-home-assistant",
        }
        if self._account_id:
            headers["ChatGPT-Account-ID"] = self._account_id
        return headers


def _normalize_base_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/") or "https://chatgpt.com"
    if (
        base.startswith(("https://chatgpt.com", "https://chat.openai.com"))
        and "/backend-api" not in base
    ):
        return f"{base}/backend-api"
    return base
