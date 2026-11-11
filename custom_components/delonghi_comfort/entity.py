"""Base entity for the De'Longhi Comfort integration."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import DeLonghiCoordinator


class DeLonghiEntity(CoordinatorEntity[DeLonghiCoordinator]):
    """Base class that attaches every entity to its device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DeLonghiCoordinator) -> None:
        """Initialize the entity and its device information."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.get_device_info()
