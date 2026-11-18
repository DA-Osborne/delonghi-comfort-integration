"""Show which device properties differ between two inspector dumps.

Usage: python scripts/compare_dumps.py BEFORE AFTER [--all]

BEFORE and AFTER are labels (as passed to inspect_device.py --label) or file
names inside the scripts folder. Timestamps are hidden unless --all is given.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
TIMESTAMP_FIELDS = ("data_updated_at", "generated_at", "updated_at")


def resolve(name: str) -> Path:
    candidates = (
        Path(name),
        SCRIPTS_DIR / name,
        SCRIPTS_DIR / f"delonghi_device_dump_{name}.json",
    )
    for path in candidates:
        if path.is_file():
            return path
    raise SystemExit(f"Dump not found for '{name}'.")


def load_properties(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    properties: dict[str, dict[str, Any]] = {}
    for record in data.get("properties", []):
        record = record.get("property", record)
        if isinstance(record, dict) and "name" in record:
            properties[record["name"]] = record
    return properties


def show(value: Any, limit: int = 160) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return text if len(text) <= limit else text[:limit] + "..."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--all", action="store_true", help="Include timestamp changes.")
    args = parser.parse_args()

    before = load_properties(resolve(args.before))
    after = load_properties(resolve(args.after))

    changed = False
    for name in sorted(set(before) | set(after)):
        old, new = before.get(name), after.get(name)
        if old is None or new is None:
            print(f"{name}: {'added' if old is None else 'removed'}")
            changed = True
            continue
        fields = sorted(set(old) | set(new))
        diffs = [
            f
            for f in fields
            if old.get(f) != new.get(f) and (args.all or f not in TIMESTAMP_FIELDS)
        ]
        if not diffs:
            continue
        changed = True
        print(name)
        for field in diffs:
            print(f"  {field}: {show(old.get(field))!r} -> {show(new.get(field))!r}")
    if not changed:
        print("No differences.")


if __name__ == "__main__":
    main()
