"""OpenAI Codex Usage integration for Home Assistant."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CodexUsageAuthError, CodexUsageClient, CodexUsageRateLimited
from .auth import CodexAuthClient, CodexAuthError, needs_refresh, token_config_data
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_ID,
    CONF_BASE_URL,
    CONF_REFRESH_TOKEN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

type CodexUsageConfigEntry = ConfigEntry[CodexUsageCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: CodexUsageConfigEntry) -> bool:
    """Set up Codex Usage from a config entry."""
    coordinator = CodexUsageCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CodexUsageConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: CodexUsageConfigEntry) -> None:
    """Handle options updates."""
    coordinator: CodexUsageCoordinator = entry.runtime_data
    interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    coordinator.update_interval = timedelta(seconds=interval)


class CodexUsageCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch Codex usage data."""

    config_entry: CodexUsageConfigEntry

    def __init__(self, hass: HomeAssistant, entry: CodexUsageConfigEntry) -> None:
        """Initialize the coordinator."""
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
            always_update=False,
        )
        self._rate_limited_until: datetime | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch usage data."""
        if self._rate_limited_until and datetime.now(UTC) < self._rate_limited_until:
            return self._with_error(self.data, rate_limited_until=self._rate_limited_until)

        session = aiohttp_client.async_get_clientsession(self.hass)
        try:
            access_token = await self._async_access_token(session)
        except CodexAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error refreshing Codex token: {err}") from err

        client = CodexUsageClient(
            session,
            access_token,
            self.config_entry.data.get(CONF_ACCOUNT_ID) or None,
            self.config_entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
        )

        try:
            data = await client.async_get_usage()
        except CodexUsageAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except CodexUsageRateLimited as err:
            self._rate_limited_until = err.retry_at
            return self._with_error(self.data, rate_limited_until=err.retry_at)
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error fetching Codex usage: {err}") from err

        self._rate_limited_until = None
        return data

    async def _async_access_token(self, session: aiohttp.ClientSession) -> str:
        """Return a valid access token, refreshing if possible."""
        data = self.config_entry.data
        refresh_token = data.get(CONF_REFRESH_TOKEN)
        if refresh_token and needs_refresh(data):
            tokens = await CodexAuthClient(session).async_refresh_tokens(refresh_token)
            updated = token_config_data(tokens, data)
            self.hass.config_entries.async_update_entry(self.config_entry, data=updated)
            return updated[CONF_ACCESS_TOKEN]
        if not refresh_token and needs_refresh(data):
            raise CodexAuthError("Codex token expired; re-authenticate")
        return data[CONF_ACCESS_TOKEN]

    @staticmethod
    def _with_error(
        data: dict[str, Any] | None, rate_limited_until: datetime | None = None
    ) -> dict[str, Any]:
        """Return previous data with API error state."""
        current = dict(data or {})
        current["api_error"] = 1
        if rate_limited_until is not None:
            current["rate_limited_until"] = rate_limited_until.isoformat()
        return current
