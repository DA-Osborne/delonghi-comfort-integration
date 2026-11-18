"""Silent mode only works while the unit is cooling.

Measured on the unit: a silent command is accepted and echoed back in cooling mode, and
ignored without any echo in dehumidify, fan and Real Feel mode. Switching to any of
those modes clears silent mode, and switching back to cooling does not restore it.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase, skipUnless
from unittest.mock import AsyncMock, MagicMock

_ROOT = Path(__file__).resolve().parents[1]
HA_INSTALLED = importlib.util.find_spec("homeassistant") is not None

COOL, DRY, FAN, REAL_FEEL = 1, 2, 3, 5


def _data(status=1, mode=COOL, silent=0):
    return {"get_device_status": status, "get_device_mode": mode, "get_silent_function": silent}


@skipUnless(HA_INSTALLED, "Home Assistant is not installed")
class SilentModeTests(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_ROOT))
        cls.coordinator_module = importlib.import_module(
            "custom_components.delonghi_comfort.coordinator"
        )
        cls.switch = importlib.import_module("custom_components.delonghi_comfort.switch")
        from homeassistant.exceptions import HomeAssistantError

        cls.HomeAssistantError = HomeAssistantError

    # ---- the rule ---------------------------------------------------------------
    def test_available_only_when_on_and_cooling(self) -> None:
        available = self.coordinator_module.silent_mode_available
        self.assertTrue(available(_data(1, COOL)))
        for status, mode in ((1, DRY), (1, FAN), (1, REAL_FEEL), (1, 4), (2, COOL), (2, DRY)):
            with self.subTest(status=status, mode=mode):
                self.assertFalse(available(_data(status, mode)))
        self.assertFalse(available({}))

    def test_a_silent_command_is_moot_outside_cooling_and_nothing_else_is(self) -> None:
        moot = self.coordinator_module.command_is_moot
        self.assertTrue(moot("get_silent_function", _data(1, DRY)))
        self.assertFalse(moot("get_silent_function", _data(1, COOL)))
        for key in ("get_device_status", "get_device_mode", "get_swing_function"):
            with self.subTest(key=key):
                self.assertFalse(moot(key, _data(1, DRY)))

    # ---- the switch -------------------------------------------------------------------
    def _switch(self, data):
        coordinator = MagicMock()
        coordinator.dsn = "DSN1"
        coordinator.data = dict(data)
        coordinator.last_update_success = True
        coordinator.available_properties = frozenset(data)
        coordinator.api.set_silent_mode = AsyncMock(return_value=True)
        coordinator.is_property_pending = lambda key: False
        coordinator.get_device_info = lambda: {}
        description = next(
            d for d in self.switch.SWITCH_DESCRIPTIONS if d.key == "get_silent_function"
        )
        return self.switch.DeLonghiSwitch(coordinator, description), coordinator

    def test_switch_is_unavailable_outside_cooling(self) -> None:
        for mode, expected in ((COOL, True), (DRY, False), (FAN, False), (REAL_FEEL, False)):
            with self.subTest(mode=mode):
                self.assertEqual(self._switch(_data(1, mode))[0].available, expected)
        self.assertFalse(self._switch(_data(2, COOL))[0].available)

    def test_switch_waits_while_a_mode_or_power_change_is_unconfirmed(self) -> None:
        for pending in ("get_device_status", "get_device_mode"):
            with self.subTest(pending=pending):
                entity, coordinator = self._switch(_data(1, COOL))
                coordinator.is_property_pending = lambda key, p=pending: key == p
                self.assertFalse(entity.available)

    async def test_turning_on_while_cooling_writes_and_holds_the_value(self) -> None:
        entity, coordinator = self._switch(_data(1, COOL))
        await entity.async_turn_on()
        coordinator.api.set_silent_mode.assert_awaited_once_with("DSN1", 1)
        coordinator.set_optimistic_value.assert_called_once_with("get_silent_function", 1)

    async def test_turning_off_while_cooling(self) -> None:
        entity, coordinator = self._switch(_data(1, COOL, silent=1))
        await entity.async_turn_off()
        coordinator.api.set_silent_mode.assert_awaited_once_with("DSN1", 0)
        coordinator.set_optimistic_value.assert_called_once_with("get_silent_function", 0)

    async def test_commands_outside_cooling_are_refused_and_nothing_is_sent_or_shown(self) -> None:
        for mode in (DRY, FAN, REAL_FEEL):
            for action in ("async_turn_on", "async_turn_off"):
                with self.subTest(mode=mode, action=action):
                    entity, coordinator = self._switch(_data(1, mode))
                    with self.assertRaises(self.HomeAssistantError) as raised:
                        await getattr(entity, action)()
                    self.assertIn("cooling", str(raised.exception))
                    coordinator.api.set_silent_mode.assert_not_awaited()
                    coordinator.set_optimistic_value.assert_not_called()

    def test_the_power_switch_is_not_affected(self) -> None:
        coordinator = MagicMock()
        coordinator.data = _data(1, DRY)
        coordinator.last_update_success = True
        coordinator.get_device_info = lambda: {}
        description = next(
            d for d in self.switch.SWITCH_DESCRIPTIONS if d.key == "get_device_status"
        )
        self.assertTrue(self.switch.DeLonghiSwitch(coordinator, description).available)

    # ---- the stale "on" that was seen in Home Assistant ----------------------------------
    async def test_a_pending_silent_command_is_dropped_when_the_mode_changes(self) -> None:
        """Silent was commanded on, then the unit changed to dehumidify (clearing it).

        Before the fix the commanded "on" stayed on screen for up to 90 seconds, so
        switching back to cooling showed silent on while the unit had it off.
        """
        coordinator_class = self.coordinator_module.DeLonghiCoordinator
        coordinator = coordinator_class.__new__(coordinator_class)
        coordinator.dsn = "DSN1"
        coordinator.async_update_listeners = MagicMock()
        coordinator.data = _data(1, COOL, silent=0)
        coordinator.available_properties = frozenset()
        coordinator.property_records = {}
        coordinator._pending_commands = {
            "get_silent_function": (1, 0, 10**12),  # waiting, far from timing out
        }

        def record(name, value):
            return {"property": {"name": name, "value": value}}

        # The unit now reports dehumidify, with silent cleared.
        coordinator.api = MagicMock()
        coordinator.api.get_device_properties = AsyncMock(
            return_value=[
                record("get_device_status", 1),
                record("get_device_mode", DRY),
                record("get_silent_function", 0),
            ]
        )
        data = await coordinator._async_update_data()
        self.assertEqual(data["get_silent_function"], 0)
        self.assertNotIn("get_silent_function", coordinator._pending_commands)

    async def test_a_pending_silent_command_is_still_held_while_cooling(self) -> None:
        coordinator_class = self.coordinator_module.DeLonghiCoordinator
        coordinator = coordinator_class.__new__(coordinator_class)
        coordinator.dsn = "DSN1"
        coordinator.async_update_listeners = MagicMock()
        coordinator.data = _data(1, COOL, silent=0)
        coordinator.available_properties = frozenset()
        coordinator.property_records = {}
        coordinator._pending_commands = {"get_silent_function": (1, 0, 10**12)}
        coordinator.api = MagicMock()
        coordinator.api.get_device_properties = AsyncMock(
            return_value=[
                {"property": {"name": "get_device_status", "value": 1}},
                {"property": {"name": "get_device_mode", "value": COOL}},
                {"property": {"name": "get_silent_function", "value": 0}},
            ]
        )
        data = await coordinator._async_update_data()
        # Still cooling and not yet confirmed, so the commanded value stays on screen.
        self.assertEqual(data["get_silent_function"], 1)
        self.assertIn("get_silent_function", coordinator._pending_commands)
