"""Tests for the heater path.

There is no heater to test against, so these use made-up data shaped like what the
code expects. They check that odd or missing values cannot crash an entity, that
entities appear only for properties the heater reports, and that nothing identifying
is copied into state attributes.
"""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import sys
import types
from unittest import IsolatedAsyncioTestCase, TestCase, skipUnless
from unittest.mock import AsyncMock, MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_DIR = _ROOT / "custom_components" / "delonghi_comfort"
_PACKAGE_NAME = "_delonghi_comfort_test"
HA_INSTALLED = importlib.util.find_spec("homeassistant") is not None

if _PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(_PACKAGE_NAME)
    package.__path__ = [str(_PACKAGE_DIR)]
    sys.modules[_PACKAGE_NAME] = package
capabilities = importlib.import_module(f"{_PACKAGE_NAME}.capabilities")

HEATER_PROPERTIES = frozenset(
    {
        "device_status", "device_mode", "MDH_Resources", "current_power_level",
        "temperature_setpoint", "room_temp", "get_eco", "set_eco", "get_lock",
        "set_lock", "current_brightness", "set_brightness", "set_status",
        "appliance_model", "mac_address",
    }
)


def _coordinator(data=None, available=HEATER_PROPERTIES):
    coordinator = MagicMock()
    coordinator.dsn = "HT000W000000002"
    coordinator.available_properties = frozenset(available)
    coordinator.data = dict(data or {})
    coordinator.api = MagicMock()
    coordinator.api.set_device_property = AsyncMock(return_value=True)
    coordinator.async_request_refresh = AsyncMock()
    coordinator.get_device_info = lambda: {}
    return coordinator


class CapabilityTests(TestCase):
    def test_a_heater_property_list_counts_as_complete(self) -> None:
        self.assertTrue(capabilities.is_complete_snapshot(HEATER_PROPERTIES))
        self.assertFalse(capabilities.is_complete_snapshot({"room_temp"}))

    def test_heater_switches_follow_the_properties_present(self) -> None:
        description = MagicMock(key="eco", required_properties=("get_eco", "set_eco"))
        supported, unsupported = capabilities.split_supported(
            HEATER_PROPERTIES - {"set_eco"}, [description]
        )
        self.assertEqual((supported, unsupported), ([], [description]))

    def test_registry_cleanup_uses_the_heater_unique_id_format(self) -> None:
        registry = MagicMock()
        registry.async_get_entity_id.return_value = "switch.old_eco"
        entity_registry = MagicMock()
        entity_registry.async_get.return_value = registry
        helpers = types.ModuleType("homeassistant.helpers")
        helpers.entity_registry = entity_registry
        description = MagicMock(key="eco", required_properties=("get_eco",))
        with patch.dict(
            sys.modules,
            {
                "homeassistant": types.ModuleType("homeassistant"),
                "homeassistant.helpers": helpers,
                "homeassistant.helpers.entity_registry": entity_registry,
            },
        ):
            capabilities.async_supported_descriptions(
                MagicMock(), "switch", "HT1", HEATER_PROPERTIES - {"get_eco"}, [description],
                unique_id_format="delonghi_heater_{dsn}_{key}",
            )
        registry.async_get_entity_id.assert_called_once_with(
            "switch", "delonghi_comfort", "delonghi_heater_HT1_eco"
        )
        registry.async_remove.assert_called_once_with("switch.old_eco")


