"""Tests for the config flow, reauthentication and the options flow.

These call the flow classes directly with mocks (Home Assistant's pytest harness does
not run on Windows). The parts of Home Assistant a flow leans on, such as creating
the entry, are replaced so the tests check this integration's own decisions.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import AsyncMock, MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
HA_INSTALLED = importlib.util.find_spec("homeassistant") is not None

USER_INPUT = {"username": "someone@example.com", "password": "secret", "language": "en-au"}


def _api(authenticated=True, failure=None, devices=None):
    api = MagicMock()
    api.authenticate = AsyncMock(return_value=authenticated)
    api.auth_failure = failure
    api.get_devices = AsyncMock(
        return_value=[{"device": {"dsn": "X"}}] if devices is None else devices
    )
    return api


@skipUnless(HA_INSTALLED, "Home Assistant is not installed")
class ConfigFlowTests(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_ROOT))
        cls.module = importlib.import_module("custom_components.delonghi_comfort.config_flow")
        cls.api_module = importlib.import_module("custom_components.delonghi_comfort.api")

    def _flow(self, api):
        flow = self.module.DelonghiComfortConfigFlow()
        flow.hass = MagicMock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(side_effect=lambda **kw: {"type": "create_entry", **kw})
        flow.async_show_form = MagicMock(side_effect=lambda **kw: {"type": "form", **kw})
        patches = (
            patch.object(self.module, "DeLonghiAPI", return_value=api),
            patch.object(self.module, "async_get_clientsession", return_value=MagicMock()),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return flow

    # ---- first setup --------------------------------------------------------
    async def test_valid_account_creates_an_entry(self) -> None:
        flow = self._flow(_api())
        result = await flow.async_step_user(USER_INPUT)
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"], USER_INPUT)
        self.assertEqual(result["title"], "De'Longhi Comfort (someone@example.com)")
        flow.async_set_unique_id.assert_awaited_once_with("someone@example.com")
        flow._abort_if_unique_id_configured.assert_called_once()

    async def test_first_visit_shows_the_form(self) -> None:
        result = await self._flow(_api()).async_step_user(None)
        self.assertEqual((result["type"], result["step_id"]), ("form", "user"))
        self.assertEqual(result["errors"], {})

    async def test_rejected_password(self) -> None:
        flow = self._flow(_api(authenticated=False, failure="invalid_auth"))
        result = await flow.async_step_user(USER_INPUT)
        self.assertEqual(result["errors"], {"base": "invalid_auth"})
        flow.async_create_entry.assert_not_called()

    async def test_any_other_login_failure_is_a_connection_problem(self) -> None:
        flow = self._flow(_api(authenticated=False, failure="network"))
        self.assertEqual((await flow.async_step_user(USER_INPUT))["errors"], {"base": "cannot_connect"})

    async def test_account_without_devices(self) -> None:
        flow = self._flow(_api(devices=[]))
        self.assertEqual((await flow.async_step_user(USER_INPUT))["errors"], {"base": "no_devices"})
        flow.async_create_entry.assert_not_called()

    async def test_unexpected_error_does_not_escape(self) -> None:
        api = _api()
        api.get_devices = AsyncMock(side_effect=RuntimeError("boom"))
        flow = self._flow(api)
        self.assertEqual((await flow.async_step_user(USER_INPUT))["errors"], {"base": "cannot_connect"})

    async def test_language_defaults_when_omitted(self) -> None:
        flow = self._flow(_api())
        result = await flow.async_step_user({"username": "a@b.c", "password": "p"})
        self.assertEqual(result["data"]["language"], "en")

    def test_form_offers_only_known_languages(self) -> None:
        schema = self._flow(_api())._get_schema()
        language = next(k for k in schema.schema if k == "language")
        validator = schema.schema[language]
        validator("en-au")
        with self.assertRaises(Exception):
            validator("klingon")

    # ---- reauthentication -----------------------------------------------------
    def _reauth(self, api):
        flow = self._flow(api)
        entry = MagicMock()
        entry.data = dict(USER_INPUT)
        flow._get_reauth_entry = MagicMock(return_value=entry)
        flow.async_update_reload_and_abort = MagicMock(
            side_effect=lambda e, **kw: {"type": "abort", "reason": "reauth_successful", **kw}
        )
        return flow, entry

    async def test_reauth_starts_on_the_password_form(self) -> None:
        flow, _ = self._reauth(_api())
        result = await flow.async_step_reauth(dict(USER_INPUT))
        self.assertEqual((result["type"], result["step_id"]), ("form", "reauth_confirm"))

    async def test_reauth_saves_only_the_new_password(self) -> None:
        flow, entry = self._reauth(_api())
        result = await flow.async_step_reauth_confirm({"password": "new"})
        self.assertEqual(result["reason"], "reauth_successful")
        self.assertEqual(result["data_updates"], {"password": "new"})
        flow.async_update_reload_and_abort.assert_called_once()
        self.assertIs(flow.async_update_reload_and_abort.call_args.args[0], entry)

    async def test_reauth_checks_the_new_password_with_the_stored_username(self) -> None:
        flow, _ = self._reauth(_api())
        await flow.async_step_reauth_confirm({"password": "new"})
        args = self.module.DeLonghiAPI.call_args.args
        self.assertEqual((args[0], args[1], args[3]), ("someone@example.com", "new", "en-au"))

    async def test_reauth_wrong_password_asks_again_and_saves_nothing(self) -> None:
        flow, _ = self._reauth(_api(authenticated=False, failure="invalid_auth"))
        result = await flow.async_step_reauth_confirm({"password": "wrong"})
        self.assertEqual(result["errors"], {"base": "invalid_auth"})
        flow.async_update_reload_and_abort.assert_not_called()

    async def test_reauth_rejected_while_listing_devices(self) -> None:
        api = _api()
        api.get_devices = AsyncMock(side_effect=self.api_module.DeLonghiAuthenticationError("no"))
        flow, _ = self._reauth(api)
        self.assertEqual((await flow.async_step_reauth_confirm({"password": "x"}))["errors"], {"base": "invalid_auth"})

    async def test_reauth_with_no_devices(self) -> None:
        flow, _ = self._reauth(_api(devices=[]))
        self.assertEqual((await flow.async_step_reauth_confirm({"password": "x"}))["errors"], {"base": "no_devices"})

    async def test_reauth_unexpected_error(self) -> None:
        api = _api()
        api.authenticate = AsyncMock(side_effect=RuntimeError("boom"))
        flow, _ = self._reauth(api)
        self.assertEqual((await flow.async_step_reauth_confirm({"password": "x"}))["errors"], {"base": "cannot_connect"})


@skipUnless(HA_INSTALLED, "Home Assistant is not installed")
class OptionsFlowTests(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_ROOT))
        cls.module = importlib.import_module("custom_components.delonghi_comfort.config_flow")

    def _flow(self, options=None):
        entry = MagicMock()
        entry.options = options or {}
        # The flow is built the way Home Assistant builds it.
        flow = self.module.DelonghiComfortConfigFlow.async_get_options_flow(entry)
        flow.hass = MagicMock()
        flow.hass.config_entries.async_get_known_entry.return_value = entry
        flow.handler = "entry-id"
        flow.async_show_form = MagicMock(side_effect=lambda **kw: {"type": "form", **kw})
        flow.async_create_entry = MagicMock(side_effect=lambda **kw: {"type": "create_entry", **kw})
        return flow

    def test_the_flow_can_be_created_and_finds_its_entry(self) -> None:
        # Assigning config_entry used to raise on current Home Assistant, so the
        # options page could not open.
        flow = self._flow()
        self.assertIsNotNone(flow.config_entry)

    async def test_form_default_is_the_saved_interval(self) -> None:
        result = await self._flow({"scan_interval": 120}).async_step_init(None)
        key = next(k for k in result["data_schema"].schema if k == "scan_interval")
        self.assertEqual(key.default(), 120)

    async def test_form_default_without_a_saved_interval(self) -> None:
        result = await self._flow().async_step_init(None)
        key = next(k for k in result["data_schema"].schema if k == "scan_interval")
        self.assertEqual(key.default(), 60)

    async def test_an_interval_saved_before_the_limits_existed_is_clamped(self) -> None:
        for saved, expected in ((5, 30), (9999, 300)):
            with self.subTest(saved=saved):
                result = await self._flow({"scan_interval": saved}).async_step_init(None)
                key = next(k for k in result["data_schema"].schema if k == "scan_interval")
                self.assertEqual(key.default(), expected)

    async def test_the_form_refuses_values_outside_the_limits(self) -> None:
        result = await self._flow().async_step_init(None)
        validator = result["data_schema"]
        validator({"scan_interval": 30})
        validator({"scan_interval": 300})
        for bad in (29, 301):
            with self.subTest(bad=bad), self.assertRaises(Exception):
                validator({"scan_interval": bad})

    async def test_submitting_saves_the_options(self) -> None:
        result = await self._flow().async_step_init({"scan_interval": 90})
        self.assertEqual((result["type"], result["data"]), ("create_entry", {"scan_interval": 90}))
