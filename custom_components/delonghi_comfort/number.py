"""Number platform for De'Longhi Comfort integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeLonghiConfigEntry
from .capabilities import async_supported_descriptions
from .entity import DeLonghiEntity

_LOGGER = logging.getLogger(__name__)

# The unit applies a Real Feel adjustment from 14 to 18 (default 16) and ignores
# anything else, so that is the range offered. A higher number is warmer.
REAL_FEEL_MIN = 14
REAL_FEEL_MAX = 18
# The remote's own timer goes up to 24 hours; the same limit is used here.
OFF_TIMER_MAX_MINUTES = 1440


def _as_number(value: Any) -> float | None:
    """Return a property value as a number, or None if it is empty or not numeric."""
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _real_feel_value(data: dict[str, Any]) -> float | None:
    return _as_number(data.get("get_real_feel_offset"))


def _off_timer_value(data: dict[str, Any]) -> float | None:
    """Minutes the timer was set to, or 0 when no timer is running.

    The unit keeps the last duration after a timer ends, so the duration alone
    cannot say whether one is active.
    """
    if _as_number(data.get("get_timer_enabled")) != 1:
        return 0
    return _as_number(data.get("onofftimer_minutes")) or 0


async def _set_real_feel(coordinator, value: float) -> bool:
    adjustment = int(value)
    # The cloud rejects a JSON true, so numbers are sent as integers.
    if not await coordinator.api.set_device_property(
        coordinator.dsn, "set_real_feel_offset", adjustment
    ):
        return False
    coordinator.set_optimistic_value("get_real_feel_offset", adjustment)
    return True


async def _set_off_timer(coordinator, value: float) -> bool:
    """Start the cloud off timer for the given minutes, or cancel it with 0."""
    minutes = int(value)
    api, dsn = coordinator.api, coordinator.dsn
    if minutes > 0:
        # The app writes the duration, then starts the timer.
        if not await api.set_device_property(dsn, "onofftimer_minutes", minutes):
            return False
        if not await api.set_device_property(dsn, "set_timer_enabled", 1):
            return False
        coordinator.set_optimistic_value("onofftimer_minutes", minutes)
        coordinator.set_optimistic_value("get_timer_enabled", 1)
        return True

    # Cancelling writes zero to both, as the app does.
    if not await api.set_device_property(dsn, "set_timer_enabled", 0):
        return False
    if not await api.set_device_property(dsn, "onofftimer_minutes", 0):
        return False
    coordinator.set_optimistic_value("get_timer_enabled", 0)
    return True


@dataclass(frozen=True, kw_only=True)
class DeLonghiNumberDescription(NumberEntityDescription):
    """Number description with the device properties it needs."""

    required_properties: tuple[str, ...]
    # How to turn the device data into the displayed value and how to write a new
    # one. Descriptions that leave these empty read the property named by `key`
    # and use the original setpoint writers.
    value_fn: Callable[[dict[str, Any]], float | None] | None = None
    set_fn: Callable[[Any, float], Awaitable[bool]] | None = None


NUMBER_DESCRIPTIONS = (
    DeLonghiNumberDescription(
        key="temp_setpoint",
        required_properties=("temp_setpoint", "set_temp_setpoint"),
        translation_key="temperature_setpoint",
        entity_registry_enabled_default=False,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=18,
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
    DeLonghiNumberDescription(
        key="get_real_feel_offset",
        required_properties=("get_real_feel_offset", "set_real_feel_offset"),
        translation_key="real_feel_adjustment",
        entity_category=EntityCategory.CONFIG,
        native_min_value=REAL_FEEL_MIN,
        native_max_value=REAL_FEEL_MAX,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=_real_feel_value,
        set_fn=_set_real_feel,
    ),
    DeLonghiNumberDescription(
        key="off_timer",
        required_properties=(
            "onofftimer_minutes",
            "set_timer_enabled",
            "get_timer_enabled",
        ),
        translation_key="off_timer",
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        native_min_value=0,
        native_max_value=OFF_TIMER_MAX_MINUTES,
        native_step=1,
        mode=NumberMode.BOX,
        value_fn=_off_timer_value,
        set_fn=_set_off_timer,
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
        description = self.entity_description
        if description.value_fn is not None:
            return description.value_fn(self.coordinator.data)
        return self.coordinator.data.get(description.key)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        description = self.entity_description
        if description.set_fn is not None:
            success = await description.set_fn(self.coordinator, value)
        elif description.key == "temp_setpoint":
            success = await self.coordinator.api.set_temperature_setpoint(
                self.coordinator.dsn, value
            )
            if success:
                await self.coordinator.async_request_refresh()
        elif description.key == "humidity_setpoint":
            success = await self.coordinator.api.set_humidity_setpoint(
                self.coordinator.dsn, value
            )
            if success:
                await self.coordinator.async_request_refresh()
        else:
            success = False

        if not success:
            _LOGGER.error("Failed to set %s to %s", description.key, value)

    @property
    def available(self) -> bool:
        """Return if the device reports every property this number needs."""
        return super().available and all(
            name in self.coordinator.data
            for name in self.entity_description.required_properties
        )
