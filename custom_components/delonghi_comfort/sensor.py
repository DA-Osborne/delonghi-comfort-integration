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

from . import DeLonghiConfigEntry
from .capabilities import async_supported_descriptions
from .entity import DeLonghiEntity

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class DeLonghiSensorDescription(SensorEntityDescription):
    """Sensor description with the device properties it needs."""

    required_properties: tuple[str, ...]
    # Maps raw device values to translated state names for enum sensors.
    value_map: dict[Any, str] | None = None


STATUS_STATES = {1: "on", 2: "off"}
MODE_STATES = {1: "cooling", 2: "dehumidification", 3: "fan_only"}
FAN_SPEED_STATES = {1: "low", 2: "medium", 3: "high", 4: "auto"}
SILENT_STATES = {0: "off", 1: "on"}


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
        entity_registry_enabled_default=False,
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
        device_class=SensorDeviceClass.ENUM,
        options=list(STATUS_STATES.values()),
        value_map=STATUS_STATES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    DeLonghiSensorDescription(
        key="get_device_mode",
        required_properties=("get_device_mode",),
        translation_key="device_mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(MODE_STATES.values()),
        value_map=MODE_STATES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    DeLonghiSensorDescription(
        key="get_int_fan_speed",
        required_properties=("get_int_fan_speed",),
        translation_key="fan_speed",
        device_class=SensorDeviceClass.ENUM,
        options=list(FAN_SPEED_STATES.values()),
        value_map=FAN_SPEED_STATES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    DeLonghiSensorDescription(
        key="get_silent_function",
        required_properties=("get_silent_function",),
        translation_key="silent_mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(SILENT_STATES.values()),
        value_map=SILENT_STATES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
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
        required_properties=("wifi_signal",),
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        translation_key="wifi_signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    DeLonghiSensorDescription(
        key="cst_rssi",
        required_properties=("cst_rssi",),
        translation_key="remote_signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeLonghiSensorDescription(
        key="second_room_temp",
        required_properties=("second_room_temp",),
        translation_key="pipe_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
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


class DeLonghiSensor(DeLonghiEntity, SensorEntity):
    """Representation of a De'Longhi sensor."""

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

    @property
    def native_value(self) -> Any:
        """Return the value of the sensor."""
        value = self.coordinator.data.get(self.entity_description.key)

        if value is None:
            return None

        if self.entity_description.value_map is not None:
            # A value outside the known map is reported as unknown.
            return self.entity_description.value_map.get(value)

        return value

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available and self.entity_description.key in self.coordinator.data
        )


class HeaterTemperature(DeLonghiEntity, SensorEntity):
    """Representation of a De'Longhi heater temperature sensor."""
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_name = "Temperature"

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"delonghi_heater_{coordinator.dsn}_temperature"

    @property
    def native_value(self) -> Any:
        """Return the value of the sensor."""
        return self.coordinator.data.get("room_temp")