@skipUnless(HA_INSTALLED, "Home Assistant is not installed")
class HeaterEntityTests(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_ROOT))
        cls.init = importlib.import_module("custom_components.delonghi_comfort")
        cls.climate = importlib.import_module("custom_components.delonghi_comfort.climate")
        cls.select = importlib.import_module("custom_components.delonghi_comfort.select")
        cls.switch = importlib.import_module("custom_components.delonghi_comfort.switch")
        from homeassistant.components.climate import HVACAction, HVACMode

        cls.HVACAction, cls.HVACMode = HVACAction, HVACMode

    def _heater(self, **data):
        coordinator = _coordinator(data)
        return self.climate.DeLonghiHeater(coordinator), coordinator

    # ---- recognising heaters ----------------------------------------------
    def test_heaters_are_recognised_by_oem_model(self) -> None:
        self.assertTrue(self.init.is_heater({"oem_model": "DL-heater"}))
        self.assertFalse(self.init.is_heater({"oem_model": "DL-pac"}))
        # A record without the field must not crash setup.
        self.assertFalse(self.init.is_heater({}))

    # ---- values that used to crash -----------------------------------------
    def test_preset_mode(self) -> None:
        names = ["Day mode", "Night mode", "Antifrost", "Manual"]
        for value, expected in (
            (1, names[0]), (2, names[1]), (4, names[3]), ("3", names[2]),
            (None, None), ("", None), (0, None), (5, None), (-1, None), ("x", None),
        ):
            with self.subTest(value=value):
                heater, _ = self._heater(device_mode=value)
                self.assertEqual(heater.preset_mode, expected)

    def test_preset_mode_when_the_property_is_missing(self) -> None:
        heater, _ = self._heater()
        self.assertIsNone(heater.preset_mode)

    def test_fan_mode(self) -> None:
        for value, expected in (
            (0, "0%"), (3, "60%"), (5, "100%"),
            (None, None), (6, None), (-1, None), ("x", None), (True, None),
        ):
            with self.subTest(value=value):
                heater, _ = self._heater(current_power_level=value)
                self.assertEqual(heater.fan_mode, expected)

    async def test_invalid_fan_mode_is_not_written(self) -> None:
        heater, coordinator = self._heater()
        await heater.async_set_fan_mode("55%")
        coordinator.api.set_device_property.assert_not_awaited()
        await heater.async_set_fan_mode("40%")
        coordinator.api.set_device_property.assert_awaited_once_with(
            "HT000W000000002", "set_power_level", 2
        )

    def test_brightness_option_handles_odd_values(self) -> None:
        coordinator = _coordinator()
        select = self.select.HeaterBrightness(coordinator)
        for value, expected in (
            (1, "Level 1"), (3, "Level 3"), (0, None), (4, None),
            (None, None), ("2", None), (True, None),
        ):
            with self.subTest(value=value):
                coordinator.data = {"current_brightness": value}
                self.assertEqual(select.current_option, expected)

    async def test_unknown_brightness_is_not_written(self) -> None:
        coordinator = _coordinator()
        select = self.select.HeaterBrightness(coordinator)
        await select.async_select_option("Level 9")
        coordinator.api.set_device_property.assert_not_awaited()

    # ---- state ---------------------------------------------------------------
    def test_hvac_mode_and_action(self) -> None:
        for status, resources, mode, action in (
            (1, 2, self.HVACMode.HEAT, self.HVACAction.HEATING),
            (1, 0, self.HVACMode.HEAT, self.HVACAction.IDLE),
            (2, 2, self.HVACMode.OFF, self.HVACAction.OFF),
            (None, None, self.HVACMode.OFF, self.HVACAction.OFF),
        ):
            with self.subTest(status=status, resources=resources):
                heater, _ = self._heater(device_status=status, MDH_Resources=resources)
                self.assertEqual(heater.hvac_mode, mode)
                self.assertEqual(heater.hvac_action, action)

    def test_attributes_no_longer_copy_every_property(self) -> None:
        heater, _ = self._heater(
            current_power_level=2, MDH_Resources=1, mac_address="aa:bb:cc", room_temp=20
        )
        self.assertEqual(
            heater.extra_state_attributes, {"current_power_level": 2, "MDH_Resources": 1}
        )
        empty, _ = self._heater(room_temp=20)
        self.assertIsNone(empty.extra_state_attributes)

    def test_temperatures_use_native_names(self) -> None:
        heater, _ = self._heater(room_temp=19.5, temperature_setpoint=21)
        self.assertEqual(heater.native_current_temperature, 19.5)
        self.assertEqual(heater.native_target_temperature, 21)

    # ---- switches ---------------------------------------------------------------
    def test_switches_only_for_the_properties_the_heater_reports(self) -> None:
        supported, _ = capabilities.split_supported(
            HEATER_PROPERTIES, self.switch.HEATER_DESCRIPTIONS
        )
        self.assertEqual({d.key for d in supported}, {"eco", "lock"})
        supported, _ = capabilities.split_supported(
            HEATER_PROPERTIES - {"get_lock", "set_lock"}, self.switch.HEATER_DESCRIPTIONS
        )
        self.assertEqual({d.key for d in supported}, {"eco"})

    async def test_switch_writes_numbers(self) -> None:
        coordinator = _coordinator({"get_eco": 0})
        description = self.switch.HEATER_DESCRIPTIONS[0]
        entity = self.switch.HeaterSwitch(coordinator, description)
        await entity.async_turn_on()
        args = coordinator.api.set_device_property.await_args.args
        self.assertEqual(args, ("HT000W000000002", "set_eco", 1))
        self.assertIs(type(args[2]), int)
