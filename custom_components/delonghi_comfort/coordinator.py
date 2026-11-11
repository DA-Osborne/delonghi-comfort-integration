"""Data update coordinator for De'Longhi Comfort integration."""

import asyncio
from datetime import timedelta
import logging
from time import monotonic
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DeLonghiAPI, DeLonghiAuthenticationError
from .const import (
    CONF_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)
_COMMAND_CONFIRMATION_INTERVAL = 10
_COMMAND_CONFIRMATION_TIMEOUT = 90


class DeLonghiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage data updates for De'Longhi devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: DeLonghiAPI,
        dsn: str,
        device_info: dict[str, Any],
        config_entry,
    ) -> None:
        """Initialize the coordinator."""
        # Get scan interval from options, fallback to default
        scan_interval = config_entry.options.get(CONF_SCAN_INTERVAL, SCAN_INTERVAL)
        scan_interval = min(max(scan_interval, MIN_SCAN_INTERVAL), MAX_SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=f"delonghi_comfort_{dsn}",
            update_interval=timedelta(seconds=scan_interval),
            always_update=False,
        )
        self.api = api
        self.dsn = dsn
        self.device_name = device_info.get("product_name", f"De'Longhi {dsn}")
        self.device_model = device_info.get("model", "Unknown")
        self.device_version = device_info.get("sw_version")
        self._config_entry = config_entry
        self.available_properties: frozenset[str] = frozenset()
        self._pending_commands: dict[str, tuple[Any, Any, float]] = {}
        self._confirmation_task: asyncio.Task[None] | None = None
        config_entry.async_on_unload(self._cancel_confirmation_task)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the API."""
        try:
            properties = await self.api.get_device_properties(self.dsn)

            # Parse properties into a more usable format
            data = {}
            for prop in properties:
                if "property" in prop:
                    prop_info = prop["property"]
                    data[prop_info["name"]] = prop_info["value"]

            # Records the device reports, regardless of whether they hold a value.
            self.available_properties = frozenset(data)

            now = monotonic()
            confirmation_changed = False
            for key, (expected, _, expires_at) in list(self._pending_commands.items()):
                actual = data.get(key)
                if actual == expected or now >= expires_at:
                    self._pending_commands.pop(key, None)
                    confirmation_changed = True
                else:
                    self._pending_commands[key] = (expected, actual, expires_at)
                    data[key] = expected

            if confirmation_changed and data == self.data:
                self.async_update_listeners()

        except DeLonghiAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        else:
            return data

    def set_optimistic_value(self, key: str, value: Any) -> None:
        """Show a command value while polling for the device's confirmation."""
        previous = self._pending_commands.get(
            key, (None, self.data.get(key), 0.0)
        )[1]
        self._pending_commands[key] = (
            value,
            previous,
            monotonic() + _COMMAND_CONFIRMATION_TIMEOUT,
        )

        data = dict(self.data)
        data[key] = value
        self.data = data
        self.async_update_listeners()

        if self._confirmation_task is None or self._confirmation_task.done():
            self._confirmation_task = self.hass.async_create_task(
                self._async_confirm_pending_commands(),
                f"{self.name} command confirmation",
            )

    def is_property_pending(self, key: str) -> bool:
        """Return whether a command for a property is awaiting confirmation."""
        return key in self._pending_commands

    async def _async_confirm_pending_commands(self) -> None:
        """Poll briefly after commands, then revert to the latest observed value."""
        try:
            while self._pending_commands:
                next_expiry = min(
                    expires_at
                    for _, _, expires_at in self._pending_commands.values()
                )
                delay = min(
                    _COMMAND_CONFIRMATION_INTERVAL,
                    max(0, next_expiry - monotonic()),
                )
                await asyncio.sleep(delay)
                await self.async_refresh()
                self._expire_pending_commands()
                if isinstance(self.last_exception, ConfigEntryAuthFailed):
                    break
        finally:
            self._confirmation_task = None

    def _expire_pending_commands(self) -> None:
        """Restore the last observed values when confirmation times out."""
        now = monotonic()
        expired = {
            key: last_value
            for key, (_, last_value, expires_at) in self._pending_commands.items()
            if now >= expires_at
        }
        if not expired:
            return

        data = dict(self.data)
        for key, last_value in expired.items():
            self._pending_commands.pop(key, None)
            if last_value is None:
                data.pop(key, None)
            else:
                data[key] = last_value

        self.data = data
        self.async_update_listeners()

    def _cancel_confirmation_task(self) -> None:
        """Cancel temporary command polling when the config entry unloads."""
        if self._confirmation_task is not None:
            self._confirmation_task.cancel()
            self._confirmation_task = None
        self._pending_commands.clear()

    def get_device_info(self) -> DeviceInfo:
        """Return device information for this coordinator.

        The cloud device record describes the Wi-Fi module (its model and agent
        version), so the appliance's own values from its properties are preferred.
        """
        data = self.data or {}
        firmware = data.get("firmware_version")
        wifi_module = data.get("mcu_host_version")
        if firmware and wifi_module:
            sw_version = f"{firmware} (Wi-Fi module {wifi_module})"
        else:
            sw_version = firmware or wifi_module or self.device_version
        hw_version = data.get("hardware_version")
        return DeviceInfo(
            identifiers={(DOMAIN, self.dsn)},
            manufacturer="De'Longhi",
            model=data.get("appliance_model") or self.device_model,
            name=self.device_name,
            hw_version=str(hw_version) if hw_version else None,
            sw_version=str(sw_version) if sw_version else None,
        )
