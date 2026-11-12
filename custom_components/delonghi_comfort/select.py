"""Select platform for De'Longhi Comfort integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeLonghiConfigEntry
from .capabilities import REAL_FEEL_MODE, async_supported_descriptions, supports_real_feel
from .entity import DeLonghiEntity

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class DeLonghiSelectDescription(SelectEntityDescription):
    """Select description with the device properties it needs."""

    required_properties: tuple[str, ...]


MODE_OPTIONS = {1: "cooling", 2: "dehumidification", 3: "fan_only"}
REAL_FEEL_OPTION = "real_feel"


SELECT_DESCRIPTIONS = (
    DeLonghiSelectDescription(
        key="get_device_mode",
        required_properties=("get_device_mode", "set_device_mode"),
        translation_key="device_mode",
        options=["cooling", "dehumidification", "fan_only"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeLonghiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi select entities."""
    coordinators = config_entry.runtime_data.coordinators

    entities = []

    for coordinator in coordinators:
        entities.extend(
            [
                DeLonghiSelect(
                    coordinator=coordinator,
                    description=description,
                )
                for description in async_supported_descriptions(
                    hass,
                    "select",
                    coordinator.dsn,
                    coordinator.available_properties,
                    SELECT_DESCRIPTIONS,
                )
            ]
        )

    entities.extend(
        HeaterBrightness(coordinator=coordinator)
        for coordinator in config_entry.runtime_data.heater_coordinators
    )

    async_add_entities(entities)


class DeLonghiSelect(DeLonghiEntity, SelectEntity):
    """Representation of a De'Longhi select entity."""

    entity_description: DeLonghiSelectDescription

    def __init__(
        self,
        coordinator,
        description: DeLonghiSelectDescription,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.dsn}_{description.key}"
        self._mode_map = dict(MODE_OPTIONS)
        if supports_real_feel(coordinator.available_properties):
            self._mode_map[REAL_FEEL_MODE] = REAL_FEEL_OPTION
        self._attr_options = list(self._mode_map.values())

    @property
    def current_option(self) -> str | None:
        """Return the current option."""
        value = self.coordinator.data.get(self.entity_description.key)

        if value is None:
            return None

        # Convert device mode value to option. A mode this model does not offer
        # (or one we do not know) shows as unknown.
        return self._mode_map.get(value)

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        # Convert option to device mode value
        option_map = {name: value for value, name in self._mode_map.items()}

        device_mode = option_map.get(option)
        if device_mode is None:
            _LOGGER.error("Unknown option: %s", option)
            return

        success = await self.coordinator.api.set_device_mode(
            self.coordinator.dsn, device_mode
        )

        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set device mode to %s", option)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available and self.entity_description.key in self.coordinator.data
        )

class HeaterBrightness(DeLonghiEntity, SelectEntity):
    """Representation of a heater brightness entity."""
    _attr_icon = "mdi:brightness-6"
    _attr_name = "Display brightness"

    _attr_options = ["Level 1", "Level 2", "Level 3"]

    def __init__(self, coordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"delonghi_heater_{coordinator.dsn}_brightness"

    @property
    def current_option(self) -> str | None:
        """Return the current option."""
        value = self.coordinator.data.get(f"current_brightness")
        return None if value is None else self.options[value - 1]

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        value = self.options.index(option) + 1
        success = await self.coordinator.api.set_device_property(
            self.coordinator.dsn, f"set_brightness", value
        )

        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set device brightness to %s", option)
