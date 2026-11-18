"""Tests for setting up and unloading the integration."""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

_ROOT = Path(__file__).resolve().parents[1]
HA_INSTALLED = importlib.util.find_spec("homeassistant") is not None


def _device(dsn, oem_model="DL-pac"):
    return {"device": {"dsn": dsn, "oem_model": oem_model, "model": "M", "product_name": dsn}}


@skipUnless(HA_INSTALLED, "Home Assistant is not installed")
class SetupTests(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_ROOT))
        cls.init = importlib.import_module("custom_components.delonghi_comfort")
        cls.api_module = importlib.import_module("custom_components.delonghi_comfort.api")
        from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

        cls.AuthFailed, cls.NotReady = ConfigEntryAuthFailed, ConfigEntryNotReady

    def _setup(self, *, authenticated=True, failure=None, devices=None, devices_error=None):
        hass = MagicMock()
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        entry = MagicMock()
        entry.data = {"username": "u", "password": "p", "language": "en-au"}
        api = MagicMock()
        api.authenticate = AsyncMock(return_value=authenticated)
        api.auth_failure = failure
        api.get_devices = AsyncMock(return_value=devices, side_effect=devices_error)
        coordinators = []

        def make_coordinator(hass_, api_, dsn, device_info, entry_):
            coordinator = MagicMock(dsn=dsn, device_record=device_info)
            coordinator.async_config_entry_first_refresh = AsyncMock()
            coordinators.append(coordinator)
            return coordinator

        patches = (
            patch.object(self.init, "DeLonghiAPI", return_value=api),
            patch.object(self.init, "DeLonghiCoordinator", side_effect=make_coordinator),
            patch.object(self.init, "async_get_clientsession", return_value=MagicMock()),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return hass, entry, coordinators

    # ---- login problems ---------------------------------------------------------
    async def test_rejected_credentials_start_reauthentication(self) -> None:
        hass, entry, _ = self._setup(authenticated=False, failure="invalid_auth")
        with self.assertRaises(self.AuthFailed):
            await self.init.async_setup_entry(hass, entry)

    async def test_other_login_failures_are_retried(self) -> None:
        hass, entry, _ = self._setup(authenticated=False, failure="network")
        with self.assertRaises(self.NotReady):
            await self.init.async_setup_entry(hass, entry)

    async def test_credentials_rejected_while_listing_devices_start_reauthentication(self) -> None:
        hass, entry, _ = self._setup(
            devices_error=self.api_module.DeLonghiAuthenticationError("rejected")
        )
        with self.assertRaises(self.AuthFailed):
            await self.init.async_setup_entry(hass, entry)

    async def test_network_and_api_errors_are_retried(self) -> None:
        for error in (aiohttp.ClientError("x"), self.api_module.DeLonghiAPIError("x"), TimeoutError()):
            with self.subTest(error=type(error).__name__):
                hass, entry, _ = self._setup(devices_error=error)
                with self.assertRaises(self.NotReady):
                    await self.init.async_setup_entry(hass, entry)

    async def test_an_account_without_devices_is_retried(self) -> None:
        hass, entry, _ = self._setup(devices=[])
        with self.assertRaises(self.NotReady):
            await self.init.async_setup_entry(hass, entry)

    # ---- sorting devices ----------------------------------------------------------
    async def test_air_conditioners_and_heaters_are_kept_apart(self) -> None:
        hass, entry, _ = self._setup(
            devices=[_device("AC1"), _device("HT1", "DL-heater"), _device("AC2")]
        )
        self.assertTrue(await self.init.async_setup_entry(hass, entry))
        runtime = entry.runtime_data
        self.assertEqual([c.dsn for c in runtime.coordinators], ["AC1", "AC2"])
        self.assertEqual([c.dsn for c in runtime.heater_coordinators], ["HT1"])
        hass.config_entries.async_forward_entry_setups.assert_awaited_once()

    async def test_each_device_is_refreshed_before_platforms_load(self) -> None:
        hass, entry, coordinators = self._setup(devices=[_device("AC1")])
        await self.init.async_setup_entry(hass, entry)
        coordinators[0].async_config_entry_first_refresh.assert_awaited_once()

    async def test_a_record_without_a_serial_number_is_skipped(self) -> None:
        hass, entry, _ = self._setup(
            devices=[{"device": {"oem_model": "DL-pac"}}, {"nope": 1}, _device("AC1")]
        )
        await self.init.async_setup_entry(hass, entry)
        self.assertEqual([c.dsn for c in entry.runtime_data.coordinators], ["AC1"])

    async def test_only_unusable_records_is_retried(self) -> None:
        hass, entry, _ = self._setup(devices=[{"device": {}}])
        with self.assertRaises(self.NotReady):
            await self.init.async_setup_entry(hass, entry)

    async def test_a_device_without_oem_model_is_treated_as_an_air_conditioner(self) -> None:
        hass, entry, _ = self._setup(devices=[{"device": {"dsn": "AC1"}}])
        await self.init.async_setup_entry(hass, entry)
        self.assertEqual([c.dsn for c in entry.runtime_data.coordinators], ["AC1"])
        self.assertEqual(entry.runtime_data.heater_coordinators, [])

    # ---- options and unload ---------------------------------------------------------
    async def test_changing_options_reloads_the_entry(self) -> None:
        hass, entry, _ = self._setup(devices=[_device("AC1")])
        hass.config_entries.async_reload = AsyncMock()
        await self.init.async_setup_entry(hass, entry)
        listener = entry.add_update_listener.call_args.args[0]
        await listener(hass, entry)
        hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)

    async def test_unloading_unloads_every_platform(self) -> None:
        hass, entry, _ = self._setup(devices=[])
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        self.assertTrue(await self.init.async_unload_entry(hass, entry))
        hass.config_entries.async_unload_platforms.assert_awaited_once_with(
            entry, self.init.PLATFORMS
        )

    def test_every_platform_the_integration_provides_is_forwarded(self) -> None:
        from homeassistant.const import Platform

        self.assertEqual(
            set(self.init.PLATFORMS),
            {Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.NUMBER,
             Platform.SELECT, Platform.SENSOR, Platform.SWITCH},
        )
        for platform in self.init.PLATFORMS:
            with self.subTest(platform=platform):
                module = importlib.import_module(
                    f"custom_components.delonghi_comfort.{platform.value}"
                )
                self.assertTrue(hasattr(module, "async_setup_entry"))
