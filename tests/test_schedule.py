"""Offline tests for the weekly schedule codec."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import types
from unittest import TestCase

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_DIR = _ROOT / "custom_components" / "delonghi_comfort"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_PACKAGE_NAME = "_delonghi_comfort_test"

if _PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(_PACKAGE_NAME)
    package.__path__ = [str(_PACKAGE_DIR)]
    sys.modules[_PACKAGE_NAME] = package
schedule = importlib.import_module(f"{_PACKAGE_NAME}.schedule")

Settings = schedule.ScheduleSettings
Block = schedule.ScheduleBlock
UPLOAD = json.loads((_FIXTURES / "schedule_app_upload.json").read_text(encoding="utf-8"))


def hm(text: str) -> int:
    hours, minutes = text.split(":")
    return int(hours) * 60 + int(minutes)


# The 15 records the app produced, as (settings, value). They come from schedules
# entered in the app one setting at a time. The unit ran schedules built from these.
KNOWN_RECORDS = [
    (Settings("cool", 20, "low", True, True), 0xC84),
    (Settings("real_feel", 20, "low", True, False), 0x887),
    (Settings("dry", 20, "low", False, True), 0x485),
    (Settings("cool", 24, "low"), 0x184),
    (Settings("cool", 25, "low"), 0x1C4),
    (Settings("cool", 18, "low"), 0x004),
    (Settings("cool", 32, "low"), 0x384),
    (Settings("cool", 24, "medium"), 0x188),
    (Settings("cool", 24, "high"), 0x18C),
    (Settings("cool", 24, "low", True, False), 0x984),
    (Settings("cool", 24, "low", False, True), 0x584),
    (Settings("dry", 20, "low"), 0x085),
    (Settings("fan", 20, "low"), 0x086),
    (Settings("fan", 20, "high"), 0x08E),
    (Settings("real_feel", 20, "low"), 0x087),
]


class SettingsRecordTests(TestCase):
    def test_encoder_reproduces_every_record_the_app_produced(self) -> None:
        for settings, value in KNOWN_RECORDS:
            with self.subTest(settings=settings):
                self.assertEqual(schedule.encode_settings(settings), value)

    def test_decoder_reverses_the_encoder(self) -> None:
        for settings, value in KNOWN_RECORDS:
            with self.subTest(value=hex(value)):
                self.assertEqual(schedule.decode_settings(value), settings)

    def test_invalid_settings_are_rejected(self) -> None:
        for bad in (
            Settings(mode="heat"),
            Settings(fan="turbo"),
            Settings(temperature=17),
            Settings(temperature=34),
        ):
            with self.subTest(bad=bad), self.assertRaises(schedule.ScheduleError):
                schedule.encode_settings(bad)


class TableTests(TestCase):
    def test_table_round_trip(self) -> None:
        records = [value for _, value in KNOWN_RECORDS]
        text = schedule.encode_records(records)
        self.assertEqual(len(text), 64)
        decoded = schedule.decode_records(text)
        self.assertEqual(decoded[: len(records)], records)
        self.assertEqual(decoded[len(records) :], [0] * (32 - len(records)))

    def test_the_apps_own_table_decodes_to_the_known_records(self) -> None:
        decoded = schedule.decode_records(UPLOAD["setpoints"])
        self.assertEqual(decoded[:15], [value for _, value in KNOWN_RECORDS])
        self.assertEqual(decoded[15:], [0] * 17)

    def test_bad_tables_are_rejected(self) -> None:
        for bad in ("not base64!!", "AAAA", "A" * 60):
            with self.subTest(bad=bad), self.assertRaises(schedule.ScheduleError):
                schedule.decode_records(bad)

    def test_a_record_over_twelve_bits_or_a_33rd_record_is_rejected(self) -> None:
        with self.assertRaises(schedule.ScheduleError):
            schedule.encode_records([0x1000])
        with self.assertRaises(schedule.ScheduleError):
            schedule.encode_records([0] * 33)


class AppUploadTests(TestCase):
    """The strings the iPad app uploaded for 14 schedules."""

    def setUp(self) -> None:
        self.blocks = schedule.decode_schedule(UPLOAD["calendar"], UPLOAD["setpoints"])

    def test_blocks_match_what_was_entered_in_the_app(self) -> None:
        expected = [
            (1, "01:00", "02:00", Settings("cool", 24, "low")),
            (1, "02:00", "03:00", Settings("cool", 25, "low")),
            (1, "03:00", "04:00", Settings("cool", 18, "low")),
            (1, "04:00", "05:00", Settings("cool", 32, "low")),
            (1, "05:00", "06:00", Settings("cool", 24, "medium")),
            (1, "06:00", "07:00", Settings("cool", 24, "high")),
            (1, "07:00", "08:00", Settings("cool", 24, "low", True, False)),
            (1, "08:00", "09:00", Settings("cool", 24, "low", False, True)),
            (1, "09:00", "10:00", Settings("dry", 20, "low")),
            (1, "10:00", "11:00", Settings("fan", 20, "low")),
            (1, "11:00", "12:00", Settings("fan", 20, "high")),
            (1, "12:00", "13:00", Settings("real_feel", 20, "low")),
            # row 13: Tuesday 23:00 to "23:59", which fills through midnight
            (1, "23:00", "24:00", Settings("cool", 24, "low")),
            # row 14: Wednesday 00:00 to 01:00
            (2, "00:00", "01:00", Settings("cool", 24, "low")),
        ]
        actual = [
            (b.day, schedule.format_time(b.start), schedule.format_time(b.end), b.settings)
            for b in self.blocks
        ]
        self.assertEqual(actual, expected)

    def test_identical_settings_shared_one_letter(self) -> None:
        # Rows 1, 13 and 14 have the same settings, so the app gave them all 'E'.
        calendar = UPLOAD["calendar"]
        self.assertEqual(calendar[1 * 96 + 4], "E")
        self.assertEqual(calendar[1 * 96 + 92], "E")
        self.assertEqual(calendar[2 * 96], "E")

    def test_decode_then_encode_describes_the_same_schedule(self) -> None:
        calendar, setpoints = schedule.encode_schedule(self.blocks)
        self.assertEqual(schedule.decode_schedule(calendar, setpoints), self.blocks)

    def test_encoding_reuses_records_for_identical_settings(self) -> None:
        _, setpoints = schedule.encode_schedule(self.blocks)
        used = [r for r in schedule.decode_records(setpoints) if r]
        # 14 blocks, but rows 13 and 14 repeat row 1, so 12 distinct records.
        self.assertEqual(len(used), 12)


class StringsTheUnitRanTests(TestCase):
    """Hand-built strings that were written to the unit and run by it."""

    def test_wednesday_test_schedule(self) -> None:
        calendar, setpoints = schedule.encode_schedule(
            [Block(2, hm("03:00"), hm("03:30"), Settings("cool", 22, "low"))]
        )
        self.assertEqual([i for i, c in enumerate(calendar) if c != "A"], [204, 205])
        self.assertEqual(set(calendar) - {"A"}, {"B"})
        self.assertEqual(setpoints, "EE" + "A" * 62)

    def test_friday_live_schedule(self) -> None:
        # Written at 15:01 and run by the unit at 15:30 on 13 Nov.
        calendar, setpoints = schedule.encode_schedule(
            [Block(4, hm("15:30"), hm("16:00"), Settings("cool", 21, "medium", False, True))]
        )
        self.assertEqual([i for i, c in enumerate(calendar) if c != "A"], [446, 447])
        self.assertEqual(setpoints, "TI" + "A" * 62)


class EncodeRulesTests(TestCase):
    def test_empty_schedule(self) -> None:
        calendar, setpoints = schedule.encode_schedule([])
        self.assertEqual(calendar, "A" * 672)
        self.assertEqual(setpoints, "A" * 64)
        self.assertEqual(schedule.decode_schedule(calendar, setpoints), [])

    def test_end_times_round_up_to_the_next_quarter_hour(self) -> None:
        calendar, _ = schedule.encode_schedule(
            [Block(0, hm("23:00"), 23 * 60 + 59, Settings())]
        )
        self.assertEqual(calendar[95], "B")  # 23:45 slot, so filled through midnight
        calendar, _ = schedule.encode_schedule(
            [Block(0, hm("01:05"), hm("01:20"), Settings())]
        )
        self.assertEqual([i for i, c in enumerate(calendar) if c != "A"], [4, 5])

    def test_same_settings_share_a_letter(self) -> None:
        blocks = [
            Block(0, hm("08:00"), hm("09:00"), Settings("cool", 24)),
            Block(2, hm("08:00"), hm("09:00"), Settings("cool", 24)),
            Block(2, hm("10:00"), hm("11:00"), Settings("dry")),
        ]
        calendar, setpoints = schedule.encode_schedule(blocks)
        self.assertEqual(set(calendar) - {"A"}, {"B", "C"})
        self.assertEqual(sum(1 for r in schedule.decode_records(setpoints) if r), 2)

    def test_bad_blocks_are_rejected(self) -> None:
        for bad in (
            Block(7, 0, 60, Settings()),
            Block(0, 60, 60, Settings()),
            Block(0, 120, 60, Settings()),
            Block(0, 0, 1441, Settings()),
        ):
            with self.subTest(bad=bad), self.assertRaises(schedule.ScheduleError):
                schedule.encode_schedule([bad])

    def test_overlapping_blocks_are_rejected(self) -> None:
        with self.assertRaises(schedule.ScheduleError):
            schedule.encode_schedule(
                [
                    Block(0, hm("08:00"), hm("09:00"), Settings()),
                    Block(0, hm("08:30"), hm("09:30"), Settings("dry")),
                ]
            )

    def test_more_than_32_different_settings_are_rejected(self) -> None:
        blocks = [
            Block(day, slot * 15, slot * 15 + 15, Settings(temperature=18 + (i % 16), fan=("low", "medium")[i // 16 % 2], swing=bool(i // 32)))
            for i, (day, slot) in enumerate((d, s) for d in range(7) for s in range(6))
        ]
        with self.assertRaises(schedule.ScheduleError):
            schedule.encode_schedule(blocks[:33])

    def test_wrong_length_calendar_is_rejected(self) -> None:
        with self.assertRaises(schedule.ScheduleError):
            schedule.decode_schedule("A" * 671, "A" * 64)

    def test_unknown_calendar_character_is_rejected(self) -> None:
        with self.assertRaises(schedule.ScheduleError):
            schedule.decode_schedule("!" + "A" * 671, "A" * 64)


class GroupingTests(TestCase):
    def test_a_repeated_schedule_is_one_entry_with_several_days(self) -> None:
        settings = Settings("cool", 22, "high", True, False)
        blocks = [Block(day, hm("13:00"), hm("14:00"), settings) for day in (0, 2, 4)]
        groups = schedule.group_blocks(blocks)
        self.assertEqual(
            groups,
            [
                {
                    "days": ["Mon", "Wed", "Fri"],
                    "start": "13:00",
                    "end": "14:00",
                    "mode": "cool",
                    "swing": True,
                    "silent": False,
                    "temperature": 22,
                    "fan": "high",
                }
            ],
        )

    def test_unused_fields_are_left_out_for_other_modes(self) -> None:
        dry = schedule.group_blocks([Block(0, 0, 60, Settings("dry"))])[0]
        self.assertNotIn("temperature", dry)
        self.assertNotIn("fan", dry)
        fan = schedule.group_blocks([Block(0, 0, 60, Settings("fan", fan="high"))])[0]
        self.assertNotIn("temperature", fan)
        self.assertEqual(fan["fan"], "high")
        real_feel = schedule.group_blocks([Block(0, 0, 60, Settings("real_feel"))])[0]
        self.assertNotIn("temperature", real_feel)
        self.assertNotIn("fan", real_feel)

    def test_entries_are_in_week_order(self) -> None:
        blocks = [
            Block(5, hm("16:00"), hm("19:00"), Settings("real_feel")),
            Block(0, hm("13:00"), hm("14:00"), Settings("dry")),
        ]
        order = [g["days"][0] for g in schedule.group_blocks(blocks)]
        self.assertEqual(order, ["Mon", "Sat"])
