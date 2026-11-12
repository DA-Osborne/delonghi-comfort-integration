"""Tests for the remote, comfort and alarm sensors."""
from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
import sys
from unittest import TestCase, skipUnless
from unittest.mock import MagicMock

_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_PACKAGE_DIR = _ROOT / "custom_components" / "delonghi_comfort"
HA_INSTALLED = importlib.util.find_spec("homeassistant") is not None

AC = frozenset(
    json.loads((_FIXTURES / "ac_el112_properties.json").read_text(encoding="utf-8"))[
        "properties"
    ]
)
TRANSLATIONS = json.loads(
    (_PACKAGE_DIR / "translations" / "en.json").read_text(encoding="utf-8")
)["entity"]


def _coordinator(data, available=AC):
    coordinator = MagicMock()
    coordinator.dsn = "DSN1"
    coordinator.available_properties = frozenset(available)
    coordinator.data = dict(data)
    coordinator.get_device_info = lambda: {}
    return coordinator


@skipUnless(HA_INSTALLED, "Home Assistant is not installed")
class SensorTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_ROOT))
        cls.sensor = importlib.import_module("custom_components.delonghi_comfort.sensor")
        cls.binary = importlib.import_module(
            "custom_components.delonghi_comfort.binary_sensor"
        )
        cls.init = importlib.import_module("custom_components.delonghi_comfort")

    def _sensor(self, key, **data):
        description = next(d for d in self.sensor.SENSOR_DESCRIPTIONS if d.key == key)
        return self.sensor.DeLonghiSensor(_coordinator(data), description)

    def _binary(self, key, **data):
        description = next(
            d for d in self.binary.BINARY_SENSOR_DESCRIPTIONS if d.key == key
        )
        return self.binary.DeLonghiBinarySensor(_coordinator(data), description)

    # ---- myEcoReal Feel comfort light ------------------------------------
    def test_comfort_light_known_codes(self) -> None:
        self.assertEqual(self._sensor("real_feel_colour", real_feel_colour=0).native_value, "inactive")
        self.assertEqual(self._sensor("real_feel_colour", real_feel_colour=4).native_value, "perfect")

    def test_comfort_light_unknown_code_is_other_and_keeps_the_raw_value(self) -> None:
        entity = self._sensor("real_feel_colour", real_feel_colour=2)
        self.assertEqual(entity.native_value, "other")
        self.assertEqual(entity.extra_state_attributes, {"raw_value": 2})

    def test_sensors_without_a_default_have_no_extra_attributes(self) -> None:
        self.assertIsNone(self._sensor("get_device_mode", get_device_mode=1).extra_state_attributes)

    def test_mode_sensor_knows_real_feel(self) -> None:
        self.assertEqual(self._sensor("get_device_mode", get_device_mode=5).native_value, "real_feel")
        # A mode we do not know reads as unknown, not as an invalid state.
        self.assertIsNone(self._sensor("get_device_mode", get_device_mode=4).native_value)

    # ---- remote readings --------------------------------------------------
    def test_remote_readings_are_unavailable_when_the_remote_is_gone(self) -> None:
        for key in ("remote_temp", "remote_hum"):
            with self.subTest(key=key):
                connected = self._sensor(key, **{key: 22, "pairing_status": 1})
                gone = self._sensor(key, **{key: 22, "pairing_status": 0})
                self.assertTrue(connected.available)
                self.assertFalse(gone.available)

    def test_ordinary_sensors_ignore_the_remote_state(self) -> None:
        entity = self._sensor("room_temp", room_temp=22, pairing_status=0)
        self.assertTrue(entity.available)

    # ---- binary sensors ---------------------------------------------------
    def test_binary_sensor_polarity(self) -> None:
        cases = (
            # remote connected: 1 connected, 0 not
            ("pairing_status", 1, True),
            ("pairing_status", 0, False),
            # sensors used is inverted: 0 means the remote's sensor is in use
            ("get_sensors_used", 0, True),
            ("get_sensors_used", 1, False),
            # bt_status 4 is the docked state; 1 (undocked) and 2 (no batteries) are not
            ("bt_status", 4, True),
            ("bt_status", 1, False),
            ("bt_status", 2, False),
            ("hl_alarm", 1, True),
            ("hl_alarm", 0, False),
            ("get_timer_enabled", 1, True),
        )
        for key, value, expected in cases:
            with self.subTest(key=key, value=value):
                self.assertIs(self._binary(key, **{key: value}).is_on, expected)

    def test_binary_sensor_handles_text_and_missing_values(self) -> None:
        self.assertIs(self._binary("hl_alarm", hl_alarm="1").is_on, True)
        self.assertIs(self._binary("hl_alarm", hl_alarm=1.0).is_on, True)
        self.assertIsNone(self._binary("hl_alarm", hl_alarm="").is_on)
        self.assertIsNone(self._binary("hl_alarm", hl_alarm=None).is_on)

    def test_binary_sensors_exist_for_the_el112(self) -> None:
        from custom_components.delonghi_comfort.capabilities import split_supported

        supported, unsupported = split_supported(AC, self.binary.BINARY_SENSOR_DESCRIPTIONS)
        self.assertEqual(len(supported), 10)
        self.assertEqual(unsupported, [])

    def test_binary_sensors_are_skipped_on_models_without_the_properties(self) -> None:
        from custom_components.delonghi_comfort.capabilities import split_supported

        bare = AC - {"hl_alarm", "pf_alarm", "pairing_status"}
        supported, unsupported = split_supported(bare, self.binary.BINARY_SENSOR_DESCRIPTIONS)
        self.assertEqual(
            {d.key for d in unsupported}, {"hl_alarm", "pf_alarm", "pairing_status"}
        )

    # ---- plumbing ---------------------------------------------------------
    def test_every_new_entity_has_a_translated_name(self) -> None:
        for description in self.binary.BINARY_SENSOR_DESCRIPTIONS:
            with self.subTest(key=description.key):
                self.assertIn(description.translation_key, TRANSLATIONS["binary_sensor"])
        for description in self.sensor.SENSOR_DESCRIPTIONS:
            if description.translation_key:
                with self.subTest(key=description.key):
                    self.assertIn(description.translation_key, TRANSLATIONS["sensor"])

    def test_binary_sensor_platform_is_registered(self) -> None:
        from homeassistant.const import Platform

        self.assertIn(Platform.BINARY_SENSOR, self.init.PLATFORMS)
