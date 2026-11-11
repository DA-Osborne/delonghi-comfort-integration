"""Sensor platform for De'Longhi Comfort integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DeLonghiConfigEntry
from .capabilities import async_supported_descriptions
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class DeLonghiSensorDescription(SensorEntityDescription):
    """Sensor description with the device properties it needs."""

    required_properties: tuple[str, ...]
    data_key: str | None = None


SENSOR_DESCRIPTIONS = (
    DeLonghiSensorDescription(
        key="room_temp",
        required_properties=("room_temp",),
        translation_key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    DeLonghiSensorDescription(
        key="temp_setpoint",
        required_properties=("temp_setpoint",),
        translation_key="target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    DeLonghiSensorDescription(
        key="room_hum",
        required_properties=("room_hum",),
        translation_key="room_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    DeLonghiSensorDescription(
        key="get_device_status",
        required_properties=("get_device_status",),
        translation_key="device_status",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeLonghiSensorDescription(
        key="get_device_mode",
        required_properties=("get_device_mode",),
        translation_key="device_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeLonghiSensorDescription(
        key="get_int_fan_speed",
        required_properties=("get_int_fan_speed",),
        translation_key="fan_speed",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeLonghiSensorDescription(
        key="get_silent_function",
        required_properties=("get_silent_function",),
        translation_key="silent_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeLonghiSensorDescription(
        key="filter_hours",
        required_properties=("filter_hours",),
        translation_key="filter_hours",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeLonghiSensorDescription(
        key="power_consumption",
        required_properties=("power_consumption",),
        translation_key="power_consumption",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeLonghiSensorDescription(
        key="wifi_signal",
        required_properties=("cst_rssi",),
        data_key="cst_rssi",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        translation_key="wifi_signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeLonghiSensorDescription(
        key="error_code",
        required_properties=("error_code",),
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    DeLonghiSensorDescription(
        key="operating_hours",
        required_properties=("operating_hours",),
        translation_key="operating_hours",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeLonghiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi sensor entities."""
    coordinators = config_entry.runtime_data.coordinators

    entities = []

    for coordinator in coordinators:
        entities.extend(
            [
                DeLonghiSensor(
                    coordinator=coordinator,
                    description=description,
                )
                for description in async_supported_descriptions(
                    hass,
                    "sensor",
                    coordinator.dsn,
                    coordinator.available_properties,
                    SENSOR_DESCRIPTIONS,
                )
            ]
        )

    entities.extend(
        HeaterTemperature(coordinator=coordinator)
        for coordinator in config_entry.runtime_data.heater_coordinators
    )

    async_add_entities(entities)


class DeLonghiSensor(CoordinatorEntity, SensorEntity):
    """Representation of a De'Longhi sensor."""

    _attr_has_entity_name = True
    entity_description: DeLonghiSensorDescription

    def __init__(
        self,
        coordinator,
        description: DeLonghiSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.dsn}_{description.key}"

        # Device information
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.dsn)},
            "name": coordinator.device_name,
            "manufacturer": "De'Longhi",
            "model": coordinator.device_model,
            "sw_version": coordinator.device_version,
        }

    @property
    def native_value(self) -> Any:
        """Return the value of the sensor."""
        value = self.coordinator.data.get(self._data_key)

        if value is None:
            return None

        # Apply value transformation for specific sensors
        if self.entity_description.key == "get_device_status":
            return "on" if value == 1 else "off" if value == 2 else "unknown"
        if self.entity_description.key == "get_device_mode":
            return {1: "cooling", 2: "dehumidification", 3: "fan_only"}.get(
                value, "unknown"
            )
        if self.entity_description.key == "get_silent_function":
            return "on" if value == 1 else "off" if value == 0 else "unknown"

        return value

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self._data_key in self.coordinator.data

    @property
    def _data_key(self) -> str:
        """Return the device property this sensor reads."""
        return self.entity_description.data_key or self.entity_description.key


class HeaterTemperature(CoordinatorEntity, SensorEntity):
    """Representation of a De'Longhi heater temperature sensor."""
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_name = "Temperature"

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"delonghi_heater_{coordinator.dsn}_temperature"
        self._attr_device_info = coordinator.get_device_info()

    @property
    def native_value(self) -> Any:
        """Return the value of the sensor."""
        return self.coordinator.data.get("room_temp")
