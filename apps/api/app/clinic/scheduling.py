"""Availability as a pure function: weekly windows minus booked slots, in clinic time."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

PartOfDay = Literal["morning", "afternoon", "any"]
# English names regardless of the server locale (strftime("%A") depends on it).
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_AFTERNOON_STARTS = time(13, 0)


@dataclass(frozen=True, slots=True)
class Window:
    doctor_id: int
    weekday: int  # 0 = Monday
    start: time
    end: time


def days_between(first: date, last: date) -> Iterator[date]:
    day = first
    while day <= last:
        yield day
        day += timedelta(days=1)


def slot_starts(
    windows: Iterable[Window], first: date, last: date, tz: ZoneInfo, slot: timedelta
) -> Iterator[tuple[int, datetime]]:
    """Every slot start (doctor_id, aware local datetime) from the weekly windows, in order."""
    by_weekday: dict[int, list[Window]] = {}
    for window in windows:
        by_weekday.setdefault(window.weekday, []).append(window)
    for day in days_between(first, last):
        for window in sorted(by_weekday.get(day.weekday(), []), key=lambda w: w.start):
            start = datetime.combine(day, window.start, tzinfo=tz)
            end = datetime.combine(day, window.end, tzinfo=tz)
            while start + slot <= end:
                yield window.doctor_id, start
                start += slot


def matches_part_of_day(start: datetime, part: PartOfDay) -> bool:
    if part == "morning":
        return start.time() < _AFTERNOON_STARTS
    if part == "afternoon":
        return start.time() >= _AFTERNOON_STARTS
    return True


def available_slots(
    windows: Iterable[Window],
    booked: Iterable[tuple[int, datetime]],
    *,
    first: date,
    last: date,
    tz: ZoneInfo,
    slot: timedelta,
    earliest: datetime,
    part_of_day: PartOfDay = "any",
) -> list[tuple[int, datetime]]:
    """Free slots, excluding booked ones and anything before `earliest` (min notice)."""
    taken = {(doctor_id, start.astimezone(UTC)) for doctor_id, start in booked}
    return [
        (doctor_id, start)
        for doctor_id, start in slot_starts(windows, first, last, tz, slot)
        if start >= earliest
        and (doctor_id, start.astimezone(UTC)) not in taken
        and matches_part_of_day(start, part_of_day)
    ]
