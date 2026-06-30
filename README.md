# OpenAI Codex Usage - Home Assistant Integration

[![Open your Home Assistant instance and open this repository inside HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=aniolpages&repository=ha-codex-usage&category=integration)

A custom Home Assistant integration that monitors OpenAI Codex usage and rate-limit state.

Inspired by [trickv/hass-claude-usage](https://github.com/trickv/hass-claude-usage). The structure follows the same small Home Assistant pattern: config flow, `DataUpdateCoordinator`, and one service device with multiple sensors.

## What It Uses

The integration calls the same Codex backend usage path used by the official open-source Codex client:

`GET https://chatgpt.com/backend-api/wham/usage`

It also calls the read-only reset-credit detail path reported in [openai/codex#28963](https://github.com/openai/codex/issues/28963):

`GET https://chatgpt.com/backend-api/wham/rate-limit-reset-credits`

OpenAI documents Codex plan limits, the Codex usage dashboard, credits, and reset credits in the [Codex pricing docs](https://developers.openai.com/codex/pricing). Business and Enterprise workspaces also have official [Codex governance and analytics docs](https://developers.openai.com/codex/enterprise/governance).

Authentication uses the Codex device-code flow used by the official Codex CLI. Home Assistant shows a one-time code and an OpenAI login link, then stores the returned access and refresh tokens in the Home Assistant config entry. Tokens are refreshed automatically while the refresh token remains valid.

## Sensors

- **Plan Type**
- **Primary Usage** and **Primary Reset Time**
- **Secondary Usage** and **Secondary Reset Time**
- **Primary Window** and **Secondary Window**
- **Credits Enabled**, **Unlimited Credits**, and **Credits Balance**
- **Reset Credits Available**
- **Next Reset Credit Expiry**
- **Rate Limit Reached Type**
- **API Rate Limited Until**
- **API Error**

If OpenAI returns additional metered limits, the integration creates matching usage, reset-time, and window sensors on first setup.

When reset-credit details are available, the **Reset Credits Available** sensor includes sanitized `credits` attributes with grant, expiry, redeemed, and status fields. Credit IDs and account identifiers are not exposed. The integration does not call the reset-credit consume endpoint.

## Installation

### HACS

1. Add this repository as a custom repository in HACS.
2. Restart Home Assistant.
3. Install **OpenAI Codex Usage**.
4. Go to Settings -> Devices & Services -> Add Integration -> **OpenAI Codex Usage**.
5. Open the shown Codex login link, enter the one-time code, then submit the Home Assistant step.

### Manual

1. Copy `custom_components/codex_usage/` to your Home Assistant `custom_components/` directory.
2. Restart Home Assistant.
3. Add the integration from the UI.

## Configuration

The integration config flow signs in with ChatGPT through Codex device-code login. It stores the returned refresh token so usage polling survives Home Assistant restarts.

Existing entries created with a manually pasted access token still work, but new setups use device-code login.

## Rate Limits

The default polling interval is 900 seconds. The minimum configurable interval is 300 seconds.

The integration respects `429 Too Many Requests` and `Retry-After`: after a rate-limit response it keeps the last known data and skips further calls until the retry time. It also parses Codex rate-limit information from both the JSON body and `x-codex-*` response headers when present.

## Development

```bash
python -m unittest discover -s tests
ruff check .
python -m compileall custom_components tests
```

## License

MIT License. See [LICENSE](LICENSE).
