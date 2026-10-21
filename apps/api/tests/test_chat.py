import uuid
from collections.abc import AsyncIterator, Sequence

from httpx import AsyncClient

from app.llm import get_provider
from app.llm.base import ChatMessage, LLMError, StreamEvent, TextDelta, ToolSpec
from app.main import app
from tests.conftest import SSEEvent, parse_sse


async def send(
    client: AsyncClient, message: str, conversation_id: str | None = None
) -> list[SSEEvent]:
    payload = {"message": message, "language": "fr", "conversation_id": conversation_id}
    response = await client.post("/api/chat", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


async def test_chat_streams_reply_and_persists_messages(client: AsyncClient) -> None:
    events = await send(client, "Bonjour")

    kinds = [e.event for e in events]
    assert kinds[0] == "meta"
    assert kinds[-1] == "done"
    assert set(kinds[1:-1]) == {"delta"}

    reply = "".join(e.data["text"] for e in events if e.event == "delta")
    assert reply == "Echo (1 messages in context): Bonjour"

    conversation_id = events[0].data["conversation_id"]
    conversation = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert conversation["language"] == "fr"
    assert [(m["role"], m["content"]) for m in conversation["messages"]] == [
        ("user", "Bonjour"),
        ("assistant", reply),
    ]
    assert events[-1].data["message_id"] == conversation["messages"][1]["id"]


async def test_follow_up_message_includes_history(client: AsyncClient) -> None:
    first = await send(client, "Bonjour")
    conversation_id = first[0].data["conversation_id"]

    second = await send(client, "Encore moi", conversation_id)

    assert second[0].data["conversation_id"] == conversation_id
    reply = "".join(e.data["text"] for e in second if e.event == "delta")
    assert reply.startswith("Echo (3 messages in context)")


async def test_unknown_conversation_returns_404(client: AsyncClient) -> None:
    response = await client.post(
        "/api/chat", json={"message": "Hi", "conversation_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404


async def test_blank_message_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 422


async def test_unsupported_language_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/chat", json={"message": "Hola", "language": "es"})
    assert response.status_code == 422


class FailingProvider:
    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        max_tokens: int,
        tools: Sequence[ToolSpec] = (),
    ) -> AsyncIterator[StreamEvent]:
        yield TextDelta("partial ")
        raise LLMError("The assistant is temporarily unavailable. Please try again.")


async def test_provider_error_emits_error_event_and_saves_no_reply(client: AsyncClient) -> None:
    app.dependency_overrides[get_provider] = FailingProvider
    events = await send(client, "Bonjour")

    assert events[-1].event == "error"
    assert "temporarily unavailable" in events[-1].data["message"]

    conversation_id = events[0].data["conversation_id"]
    conversation = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert [m["role"] for m in conversation["messages"]] == ["user"]


async def test_get_unknown_conversation_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/conversations/{uuid.uuid4()}")
    assert response.status_code == 404
