"""Doctors and weekly schedules, matching data/clinic-src/medecins.md.

Run: python -m app.clinic.seed   (safe to re-run; appointments are not touched)
"""

import asyncio
from datetime import time

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionFactory, engine
from app.models import Doctor, Schedule

MON, TUE, WED, THU, FRI, SAT = range(6)
WEEKDAYS = (MON, TUE, WED, THU, FRI)

# slug, name, specialty, languages, room, [(weekdays, start, end)]
DOCTORS: list[tuple[str, str, str, list[str], str, list[tuple[tuple[int, ...], time, time]]]] = [
    (
        "sami-gharbi",
        "Dr Sami Gharbi",
        "general_medicine",
        ["ar", "fr"],
        "Ground floor, room 002",
        [(WEEKDAYS, time(8), time(14))],
    ),
    (
        "mariem-ayari",
        "Dr Mariem Ayari",
        "general_medicine",
        ["ar", "fr", "en"],
        "Ground floor, room 004",
        [(WEEKDAYS, time(13), time(19)), ((SAT,), time(8), time(13))],
    ),
    (
        "amira-ben-salah",
        "Dr Amira Ben Salah",
        "cardiology",
        ["ar", "fr", "en"],
        "2nd floor, room 204",
        [((MON, WED, FRI), time(9), time(13))],
    ),
    (
        "hichem-saidi",
        "Dr Hichem Saidi",
        "cardiology",
        ["ar", "fr"],
        "2nd floor, room 206",
        [((TUE, THU), time(14), time(19))],
    ),
    (
        "karim-trabelsi",
        "Dr Karim Trabelsi",
        "dentistry",
        ["ar", "fr"],
        "1st floor, room 105",
        [((MON, TUE, WED, THU), time(14), time(19))],
    ),
    (
        "leila-mansouri",
        "Dr Leila Mansouri",
        "pediatrics",
        ["ar", "fr", "en"],
        "1st floor, room 110",
        [((TUE, THU), time(9), time(13)), ((SAT,), time(9), time(12))],
    ),
    (
        "youssef-hamdi",
        "Dr Youssef Hamdi",
        "dermatology",
        ["ar", "fr", "en"],
        "1st floor, room 112",
        [((WED,), time(9), time(17)), ((SAT,), time(8), time(12))],
    ),
    (
        "nadia-chaabane",
        "Dr Nadia Chaabane",
        "gynecology",
        ["ar", "fr"],
        "2nd floor, room 210",
        [((TUE, THU), time(14), time(18))],
    ),
    (
        "ines-jaziri",
        "Dr Ines Jaziri",
        "ophthalmology",
        ["fr", "en"],
        "2nd floor, room 215",
        [((MON, THU), time(9), time(15))],
    ),
]


async def seed_clinic(session: AsyncSession) -> int:
    """Upsert doctors by slug and replace their weekly schedules. Returns the doctor count."""
    existing = {d.slug: d for d in await session.scalars(select(Doctor))}
    for slug, name, specialty, languages, room, windows in DOCTORS:
        doctor = existing.get(slug) or Doctor(slug=slug)
        doctor.name, doctor.specialty, doctor.languages, doctor.room = (
            name,
            specialty,
            languages,
            room,
        )
        session.add(doctor)
        await session.flush()
        await session.execute(delete(Schedule).where(Schedule.doctor_id == doctor.id))
        session.add_all(
            Schedule(doctor_id=doctor.id, weekday=day, start_time=start, end_time=end)
            for days, start, end in windows
            for day in days
        )
    await session.commit()
    return len(DOCTORS)


async def _main() -> None:
    try:
        async with SessionFactory() as session:
            count = await seed_clinic(session)
    finally:
        await engine.dispose()
    print(f"seeded {count} doctors")


if __name__ == "__main__":
    asyncio.run(_main())
