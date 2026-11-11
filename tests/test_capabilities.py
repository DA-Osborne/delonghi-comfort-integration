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
                "wifi_signal",
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

    def test_wifi_signal_reads_cst_rssi(self) -> None:
        description = next(
            d for d in self.sensor.SENSOR_DESCRIPTIONS if d.key == "wifi_signal"
        )
        self.assertEqual(description.data_key, "cst_rssi")
        self.assertIn("cst_rssi", AC)
