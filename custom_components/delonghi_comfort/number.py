"""Number platform for De'Longhi Comfort integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeLonghiConfigEntry
from .capabilities import async_supported_descriptions
from .entity import DeLonghiEntity

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class DeLonghiNumberDescription(NumberEntityDescription):
    """Number description with the device properties it needs."""

    required_properties: tuple[str, ...]


NUMBER_DESCRIPTIONS = (
    DeLonghiNumberDescription(
        key="temp_setpoint",
        required_properties=("temp_setpoint", "set_temp_setpoint"),
        translation_key="temperature_setpoint",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=16,
        native_max_value=32,
        native_step=1,
        mode=NumberMode.BOX,
    ),
    DeLonghiNumberDescription(
        key="humidity_setpoint",
        required_properties=("humidity_setpoint",),
        translation_key="humidity_setpoint",
        device_class=NumberDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=30,
        native_max_value=80,
        native_step=5,
        mode=NumberMode.BOX,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeLonghiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi number entities."""
    coordinators = config_entry.runtime_data.coordinators

    entities = []

    for coordinator in coordinators:
        entities.extend(
            [
                DeLonghiNumber(
                    coordinator=coordinator,
                    description=description,
                )
                for description in async_supported_descriptions(
                    hass,
                    "number",
                    coordinator.dsn,
                    coordinator.available_properties,
                    NUMBER_DESCRIPTIONS,
                )
            ]
        )

    async_add_entities(entities)


class DeLonghiNumber(DeLonghiEntity, NumberEntity):
    """Representation of a De'Longhi number entity."""

    entity_description: DeLonghiNumberDescription

    def __init__(
        self,
        coordinator,
        description: DeLonghiNumberDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.dsn}_{description.key}"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self.coordinator.data.get(self.entity_description.key)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        if self.entity_description.key == "temp_setpoint":
            success = await self.coordinator.api.set_temperature_setpoint(
                self.coordinator.dsn, value
            )
        elif self.entity_description.key == "humidity_setpoint":
            success = await self.coordinator.api.set_humidity_setpoint(
                self.coordinator.dsn, value
            )
        else:
            success = False

        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set %s to %s", self.entity_description.key, value)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available and self.entity_description.key in self.coordinator.data
        )
