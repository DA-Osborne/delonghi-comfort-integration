"""The De'Longhi Comfort integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_LANGUAGE,
    DEFAULT_LANGUAGE,
)
from .api import DeLonghiAPI, DeLonghiAPIError, DeLonghiAuthenticationError
from .coordinator import DeLonghiCoordinator


@dataclass(slots=True)
class DeLonghiRuntimeData:
    """Runtime objects shared by the integration platforms."""

    api: DeLonghiAPI
    coordinators: list[DeLonghiCoordinator]
    heater_coordinators: list[DeLonghiCoordinator]


DeLonghiConfigEntry: TypeAlias = ConfigEntry[DeLonghiRuntimeData]


PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: DeLonghiConfigEntry) -> bool:
    """Set up De'Longhi Comfort from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    language = entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)

    session = async_get_clientsession(hass)
    api = DeLonghiAPI(username, password, session, language)

    # Test authentication
    if not await api.authenticate():
        if api.auth_failure == "invalid_auth":
            raise ConfigEntryAuthFailed("De'Longhi rejected the account credentials")
        raise ConfigEntryNotReady("Unable to authenticate with De'Longhi")

    # Get devices
    try:
        devices = await api.get_devices()
    except DeLonghiAuthenticationError as err:
        raise ConfigEntryAuthFailed from err
    except (aiohttp.ClientError, DeLonghiAPIError, ValueError, TimeoutError) as err:
        raise ConfigEntryNotReady from err
    if not devices:
        raise ConfigEntryNotReady("No De'Longhi devices returned")

    # Create coordinators for each device
    coordinators = []
    heater_coordinators = []
    for device in devices:
        device_info = device["device"]
        dsn = device_info["dsn"]

        coordinator = DeLonghiCoordinator(hass, api, dsn, device_info, entry)
        await coordinator.async_config_entry_first_refresh()
        if device_info["oem_model"] == "DL-heater":
            heater_coordinators.append(coordinator)
        else:
            coordinators.append(coordinator)

    entry.runtime_data = DeLonghiRuntimeData(
        api=api,
        coordinators=coordinators,
        heater_coordinators=heater_coordinators,
    )

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the De'Longhi Comfort integration."""
    # This integration is only configurable via config flow
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)
