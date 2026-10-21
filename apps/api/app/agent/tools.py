"""Tools the agent can call. Arguments are validated with Pydantic; results are compact JSON.

Writes (book / reschedule / cancel) never change an appointment directly: they create a
pending action that the patient confirms with a button (see Clinic.decide).
"""

import datetime as dt
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.clinic.phone import mask_phone, normalize_phone
from app.clinic.scheduling import WEEKDAY_NAMES
from app.clinic.service import (
    LATE_CANCELLATION,
    LATE_CANCELLATION_FEE_DT,
    Clinic,
    ClinicError,
    utc_iso,
)
from app.llm.base import ToolCall, ToolSpec
from app.models import Appointment, Doctor, PendingAction

logger = logging.getLogger(__name__)

Specialty = Literal[
    "general_medicine",
    "cardiology",
    "dentistry",
    "pediatrics",
    "dermatology",
    "gynecology",
    "ophthalmology",
]
WEEKDAYS = WEEKDAY_NAMES
MAX_SEARCH_DAYS = 21
NEXT_AVAILABLE_DAYS = 14
MAX_DOCTORS, MAX_DAYS_PER_DOCTOR, SUGGESTED_PER_DAY = 4, 3, 3
CONFIRM_INSTRUCTION = (
    "Nothing is changed yet. Briefly summarize these details and ask the patient to press the "
    "confirmation button on the card shown under your message. Do not say it is done."
)
_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


@dataclass
class ToolContext:
    clinic: Clinic
    conversation_id: uuid.UUID
    proposed: PendingAction | None = None  # set when a write tool creates a Confirm card


# --- arguments ---------------------------------------------------------------------------


class ListDoctorsArgs(BaseModel):
    specialty: Specialty | None = Field(None, description="Only doctors of this specialty.")


RelativeDay = Literal["today", "tomorrow", "day_after_tomorrow"]
Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class CheckAvailabilityArgs(BaseModel):
    specialty: Specialty | None = Field(None, description="Search all doctors of a specialty.")
    doctor_id: int | None = Field(None, description="Or one doctor (id from list_doctors).")
    day: RelativeDay | None = Field(
        None, description='For "tomorrow", "after tomorrow" (بعد غدوة) etc. Do not compute dates.'
    )
    weekday: Weekday | None = Field(
        None,
        description='For a weekday name ("next Monday", "vendredi"): its next occurrence. '
        "Do not compute dates.",
    )
    date_from: date | None = Field(None, description="Explicit first day (YYYY-MM-DD).")
    date_to: date | None = Field(None, description="Explicit last day (YYYY-MM-DD).")
    part_of_day: Literal["morning", "afternoon", "any"] = "any"


def resolve_days(args: CheckAvailabilityArgs, today: date) -> tuple[date, date]:
    """The days to search. Relative days are resolved here, not by the model: models are
    unreliable at calendar arithmetic (e.g. "next Monday" became a Saturday)."""
    if args.day is not None:
        day = today + timedelta(days=("today", "tomorrow", "day_after_tomorrow").index(args.day))
        return day, day
    if args.weekday is not None:
        target = WEEKDAYS.index(args.weekday.capitalize())
        day = today + timedelta(days=(target - today.weekday() - 1) % 7 + 1)  # 1..7 days ahead
        return day, day
    first = max(args.date_from or today, today)
    last = min(args.date_to or first + timedelta(days=7), first + timedelta(days=MAX_SEARCH_DAYS))
    return first, max(first, last)


class BookArgs(BaseModel):
    doctor_id: int
    date: dt.date = Field(description="YYYY-MM-DD, a day returned by check_availability.")
    time: str = Field(pattern=_TIME_PATTERN, description="HH:MM, a time from check_availability.")
    patient_name: str = Field(min_length=2, max_length=120, description="Patient's full name.")
    patient_phone: str = Field(min_length=6, max_length=25)


class AppointmentRef(BaseModel):
    booking_code: str = Field(min_length=4, max_length=12, description="e.g. RFQ-7K3PX")
    patient_phone: str = Field(min_length=6, max_length=25, description="Phone used to book.")


