from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import TOOL_SPECS, CheckAvailabilityArgs, ToolContext, resolve_days, run_tool
from app.clinic.seed import seed_clinic
from app.clinic.service import Clinic
from app.core.config import get_settings
from app.core.db import SessionFactory
from app.llm.base import ToolCall
from app.models import Appointment, CallbackRequest, Conversation, Doctor, Message, Schedule
from tests.agent_helpers import NOW

AMIRA, HICHEM = 3, 4  # cardiologists, ids follow the seed order
PHONE = "+216 20 000 123"


@dataclass
class Env:
    session: AsyncSession
    clinic: Clinic
    ctx: ToolContext

    async def call(self, name: str, **arguments: Any) -> dict[str, Any]:
        return await run_tool(self.ctx, ToolCall("call_1", name, arguments))

    async def other_conversation(self) -> ToolContext:
        conversation = Conversation(language="fr")
        self.session.add(conversation)
        await self.session.flush()
        return ToolContext(clinic=self.clinic, conversation_id=conversation.id)


@pytest.fixture
async def env() -> AsyncIterator[Env]:
    async with SessionFactory() as session:
        await seed_clinic(session)
        conversation = Conversation(language="fr")
        session.add(conversation)
        await session.flush()
        clinic = Clinic(session, get_settings(), NOW)
        yield Env(session, clinic, ToolContext(clinic=clinic, conversation_id=conversation.id))


async def book_and_confirm(env: Env, day: str = "2026-10-23", hhmm: str = "10:00") -> str:
    result = await env.call(
        "book_appointment",
        doctor_id=AMIRA,
        date=day,
        time=hhmm,
        patient_name="Salma Ben Ali",
        patient_phone=PHONE,
    )
    assert result["status"] == "awaiting_patient_confirmation", result
    assert env.ctx.proposed is not None
    outcome = await env.clinic.decide(env.ctx.proposed, confirm=True)
    assert outcome["status"] == "confirmed", outcome
    return str(outcome["booking_code"])


async def test_seed_is_idempotent(env: Env) -> None:
    await seed_clinic(env.session)
    assert await env.session.scalar(select(func.count()).select_from(Doctor)) == 9
    amira_windows = await env.session.scalar(
        select(func.count()).select_from(Schedule).where(Schedule.doctor_id == AMIRA)
    )
    assert amira_windows == 3  # Monday, Wednesday, Friday


async def test_list_doctors_shows_weekly_hours(env: Env) -> None:
    result = await env.call("list_doctors", specialty="cardiology")
    assert [(d["name"], d["hours"]) for d in result["doctors"]] == [
        ("Dr Amira Ben Salah", ["Mon 09:00-13:00", "Wed 09:00-13:00", "Fri 09:00-13:00"]),
        ("Dr Hichem Saidi", ["Tue 14:00-19:00", "Thu 14:00-19:00"]),
    ]


async def test_availability_respects_schedules_and_minimum_notice(env: Env) -> None:
    result = await env.call(
        "check_availability", specialty="cardiology", date_from="2026-10-21", date_to="2026-10-23"
    )
    slots = {(s["doctor"], s["date"]): s for s in result["slots"]}
    # It is 09:00 on Wednesday; with 2 hours' notice the first slot today is 11:00.
    amira_today = slots[("Dr Amira Ben Salah", "2026-10-21")]
    assert amira_today["free"] == ["11:00-12:30"]
    assert amira_today["suggested"] == ["11:00", "12:00", "12:30"]  # spread, not the full list
    assert slots[("Dr Hichem Saidi", "2026-10-22")]["free"] == ["14:00-18:30"]
    assert ("Dr Hichem Saidi", "2026-10-21") not in slots  # he works Tuesday and Thursday


async def test_availability_needs_a_specialty_or_doctor(env: Env) -> None:
    assert (await env.call("check_availability"))["error"] == "missing_criteria"


async def test_booking_waits_for_confirmation_then_creates_the_appointment(env: Env) -> None:
    result = await env.call(
        "book_appointment",
        doctor_id=AMIRA,
        date="2026-10-23",
        time="10:00",
        patient_name="Salma Ben Ali",
        patient_phone=PHONE,
    )
    assert result["summary"]["starts_at"] == "2026-10-23T10:00:00+01:00"
    assert result["summary"]["patient_phone"] == "+216•••••123"
    assert await env.session.scalar(select(func.count()).select_from(Appointment)) == 0

    assert env.ctx.proposed is not None
    outcome = await env.clinic.decide(env.ctx.proposed, confirm=True)
    appointment = await env.session.scalar(select(Appointment))
    assert appointment is not None
    assert outcome["booking_code"] == appointment.booking_code
    assert appointment.booking_code.startswith("RFQ-")
    assert appointment.patient_phone == "+21620000123"

    again = await env.call(
        "check_availability", doctor_id=AMIRA, date_from="2026-10-23", date_to="2026-10-23"
    )
    assert again["slots"][0]["free"] == ["09:00-09:30", "10:30-12:30"]  # 10:00 is taken


