"""Config flow for OpenAI Codex Usage."""

from __future__ import annotations

import hashlib
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client

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


class CodexUsageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenAI Codex Usage."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN].strip()
            account_id = user_input.get(CONF_ACCOUNT_ID, "").strip()
            base_url = user_input.get(CONF_BASE_URL, DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL

            try:
                await self._validate(token, account_id or None, base_url)
            except CodexUsageAuthError:
                errors["base"] = "invalid_auth"
            except (CodexUsageRateLimited, aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                unique_id = account_id or hashlib.sha256(token.encode()).hexdigest()[:16]
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="OpenAI Codex Usage",
                    data={
                        CONF_ACCESS_TOKEN: token,
                        CONF_ACCOUNT_ID: account_id,
                        CONF_BASE_URL: base_url,
                    },
                    options={CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCESS_TOKEN): str,
                    vol.Optional(CONF_ACCOUNT_ID): str,
                    vol.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a new token."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN].strip()
            account_id = entry.data.get(CONF_ACCOUNT_ID) or None
            base_url = entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL)
            try:
                await self._validate(token, account_id, base_url)
            except CodexUsageAuthError:
                errors["base"] = "invalid_auth"
            except (CodexUsageRateLimited, aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_ACCESS_TOKEN: token},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_ACCESS_TOKEN): str}),
            errors=errors,
        )

    async def _validate(self, token: str, account_id: str | None, base_url: str) -> None:
        """Validate credentials by fetching usage once."""
        client = CodexUsageClient(
            aiohttp_client.async_get_clientsession(self.hass),
            token,
            account_id,
            base_url,
        )
        await client.async_get_usage()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow."""
        return CodexUsageOptionsFlow()


class CodexUsageOptionsFlow(OptionsFlow):
    """Handle options for OpenAI Codex Usage."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UPDATE_INTERVAL, default=current_interval): vol.All(
                        int, vol.Range(min=300, max=86400)
                    ),
                }
            ),
        )
