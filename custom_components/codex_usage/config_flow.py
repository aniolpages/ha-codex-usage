"""Config flow for OpenAI Codex Usage."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client

from .api import CodexUsageAuthError, CodexUsageClient, CodexUsageRateLimited
from .auth import (
    CodexAuthClient,
    CodexAuthError,
    CodexAuthPending,
    CodexDeviceCode,
    token_config_data,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_ID,
    CONF_ACCOUNT_EMAIL,
    CONF_BASE_URL,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)


class CodexUsageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenAI Codex Usage."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._device_code: CodexDeviceCode | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Start device-code login."""
        return await self.async_step_device_auth(user_input)

    async def async_step_device_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Codex device-code login."""
        errors: dict[str, str] = {}

        if self._device_code is None:
            try:
                self._device_code = await self._auth_client().async_request_device_code()
            except (CodexAuthError, aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"

        if user_input is not None:
            try:
                if self._device_code is None:
                    raise CodexAuthError("device code was not created")
                tokens = await self._auth_client().async_complete_device_code(self._device_code)
                data = token_config_data(tokens, {CONF_BASE_URL: DEFAULT_BASE_URL})
                await self._validate(
                    data[CONF_ACCESS_TOKEN],
                    data.get(CONF_ACCOUNT_ID) or None,
                    DEFAULT_BASE_URL,
                )
            except CodexAuthPending:
                errors["base"] = "authorization_pending"
            except (CodexAuthError, KeyError):
                errors["base"] = "exchange_failed"
            except CodexUsageAuthError:
                errors["base"] = "invalid_auth"
            except (CodexUsageRateLimited, aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                unique_id = data.get(CONF_ACCOUNT_ID) or data.get(CONF_ACCOUNT_EMAIL) or DOMAIN
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_title(data),
                    data=data,
                    options={CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
                )

        placeholders = _device_code_placeholders(self._device_code)
        return self.async_show_form(
            step_id="device_auth",
            data_schema=vol.Schema({}),
            description_placeholders=placeholders,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication."""
        self._device_code = None
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle device-code reauthentication."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if self._device_code is None:
            try:
                self._device_code = await self._auth_client().async_request_device_code()
            except (CodexAuthError, aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"

        if user_input is not None:
            try:
                if self._device_code is None:
                    raise CodexAuthError("device code was not created")
                tokens = await self._auth_client().async_complete_device_code(self._device_code)
                data = token_config_data(tokens, entry.data)
                await self._validate(
                    data[CONF_ACCESS_TOKEN],
                    data.get(CONF_ACCOUNT_ID) or None,
                    data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
                )
            except CodexAuthPending:
                errors["base"] = "authorization_pending"
            except (CodexAuthError, KeyError):
                errors["base"] = "exchange_failed"
            except CodexUsageAuthError:
                errors["base"] = "invalid_auth"
            except (CodexUsageRateLimited, aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                kwargs: dict[str, Any] = {"data_updates": data}
                if unique_id := data.get(CONF_ACCOUNT_ID) or data.get(CONF_ACCOUNT_EMAIL):
                    kwargs["unique_id"] = unique_id
                return self.async_update_reload_and_abort(entry, **kwargs)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({}),
            description_placeholders=_device_code_placeholders(self._device_code),
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

    def _auth_client(self) -> CodexAuthClient:
        """Return the Codex auth client."""
        return CodexAuthClient(aiohttp_client.async_get_clientsession(self.hass))

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


def _device_code_placeholders(device_code: CodexDeviceCode | None) -> dict[str, str]:
    return {
        "url": device_code.verification_url if device_code else "",
        "user_code": device_code.user_code if device_code else "",
    }


def _title(data: dict[str, Any]) -> str:
    email = data.get(CONF_ACCOUNT_EMAIL)
    return f"OpenAI Codex Usage ({email})" if email else "OpenAI Codex Usage"
