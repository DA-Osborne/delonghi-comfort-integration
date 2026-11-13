"""Decode and encode the weekly schedule stored on the unit.

The cloud holds the schedule in two strings. The format was worked out from
schedules created in the De'Longhi Comfort app and is documented in
docs/device-properties.md. In short:

* ``weeklyschedule_calendar`` has one character per quarter hour of the week
  (7 days of 96, Monday first). ``A`` means nothing is scheduled. Any other
  character is a reference to a settings record.
* ``weeklyschedule_setpoints`` is a table of 32 settings records of 12 bits each,
  stored as base64. A calendar character's index in the base64 alphabet, minus 1,
  is the record number.
* A record holds swing, silent, temperature, fan speed and mode.

There is no power field: the unit is on during scheduled times and off outside
them. In tests the unit applied the mode, fan speed and swing of a record but not
its temperature or silent setting.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Iterable

SLOTS_PER_DAY = 96
SLOT_MINUTES = 15
DAYS_PER_WEEK = 7
CALENDAR_LENGTH = SLOTS_PER_DAY * DAYS_PER_WEEK
RECORD_BITS = 12
RECORD_COUNT = 32
TABLE_BYTES = RECORD_BITS * RECORD_COUNT // 8
SETPOINTS_LENGTH = (TABLE_BYTES // 3) * 4

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MODES = ("cool", "dry", "fan", "real_feel")
FAN_SPEEDS = ("auto", "low", "medium", "high")
MIN_TEMPERATURE = 18
MAX_TEMPERATURE = 33

_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
NO_SCHEDULE = "A"


class ScheduleError(ValueError):
    """The schedule strings or a requested schedule are not valid."""


@dataclass(frozen=True)
class ScheduleSettings:
    """What the unit does while a schedule slot is running."""

    mode: str = "cool"
    temperature: int = 20
    fan: str = "low"
    swing: bool = False
    silent: bool = False


@dataclass(frozen=True)
class ScheduleBlock:
    """One run of quarter hours on one day, with the same settings."""

    day: int  # 0 = Monday
    start: int  # minutes after midnight
    end: int  # minutes after midnight; 1440 means the end of the day
    settings: ScheduleSettings


def format_time(minutes: int) -> str:
    """Return minutes after midnight as HH:MM (1440 gives 24:00)."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ---- one settings record -------------------------------------------------------


def encode_settings(settings: ScheduleSettings) -> int:
    """Return the 12-bit record for the given settings."""
    if settings.mode not in MODES:
        raise ScheduleError(f"Unknown mode {settings.mode!r}")
    if settings.fan not in FAN_SPEEDS:
        raise ScheduleError(f"Unknown fan speed {settings.fan!r}")
    if not MIN_TEMPERATURE <= settings.temperature <= MAX_TEMPERATURE:
        raise ScheduleError(
            f"Temperature must be {MIN_TEMPERATURE} to {MAX_TEMPERATURE}"
        )
    return (
        (int(settings.swing) << 11)
        | (int(settings.silent) << 10)
        | ((settings.temperature - MIN_TEMPERATURE) << 6)
        | (FAN_SPEEDS.index(settings.fan) << 2)
        | MODES.index(settings.mode)
    )


def decode_settings(record: int) -> ScheduleSettings:
    """Return the settings held in a 12-bit record."""
    return ScheduleSettings(
        mode=MODES[record & 0b11],
        temperature=MIN_TEMPERATURE + ((record >> 6) & 0b1111),
        fan=FAN_SPEEDS[(record >> 2) & 0b11],
        swing=bool((record >> 11) & 1),
        silent=bool((record >> 10) & 1),
    )


# ---- the settings table --------------------------------------------------------


def decode_records(setpoints: str) -> list[int]:
    """Split the base64 setpoints string into its 32 records."""
    try:
        raw = base64.b64decode(setpoints, validate=True)
    except (ValueError, TypeError) as err:
        raise ScheduleError("Setpoints are not valid base64") from err
    if len(raw) != TABLE_BYTES:
        raise ScheduleError(
            f"Setpoints hold {len(raw)} bytes, expected {TABLE_BYTES}"
        )
    bits = int.from_bytes(raw, "big")
    total = TABLE_BYTES * 8
    return [
        (bits >> (total - RECORD_BITS * (index + 1))) & 0xFFF
        for index in range(RECORD_COUNT)
    ]