async def test_booking_outside_the_schedule_is_refused(env: Env) -> None:
    result = await env.call(
        "book_appointment",
        doctor_id=AMIRA,
        date="2026-10-22",  # Thursday: Dr Ben Salah does not work
        time="10:00",
        patient_name="Salma Ben Ali",
        patient_phone=PHONE,
    )
    assert result["error"] == "slot_unavailable"
    assert env.ctx.proposed is None


async def test_second_confirmation_for_the_same_slot_fails(env: Env) -> None:
    await env.call(
        "book_appointment",
        doctor_id=AMIRA,
        date="2026-10-23",
        time="10:00",
        patient_name="Patient A",
        patient_phone=PHONE,
    )
    first = env.ctx.proposed
    other = await env.other_conversation()
    await run_tool(
        other,
        ToolCall(
            "c2",
            "book_appointment",
            {
                "doctor_id": AMIRA,
                "date": "2026-10-23",
                "time": "10:00",
                "patient_name": "Patient B",
                "patient_phone": "+216 20 000 999",
            },
        ),
    )
    assert first is not None and other.proposed is not None

    assert (await env.clinic.decide(first, confirm=True))["status"] == "confirmed"
    second = await env.clinic.decide(other.proposed, confirm=True)
    assert (second["status"], second["error"]) == ("failed", "slot_unavailable")


async def test_database_rejects_two_bookings_for_one_slot(env: Env) -> None:
    start = datetime.fromisoformat("2026-10-23T10:00:00+01:00")
    for code in ("RFQ-AAAAA", "RFQ-BBBBB"):
        env.session.add(
            Appointment(
                booking_code=code,
                doctor_id=AMIRA,
                starts_at=start,
                ends_at=start + timedelta(minutes=30),
                patient_name="X",
                patient_phone="+21620000000",
            )
        )
    with pytest.raises(IntegrityError, match="uq_appointments_doctor_slot"):
        await env.session.flush()


async def test_lookup_needs_the_matching_phone(env: Env) -> None:
    code = await book_and_confirm(env)

    wrong = await env.call("lookup_appointment", booking_code=code, patient_phone="20 999 999")
    assert wrong["error"] == "not_found"

    found = await env.call("lookup_appointment", booking_code=code.lower(), patient_phone=PHONE)
    assert found["appointment"]["doctor"] == "Dr Amira Ben Salah"
    assert found["appointment"]["weekday"] == "Friday"


async def test_reschedule_keeps_the_booking_code(env: Env) -> None:
    code = await book_and_confirm(env)
    result = await env.call(
        "reschedule_appointment",
        booking_code=code,
        patient_phone=PHONE,
        new_date="2026-10-26",
        new_time="11:30",
    )
    assert result["summary"]["previous_starts_at"] == "2026-10-23T10:00:00+01:00"
    assert env.ctx.proposed is not None
    outcome = await env.clinic.decide(env.ctx.proposed, confirm=True)

    appointment = await env.session.scalar(select(Appointment))
    assert appointment is not None
    assert outcome["booking_code"] == code == appointment.booking_code
    assert env.clinic.local(appointment.starts_at).isoformat() == "2026-10-26T11:30:00+01:00"


async def test_late_cancellation_mentions_the_fee(env: Env) -> None:
    soon = await book_and_confirm(env, day="2026-10-21", hhmm="12:00")  # 3 hours from now
    later = await book_and_confirm(env, day="2026-10-23", hhmm="10:00")

    late = await env.call("cancel_appointment", booking_code=soon, patient_phone=PHONE)
    early = await env.call("cancel_appointment", booking_code=later, patient_phone=PHONE)

    assert late["summary"]["late_cancellation_fee_dt"] == 20
    assert "late_cancellation_fee_dt" not in early["summary"]


async def test_cancel_then_slot_is_free_again(env: Env) -> None:
    code = await book_and_confirm(env)
    await env.call("cancel_appointment", booking_code=code, patient_phone=PHONE)
    assert env.ctx.proposed is not None
    assert (await env.clinic.decide(env.ctx.proposed, confirm=True))["status"] == "confirmed"

    again = await env.call(
        "check_availability", doctor_id=AMIRA, date_from="2026-10-23", date_to="2026-10-23"
    )
    assert again["slots"][0]["free"] == ["09:00-12:30"]
    assert (await env.call("cancel_appointment", booking_code=code, patient_phone=PHONE))[
        "error"
    ] == "already_cancelled"


