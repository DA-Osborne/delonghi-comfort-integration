"""Binary sensor platform for De'Longhi Comfort integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeLonghiConfigEntry
from .capabilities import async_supported_descriptions
from .entity import DeLonghiEntity


@dataclass(frozen=True, kw_only=True)
class DeLonghiBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor description with the device property it reads."""

    required_properties: tuple[str, ...]
    # Raw values that mean "on". Some properties are inverted (0 means the remote
    # sensor is in use), so this is not always 1.
    on_values: tuple[int, ...] = (1,)


BINARY_SENSOR_DESCRIPTIONS = (
    # The CST remote control, a Bluetooth remote with a built-in temperature and
    # humidity sensor.
    DeLonghiBinarySensorDescription(
        key="pairing_status",
        required_properties=("pairing_status",),
        translation_key="remote_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeLonghiBinarySensorDescription(
        # 0 means the remote's sensor is used, 1 means the unit's own sensor is.
        key="get_sensors_used",
        required_properties=("get_sensors_used",),
        translation_key="remote_sensor_in_use",
        on_values=(0,),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeLonghiBinarySensorDescription(
        # bt_status is 4 with the remote docked in the unit, 1 when it is out of
        # the dock and 2 when it has no batteries.
        key="bt_status",
        required_properties=("bt_status",),
        translation_key="remote_docked",
        on_values=(4,),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeLonghiBinarySensorDescription(
        key="get_timer_enabled",
        required_properties=("get_timer_enabled",),
        translation_key="timer_active",
    ),
    DeLonghiBinarySensorDescription(
        key="get_weeklysched_enable",
        required_properties=("get_weeklysched_enable",),
        translation_key="weekly_schedule",
    ),
    # Alarms shown on the unit's display (HL, PF, LH, LT). A value of 1 is
    # assumed to mean active; none has been triggered on the reference unit.
    DeLonghiBinarySensorDescription(
        key="hl_alarm",
        required_properties=("hl_alarm",),
        translation_key="tray_full",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    DeLonghiBinarySensorDescription(
        key="pf_alarm",
        required_properties=("pf_alarm",),
        translation_key="probe_failure",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    DeLonghiBinarySensorDescription(
        # Only raised in myEcoReal Feel mode, which stops until another mode is
        # selected.
        key="lh_alarm",
        required_properties=("lh_alarm",),
        translation_key="low_humidity",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    DeLonghiBinarySensorDescription(
        # Frost prevention. The unit defrosts and restarts by itself, so this is
        # information, not a fault.
        key="lt_alarm",
        required_properties=("lt_alarm",),
        translation_key="frost_protection",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeLonghiBinarySensorDescription(
        key="ht_alarm",
        required_properties=("ht_alarm",),
        translation_key="high_temperature",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeLonghiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi binary sensors."""
    entities = [
        DeLonghiBinarySensor(coordinator, description)
        for coordinator in config_entry.runtime_data.coordinators
        for description in async_supported_descriptions(
            hass,
            "binary_sensor",
            coordinator.dsn,
            coordinator.available_properties,
            BINARY_SENSOR_DESCRIPTIONS,
        )
    ]
    async_add_entities(entities)


def _as_int(value: Any) -> int | None:
    """Return a property value as an integer, or None if it is not a number."""
    if isinstance(value, bool):
        return int(value)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class DeLonghiBinarySensor(DeLonghiEntity, BinarySensorEntity):
    """A two-state value reported by the device."""

    entity_description: DeLonghiBinarySensorDescription

    def __init__(
        self, coordinator, description: DeLonghiBinarySensorDescription
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.dsn}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return whether the property holds one of the "on" values."""
        value = _as_int(self.coordinator.data.get(self.entity_description.key))
        if value is None:
            return None
        return value in self.entity_description.on_values

    @property
    def available(self) -> bool:
        """Return if the device reports the property."""
        return (
            super().available and self.entity_description.key in self.coordinator.data
        )
