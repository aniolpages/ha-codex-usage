"""Parse OpenAI Codex usage responses."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any


def parse_usage_response(
    body: dict[str, Any], headers: dict[str, str], now: datetime | None = None
) -> dict[str, Any]:
    """Parse Codex usage JSON and response headers into flat sensor values."""
    data: dict[str, Any] = {}
    now = now or datetime.now(UTC)

    data.update(_without_none(_parse_body(body)))
    data.update(_without_none(_parse_headers(headers)))

    retry_at = retry_after_to_datetime(headers.get("retry-after"), now)
    if retry_at is not None:
        data["rate_limited_until"] = retry_at.isoformat()

    return _without_none(data)


def parse_reset_credits_response(body: dict[str, Any]) -> dict[str, Any]:
    """Parse detailed reset-credit data without exposing credit IDs."""
    data: dict[str, Any] = {}
    credits = body.get("credits")
    if not isinstance(credits, list):
        credits = []

    clean_credits = [_clean_reset_credit(item) for item in credits if isinstance(item, dict)]
    clean_credits = [item for item in clean_credits if item]

    data["reset_credits_available"] = _int(body.get("available_count"))
    if data["reset_credits_available"] is None and clean_credits:
        data["reset_credits_available"] = len(clean_credits)
    if clean_credits:
        data["reset_credits"] = clean_credits
        expiries = [item["expires_at"] for item in clean_credits if "expires_at" in item]
        if expiries:
            data["reset_credits_expiry"] = min(expiries)
    return _without_none(data)


def retry_after_to_datetime(value: str | None, now: datetime) -> datetime | None:
    """Return a Retry-After timestamp for delta-seconds or HTTP-date values."""
    if not value:
        return None
    value = value.strip()
    try:
        seconds = int(value)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return now + timedelta(seconds=max(0, seconds))


def _parse_body(body: dict[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {}

    plan_type = body.get("plan_type")
    if isinstance(plan_type, str):
        data["plan_type"] = plan_type

    _copy_rate_limit(data, body.get("rate_limit"), "codex")

    credits = body.get("credits")
    if isinstance(credits, dict):
        data["credits_enabled"] = credits.get("has_credits")
        data["credits_unlimited"] = credits.get("unlimited")
        data["credits_balance"] = _number_or_string(credits.get("balance"))

    reached = body.get("rate_limit_reached_type")
    if isinstance(reached, dict):
        data["rate_limit_reached_type"] = reached.get("type")

    resets = body.get("rate_limit_reset_credits")
    if isinstance(resets, dict):
        data["reset_credits_available"] = resets.get("available_count")
        data["reset_credits_expiry"] = _iso_from_timestampish(
            resets.get("expires_at") or resets.get("expiresAt")
        )

    additional = body.get("additional_rate_limits")
    if isinstance(additional, list):
        for item in additional:
            if not isinstance(item, dict):
                continue
            limit_id = _limit_id(item.get("metered_feature") or item.get("limit_name"))
            _copy_rate_limit(data, item.get("rate_limit"), limit_id)
            name = item.get("limit_name")
            if isinstance(name, str) and name:
                data[f"{limit_id}_limit_name"] = name

    return data


def _clean_reset_credit(credit: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key in ("granted_at", "expires_at", "redeemed_at"):
        value = _iso_from_timestampish(credit.get(key) or credit.get(_camel(key)))
        if value:
            clean[key] = value
    status = _text(credit.get("status") or credit.get("state"))
    if status:
        clean["status"] = status
    return clean


def _copy_rate_limit(data: dict[str, Any], rate_limit: Any, limit_id: str) -> None:
    if not isinstance(rate_limit, dict):
        return

    data[f"{limit_id}_allowed"] = rate_limit.get("allowed")
    data[f"{limit_id}_limit_reached"] = rate_limit.get("limit_reached")
    _copy_window(data, rate_limit.get("primary_window"), f"{limit_id}_primary")
    _copy_window(data, rate_limit.get("secondary_window"), f"{limit_id}_secondary")


def _copy_window(data: dict[str, Any], window: Any, prefix: str) -> None:
    if not isinstance(window, dict):
        return

    data[f"{prefix}_usage_percent"] = window.get("used_percent")
    data[f"{prefix}_window_minutes"] = _seconds_to_minutes(window.get("limit_window_seconds"))
    data[f"{prefix}_reset_after_seconds"] = window.get("reset_after_seconds")
    data[f"{prefix}_reset_time"] = _iso_from_timestampish(window.get("reset_at"))


def _parse_headers(headers: dict[str, str]) -> dict[str, Any]:
    normalized = {key.lower(): value for key, value in headers.items()}
    data: dict[str, Any] = {}

    for limit_id in _limit_ids_from_headers(normalized):
        prefix = f"x-{limit_id.replace('_', '-')}"
        out_prefix = _limit_id(limit_id)
        data[f"{out_prefix}_limit_name"] = _text(normalized.get(f"{prefix}-limit-name"))
        _copy_header_window(data, normalized, prefix, f"{out_prefix}_primary", "primary")
        _copy_header_window(data, normalized, prefix, f"{out_prefix}_secondary", "secondary")

    data["credits_enabled"] = _bool(normalized.get("x-codex-credits-has-credits"))
    data["credits_unlimited"] = _bool(normalized.get("x-codex-credits-unlimited"))
    data["credits_balance"] = _number_or_string(normalized.get("x-codex-credits-balance"))
    data["promo_message"] = _text(normalized.get("x-codex-promo-message"))
    data["rate_limit_reached_type"] = _text(normalized.get("x-codex-rate-limit-reached-type"))
    return data


def _copy_header_window(
    data: dict[str, Any],
    headers: dict[str, str],
    header_prefix: str,
    out_prefix: str,
    window_name: str,
) -> None:
    usage = _float(headers.get(f"{header_prefix}-{window_name}-used-percent"))
    if usage is None:
        return
    data[f"{out_prefix}_usage_percent"] = usage
    data[f"{out_prefix}_window_minutes"] = _int(
        headers.get(f"{header_prefix}-{window_name}-window-minutes")
    )
    data[f"{out_prefix}_reset_time"] = _iso_from_timestampish(
        headers.get(f"{header_prefix}-{window_name}-reset-at")
    )


def _limit_ids_from_headers(headers: dict[str, str]) -> set[str]:
    ids = {"codex"}
    suffix = "-primary-used-percent"
    for name in headers:
        if name.startswith("x-codex-") and name.endswith(suffix):
            ids.add(name.removeprefix("x-").removesuffix(suffix).replace("-", "_"))
    return ids


def _limit_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "codex"
    return "".join(char if char.isalnum() else "_" for char in value.strip().lower()).strip("_")


def _iso_from_timestampish(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str) and not value.isdigit():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).isoformat()
        except ValueError:
            return None
    try:
        return datetime.fromtimestamp(int(value), UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _seconds_to_minutes(value: Any) -> int | None:
    seconds = _int(value)
    return round(seconds / 60) if seconds is not None else None


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in {"true", "1"}:
            return True
        if value.lower() in {"false", "0"}:
            return False
    return None


def _float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and parsed not in {float("inf"), float("-inf")} else None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number_or_string(value: Any) -> int | float | str | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        return value
    if not isinstance(value, str):
        return None
    parsed_float = _float(value)
    if parsed_float is None:
        return value
    parsed_int = _int(value)
    return parsed_int if parsed_int is not None and parsed_int == parsed_float else parsed_float


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


def _without_none(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}
