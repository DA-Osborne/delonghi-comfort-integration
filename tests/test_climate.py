"""Tests for swing and myEcoReal Feel handling on the air conditioner entities."""
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
HA_INSTALLED = importlib.util.find_spec("homeassistant") is not None

AC = frozenset(
    json.loads((_FIXTURES / "ac_el112_properties.json").read_text(encoding="utf-8"))[
        "properties"
    ]
)
# The same unit without the features added for myEcoReal Feel and swing.
BASIC = AC - {
    "real_feel_colour",
    "get_real_feel_offset",
    "set_real_feel_offset",
    "get_swing_function",
    "set_swing_function",
}


def _coordinator(available, data):
    coordinator = MagicMock()
    coordinator.dsn = "DSN1"
    coordinator.device_name = "Lounge-AirCon"
    coordinator.available_properties = frozenset(available)
    coordinator.data = dict(data)
    coordinator.api = MagicMock()
    coordinator.api.set_device_mode = AsyncMock(return_value=True)
    coordinator.api.set_device_status = AsyncMock(return_value=True)
    coordinator.api.set_device_property = AsyncMock(return_value=True)
    coordinator.async_request_refresh = AsyncMock()
    coordinator.get_device_info = lambda: {}
    return coordinator


@skipUnless(HA_INSTALLED, "Home Assistant is not installed")
class ClimateRealFeelTests(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_ROOT))
        cls.climate = importlib.import_module("custom_components.delonghi_comfort.climate")
        cls.select = importlib.import_module("custom_components.delonghi_comfort.select")
        from homeassistant.components.climate import (
            SWING_OFF,
            SWING_ON,
            ClimateEntityFeature,
            HVACAction,
            HVACMode,
        )

        cls.SWING_OFF, cls.SWING_ON = SWING_OFF, SWING_ON
        cls.Feature, cls.HVACAction, cls.HVACMode = ClimateEntityFeature, HVACAction, HVACMode

    def _entity(self, available=AC, **data):
        base = {"get_device_status": 1, "get_device_mode": 1}
        base.update(data)
        coordinator = _coordinator(available, base)
        return self.climate.DeLonghiClimate(coordinator), coordinator

    def test_model_with_real_feel_and_swing_offers_both(self) -> None:
        entity, _ = self._entity()
        self.assertIn(self.HVACMode.AUTO, entity.hvac_modes)
        self.assertTrue(entity.supported_features & self.Feature.SWING_MODE)
        self.assertEqual(entity.swing_modes, [self.SWING_OFF, self.SWING_ON])

    def test_model_without_them_offers_neither(self) -> None:
        entity, _ = self._entity(BASIC)
        self.assertNotIn(self.HVACMode.AUTO, entity.hvac_modes)
        self.assertFalse(entity.supported_features & self.Feature.SWING_MODE)

    def test_mode_mapping(self) -> None:
        for device_mode, expected in (
            (1, self.HVACMode.COOL),
            (2, self.HVACMode.DRY),
            (3, self.HVACMode.FAN_ONLY),
            (5, self.HVACMode.AUTO),
            # Mode 4 is heat, which the EL112 does not have; it reports unknown.
            (4, None),
        ):
            with self.subTest(device_mode=device_mode):
                entity, _ = self._entity(get_device_mode=device_mode)
                self.assertEqual(entity.hvac_mode, expected)

    def test_off_wins_over_mode(self) -> None:
        entity, _ = self._entity(get_device_status=2, get_device_mode=5)
        self.assertEqual(entity.hvac_mode, self.HVACMode.OFF)

    def test_real_feel_action_is_not_reported(self) -> None:
        entity, _ = self._entity(get_device_mode=5)
        self.assertIsNone(entity.hvac_action)

    async def test_selecting_auto_writes_mode_five(self) -> None:
        entity, coordinator = self._entity()
        await entity.async_set_hvac_mode(self.HVACMode.AUTO)
        coordinator.api.set_device_mode.assert_awaited_once_with("DSN1", 5)
        coordinator.set_optimistic_value.assert_called_once_with("get_device_mode", 5)

    async def test_selecting_auto_turns_the_unit_on_first(self) -> None:
        entity, coordinator = self._entity(get_device_status=2)
        await entity.async_set_hvac_mode(self.HVACMode.AUTO)
        coordinator.api.set_device_status.assert_awaited_once_with("DSN1", 1)
        coordinator.api.set_device_mode.assert_awaited_once_with("DSN1", 5)

    async def test_auto_is_ignored_on_models_without_real_feel(self) -> None:
        entity, coordinator = self._entity(BASIC)
        await entity.async_set_hvac_mode(self.HVACMode.AUTO)
        coordinator.api.set_device_mode.assert_not_awaited()

    def test_swing_state(self) -> None:
        self.assertEqual(self._entity(get_swing_function=1)[0].swing_mode, self.SWING_ON)
        self.assertEqual(self._entity(get_swing_function=0)[0].swing_mode, self.SWING_OFF)
        self.assertIsNone(self._entity()[0].swing_mode)

    async def test_swing_writes_numbers_not_booleans(self) -> None:
        # The cloud answers HTTP 422 to a JSON true; the numbers 1 and 0 work.
        entity, coordinator = self._entity(get_swing_function=1)
        for swing, expected in ((self.SWING_OFF, 0), (self.SWING_ON, 1)):
            coordinator.api.set_device_property.reset_mock()
            await entity.async_set_swing_mode(swing)
            args = coordinator.api.set_device_property.await_args.args
            self.assertEqual(args[:2], ("DSN1", "set_swing_function"))
            self.assertEqual(args[2], expected)
            self.assertIs(type(args[2]), int)

    async def test_invalid_swing_mode_writes_nothing(self) -> None:
        entity, coordinator = self._entity()
        await entity.async_set_swing_mode("both")
        coordinator.api.set_device_property.assert_not_awaited()

    def _select(self, available=AC, **data):
        coordinator = _coordinator(available, data)
        description = self.select.SELECT_DESCRIPTIONS[0]
        return self.select.DeLonghiSelect(coordinator, description), coordinator

    def test_mode_select_lists_real_feel_only_when_supported(self) -> None:
        self.assertIn("real_feel", self._select()[0].options)
        self.assertNotIn("real_feel", self._select(BASIC)[0].options)

    def test_mode_select_reports_current_option(self) -> None:
        self.assertEqual(self._select(get_device_mode=5)[0].current_option, "real_feel")
        self.assertEqual(self._select(get_device_mode=2)[0].current_option, "dehumidification")
        # Heat is not an option on this model, so it shows as unknown.
        self.assertIsNone(self._select(get_device_mode=4)[0].current_option)
        self.assertIsNone(self._select(BASIC, get_device_mode=5)[0].current_option)

    async def test_mode_select_writes_mode_five(self) -> None:
        entity, coordinator = self._select()
        await entity.async_select_option("real_feel")
        coordinator.api.set_device_mode.assert_awaited_once_with("DSN1", 5)

    async def test_mode_select_never_writes_other_values(self) -> None:
        entity, coordinator = self._select(BASIC)
        await entity.async_select_option("real_feel")
        coordinator.api.set_device_mode.assert_not_awaited()
