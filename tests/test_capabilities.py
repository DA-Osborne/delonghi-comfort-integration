"""Offline tests for capability detection."""
from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
import sys
import types
from unittest import TestCase, skipUnless
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_DIR = _ROOT / "custom_components" / "delonghi_comfort"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_PACKAGE_NAME = "_delonghi_comfort_test"

if _PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(_PACKAGE_NAME)
    package.__path__ = [str(_PACKAGE_DIR)]
    sys.modules[_PACKAGE_NAME] = package
capabilities = importlib.import_module(f"{_PACKAGE_NAME}.capabilities")

HA_INSTALLED = importlib.util.find_spec("homeassistant") is not None


def _load_properties(name: str) -> frozenset[str]:
    data = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    return frozenset(data["properties"])


AC = _load_properties("ac_el112_properties.json")
DEHUMIDIFIER = _load_properties("synthetic_dehumidifier_properties.json")


class _Description:
    def __init__(self, key: str, required: tuple[str, ...]) -> None:
        self.key = key
        self.required_properties = required


class SupportsTests(TestCase):
    """Test the pure matching helpers."""

    def test_all_required_must_be_present(self) -> None:
        self.assertTrue(capabilities.supports({"a", "b"}, ("a", "b")))
        self.assertFalse(capabilities.supports({"a"}, ("a", "b")))

    def test_no_requirements_is_supported(self) -> None:
        self.assertTrue(capabilities.supports(set(), ()))

    def test_complete_snapshot_needs_core_properties(self) -> None:
        self.assertTrue(capabilities.is_complete_snapshot(AC))
        self.assertFalse(capabilities.is_complete_snapshot(frozenset()))
        self.assertFalse(capabilities.is_complete_snapshot({"get_device_status"}))

    def test_split_supported(self) -> None:
        wanted = _Description("wanted", ("get_device_status",))
        missing = _Description("missing", ("no_such_property",))
        supported, unsupported = capabilities.split_supported(AC, (wanted, missing))
        self.assertEqual(supported, [wanted])
        self.assertEqual(unsupported, [missing])

    def test_empty_valued_records_still_count_as_present(self) -> None:
        # The coordinator records names, not values, so a record whose value is
        # empty (set_swing_function in the EL112 dump) still counts as present.
        self.assertIn("set_swing_function", AC)


class RegistryCleanupTests(TestCase):
    """Test removal of registry entries for unsupported entities."""

    def _run(self, available, registry_entries):
        registry = MagicMock()
        registry.async_get_entity_id.side_effect = (
            lambda platform, domain, unique_id: registry_entries.get(
                (platform, unique_id)
            )
        )
        descriptions = (
            _Description("filter_hours", ("filter_hours",)),
            _Description("room_temp", ("room_temp",)),
        )
        entity_registry = MagicMock()
        entity_registry.async_get.return_value = registry
        helpers = types.ModuleType("homeassistant.helpers")
        helpers.entity_registry = entity_registry
        with patch.dict(
            sys.modules,
            {
                "homeassistant": types.ModuleType("homeassistant"),
                "homeassistant.helpers": helpers,
                "homeassistant.helpers.entity_registry": entity_registry,
            },
        ):
            supported = capabilities.async_supported_descriptions(
                MagicMock(), "sensor", "DSN1", available, descriptions
            )
        return supported, registry

    def test_removes_entries_for_properties_the_device_lacks(self) -> None:
        supported, registry = self._run(
            AC, {("sensor", "DSN1_filter_hours"): "sensor.old_filter_hours"}
        )
        self.assertEqual([d.key for d in supported], ["room_temp"])
        registry.async_remove.assert_called_once_with("sensor.old_filter_hours")

    def test_keeps_entries_when_property_list_looks_incomplete(self) -> None:
        supported, registry = self._run(
            frozenset({"room_temp"}),
            {("sensor", "DSN1_filter_hours"): "sensor.old_filter_hours"},
        )
        self.assertEqual([d.key for d in supported], ["room_temp"])
        registry.async_remove.assert_not_called()

    def test_keeps_entries_for_supported_properties(self) -> None:
        supported, registry = self._run(
            DEHUMIDIFIER, {("sensor", "DSN1_filter_hours"): "sensor.filter_hours"}
        )
        self.assertEqual([d.key for d in supported], ["filter_hours", "room_temp"])
        registry.async_remove.assert_not_called()