async def test_declined_expired_and_superseded_actions_change_nothing(env: Env) -> None:
    args = {
        "doctor_id": AMIRA,
        "date": "2026-10-23",
        "patient_name": "Salma Ben Ali",
        "patient_phone": PHONE,
    }
    await env.call("book_appointment", time="10:00", **args)
    first = env.ctx.proposed
    await env.call("book_appointment", time="10:30", **args)
    second = env.ctx.proposed
    assert first is not None and second is not None
    await env.session.refresh(first)
    assert first.status == "superseded"  # only the latest card in a chat stays valid

    assert (await env.clinic.decide(first, confirm=True))["status"] == "superseded"
    assert (await env.clinic.decide(second, confirm=False))["status"] == "declined"

    await env.call("book_appointment", time="11:00", **args)
    third = env.ctx.proposed
    assert third is not None
    later = Clinic(env.session, get_settings(), NOW + timedelta(minutes=16))
    assert (await later.decide(third, confirm=True))["status"] == "expired"
    assert await env.session.scalar(select(func.count()).select_from(Appointment)) == 0


async def test_handoff_records_a_callback_request(env: Env) -> None:
    result = await env.call("handoff_to_human", reason="Complaint", patient_phone="20 000 555")
    assert result["status"] == "callback_requested"
    request = await env.session.scalar(select(CallbackRequest))
    assert request is not None and request.patient_phone == "+21620000555"


async def test_bad_arguments_and_unknown_tools_are_reported_to_the_model(env: Env) -> None:
    invalid = await env.call("book_appointment", doctor_id=AMIRA, date="tomorrow", time="25:00")
    assert invalid["error"] == "invalid_arguments"
    assert any(p.startswith("date") for p in invalid["problems"])
    assert (await env.call("delete_everything"))["error"] == "unknown_tool"


def test_tool_schemas_have_no_titles() -> None:
    assert "title" not in str(TOOL_SPECS)
    assert {t.name for t in TOOL_SPECS} >= {"check_availability", "book_appointment"}


async def test_lookup_gives_the_doctor_id_needed_to_reschedule(env: Env) -> None:
    code = await book_and_confirm(env)
    found = await env.call("lookup_appointment", booking_code=code, patient_phone=PHONE)
    assert found["appointment"]["doctor_id"] == AMIRA


async def test_empty_json_columns_are_sql_null(env: Env) -> None:
    env.session.add(Message(conversation_id=env.ctx.conversation_id, role="user", content="Hi"))
    await env.session.flush()
    nulls = await env.session.scalar(
        text("SELECT count(*) FROM messages WHERE sources IS NULL AND tool_calls IS NULL")
    )
    assert nulls == 1


async def test_empty_search_labels_weekdays_and_offers_the_next_free_slots(env: Env) -> None:
    # Saturday: Dr Trabelsi (dentist) only works Monday to Thursday afternoons.
    result = await env.call(
        "check_availability", specialty="dentistry", date_from="2026-10-24", date_to="2026-10-24"
    )
    assert result["searched"] == {"from": "2026-10-24 (Saturday)", "to": "2026-10-24 (Saturday)"}
    assert result["slots"] == []
    first = result["next_available"][0]
    assert (first["date"], first["weekday"], first["free"]) == (
        "2026-10-26",
        "Monday",
        ["14:00-18:30"],
    )


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"day": "today"}, ("2026-10-21", "2026-10-21")),
        ({"day": "tomorrow"}, ("2026-10-22", "2026-10-22")),
        ({"day": "day_after_tomorrow"}, ("2026-10-23", "2026-10-23")),
        ({"weekday": "monday"}, ("2026-10-26", "2026-10-26")),
        ({"weekday": "wednesday"}, ("2026-10-28", "2026-10-28")),  # today is Wednesday
        ({"weekday": "thursday"}, ("2026-10-22", "2026-10-22")),
        ({"date_from": "2026-10-01"}, ("2026-10-21", "2026-10-28")),  # past dates clamp to today
        ({"date_from": "2026-10-25", "date_to": "2026-12-31"}, ("2026-10-25", "2026-11-15")),
    ],
)
def test_relative_days_are_resolved_in_code(
    arguments: dict[str, str], expected: tuple[str, str]
) -> None:
    args = CheckAvailabilityArgs.model_validate(arguments)
    first, last = resolve_days(args, date(2026, 10, 21))
    assert (first.isoformat(), last.isoformat()) == expected
