"""The tool loop and the full booking flow through the API, with a scripted model."""

import json
from collections.abc import Callable
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.agent.history import action_note, expand
from app.agent.loop import MAX_STEPS_REPLIES, AgentDone, ToolFinished, run_agent
from app.agent.prompts import format_calendar
from app.agent.tools import ToolContext
from app.clinic.seed import seed_clinic
from app.clinic.service import Clinic
from app.core.clock import get_clock
from app.core.config import get_settings
from app.core.db import SessionFactory
from app.llm import get_provider
from app.llm.base import ChatMessage, ToolCall
from app.main import app
from app.models import Appointment, Conversation, Message
from tests.agent_helpers import NOW, ScriptedProvider, Step
from tests.conftest import SSEEvent, parse_sse

Install = Callable[[ScriptedProvider], ScriptedProvider]

AMIRA = 3
BOOKING = {
    "doctor_id": AMIRA,
    "date": "2026-10-23",
    "time": "10:00",
    "patient_name": "Salma Ben Ali",
    "patient_phone": "20 000 123",
}


@pytest.fixture
async def seeded() -> None:
    async with SessionFactory() as session:
        await seed_clinic(session)


@pytest.fixture
def use(seeded: None) -> Install:
    """Install a scripted model and the pinned clock for API tests."""

    def install(provider: ScriptedProvider) -> ScriptedProvider:
        app.dependency_overrides[get_provider] = lambda: provider
        app.dependency_overrides[get_clock] = lambda: lambda: NOW
        return provider

    return install


async def post(client: AsyncClient, **body: Any) -> list[SSEEvent]:
    response = await client.post("/api/chat", json={"language": "fr", **body})
    assert response.status_code == 200, response.text
    return parse_sse(response.text)


def of(events: list[SSEEvent], kind: str) -> list[Any]:
    return [e.data for e in events if e.event == kind]


# --- loop ---------------------------------------------------------------------------------


async def run(provider: ScriptedProvider, max_steps: int = 5) -> list[Any]:
    async with SessionFactory() as session:
        await seed_clinic(session)
        conversation = Conversation(language="fr")
        session.add(conversation)
        await session.flush()
        ctx = ToolContext(Clinic(session, get_settings(), NOW), conversation.id)
        return [
            event
            async for event in run_agent(
                provider,
                system="sys",
                history=[ChatMessage("user", "Je veux voir un cardiologue")],
                ctx=ctx,
                max_steps=max_steps,
                max_tokens=100,
            )
        ]


async def test_loop_runs_tools_and_feeds_results_back() -> None:
    provider = ScriptedProvider(
        [("check_availability", {"specialty": "cardiology", "date_from": "2026-10-23"})],
        "Dr Ben Salah est disponible vendredi à 09:00.",
    )
    events = await run(provider)

    done = events[-1]
    assert isinstance(done, AgentDone)
    assert (done.steps, done.text) == (2, "Dr Ben Salah est disponible vendredi à 09:00.")
    assert (done.input_tokens, done.output_tokens) == (200, 20)
    assert [c["name"] for c in done.tool_calls] == ["check_availability"]

    [result] = provider.tool_results()  # what the model saw on its second call
    assert json.loads(result.content)["slots"][0]["doctor"] == "Dr Amira Ben Salah"
    assert "check_availability" in provider.calls[0][2]  # tools were offered


async def test_tool_errors_are_returned_to_the_model_not_raised() -> None:
    provider = ScriptedProvider([("book_appointment", {"doctor_id": 99})], "Désolé.")
    events = await run(provider)
    [finished] = [e for e in events if isinstance(e, ToolFinished)]
    assert not finished.ok
    assert finished.result["error"] == "invalid_arguments"


async def test_loop_stops_after_max_steps() -> None:
    lookup: Step = [("list_doctors", {})]
    events = await run(ScriptedProvider(lookup, lookup, lookup), max_steps=2)
    done = events[-1]
    assert isinstance(done, AgentDone)
    assert (done.stop_reason, done.text) == ("max_steps", MAX_STEPS_REPLIES["en"])


# --- history ------------------------------------------------------------------------------


def test_stored_tool_calls_replay_as_call_then_result() -> None:
    stored = Message(
        role="assistant",
        content="Voici les créneaux.",
        tool_calls=[{"id": "c1", "name": "list_doctors", "arguments": {}, "result": {"ok": 1}}],
    )
    assert expand(stored) == [
        ChatMessage("assistant", tool_calls=(ToolCall("c1", "list_doctors", {}),)),
        ChatMessage("tool", '{"ok": 1}', tool_call_id="c1"),
        ChatMessage("assistant", "Voici les créneaux."),
    ]


