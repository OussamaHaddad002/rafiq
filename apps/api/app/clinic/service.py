"""Scheduling operations used by the agent's tools and by the Confirm / Cancel buttons."""

import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clinic.phone import normalize_phone
from app.clinic.scheduling import PartOfDay, Window, available_slots
from app.core.config import Settings
from app.models import Appointment, CallbackRequest, Doctor, PendingAction, Schedule

CODE_PREFIX = "RFQ-"
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L look-alikes
LATE_CANCELLATION = timedelta(hours=24)
LATE_CANCELLATION_FEE_DT = 20  # from politiques.md
SLOT_CONSTRAINT = "uq_appointments_doctor_slot"


class ClinicError(Exception):
    """An expected problem the agent should explain to the patient (e.g. a slot was taken)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def new_booking_code() -> str:
    return CODE_PREFIX + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(5))


class Clinic:
    """Scheduling for one request: a database session, the current time and clinic settings."""

    def __init__(self, session: AsyncSession, settings: Settings, now: datetime) -> None:
        self.session = session
        self.tz = ZoneInfo(settings.clinic_timezone)
        self.now = now
        self.slot = timedelta(minutes=settings.slot_minutes)
        self.min_notice = timedelta(minutes=settings.booking_min_notice_minutes)
        self.action_ttl = timedelta(minutes=settings.pending_action_ttl_minutes)

    @property
    def today(self) -> date:
        return self.now.astimezone(self.tz).date()

    def local(self, moment: datetime) -> datetime:
        return moment.astimezone(self.tz)

    # --- reads -----------------------------------------------------------------------------

    async def doctors(
        self, *, specialty: str | None = None, doctor_id: int | None = None
    ) -> list[Doctor]:
        query = select(Doctor).order_by(Doctor.id)
        if specialty:
            query = query.where(Doctor.specialty == specialty)
        if doctor_id is not None:
            query = query.where(Doctor.id == doctor_id)
        return list(await self.session.scalars(query))

    async def doctor(self, doctor_id: int) -> Doctor:
        found = await self.session.get(Doctor, doctor_id)
        if found is None:
            raise ClinicError("unknown_doctor", f"There is no doctor with id {doctor_id}.")
        return found

    async def windows(self, doctor_ids: list[int]) -> list[Window]:
        rows = await self.session.scalars(
            select(Schedule).where(Schedule.doctor_id.in_(doctor_ids))
        )
        return [Window(s.doctor_id, s.weekday, s.start_time, s.end_time) for s in rows]

    async def free_slots(
        self,
        doctor_ids: list[int],
        first: date,
        last: date,
        part_of_day: PartOfDay = "any",
        ignore_appointment_id: int | None = None,
    ) -> list[tuple[int, datetime]]:
        start = datetime.combine(first, datetime.min.time(), tzinfo=self.tz)
        end = datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=self.tz)
        booked_query = select(Appointment.doctor_id, Appointment.starts_at).where(
            Appointment.doctor_id.in_(doctor_ids),
            Appointment.status == "booked",
            Appointment.starts_at >= start,
            Appointment.starts_at < end,
        )
        if ignore_appointment_id is not None:
            booked_query = booked_query.where(Appointment.id != ignore_appointment_id)
        booked = [
            (doctor_id, starts_at)
            for doctor_id, starts_at in await self.session.execute(booked_query)
        ]
        return available_slots(
            await self.windows(doctor_ids),
            booked,
            first=first,
            last=last,
            tz=self.tz,
            slot=self.slot,
            earliest=self.now + self.min_notice,
            part_of_day=part_of_day,
        )

    async def ensure_free(
        self, doctor_id: int, start: datetime, ignore_appointment_id: int | None = None
    ) -> None:
        local = self.local(start)
        free = await self.free_slots(
            [doctor_id], local.date(), local.date(), ignore_appointment_id=ignore_appointment_id
        )
        if (doctor_id, local) not in {(d, s) for d, s in free}:
            raise ClinicError(
                "slot_unavailable",
                "This time is not available. Check availability again and offer another time.",
            )

    async def find_appointment(self, booking_code: str, phone: str) -> Appointment:
        """Both the code and the phone number must match, so a code alone reveals nothing."""
        normalized = normalize_phone(phone)
        appointment = await self.session.scalar(
            select(Appointment).where(
                Appointment.booking_code == booking_code.strip().upper(),
                Appointment.patient_phone == (normalized or ""),
            )
        )
        if appointment is None:
            raise ClinicError(
                "not_found",
                "No appointment matches this booking code and phone number.",
            )
        return appointment

    async def upcoming_appointment(self, booking_code: str, phone: str) -> Appointment:
        appointment = await self.find_appointment(booking_code, phone)
        if appointment.status != "booked":
            raise ClinicError("already_cancelled", "This appointment is already cancelled.")
        if appointment.starts_at <= self.now:
            raise ClinicError("in_the_past", "This appointment has already taken place.")
        return appointment

    # --- pending actions -------------------------------------------------------------------

    async def propose(
        self,
        conversation_id: uuid.UUID,
        kind: str,
        payload: dict[str, Any],
        details: dict[str, Any],
    ) -> PendingAction:
        """Store a write for the patient to confirm. Older pending cards in the chat lapse."""
        await self.session.execute(
            update(PendingAction)
            .where(
                PendingAction.conversation_id == conversation_id,
                PendingAction.status == "pending",
            )
            .values(status="superseded")
        )
        action = PendingAction(
            conversation_id=conversation_id,
            kind=kind,
            payload=payload,
            details=details,
            expires_at=self.now + self.action_ttl,
        )
        self.session.add(action)
        await self.session.flush()
        return action

    def effective_status(self, action: PendingAction) -> str:
        if action.status == "pending" and action.expires_at <= self.now:
            return "expired"
        return action.status

    async def decide(self, action: PendingAction, confirm: bool) -> dict[str, Any]:
        """Run (or decline) a pending action. Returns the result; never raises ClinicError."""
        status = self.effective_status(action)
        if status != "pending":
            return {"status": status, "error": f"This request is {status} and cannot be changed."}
        if not confirm:
            action.status = "declined"
            return {"status": "declined"}
        try:
            match action.kind:
                case "book":
                    result = await self._book(action)
                case "reschedule":
                    result = await self._reschedule(action)
                case _:
                    result = await self._cancel(action)
        except ClinicError as exc:
            action.status = "failed"
            action.result = {"error": exc.code, "message": exc.message}
            return {"status": "failed", **action.result}
        action.status = "confirmed"
        action.result = result
        return {"status": "confirmed", **result}

    async def _book(self, action: PendingAction) -> dict[str, Any]:
        payload = action.payload
        start = datetime.fromisoformat(payload["starts_at"])
        await self.ensure_free(payload["doctor_id"], start)
        for _ in range(5):  # retry only on a (very unlikely) booking-code collision
            appointment = Appointment(
                booking_code=new_booking_code(),
                doctor_id=payload["doctor_id"],
                starts_at=start,
                ends_at=start + self.slot,
                patient_name=payload["patient_name"],
                patient_phone=payload["patient_phone"],
                conversation_id=action.conversation_id,
            )
            try:
                async with self.session.begin_nested():
                    self.session.add(appointment)
            except IntegrityError as exc:
                if SLOT_CONSTRAINT in str(exc.orig):
                    raise ClinicError("slot_taken", "Someone just booked this slot.") from exc
                continue
            return {"booking_code": appointment.booking_code}
        raise ClinicError("internal", "Could not create a booking code.")  # pragma: no cover

    async def _reschedule(self, action: PendingAction) -> dict[str, Any]:
        payload = action.payload
        appointment = await self.session.get(Appointment, payload["appointment_id"])
        if appointment is None or appointment.status != "booked":
            raise ClinicError("already_cancelled", "This appointment is no longer active.")
        start = datetime.fromisoformat(payload["starts_at"])
        await self.ensure_free(payload["doctor_id"], start, ignore_appointment_id=appointment.id)
        try:
            async with self.session.begin_nested():
                appointment.doctor_id = payload["doctor_id"]
                appointment.starts_at = start
                appointment.ends_at = start + self.slot
        except IntegrityError as exc:
            raise ClinicError("slot_taken", "Someone just booked this slot.") from exc
        return {"booking_code": appointment.booking_code}

    async def _cancel(self, action: PendingAction) -> dict[str, Any]:
        appointment = await self.session.get(Appointment, action.payload["appointment_id"])
        if appointment is None or appointment.status != "booked":
            raise ClinicError("already_cancelled", "This appointment is already cancelled.")
        appointment.status = "cancelled"
        appointment.cancelled_at = self.now
        return {"booking_code": appointment.booking_code}

    # --- handoff ---------------------------------------------------------------------------

    async def request_callback(
        self,
        conversation_id: uuid.UUID,
        reason: str,
        patient_name: str | None,
        patient_phone: str | None,
    ) -> CallbackRequest:
        request = CallbackRequest(
            conversation_id=conversation_id,
            reason=reason,
            patient_name=patient_name,
            patient_phone=normalize_phone(patient_phone) if patient_phone else None,
        )
        self.session.add(request)
        await self.session.flush()
        return request


def utc_iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()
