"""Work out which entities a device model supports.

De'Longhi models report different property sets. An entity is created only when
every property record it needs is present in the device's property list. Presence
is what counts, not the value: some supported properties have an empty value.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
import logging
from typing import TYPE_CHECKING, Any, Protocol

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# A property list without these is treated as incomplete (for example a partial
# cloud response), so nothing is removed from the entity registry because of it.
CORE_PROPERTIES = ("get_device_status", "get_device_mode")


class SupportsRequirements(Protocol):
    """An entity description that declares the properties it needs."""

    key: str
    required_properties: tuple[str, ...]


def supports(available: Collection[str], required: Iterable[str]) -> bool:
    """Return whether every required property is reported by the device."""
    return all(name in available for name in required)


def is_complete_snapshot(available: Collection[str]) -> bool:
    """Return whether the property list looks like a full device response."""
    return supports(available, CORE_PROPERTIES)


def split_supported(
    available: Collection[str], descriptions: Iterable[Any]
) -> tuple[list[Any], list[Any]]:
    """Split descriptions into supported and unsupported for a device."""
    supported: list[Any] = []
    unsupported: list[Any] = []
    for description in descriptions:
        if supports(available, description.required_properties):
            supported.append(description)
        else:
            unsupported.append(description)
    return supported, unsupported


def async_supported_descriptions(
    hass: HomeAssistant,
    platform: str,
    dsn: str,
    available: Collection[str],
    descriptions: Iterable[SupportsRequirements],
) -> list[Any]:
    """Return the descriptions a device supports.

    Registry entries for unsupported descriptions are removed when the property
    list is complete, because those entities can never report data.
    """
    supported, unsupported = split_supported(available, descriptions)
    if not unsupported:
        return supported

    if not is_complete_snapshot(available):
        _LOGGER.debug(
            "Property list for %s looks incomplete; not removing unsupported %s entities",
            dsn,
            platform,
        )
        return supported

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    for description in unsupported:
        entity_id = registry.async_get_entity_id(
            platform, DOMAIN, f"{dsn}_{description.key}"
        )
        if entity_id is not None:
            _LOGGER.info(
                "Removing %s: this device does not report %s",
                entity_id,
                ", ".join(
                    name
                    for name in description.required_properties
                    if name not in available
                ),
            )
            registry.async_remove(entity_id)
    return supported
