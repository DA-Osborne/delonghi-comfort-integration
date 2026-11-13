"""Tests for the Real Feel adjustment and Off timer numbers."""
from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
import sys
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import AsyncMock, MagicMock

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
)["entity"]["number"]


def _coordinator(data, available=AC, set_ok=True):
    coordinator = MagicMock()
    coordinator.dsn = "DSN1"
    coordinator.available_properties = frozenset(available)
    coordinator.data = dict(data)
    coordinator.api = MagicMock()
    coordinator.api.set_device_property = AsyncMock(return_value=set_ok)
    coordinator.api.set_temperature_setpoint = AsyncMock(return_value=True)
    coordinator.async_request_refresh = AsyncMock()
    coordinator.get_device_info = lambda: {}
    return coordinator


@skipUnless(HA_INSTALLED, "Home Assistant is not installed")
class NumberTests(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_ROOT))
        cls.number = importlib.import_module("custom_components.delonghi_comfort.number")
        cls.capabilities = importlib.import_module(
            "custom_components.delonghi_comfort.capabilities"
        )

    def _entity(self, key, data=None, **kwargs):
        description = next(d for d in self.number.NUMBER_DESCRIPTIONS if d.key == key)
        coordinator = _coordinator(data or {}, **kwargs)
        return self.number.DeLonghiNumber(coordinator, description), coordinator

    # ---- which numbers a model gets ---------------------------------------
    def test_el112_gets_the_new_numbers(self) -> None:
        supported, _ = self.capabilities.split_supported(AC, self.number.NUMBER_DESCRIPTIONS)
        self.assertEqual(
            {d.key for d in supported},
            {"temp_setpoint", "get_real_feel_offset", "off_timer"},
        )

    def test_models_without_the_properties_do_not(self) -> None:
        bare = AC - {"get_real_feel_offset", "set_real_feel_offset", "onofftimer_minutes"}
        supported, _ = self.capabilities.split_supported(bare, self.number.NUMBER_DESCRIPTIONS)
        self.assertEqual({d.key for d in supported}, {"temp_setpoint"})

    def test_new_numbers_have_translated_names(self) -> None:
        for description in self.number.NUMBER_DESCRIPTIONS:
            with self.subTest(key=description.key):
                self.assertIn(description.translation_key, TRANSLATIONS)

    # ---- ranges -----------------------------------------------------------
    def test_ranges_match_what_the_unit_accepts(self) -> None:
        by_key = {d.key: d for d in self.number.NUMBER_DESCRIPTIONS}
        real_feel = by_key["get_real_feel_offset"]
        self.assertEqual((real_feel.native_min_value, real_feel.native_max_value), (14, 18))
        setpoint = by_key["temp_setpoint"]
        self.assertEqual((setpoint.native_min_value, setpoint.native_max_value), (18, 32))
        self.assertEqual(setpoint.native_step, 1)

    # ---- Real Feel adjustment ---------------------------------------------
    def test_real_feel_reads_the_device_value(self) -> None:
        entity, _ = self._entity("get_real_feel_offset", {"get_real_feel_offset": 17})
        self.assertEqual(entity.native_value, 17)

    async def test_real_feel_writes_an_integer_and_holds_the_value(self) -> None:
        entity, coordinator = self._entity("get_real_feel_offset", {"get_real_feel_offset": 16})
        await entity.async_set_native_value(18.0)
        args = coordinator.api.set_device_property.await_args.args
        self.assertEqual(args[:2], ("DSN1", "set_real_feel_offset"))
        self.assertEqual(args[2], 18)
        self.assertIs(type(args[2]), int)
        coordinator.set_optimistic_value.assert_called_once_with("get_real_feel_offset", 18)

    async def test_failed_write_does_not_hold_a_value(self) -> None:
        entity, coordinator = self._entity(
            "get_real_feel_offset", {"get_real_feel_offset": 16}, set_ok=False
        )
        await entity.async_set_native_value(17)
        coordinator.set_optimistic_value.assert_not_called()

    # ---- Off timer ----------------------------------------------------------
    def test_off_timer_shows_zero_when_no_timer_runs(self) -> None:
        # The unit keeps the last duration after a timer ends.
        entity, _ = self._entity("off_timer", {"get_timer_enabled": 0, "onofftimer_minutes": 15})
        self.assertEqual(entity.native_value, 0)

    def test_off_timer_shows_the_duration_while_running(self) -> None:
        entity, _ = self._entity("off_timer", {"get_timer_enabled": 1, "onofftimer_minutes": 15})
        self.assertEqual(entity.native_value, 15)

    def test_off_timer_copes_with_empty_values(self) -> None:
        entity, _ = self._entity("off_timer", {"get_timer_enabled": 1, "onofftimer_minutes": ""})
        self.assertEqual(entity.native_value, 0)

    async def test_starting_the_timer_writes_minutes_then_enables(self) -> None:
        entity, coordinator = self._entity("off_timer", {"get_timer_enabled": 0})
        await entity.async_set_native_value(30)
        calls = [c.args for c in coordinator.api.set_device_property.await_args_list]
        self.assertEqual(calls, [("DSN1", "onofftimer_minutes", 30), ("DSN1", "set_timer_enabled", 1)])
        for call in calls:
            self.assertIs(type(call[2]), int)
        coordinator.set_optimistic_value.assert_any_call("get_timer_enabled", 1)

    async def test_zero_cancels_the_timer(self) -> None:
        entity, coordinator = self._entity("off_timer", {"get_timer_enabled": 1})
        await entity.async_set_native_value(0)
        calls = [c.args for c in coordinator.api.set_device_property.await_args_list]
        self.assertEqual(calls, [("DSN1", "set_timer_enabled", 0), ("DSN1", "onofftimer_minutes", 0)])
        coordinator.set_optimistic_value.assert_called_once_with("get_timer_enabled", 0)

    async def test_timer_is_not_enabled_if_the_duration_write_fails(self) -> None:
        entity, coordinator = self._entity("off_timer", {"get_timer_enabled": 0}, set_ok=False)
        await entity.async_set_native_value(30)
        self.assertEqual(coordinator.api.set_device_property.await_count, 1)
        coordinator.set_optimistic_value.assert_not_called()

    # ---- availability -------------------------------------------------------
    def test_numbers_are_unavailable_until_the_device_reports_their_properties(self) -> None:
        entity, _ = self._entity("off_timer", {"onofftimer_minutes": 0})
        self.assertFalse(entity.available)
        entity, _ = self._entity(
            "off_timer",
            {"onofftimer_minutes": 0, "set_timer_enabled": 0, "get_timer_enabled": 0},
        )
        self.assertTrue(entity.available)

    # ---- the original setpoint number keeps working ---------------------------
    async def test_temperature_setpoint_still_refreshes_after_a_write(self) -> None:
        entity, coordinator = self._entity("temp_setpoint", {"temp_setpoint": 24})
        await entity.async_set_native_value(25)
        coordinator.api.set_temperature_setpoint.assert_awaited_once_with("DSN1", 25)
        coordinator.async_request_refresh.assert_awaited_once()
