from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.clinic.phone import mask_phone, normalize_phone
from app.clinic.scheduling import PartOfDay, Window, available_slots

TUNIS = ZoneInfo("Africa/Tunis")
SLOT = timedelta(minutes=30)
WEDNESDAY = date(2026, 10, 21)
# Doctor 1: Wednesday 09:00-11:00 and Thursday 14:00-15:00.
WINDOWS = [Window(1, 2, time(9), time(11)), Window(1, 3, time(14), time(15))]


def local(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=TUNIS)


def free(
    booked: list[tuple[int, datetime]] | None = None,
    earliest: datetime | None = None,
    part: PartOfDay = "any",
) -> list[tuple[int, datetime]]:
    return available_slots(
        WINDOWS,
        booked or [],
        first=WEDNESDAY,
        last=WEDNESDAY + timedelta(days=1),
        tz=TUNIS,
        slot=SLOT,
        earliest=earliest or local(WEDNESDAY, 0),
        part_of_day=part,
    )


def test_slots_follow_the_weekly_windows() -> None:
    assert [f"{s:%a %H:%M}" for _, s in free()] == [
        "Wed 09:00",
        "Wed 09:30",
        "Wed 10:00",
        "Wed 10:30",
        "Thu 14:00",
        "Thu 14:30",
    ]


def test_booked_slots_are_excluded_whatever_the_timezone() -> None:
    booked_utc = local(WEDNESDAY, 9, 30).astimezone(UTC)
    assert local(WEDNESDAY, 9, 30) not in [s for _, s in free(booked=[(1, booked_utc)])]


def test_booking_another_doctor_does_not_block_the_slot() -> None:
    assert local(WEDNESDAY, 9, 30) in [s for _, s in free(booked=[(2, local(WEDNESDAY, 9, 30))])]


def test_minimum_notice_hides_slots_that_are_too_soon() -> None:
    slots = free(earliest=local(WEDNESDAY, 10))
    assert [f"{s:%a %H:%M}" for _, s in slots][:2] == ["Wed 10:00", "Wed 10:30"]


@pytest.mark.parametrize(("part", "expected"), [("morning", 4), ("afternoon", 2)])
def test_part_of_day_filter(part: PartOfDay, expected: int) -> None:
    assert len(free(part=part)) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("20 000 100", "+21620000100"),
        ("+216 70 000 100", "+21670000100"),
        ("00216-70-000-100", "+21670000100"),
        ("+33 6 12 34 56 78", "+33612345678"),
        ("12345", None),
        ("not a phone", None),
    ],
)
def test_normalize_phone(raw: str, expected: str | None) -> None:
    assert normalize_phone(raw) == expected


def test_mask_phone_keeps_only_the_last_digits() -> None:
    assert mask_phone("+21620000123") == "+216•••••123"
