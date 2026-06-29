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
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_ID,
    CONF_BASE_URL,
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

        client = CodexUsageClient(
            aiohttp_client.async_get_clientsession(self.hass),
            self.config_entry.data[CONF_ACCESS_TOKEN],
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
