# OpenAI Codex Usage - Home Assistant Integration

[![Open your Home Assistant instance and open this repository inside HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=aniolpages&repository=ha-codex-usage&category=integration)

A custom Home Assistant integration that monitors OpenAI Codex usage and rate-limit state.

Inspired by [trickv/hass-claude-usage](https://github.com/trickv/hass-claude-usage). The structure follows the same small Home Assistant pattern: config flow, `DataUpdateCoordinator`, and one service device with multiple sensors.

## What It Uses

The integration calls the same Codex backend usage path used by the official open-source Codex client:

`GET https://chatgpt.com/backend-api/wham/usage`

OpenAI documents Codex plan limits, the Codex usage dashboard, credits, and reset credits in the [Codex pricing docs](https://developers.openai.com/codex/pricing). Business and Enterprise workspaces also have official [Codex governance and analytics docs](https://developers.openai.com/codex/enterprise/governance).

OpenAI does not publicly document a third-party OAuth flow for personal ChatGPT accounts. For that reason, this integration does not try to recreate one. It accepts a bearer token that the Codex backend accepts. Business and Enterprise users should prefer a Codex access token from ChatGPT admin settings.

## Sensors

- **Plan Type**
- **Primary Usage** and **Primary Reset Time**
- **Secondary Usage** and **Secondary Reset Time**
- **Primary Window** and **Secondary Window**
- **Credits Enabled**, **Unlimited Credits**, and **Credits Balance**
- **Reset Credits Available**
- **Reset Credits Expiry**, only if OpenAI returns an expiry field
- **Rate Limit Reached Type**
- **API Rate Limited Until**
- **API Error**

If OpenAI returns additional metered limits, the integration creates matching usage, reset-time, and window sensors on first setup.

The usage endpoint currently exposes the number of available reset credits. The official client schema does not expose an expiry timestamp for those credits; this integration will show one only if the response starts returning it.

## Installation

### HACS

1. Add this repository as a custom repository in HACS.
2. Restart Home Assistant.
3. Install **OpenAI Codex Usage**.
4. Go to Settings -> Devices & Services -> Add Integration -> **OpenAI Codex Usage**.
5. Enter your token.

### Manual

1. Copy `custom_components/codex_usage/` to your Home Assistant `custom_components/` directory.
2. Restart Home Assistant.
3. Add the integration from the UI.

## Configuration

- **Access token**: bearer token accepted by the Codex backend.
- **ChatGPT account ID**: optional; passed as `ChatGPT-Account-ID` when your token needs workspace routing.
- **Base URL**: defaults to `https://chatgpt.com`. The integration normalizes this to `https://chatgpt.com/backend-api`.

## Rate Limits

The default polling interval is 900 seconds. The minimum configurable interval is 300 seconds.

The integration respects `429 Too Many Requests` and `Retry-After`: after a rate-limit response it keeps the last known data and skips further calls until the retry time. It also parses Codex rate-limit information from both the JSON body and `x-codex-*` response headers when present.

## Development

```bash
python -m unittest
ruff check .
python -m compileall custom_components tests
```

## License

MIT License. See [LICENSE](LICENSE).
