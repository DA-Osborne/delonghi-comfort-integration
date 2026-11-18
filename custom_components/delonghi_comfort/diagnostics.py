"""Diagnostics for the De'Longhi Comfort integration.

The download lists every property the cloud reports for each device, with its type,
direction and label, and which entities were created. That is what is needed to add
support for a model this integration has not seen. Account details and anything that
identifies the device or the home are removed.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import DeLonghiConfigEntry
from .capabilities import is_complete_snapshot, supports_real_feel, supports_swing
from .const import CONF_PASSWORD, CONF_USERNAME

TO_REDACT_CONFIG = {CONF_USERNAME, CONF_PASSWORD}

# Fields of the cloud's device record that identify the unit, its network or the home.
TO_REDACT_DEVICE = {
    "dsn",
    "mac",
    "lan_ip",
    "lat",
    "lng",
    "key",
    "unique_hardware_id",
    "template_id",
    "facility_uuid",
    "oem",
    "locality",
    "product_name",
}

# Property values that identify the unit, or that the app fills in from the owner's
# location (outdoor weather).
REDACT_PROPERTY_NAMES = {"cst_mac_address", "serial_number"}
REDACT_PROPERTY_PREFIXES = ("outdoor_",)

PROPERTY_FIELDS = (
    "base_type",
    "read_only",
    "direction",
    "display_name",
    "value",
    "data_updated_at",
)


def _redact_property(name: str, record: dict[str, Any]) -> dict[str, Any]:
    entry = {field: record.get(field) for field in PROPERTY_FIELDS}
    if name in REDACT_PROPERTY_NAMES or name.startswith(REDACT_PROPERTY_PREFIXES):
        entry["value"] = "**REDACTED**"
    return entry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DeLonghiConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    registry = er.async_get(hass)
    registry_entries = er.async_entries_for_config_entry(registry, entry.entry_id)

    devices = []
    for kind, coordinators in (
        ("air conditioner", runtime.coordinators),
        ("heater", runtime.heater_coordinators),
    ):
        for coordinator in coordinators:
            available = coordinator.available_properties
            entities = [
                {
                    "platform": item.domain,
                    # The device serial number is part of every unique ID.
                    "unique_id": (item.unique_id or "").replace(coordinator.dsn, "<dsn>"),
                    "translation_key": item.translation_key,
                    "entity_category": item.entity_category,
                    "disabled_by": item.disabled_by,
                }
                for item in registry_entries
                if coordinator.dsn in (item.unique_id or "")
            ]
            devices.append(
                {
                    "kind": kind,
                    "device_record": async_redact_data(
                        coordinator.device_record, TO_REDACT_DEVICE
                    ),
                    "last_update_success": coordinator.last_update_success,
                    "capabilities": {
                        "complete_property_list": is_complete_snapshot(available),
                        "myEcoReal Feel": supports_real_feel(available),
                        "swing": supports_swing(available),
                    },
                    "properties": {
                        name: _redact_property(name, record)
                        for name, record in sorted(coordinator.property_records.items())
                    },
                    "entities": sorted(
                        entities, key=lambda e: (e["platform"], e["unique_id"])
                    ),
                }
            )

    return {
        "config_entry": async_redact_data(
            {"data": dict(entry.data), "options": dict(entry.options)},
            TO_REDACT_CONFIG,
        ),
        "devices": devices,
    }
