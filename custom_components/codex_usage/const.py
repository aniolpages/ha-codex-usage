"""Constants for Codex Usage integration."""

DOMAIN = "codex_usage"

DEFAULT_BASE_URL = "https://chatgpt.com"
DEFAULT_UPDATE_INTERVAL = 900

CONF_ACCESS_TOKEN = "access_token"
CONF_ACCOUNT_ID = "account_id"
CONF_BASE_URL = "base_url"
CONF_UPDATE_INTERVAL = "update_interval"

SENSOR_DEFINITIONS = [
    ("plan_type", "Plan Type", None, "mdi:account-badge", None),
    ("codex_primary_usage_percent", "Primary Usage", "%", "mdi:timer-sand", None),
    ("codex_primary_reset_time", "Primary Reset Time", None, "mdi:timer-refresh", "timestamp"),
    ("codex_primary_window_minutes", "Primary Window", "min", "mdi:timer-outline", None),
    ("codex_secondary_usage_percent", "Secondary Usage", "%", "mdi:calendar-clock", None),
    (
        "codex_secondary_reset_time",
        "Secondary Reset Time",
        None,
        "mdi:calendar-refresh",
        "timestamp",
    ),
    ("codex_secondary_window_minutes", "Secondary Window", "min", "mdi:calendar-range", None),
    ("credits_enabled", "Credits Enabled", None, "mdi:credit-card-check", None),
    ("credits_unlimited", "Unlimited Credits", None, "mdi:infinity", None),
    ("credits_balance", "Credits Balance", "credits", "mdi:credit-card-outline", None),
    ("reset_credits_available", "Reset Credits Available", "resets", "mdi:restore", None),
    (
        "reset_credits_expiry",
        "Next Reset Credit Expiry",
        None,
        "mdi:calendar-expire",
        "timestamp",
    ),
    ("rate_limit_reached_type", "Rate Limit Reached Type", None, "mdi:alert-circle-outline", None),
    ("rate_limited_until", "API Rate Limited Until", None, "mdi:clock-alert", "timestamp"),
    ("api_error", "API Error", "errors", "mdi:alert-circle", None),
]
