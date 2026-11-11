"""Print one De'Longhi device record and its raw property responses."""

from __future__ import annotations

import asyncio
import getpass
import importlib
import json
import logging
import sys
import types
from pathlib import Path
from typing import Any

import aiohttp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = PROJECT_ROOT / "custom_components" / "delonghi_comfort"
PACKAGE_NAME = "_delonghi_inspector"
SENSITIVE_KEY_PARTS = ("token", "secret", "password", "signature", "authorization")

package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(PACKAGE_DIR)]
sys.modules[PACKAGE_NAME] = package
api_module = importlib.import_module(f"{PACKAGE_NAME}.api")


def redact_sensitive(value: Any) -> Any:
    """Redact values under keys that commonly contain authentication secrets."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if any(part in str(key).lower() for part in SENSITIVE_KEY_PARTS)
            else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


def device_info(device: dict[str, Any]) -> dict[str, Any]:
    """Return the nested device record when the API wraps it."""
    nested = device.get("device")
    return nested if isinstance(nested, dict) else device


async def main() -> None:
    logging.getLogger(PACKAGE_NAME).setLevel(logging.CRITICAL)
    username = input("De'Longhi account email: ").strip()
    password = getpass.getpass("De'Longhi account password (not echoed): ")
    language = input("Account language [en-au]: ").strip() or "en-au"

    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        api = api_module.DeLonghiAPI(username, password, session, language)
        if not await api.authenticate():
            print(f"Authentication failed ({api.auth_failure or 'unknown reason'}).")
            return

        try:
            devices = await api.get_devices()
        except Exception as err:
            print(f"Device-list request failed ({type(err).__name__}).")
            return

        if not devices:
            print("The account returned no devices.")
            return

        print(f"Devices found: {len(devices)}")
        for index, device in enumerate(devices):
            info = device_info(device)
            label = info.get("product_name") or info.get("model") or "De'Longhi device"
            print(
                f"[{index}] {label} "
                f"DSN={info.get('dsn', '<unknown>')} "
                f"model={info.get('model', '<unknown>')}"
            )

        selection = input("Device index to inspect [0]: ").strip() or "0"
        try:
            selected = devices[int(selection)]
        except (ValueError, IndexError):
            print("Invalid device index.")
            return

        info = device_info(selected)
        dsn = info.get("dsn")
        if not dsn:
            print("Selected device record has no DSN; saving the record without properties.")
            properties = []
        else:
            try:
                properties = await api.get_device_properties(str(dsn))
            except Exception as err:
                print(f"Property request failed ({type(err).__name__}).")
                return

        try:
            output_path = Path(__file__).resolve().with_name("delonghi_device_dump.json")
            output_path.write_text(
                json.dumps(
                    redact_sensitive(
                        {"device": selected, "properties": properties}
                    ),
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError as err:
            print(f"Could not write JSON file ({type(err).__name__}).")
            return

    print(f"Property records returned: {len(properties)}")
    print(f"JSON saved to: {output_path}")
    print("Review device identifiers and property values before sharing the file.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (aiohttp.ClientError, TimeoutError) as err:
        print(f"Request failed ({type(err).__name__}).")