def encode_records(records: Iterable[int]) -> str:
    """Build the base64 setpoints string from up to 32 records."""
    records = list(records)
    if len(records) > RECORD_COUNT:
        raise ScheduleError(f"At most {RECORD_COUNT} different settings fit")
    bits = 0
    total = TABLE_BYTES * 8
    for index, record in enumerate(records):
        if not 0 <= record <= 0xFFF:
            raise ScheduleError("A record is 12 bits")
        bits |= record << (total - RECORD_BITS * (index + 1))
    return base64.b64encode(bits.to_bytes(TABLE_BYTES, "big")).decode("ascii")


# ---- the whole schedule --------------------------------------------------------


def decode_schedule(calendar: str, setpoints: str) -> list[ScheduleBlock]:
    """Return the schedule blocks the two strings describe, in week order.

    Settings records that no calendar slot refers to are ignored: the app leaves
    the records of deleted schedules in the table.
    """
    if len(calendar) != CALENDAR_LENGTH:
        raise ScheduleError(
            f"Calendar has {len(calendar)} characters, expected {CALENDAR_LENGTH}"
        )
    records = decode_records(setpoints)

    blocks: list[ScheduleBlock] = []
    for day in range(DAYS_PER_WEEK):
        row = calendar[day * SLOTS_PER_DAY : (day + 1) * SLOTS_PER_DAY]
        slot = 0
        while slot < SLOTS_PER_DAY:
            letter = row[slot]
            if letter == NO_SCHEDULE:
                slot += 1
                continue
            end = slot
            while end < SLOTS_PER_DAY and row[end] == letter:
                end += 1
            index = _ALPHABET.find(letter) - 1
            if index < 0 or index >= RECORD_COUNT:
                raise ScheduleError(f"Calendar character {letter!r} is not a record")
            blocks.append(
                ScheduleBlock(
                    day=day,
                    start=slot * SLOT_MINUTES,
                    end=end * SLOT_MINUTES,
                    settings=decode_settings(records[index]),
                )
            )
            slot = end
    return blocks


def encode_schedule(blocks: Iterable[ScheduleBlock]) -> tuple[str, str]:
    """Return the (calendar, setpoints) strings for the given blocks.

    Blocks with identical settings share one record and one calendar letter, as the
    app does. Start and end times are rounded outward to whole quarter hours.
    """
    records: list[int] = []
    calendar = [NO_SCHEDULE] * CALENDAR_LENGTH

    for block in blocks:
        if not 0 <= block.day < DAYS_PER_WEEK:
            raise ScheduleError("Day must be 0 (Monday) to 6 (Sunday)")
        if not 0 <= block.start < block.end <= 24 * 60:
            raise ScheduleError("A block must start before it ends, within one day")
        record = encode_settings(block.settings)
        if record not in records:
            records.append(record)
            if len(records) > RECORD_COUNT:
                raise ScheduleError(
                    f"At most {RECORD_COUNT} different settings fit"
                )
        letter = _ALPHABET[records.index(record) + 1]

        first = block.start // SLOT_MINUTES
        last = -(-block.end // SLOT_MINUTES)  # round up
        for slot in range(first, last):
            position = block.day * SLOTS_PER_DAY + slot
            if calendar[position] != NO_SCHEDULE:
                raise ScheduleError(
                    f"Blocks overlap on {DAY_NAMES[block.day]} at "
                    f"{format_time(slot * SLOT_MINUTES)}"
                )
            calendar[position] = letter

    return "".join(calendar), encode_records(records)


def group_blocks(blocks: Iterable[ScheduleBlock]) -> list[dict]:
    """Merge blocks that repeat on several days into one entry for display."""
    groups: dict[tuple, list[int]] = {}
    for block in blocks:
        groups.setdefault((block.start, block.end, block.settings), []).append(block.day)

    result = []
    for (start, end, settings), days in sorted(
        groups.items(), key=lambda item: (min(item[1]), item[0][0])
    ):
        entry: dict = {
            "days": [DAY_NAMES[day] for day in sorted(days)],
            "start": format_time(start),
            "end": format_time(end),
            "mode": settings.mode,
            "swing": settings.swing,
            "silent": settings.silent,
        }
        # Dehumidify and Real Feel have no temperature; only cool has one.
        if settings.mode == "cool":
            entry["temperature"] = settings.temperature
        # Fan speed applies in cool and fan modes only.
        if settings.mode in ("cool", "fan"):
            entry["fan"] = settings.fan
        result.append(entry)
    return result