@skipUnless(HA_INSTALLED, "Home Assistant is not installed")
class PlatformGatingTests(TestCase):
    """Check the real entity descriptions against the property fixtures."""

    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_ROOT))
        cls.sensor = importlib.import_module("custom_components.delonghi_comfort.sensor")
        cls.number = importlib.import_module("custom_components.delonghi_comfort.number")
        cls.select = importlib.import_module("custom_components.delonghi_comfort.select")
        cls.switch = importlib.import_module("custom_components.delonghi_comfort.switch")

    def _keys(self, descriptions, available) -> set[str]:
        supported, _ = capabilities.split_supported(available, descriptions)
        return {description.key for description in supported}

    def test_every_description_declares_requirements(self) -> None:
        for module, descriptions in (
            (self.sensor, self.sensor.SENSOR_DESCRIPTIONS),
            (self.number, self.number.NUMBER_DESCRIPTIONS),
            (self.select, self.select.SELECT_DESCRIPTIONS),
            (self.switch, self.switch.SWITCH_DESCRIPTIONS),
        ):
            for description in descriptions:
                with self.subTest(module=module.__name__, key=description.key):
                    self.assertTrue(description.required_properties)

    def test_el112_gets_only_entities_it_reports(self) -> None:
        self.assertEqual(
            self._keys(self.sensor.SENSOR_DESCRIPTIONS, AC),
            {
                "room_temp",
                "temp_setpoint",
                "room_hum",
                "get_device_status",
                "get_device_mode",
                "get_int_fan_speed",
                "get_silent_function",
                "cst_rssi",
                "second_room_temp",
            },
        )
        self.assertEqual(
            self._keys(self.number.NUMBER_DESCRIPTIONS, AC), {"temp_setpoint"}
        )
        self.assertEqual(
            self._keys(self.select.SELECT_DESCRIPTIONS, AC), {"get_device_mode"}
        )
        self.assertEqual(
            self._keys(self.switch.SWITCH_DESCRIPTIONS, AC),
            {"get_device_status", "get_silent_function"},
        )

    def test_model_reporting_more_properties_gets_more_entities(self) -> None:
        self.assertIn(
            "filter_hours", self._keys(self.sensor.SENSOR_DESCRIPTIONS, DEHUMIDIFIER)
        )
        self.assertIn(
            "humidity_setpoint",
            self._keys(self.number.NUMBER_DESCRIPTIONS, DEHUMIDIFIER),
        )

    def _coordinator(self, data):
        from custom_components.delonghi_comfort.coordinator import DeLonghiCoordinator

        coordinator = MagicMock()
        coordinator.dsn = "DSN1"
        coordinator.device_name = "Lounge-AirCon"
        coordinator.device_model = "AY008ESP1"
        coordinator.device_version = "ADA 1.8.1"
        coordinator.data = data
        coordinator.get_device_info = lambda: DeLonghiCoordinator.get_device_info(
            coordinator
        )
        return coordinator

    def test_device_info_prefers_appliance_properties(self) -> None:
        info = self._coordinator(
            {
                "appliance_model": "EL112",
                "hardware_version": 1.1,
                "firmware_version": "2.1",
                "mcu_host_version": "4.2.2",
            }
        ).get_device_info()
        self.assertEqual(info["model"], "EL112")
        self.assertEqual(info["hw_version"], "1.1")
        self.assertEqual(info["sw_version"], "2.1 (Wi-Fi module 4.2.2)")
        self.assertEqual(info["name"], "Lounge-AirCon")
        self.assertEqual(info["identifiers"], {("delonghi_comfort", "DSN1")})

    def test_device_info_falls_back_to_device_record(self) -> None:
        info = self._coordinator({}).get_device_info()
        self.assertEqual(info["model"], "AY008ESP1")
        self.assertEqual(info["sw_version"], "ADA 1.8.1")
        self.assertIsNone(info["hw_version"])

    def test_entities_share_device_and_naming(self) -> None:
        climate = importlib.import_module("custom_components.delonghi_comfort.climate")
        coordinator = self._coordinator({"appliance_model": "EL112"})
        entities = [
            climate.DeLonghiClimate(coordinator),
            self.sensor.DeLonghiSensor(coordinator, self.sensor.SENSOR_DESCRIPTIONS[0]),
            self.switch.DeLonghiSwitch(coordinator, self.switch.SWITCH_DESCRIPTIONS[0]),
            self.number.DeLonghiNumber(coordinator, self.number.NUMBER_DESCRIPTIONS[0]),
            self.select.DeLonghiSelect(coordinator, self.select.SELECT_DESCRIPTIONS[0]),
        ]
        for entity in entities:
            with self.subTest(entity=type(entity).__name__):
                self.assertTrue(entity.has_entity_name)
                self.assertEqual(entity.device_info["model"], "EL112")
        self.assertIsNone(entities[0].name)

    def test_enum_sensors_have_options_and_translated_states(self) -> None:
        translations = json.loads(
            (_PACKAGE_DIR / "translations" / "en.json").read_text(encoding="utf-8")
        )["entity"]["sensor"]
        enum_sensors = [
            d for d in self.sensor.SENSOR_DESCRIPTIONS if d.value_map is not None
        ]
        self.assertEqual(len(enum_sensors), 4)
        for description in enum_sensors:
            with self.subTest(key=description.key):
                self.assertEqual(description.options, list(description.value_map.values()))
                states = translations[description.translation_key]["state"]
                self.assertEqual(set(states), set(description.options))

    def test_enum_sensor_reports_unknown_values_as_none(self) -> None:
        coordinator = self._coordinator({"get_device_status": 7, "get_device_mode": 2})
        by_key = {d.key: d for d in self.sensor.SENSOR_DESCRIPTIONS}
        status = self.sensor.DeLonghiSensor(coordinator, by_key["get_device_status"])
        mode = self.sensor.DeLonghiSensor(coordinator, by_key["get_device_mode"])
        self.assertIsNone(status.native_value)
        self.assertEqual(mode.native_value, "dehumidification")

    def test_duplicates_are_disabled_by_default_and_primary_entities_are_not(self) -> None:
        disabled = {
            d.key
            for d in self.sensor.SENSOR_DESCRIPTIONS
            if not d.entity_registry_enabled_default
        }
        self.assertEqual(
            disabled,
            {"temp_setpoint", "get_device_status", "get_device_mode",
             "get_int_fan_speed", "get_silent_function", "error_code",
             "operating_hours", "wifi_signal"},
        )
        switches = {d.key: d for d in self.switch.SWITCH_DESCRIPTIONS}
        self.assertFalse(switches["get_device_status"].entity_registry_enabled_default)
        self.assertTrue(switches["get_silent_function"].entity_registry_enabled_default)
        numbers = {d.key: d for d in self.number.NUMBER_DESCRIPTIONS}
        self.assertFalse(numbers["temp_setpoint"].entity_registry_enabled_default)

    def test_translated_switches_have_icons(self) -> None:
        icons = json.loads((_PACKAGE_DIR / "icons.json").read_text(encoding="utf-8"))
        for description in self.switch.SWITCH_DESCRIPTIONS:
            with self.subTest(key=description.key):
                self.assertIsNone(description.icon)
                self.assertIn(description.translation_key, icons["entity"]["switch"])

    def test_ac_climate_does_not_dump_raw_properties(self) -> None:
        climate = importlib.import_module("custom_components.delonghi_comfort.climate")
        entity = climate.DeLonghiClimate(self._coordinator({"room_temp": 22.4}))
        self.assertIsNone(entity.extra_state_attributes)

    def test_remote_link_is_not_presented_as_wifi(self) -> None:
        # cst_rssi is the Bluetooth link to the CST remote. It is verified by the
        # remote_cradle capture (-72 away from the unit, -49 docked). The device
        # reports no Wi-Fi signal property, so the Wi-Fi sensor must not exist.
        by_key = {d.key: d for d in self.sensor.SENSOR_DESCRIPTIONS}
        self.assertEqual(by_key["cst_rssi"].translation_key, "remote_signal_strength")
        self.assertEqual(by_key["wifi_signal"].required_properties, ("wifi_signal",))
        self.assertNotIn("wifi_signal", AC)
        self.assertIn("cst_rssi", AC)
