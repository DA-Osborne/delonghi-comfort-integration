"""Switch platform for De'Longhi Comfort integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription, SwitchDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeLonghiConfigEntry
from .capabilities import async_supported_descriptions
from .entity import DeLonghiEntity

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class DeLonghiSwitchDescription(SwitchEntityDescription):
    """Switch description with the device properties it needs."""

    required_properties: tuple[str, ...]


SWITCH_DESCRIPTIONS = (
    DeLonghiSwitchDescription(
        key="get_device_status",
        required_properties=("get_device_status", "set_device_status"),
        translation_key="device_power",
        entity_registry_enabled_default=False,
    ),
    DeLonghiSwitchDescription(
        key="get_silent_function",
        required_properties=("get_silent_function", "set_silent_function"),
        translation_key="silent_mode",
    ),
)

HEATER_DESCRIPTIONS = (
    SwitchEntityDescription(
        key="eco",
        icon="mdi:sprout",
        name="Eco",
    ),
    SwitchEntityDescription(
        key="lock",
        icon="mdi:lock",
        name="Child lock",
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeLonghiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi switch entities."""
    coordinators = config_entry.runtime_data.coordinators

    entities = []

    for coordinator in coordinators:
        entities.extend(
            [
                DeLonghiSwitch(
                    coordinator=coordinator,
                    description=description,
                )
                for description in async_supported_descriptions(
                    hass,
                    "switch",
                    coordinator.dsn,
                    coordinator.available_properties,
                    SWITCH_DESCRIPTIONS,
                )
            ]
        )

    for coordinator in config_entry.runtime_data.heater_coordinators:
        entities.extend(
            [
                HeaterSwitch(
                    coordinator=coordinator,
                    description=description,
                )
                for description in HEATER_DESCRIPTIONS
            ]
        )

    async_add_entities(entities)


class DeLonghiSwitch(DeLonghiEntity, SwitchEntity):
    """Representation of a De'Longhi switch entity."""

    entity_description: DeLonghiSwitchDescription

    def __init__(
        self,
        coordinator,
        description: DeLonghiSwitchDescription,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.dsn}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return True if the switch is on."""
        value = self.coordinator.data.get(self.entity_description.key)

        if value is None:
            return None

        # Device status: 1 = ON, 2 = OFF
        return value == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if self.entity_description.key == "get_device_status":
            success = await self.coordinator.api.set_device_status(self.coordinator.dsn, 1)
            optimistic_value = 1
        elif self.entity_description.key == "get_silent_function":
            success = await self.coordinator.api.set_silent_mode(self.coordinator.dsn, 1)
            optimistic_value = 1

        if success:
            self.coordinator.set_optimistic_value(
                self.entity_description.key, optimistic_value
            )
        else:
            _LOGGER.error("Failed to change %s to 1", self.entity_description.key)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        if self.entity_description.key == "get_device_status":
            success = await self.coordinator.api.set_device_status(self.coordinator.dsn, 2)
            optimistic_value = 2
        elif self.entity_description.key == "get_silent_function":
            success = await self.coordinator.api.set_silent_mode(self.coordinator.dsn, 0)
            optimistic_value = 0

        if success:
            self.coordinator.set_optimistic_value(
                self.entity_description.key, optimistic_value
            )
        else:
            _LOGGER.error("Failed to turn off %s", self.entity_description.key)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if self.entity_description.key == "get_silent_function":
            return (
                super().available
                and self.entity_description.key in self.coordinator.data
                and self.coordinator.data.get("get_device_status") == 1
                and not self.coordinator.is_property_pending("get_device_status")
            )
        return (
            super().available and self.entity_description.key in self.coordinator.data
        )

class HeaterSwitch(DeLonghiEntity, SwitchEntity):
    """Representation of a De'Longhi heater switch entity."""

    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(
        self,
        coordinator,
        description: SwitchEntityDescription,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_unique_id = f"delonghi_heater_{coordinator.dsn}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return True if the switch is on."""
        value = self.coordinator.data.get(f"get_{self.entity_description.key}")
        if value is None:
            return None
        # Device status: 1 = ON, 0 = OFF
        return value == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        success = await self.coordinator.api.set_device_property(self.coordinator.dsn, f"set_{self.entity_description.key}", 1)
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn on: %s", self.entity_description.key)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        success = await self.coordinator.api.set_device_property(self.coordinator.dsn, f"set_{self.entity_description.key}", 0)
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn off: %s", self.entity_description.key)