def test_button_press_is_explained_to_the_model() -> None:
    note = action_note(
        {"action_id": "x", "kind": "book", "decision": "confirm", "status": "confirmed"}
    )
    assert note.startswith("[In the app, the patient pressed Confirm on the book card.")
    assert '"status": "confirmed"' in note


def test_calendar_lists_the_next_two_weeks() -> None:
    calendar = format_calendar(NOW.astimezone(ZoneInfo("Africa/Tunis")))
    assert "Now: Wednesday 2026-10-21 09:00 (clinic time)." in calendar
    assert "Thursday 2026-10-22, Friday 2026-10-23" in calendar
    assert calendar.count(", ") == 13  # 14 days


# --- API flow -----------------------------------------------------------------------------


async def test_booking_flow_from_question_to_confirmation(
    client: AsyncClient, use: Install
) -> None:
    provider = use(
        ScriptedProvider(
            [("check_availability", {"specialty": "cardiology", "date_from": "2026-10-23"})],
            [("book_appointment", BOOKING)],
            "Voici le récapitulatif. Appuyez sur Confirmer.",
            "C'est confirmé. Votre code est dans la réponse.",
        )
    )

    first = await post(client, message="RDV cardiologue vendredi 10h, Salma Ben Ali, 20000123")
    tools = of(first, "tool")
    assert [(t["name"], t["status"]) for t in tools] == [
        ("check_availability", "running"),
        ("check_availability", "done"),
        ("book_appointment", "running"),
        ("book_appointment", "done"),
    ]
    [card] = of(first, "confirmation")
    assert (card["kind"], card["status"]) == ("book", "pending")
    assert card["details"]["doctor"] == "Dr Amira Ben Salah"
    assert of(first, "done")

    conversation_id = of(first, "meta")[0]["conversation_id"]
    second = await post(
        client,
        conversation_id=conversation_id,
        message="Confirmer",
        action={"id": card["action_id"], "decision": "confirm"},
    )
    [result] = of(second, "action_result")
    assert (result["status"], result["decision"]) == ("confirmed", "confirm")
    assert result["booking_code"].startswith("RFQ-")
    assert not of(second, "sources")  # a button press is not a document question
    # The model was told about the confirmation, with the booking code.
    last_user = [m for m in provider.calls[-1][1] if m.role == "user"][-1]
    assert result["booking_code"] in last_user.content

    conversation = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assistant = conversation["messages"][1]
    assert assistant["confirmation"]["status"] == "confirmed"
    assert assistant["confirmation"]["result"]["booking_code"] == result["booking_code"]
    assert conversation["messages"][2]["action_result"]["status"] == "confirmed"


async def test_declining_a_card_books_nothing(client: AsyncClient, use: Install) -> None:
    use(ScriptedProvider([("book_appointment", BOOKING)], "Confirmez ?", "D'accord, annulé."))
    first = await post(client, message="Réserver")
    [card] = of(first, "confirmation")
    second = await post(
        client,
        conversation_id=of(first, "meta")[0]["conversation_id"],
        message="Annuler",
        action={"id": card["action_id"], "decision": "decline"},
    )
    assert of(second, "action_result")[0]["status"] == "declined"
    async with SessionFactory() as session:
        assert await session.scalar(select(func.count()).select_from(Appointment)) == 0


async def test_cannot_confirm_a_card_from_another_conversation(
    client: AsyncClient, use: Install
) -> None:
    use(ScriptedProvider([("book_appointment", BOOKING)], "Confirmez ?", "Bonjour"))
    first = await post(client, message="Réserver")
    [card] = of(first, "confirmation")
    stranger = of(await post(client, message="Bonjour"), "meta")[0]["conversation_id"]

    response = await client.post(
        "/api/chat",
        json={
            "conversation_id": stranger,
            "message": "Confirmer",
            "action": {"id": card["action_id"], "decision": "confirm"},
        },
    )
    assert response.status_code == 404


async def test_action_without_conversation_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/chat",
        json={
            "message": "Confirmer",
            "action": {"id": "6f1c2f0e-8a8e-4c41-9d55-1b2f6a1a7c10", "decision": "confirm"},
        },
    )
    assert response.status_code == 422
