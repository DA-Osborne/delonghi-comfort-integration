"""Offline tests for the De'Longhi API client."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

import aiohttp

_PACKAGE_NAME = "_delonghi_comfort_test"
_PACKAGE_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "delonghi_comfort"
if _PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(_PACKAGE_NAME)
    package.__path__ = [str(_PACKAGE_DIR)]
    sys.modules[_PACKAGE_NAME] = package

api_module = importlib.import_module(f"{_PACKAGE_NAME}.api")
DeLonghiAPI = api_module.DeLonghiAPI
DeLonghiAPIError = api_module.DeLonghiAPIError
DeLonghiAuthenticationError = api_module.DeLonghiAuthenticationError


class ConsentSignatureTests(IsolatedAsyncioTestCase):
    """Test extraction of consent signatures from server HTML."""

    def test_extracts_supported_declaration_forms(self) -> None:
        cases = (
            "const consentObj2Sig = 'sig-value';",
            'let consentObj2Sig  =  "sig-value";',
            "var consentObj2Sig='sig-value';",
        )
        for html in cases:
            with self.subTest(html=html):
                self.assertEqual(api_module._extract_consent_signature(html), "sig-value")

    def test_missing_signature_returns_none(self) -> None:
        self.assertIsNone(api_module._extract_consent_signature("<html>no signature</html>"))


class DeLonghiAPITests(IsolatedAsyncioTestCase):
    """Test read error handling and property command payloads."""

    def setUp(self) -> None:
        self.api = DeLonghiAPI("unused", "unused", None)
        self.api.access_token = "test-token"

    async def test_empty_device_and_property_lists_are_valid(self) -> None:
        self.api._get_request = AsyncMock(return_value=[])

        self.assertEqual(await self.api.get_devices(), [])
        self.assertEqual(await self.api.get_device_properties("test-dsn"), [])

    async def test_device_read_network_errors_propagate(self) -> None:
        self.api._get_request = AsyncMock(
            side_effect=aiohttp.ClientConnectionError("offline")
        )

        with self.assertRaises(aiohttp.ClientConnectionError):
            await self.api.get_devices()

    async def test_invalid_device_response_shape_raises_api_error(self) -> None:
        self.api._get_request = AsyncMock(return_value={"unexpected": True})

        with self.assertRaises(DeLonghiAPIError):
            await self.api.get_devices()

    async def test_rejected_credentials_raise_authentication_error(self) -> None:
        self.api.access_token = None
        self.api.auth_failure = "invalid_auth"
        self.api.authenticate = AsyncMock(return_value=False)

        with self.assertRaises(DeLonghiAuthenticationError):
            await self.api.get_devices()

    async def test_silent_mode_off_sends_boolean_false(self) -> None:
        self.api._post_request = AsyncMock(return_value={"accepted": True})

        self.assertTrue(await self.api.set_silent_mode("test-dsn", 0))
        self.api._post_request.assert_awaited_once_with(
            "apiv1/dsns/test-dsn/properties/set_silent_function/datapoints.json",
            {"datapoint": {"value": 0}},
        )