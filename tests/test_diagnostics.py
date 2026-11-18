"""Tests for the diagnostics download."""
from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
HA_INSTALLED = importlib.util.find_spec("homeassistant") is not None

AC_NAMES = json.loads(
    (_FIXTURES / "ac_el112_properties.json").read_text(encoding="utf-8")
)["properties"]

# Fake identifiers, so the test can check none of them reach the output.
USERNAME = "someone@example.com"
PASSWORD = "hunter2-not-real"
DSN = "AC000W000000001"
MAC = "aa:bb:cc:dd:ee:ff"
SERIAL = "SERIAL-NOT-REAL-123"
HOME_NAME = "Fake Lounge Unit"
LAN_IP = "192.168.77.77"


def _record(name, value):
    return {
        "name": name,
        "base_type": "integer",
        "read_only": name.startswith(("get_", "room_")),
        "direction": "output",
        "display_name": name.replace("_", " ").title(),
        "value": value,
        "data_updated_at": "2026-01-01T00:00:00Z",
        "key": 12345,  # a field the output must not copy
    }


def _coordinator():
    values = {name: 1 for name in AC_NAMES}
    values["cst_mac_address"] = MAC
    values["serial_number"] = SERIAL
    values["outdoor_temp"] = 17
    values["outdoor_Weather_condition"] = "Sunny"
    coordinator = MagicMock()
    coordinator.dsn = DSN
    coordinator.last_update_success = True
    coordinator.available_properties = frozenset(AC_NAMES)
    coordinator.property_records = {n: _record(n, v) for n, v in values.items()}
    coordinator.device_record = {
        "dsn": DSN, "mac": MAC, "lan_ip": LAN_IP, "product_name": HOME_NAME,
        "lat": "-37.8", "lng": "144.9", "key": 99, "unique_hardware_id": "uhid",
        "model": "AY008ESP1", "oem_model": "DL-pac", "connection_status": "Online",
    }
    return coordinator


@skipUnless(HA_INSTALLED, "Home Assistant is not installed")
class DiagnosticsTests(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_ROOT))
        cls.diagnostics = importlib.import_module(
            "custom_components.delonghi_comfort.diagnostics"
        )

    async def _run(self, heaters=()):
        entry = MagicMock()
        entry.entry_id = "entry1"
        entry.data = {"username": USERNAME, "password": PASSWORD, "language": "en-au"}
        entry.options = {"scan_interval": 90}
        entry.runtime_data = SimpleNamespace(
            coordinators=[_coordinator()], heater_coordinators=list(heaters)
        )
        registry_entries = [
            SimpleNamespace(
                domain="sensor", unique_id=f"{DSN}_room_temp", translation_key="room_temperature",
                entity_category=None, disabled_by=None,
            ),
            SimpleNamespace(
                domain="climate", unique_id=f"delonghi_comfort_{DSN}", translation_key=None,
                entity_category=None, disabled_by=None,
            ),
            SimpleNamespace(
                domain="sensor", unique_id="someone_elses_device_room_temp",
                translation_key="room_temperature", entity_category=None, disabled_by=None,
            ),
        ]
        with patch.object(self.diagnostics.er, "async_get", return_value=MagicMock()), patch.object(
            self.diagnostics.er, "async_entries_for_config_entry", return_value=registry_entries
        ):
            return await self.diagnostics.async_get_config_entry_diagnostics(MagicMock(), entry)

    async def test_nothing_identifying_reaches_the_output(self) -> None:
        text = json.dumps(await self._run(), default=str)
        for secret in (USERNAME, PASSWORD, DSN, MAC, SERIAL, HOME_NAME, LAN_IP, "uhid"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, text)

    async def test_account_fields_are_redacted_but_other_settings_stay(self) -> None:
        result = await self._run()
        config = result["config_entry"]
        self.assertEqual(config["data"]["username"], "**REDACTED**")
        self.assertEqual(config["data"]["password"], "**REDACTED**")
        self.assertEqual(config["data"]["language"], "en-au")
        self.assertEqual(config["options"], {"scan_interval": 90})

    async def test_every_property_is_listed_with_its_type_and_label(self) -> None:
        device = (await self._run())["devices"][0]
        self.assertEqual(set(device["properties"]), set(AC_NAMES) | {"outdoor_temp", "outdoor_Weather_condition"})
        room_temp = device["properties"]["room_temp"]
        self.assertEqual(
            set(room_temp),
            {"base_type", "read_only", "direction", "display_name", "value", "data_updated_at"},
        )
        self.assertEqual(room_temp["display_name"], "Room Temp")

    async def test_identifying_and_location_values_are_hidden(self) -> None:
        props = (await self._run())["devices"][0]["properties"]
        for name in ("cst_mac_address", "serial_number", "outdoor_temp", "outdoor_Weather_condition"):
            with self.subTest(name=name):
                self.assertEqual(props[name]["value"], "**REDACTED**")
        self.assertEqual(props["room_temp"]["value"], 1)

    async def test_device_record_keeps_the_model_but_not_the_identity(self) -> None:
        record = (await self._run())["devices"][0]["device_record"]
        self.assertEqual(record["model"], "AY008ESP1")
        self.assertEqual(record["oem_model"], "DL-pac")
        for key in ("dsn", "mac", "lan_ip", "product_name", "lat", "lng", "key"):
            self.assertEqual(record[key], "**REDACTED**", key)

    async def test_only_this_devices_entities_are_listed_with_masked_ids(self) -> None:
        device = (await self._run())["devices"][0]
        ids = [(e["platform"], e["unique_id"]) for e in device["entities"]]
        self.assertEqual(ids, [("climate", "delonghi_comfort_<dsn>"), ("sensor", "<dsn>_room_temp")])

    async def test_capabilities_are_summarised(self) -> None:
        capabilities = (await self._run())["devices"][0]["capabilities"]
        self.assertEqual(
            capabilities,
            {"complete_property_list": True, "myEcoReal Feel": True, "swing": True},
        )

    async def test_heaters_are_included_and_labelled(self) -> None:
        heater = _coordinator()
        heater.dsn = "HT000W000000002"
        heater.device_record = {"dsn": "HT000W000000002", "oem_model": "DL-heater"}
        result = await self._run(heaters=[heater])
        self.assertEqual([d["kind"] for d in result["devices"]], ["air conditioner", "heater"])
        self.assertNotIn("HT000W000000002", json.dumps(result, default=str))
