"""Sensor platform for OpenAI Codex Usage."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CodexUsageConfigEntry, CodexUsageCoordinator
from .const import CONF_ACCOUNT_ID, DOMAIN, SENSOR_DEFINITIONS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CodexUsageConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Codex Usage sensors."""
    coordinator = entry.runtime_data
    definitions = [*SENSOR_DEFINITIONS, *_dynamic_sensor_definitions(coordinator.data or {})]
    async_add_entities(
        CodexUsageSensor(coordinator, entry, key, name, unit, icon, device_class)
        for key, name, unit, icon, device_class in definitions
    )


class CodexUsageSensor(CoordinatorEntity[CodexUsageCoordinator], SensorEntity):
    """A sensor for a Codex usage metric."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CodexUsageCoordinator,
        entry: CodexUsageConfigEntry,
        key: str,
        name: str,
        unit: str | None,
        icon: str,
        device_class: str | None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._is_timestamp = device_class == "timestamp"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        if self._is_timestamp:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif unit is not None:
            self._attr_state_class = SensorStateClass.MEASUREMENT

        account_id = entry.data.get(CONF_ACCOUNT_ID)
        name_suffix = f" ({account_id})" if account_id else ""
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"OpenAI Codex Usage{name_suffix}",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        """Return True if the sensor value is present."""
        if self._key == "api_error":
            return True
        if not super().available or self.coordinator.data is None:
            return False
        return self._key in self.coordinator.data

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self._key == "api_error" and self.coordinator.data is None:
            return 0 if self.coordinator.last_update_success else 1
        if self.coordinator.data is None:
            return None

        value = self.coordinator.data.get(self._key)
        if value is not None and self._is_timestamp:
            try:
                return datetime.fromisoformat(str(value))
            except ValueError:
                _LOGGER.warning("Invalid timestamp value for %s: %s", self._key, value)
                return None
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return reset-credit details as attributes."""
        if self._key != "reset_credits_available" or self.coordinator.data is None:
            return None
        credits = self.coordinator.data.get("reset_credits")
        if not isinstance(credits, list):
            return None
        return {"credits": credits}


def _dynamic_sensor_definitions(
    data: dict[str, Any],
) -> list[tuple[str, str, str | None, str, str | None]]:
    static_keys = {item[0] for item in SENSOR_DEFINITIONS}
    definitions: list[tuple[str, str, str | None, str, str | None]] = []
    for key in sorted(data):
        if key in static_keys:
            continue
        if key.endswith("_usage_percent"):
            definitions.append((key, _label(key), "%", "mdi:gauge", None))
        elif key.endswith("_reset_time"):
            definitions.append((key, _label(key), None, "mdi:timer-refresh", "timestamp"))
        elif key.endswith("_window_minutes"):
            definitions.append((key, _label(key), "min", "mdi:timer-outline", None))
    return definitions


def _label(key: str) -> str:
    return key.replace("_", " ").title()