class RescheduleArgs(AppointmentRef):
    new_date: date = Field(description="YYYY-MM-DD, a day returned by check_availability.")
    new_time: str = Field(pattern=_TIME_PATTERN, description="HH:MM")
    doctor_id: int | None = Field(None, description="Only to change doctor. Default: same.")


class HandoffArgs(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    patient_name: str | None = None
    patient_phone: str | None = None


# --- helpers -----------------------------------------------------------------------------


def hours_summary(clinic_windows: list[tuple[int, time, time]]) -> list[str]:
    return [
        f"{WEEKDAYS[day][:3]} {start:%H:%M}-{end:%H:%M}"
        for day, start, end in sorted(clinic_windows)
    ]


def appointment_details(clinic: Clinic, appointment: Appointment, doctor: Doctor) -> dict[str, Any]:
    starts = clinic.local(appointment.starts_at)
    return {
        "booking_code": appointment.booking_code,
        "doctor_id": doctor.id,
        "doctor": doctor.name,
        "specialty": doctor.specialty,
        "room": doctor.room,
        "starts_at": starts.isoformat(),
        "weekday": WEEKDAYS[starts.weekday()],
        "patient_name": appointment.patient_name,
        "patient_phone": mask_phone(appointment.patient_phone),
        "status": appointment.status,
    }


def local_start(clinic: Clinic, day: date, hhmm: str) -> datetime:
    return datetime.combine(day, time.fromisoformat(hhmm), tzinfo=clinic.tz)


def proposal(action: PendingAction) -> dict[str, Any]:
    return {
        "status": "awaiting_patient_confirmation",
        "summary": action.details,
        "next_step": CONFIRM_INSTRUCTION,
    }


# --- tools -------------------------------------------------------------------------------


async def list_doctors(ctx: ToolContext, args: ListDoctorsArgs) -> dict[str, Any]:
    doctors = await ctx.clinic.doctors(specialty=args.specialty)
    windows = await ctx.clinic.windows([d.id for d in doctors])
    return {
        "doctors": [
            {
                "doctor_id": d.id,
                "name": d.name,
                "specialty": d.specialty,
                "languages": d.languages,
                "room": d.room,
                "hours": hours_summary(
                    [(w.weekday, w.start, w.end) for w in windows if w.doctor_id == d.id]
                ),
            }
            for d in doctors
        ]
    }


async def check_availability(ctx: ToolContext, args: CheckAvailabilityArgs) -> dict[str, Any]:
    clinic = ctx.clinic
    if args.doctor_id is None and args.specialty is None:
        raise ClinicError("missing_criteria", "Give a specialty or a doctor_id.")
    doctors = await clinic.doctors(specialty=args.specialty, doctor_id=args.doctor_id)
    if not doctors:
        raise ClinicError("unknown_doctor", "No doctor matches. Use list_doctors.")
    first, last = resolve_days(args, clinic.today)
    names = {d.id: d.name for d in doctors}
    doctor_ids = list(names)

    results = group_slots(
        await clinic.free_slots(doctor_ids, first, last, args.part_of_day), names, clinic.slot
    )
    answer: dict[str, Any] = {
        # Weekday names let the model notice a wrong date (e.g. "Monday" resolved to a Saturday).
        "searched": {"from": labelled(first), "to": labelled(last)},
        "slots": results,
        "note": f"Clinic time. Appointments start every {clinic.slot.seconds // 60} minutes "
        "inside the free ranges. Offer the suggested times (or the range), not every slot.",
    }
    if not results:
        # Never leave the patient without options: show the nearest free slots after the range.
        after = await clinic.free_slots(
            doctor_ids, last + timedelta(days=1), last + timedelta(days=NEXT_AVAILABLE_DAYS)
        )
        answer["note"] = "No free slot in the searched period."
        answer["next_available"] = group_slots(after, names, clinic.slot, max_days=2)
    return answer


def labelled(day: date) -> str:
    return f"{day.isoformat()} ({WEEKDAYS[day.weekday()]})"


def free_ranges(starts: list[datetime], step: timedelta) -> list[str]:
    """Consecutive slot starts as ranges: 09:00, 09:30 … 12:30 -> "09:00-12:30"."""
    runs: list[list[datetime]] = []
    for start in starts:
        if runs and start - runs[-1][-1] == step:
            runs[-1].append(start)
        else:
            runs.append([start])
    return [f"{r[0]:%H:%M}" if len(r) == 1 else f"{r[0]:%H:%M}-{r[-1]:%H:%M}" for r in runs]


def suggested_times(starts: list[datetime], count: int = SUGGESTED_PER_DAY) -> list[str]:
    """A few times spread over the day, so the model offers choices instead of a long list."""
    if len(starts) <= count:
        picks = starts
    else:
        picks = [starts[round(i * (len(starts) - 1) / (count - 1))] for i in range(count)]
    return [f"{start:%H:%M}" for start in picks]


def group_slots(
    slots: list[tuple[int, datetime]],
    names: dict[int, str],
    step: timedelta,
    max_days: int = MAX_DAYS_PER_DOCTOR,
) -> list[dict[str, Any]]:
    """Slots grouped by doctor and day as compact ranges plus suggestions."""
    grouped: dict[int, dict[date, list[datetime]]] = {}
    for doctor_id, start in slots:
        days = grouped.setdefault(doctor_id, {})
        if start.date() in days or len(days) < max_days:
            days.setdefault(start.date(), []).append(start)
    return [
        {
            "doctor_id": doctor_id,
            "doctor": names[doctor_id],
            "date": day.isoformat(),
            "weekday": WEEKDAYS[day.weekday()],
            "free": free_ranges(starts, step),
            "suggested": suggested_times(starts),
        }
        for doctor_id, days in list(grouped.items())[:MAX_DOCTORS]
        for day, starts in days.items()
    ]


async def book_appointment(ctx: ToolContext, args: BookArgs) -> dict[str, Any]:
    clinic = ctx.clinic
    doctor = await clinic.doctor(args.doctor_id)
    start = local_start(clinic, args.date, args.time)
    await clinic.ensure_free(doctor.id, start)
    phone = normalize_phone(args.patient_phone)
    if phone is None:
        raise ClinicError("invalid_phone", "Ask the patient for a valid phone number.")
    ctx.proposed = await clinic.propose(
        ctx.conversation_id,
        "book",
        payload={
            "doctor_id": doctor.id,
            "starts_at": utc_iso(start),
            "patient_name": args.patient_name.strip(),
            "patient_phone": phone,
        },
        details={
            "doctor": doctor.name,
            "specialty": doctor.specialty,
            "room": doctor.room,
            "starts_at": start.isoformat(),
            "weekday": WEEKDAYS[start.weekday()],
            "patient_name": args.patient_name.strip(),
            "patient_phone": mask_phone(phone),
        },
    )
    return proposal(ctx.proposed)


async def lookup_appointment(ctx: ToolContext, args: AppointmentRef) -> dict[str, Any]:
    appointment = await ctx.clinic.find_appointment(args.booking_code, args.patient_phone)
    doctor = await ctx.clinic.doctor(appointment.doctor_id)
    return {"appointment": appointment_details(ctx.clinic, appointment, doctor)}


async def reschedule_appointment(ctx: ToolContext, args: RescheduleArgs) -> dict[str, Any]:
    clinic = ctx.clinic
    appointment = await clinic.upcoming_appointment(args.booking_code, args.patient_phone)
    doctor = await clinic.doctor(args.doctor_id or appointment.doctor_id)
    start = local_start(clinic, args.new_date, args.new_time)
    await clinic.ensure_free(doctor.id, start, ignore_appointment_id=appointment.id)
    current = appointment_details(clinic, appointment, await clinic.doctor(appointment.doctor_id))
    ctx.proposed = await clinic.propose(
        ctx.conversation_id,
        "reschedule",
        payload={
            "appointment_id": appointment.id,
            "doctor_id": doctor.id,
            "starts_at": utc_iso(start),
        },
        details={
            **current,
            "doctor": doctor.name,
            "specialty": doctor.specialty,
            "room": doctor.room,
            "previous_starts_at": current["starts_at"],
            "starts_at": start.isoformat(),
            "weekday": WEEKDAYS[start.weekday()],
        },
    )
    return proposal(ctx.proposed)


async def cancel_appointment(ctx: ToolContext, args: AppointmentRef) -> dict[str, Any]:
    clinic = ctx.clinic
    appointment = await clinic.upcoming_appointment(args.booking_code, args.patient_phone)
    details = appointment_details(clinic, appointment, await clinic.doctor(appointment.doctor_id))
    if appointment.starts_at - clinic.now < LATE_CANCELLATION:
        details["late_cancellation_fee_dt"] = LATE_CANCELLATION_FEE_DT
    ctx.proposed = await clinic.propose(
        ctx.conversation_id, "cancel", payload={"appointment_id": appointment.id}, details=details
    )
    return proposal(ctx.proposed)


async def handoff_to_human(ctx: ToolContext, args: HandoffArgs) -> dict[str, Any]:
    await ctx.clinic.request_callback(
        ctx.conversation_id, args.reason, args.patient_name, args.patient_phone
    )
    return {
        "status": "callback_requested",
        "message": "A receptionist will call the patient back during opening hours.",
        "has_phone": bool(args.patient_phone),
    }


# --- registry ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    run: Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, strip_titles(self.args.model_json_schema()))


def strip_titles(schema: Any) -> Any:
    """Pydantic adds a "title" to every field; the model doesn't need them (saves tokens)."""
    if isinstance(schema, dict):
        return {
            key: strip_titles(value)
            for key, value in schema.items()
            if not (key == "title" and isinstance(value, str))
        }
    if isinstance(schema, list):
        return [strip_titles(item) for item in schema]
    return schema


TOOLS = {
    tool.name: tool
    for tool in [
        Tool(
            "list_doctors",
            "List the clinic's doctors with their id, specialty, languages and weekly hours.",
            ListDoctorsArgs,
            list_doctors,
        ),
        Tool(
            "check_availability",
            "Find free appointment slots for a specialty or a doctor. For relative days use "
            "`day` or `weekday`; use `date_from`/`date_to` only for explicit dates.",
            CheckAvailabilityArgs,
            check_availability,
        ),
        Tool(
            "book_appointment",
            "Prepare a booking for a free slot. The patient must then press Confirm.",
            BookArgs,
            book_appointment,
        ),
        Tool(
            "lookup_appointment",
            "Find an existing appointment from its booking code and the patient's phone.",
            AppointmentRef,
            lookup_appointment,
        ),
        Tool(
            "reschedule_appointment",
            "Prepare moving an existing appointment to a new free slot. Needs Confirm.",
            RescheduleArgs,
            reschedule_appointment,
        ),
        Tool(
            "cancel_appointment",
            "Prepare cancelling an existing appointment. Needs Confirm.",
            AppointmentRef,
            cancel_appointment,
        ),
        Tool(
            "handoff_to_human",
            "Ask a human receptionist to call the patient back (complaints, requests you "
            "cannot handle, or when the patient asks for a person).",
            HandoffArgs,
            handoff_to_human,
        ),
    ]
}
TOOL_SPECS = [tool.spec for tool in TOOLS.values()]


async def run_tool(ctx: ToolContext, call: ToolCall) -> dict[str, Any]:
    """Execute one tool call. Errors become results the model can read and recover from."""
    tool = TOOLS.get(call.name)
    if tool is None:
        return {"error": "unknown_tool", "message": f"There is no tool named {call.name}."}
    try:
        args = tool.args.model_validate(call.arguments)
    except ValidationError as exc:
        problems = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()][:5]
        return {"error": "invalid_arguments", "problems": problems}
    try:
        return await tool.run(ctx, args)
    except ClinicError as exc:
        return {"error": exc.code, "message": exc.message}
