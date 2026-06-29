"""HTTP client for OpenAI Codex usage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import aiohttp

from .parser import parse_usage_response, retry_after_to_datetime


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
        url = f"{self._base_url}/wham/usage"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "codex-usage-home-assistant",
        }
        if self._account_id:
            headers["ChatGPT-Account-ID"] = self._account_id

        async with self._session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            response_headers = {key.lower(): value for key, value in resp.headers.items()}
            if resp.status in {401, 403}:
                raise CodexUsageAuthError(f"authentication failed ({resp.status})")
            if resp.status == 429:
                retry_at = retry_after_to_datetime(
                    response_headers.get("retry-after"), datetime.now(UTC)
                ) or datetime.now(UTC)
                raise CodexUsageRateLimited(retry_at)
            resp.raise_for_status()
            body = await resp.json(content_type=None)

        if not isinstance(body, dict):
            body = {}
        data = parse_usage_response(body, response_headers)
        data["last_http_status"] = resp.status
        data["api_error"] = 0
        return data


def _normalize_base_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/") or "https://chatgpt.com"
    if (
        base.startswith(("https://chatgpt.com", "https://chat.openai.com"))
        and "/backend-api" not in base
    ):
        return f"{base}/backend-api"
    return base
