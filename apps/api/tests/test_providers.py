"""Provider adapters against recorded-shape streaming responses (no network)."""

import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from openai.types.responses import ResponseFunctionToolCall

from app.llm.anthropic_provider import AnthropicProvider
from app.llm.anthropic_provider import to_messages as anthropic_to_messages
from app.llm.base import (
    ChatMessage,
    LLMError,
    LLMProvider,
    StreamEnd,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolSpec,
)
from app.llm.openai_provider import OpenAIProvider, parse_tool_call
from app.llm.openai_provider import to_input as openai_to_input

MESSAGES = [ChatMessage("user", "Bonjour")]


def sse(*events: dict[str, Any]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def mock_client(
    body: bytes, status: int = 200, captured: list[httpx2.Request] | None = None
) -> httpx2.AsyncClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if captured is not None:
            captured.append(request)
        content_type = "text/event-stream" if status == 200 else "application/json"
        return httpx2.Response(status, content=body, headers={"content-type": content_type})

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


async def collect(provider: LLMProvider) -> list[StreamEvent]:
    return [e async for e in provider.stream(system="sys", messages=MESSAGES, max_tokens=100)]


def openai_completed(status: str = "completed", incomplete: str | None = None) -> dict[str, Any]:
    return {
        "type": f"response.{status}",
        "sequence_number": 9,
        "response": {
            "id": "resp_1",
            "object": "response",
            "created_at": 0,
            "model": "gpt-4o-mini-2024-07-18",
            "status": status,
            "output": [],
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "incomplete_details": {"reason": incomplete} if incomplete else None,
            "usage": {
                "input_tokens": 20,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens": 5,
                "output_tokens_details": {"reasoning_tokens": 2},
                "total_tokens": 25,
            },
        },
    }


def openai_delta(text: str) -> dict[str, Any]:
    return {
        "type": "response.output_text.delta",
        "item_id": "msg_1",
        "output_index": 0,
        "content_index": 0,
        "delta": text,
        "sequence_number": 1,
        "logprobs": [],
    }


OpenAIFactory = Callable[[httpx2.AsyncClient], OpenAIProvider]


@pytest.fixture
def make_openai() -> OpenAIFactory:
    return lambda client: OpenAIProvider(api_key="test", model="gpt-4o-mini", http_client=client)


async def test_openai_streams_text_and_usage(make_openai: OpenAIFactory) -> None:
    captured: list[httpx2.Request] = []
    body = sse(openai_delta("Bon"), openai_delta("jour"), openai_completed())

    events = await collect(make_openai(mock_client(body, captured=captured)))

    assert events == [
        TextDelta("Bon"),
        TextDelta("jour"),
        StreamEnd(
            model="gpt-4o-mini-2024-07-18",
            usage=events[-1].usage,  # type: ignore[union-attr]
            stop_reason="completed",
        ),
    ]
    end = events[-1]
    assert isinstance(end, StreamEnd)
    assert (end.usage.input_tokens, end.usage.output_tokens) == (20, 5)

    sent = json.loads(captured[0].content)
    assert sent["model"] == "gpt-4o-mini"
    assert sent["instructions"] == "sys"
    assert sent["input"] == [{"role": "user", "content": "Bonjour"}]
    assert sent["max_output_tokens"] == 100
    assert sent["store"] is False
    assert "reasoning" not in sent
    assert sent["stream"] is True


async def test_openai_incomplete_response_still_ends_the_stream(
    make_openai: OpenAIFactory,
) -> None:
    body = sse(openai_delta("Bon"), openai_completed("incomplete", "max_output_tokens"))
    events = await collect(make_openai(mock_client(body)))
    end = events[-1]
    assert isinstance(end, StreamEnd)
    assert end.stop_reason == "max_output_tokens"


async def test_openai_failed_response_raises(make_openai: OpenAIFactory) -> None:
    failed = openai_completed("failed")
    with pytest.raises(LLMError):
        await collect(make_openai(mock_client(sse(failed))))


async def test_openai_http_error_raises(make_openai: OpenAIFactory) -> None:
    body = json.dumps({"error": {"message": "bad key", "type": "invalid_request_error"}}).encode()
    with pytest.raises(LLMError):
        await collect(make_openai(mock_client(body, status=401)))


async def test_openai_sends_reasoning_effort_to_reasoning_models() -> None:
    captured: list[httpx2.Request] = []
    client = mock_client(sse(openai_completed()), captured=captured)
    provider = OpenAIProvider(
        api_key="test", model="o4-mini", reasoning_effort="low", http_client=client
    )
    await collect(provider)
    assert json.loads(captured[0].content)["reasoning"] == {"effort": "low"}


async def test_anthropic_streams_text_and_usage() -> None:
    body = sse(
        {
            "type": "message_start",
            "message": {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5-5",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 20, "output_tokens": 1},
            },
        },
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Bon"}},
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "jour"},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 5},
        },
        {"type": "message_stop"},
    )
    provider = AnthropicProvider(
        api_key="test", model="claude-sonnet-5-5", http_client=mock_client(body)
    )

    events = await collect(provider)

    assert events[:2] == [TextDelta("Bon"), TextDelta("jour")]
    end = events[-1]
    assert isinstance(end, StreamEnd)
    assert (end.model, end.stop_reason) == ("claude-sonnet-5-5", "end_turn")
    assert (end.usage.input_tokens, end.usage.output_tokens) == (20, 5)


# --- tool calling -------------------------------------------------------------------------

TOOLS = [ToolSpec("list_doctors", "List doctors.", {"type": "object", "properties": {}})]
CALL = ToolCall("call_abc", "list_doctors", {"specialty": "cardiology"})
HISTORY = [
    ChatMessage("user", "Cardiologues ?"),
    ChatMessage("assistant", tool_calls=(CALL,)),
    ChatMessage("tool", '{"doctors": []}', tool_call_id="call_abc"),
    ChatMessage("assistant", "Aucun."),
    ChatMessage("user", "Merci"),
]


def test_openai_history_maps_to_function_call_items() -> None:
    assert openai_to_input(HISTORY) == [
        {"role": "user", "content": "Cardiologues ?"},
        {
            "type": "function_call",
            "call_id": "call_abc",
            "name": "list_doctors",
            "arguments": '{"specialty": "cardiology"}',
        },
        {"type": "function_call_output", "call_id": "call_abc", "output": '{"doctors": []}'},
        {"role": "assistant", "content": "Aucun."},
        {"role": "user", "content": "Merci"},
    ]


async def test_openai_returns_tool_calls_from_the_response(make_openai: OpenAIFactory) -> None:
    completed = openai_completed()
    completed["response"]["output"] = [
        {
            "type": "function_call",
            "id": "fc_1",
            "call_id": "call_abc",
            "name": "list_doctors",
            "arguments": '{"specialty": "cardiology"}',
            "status": "completed",
        }
    ]
    captured: list[httpx2.Request] = []
    provider = make_openai(mock_client(sse(completed), captured=captured))

    events = [
        e
        async for e in provider.stream(system="sys", messages=HISTORY, max_tokens=100, tools=TOOLS)
    ]

    end = events[-1]
    assert isinstance(end, StreamEnd)
    assert end.tool_calls == (CALL,)
    sent = json.loads(captured[0].content)
    assert sent["tools"] == [
        {
            "type": "function",
            "name": "list_doctors",
            "description": "List doctors.",
            "parameters": {"type": "object", "properties": {}},
            "strict": False,
        }
    ]


def test_openai_malformed_arguments_reach_the_tool_for_validation() -> None:
    item = ResponseFunctionToolCall(
        type="function_call", call_id="c", name="list_doctors", arguments="{not json"
    )
    assert parse_tool_call(item).arguments == {"_unparsed": "{not json"}


def test_anthropic_merges_tool_results_with_the_next_user_turn() -> None:
    history = [*HISTORY[:3], ChatMessage("user", "Et demain ?")]
    assert anthropic_to_messages(history) == [
        {"role": "user", "content": [{"type": "text", "text": "Cardiologues ?"}]},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "call_abc",
                    "name": "list_doctors",
                    "input": {"specialty": "cardiology"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_abc", "content": '{"doctors": []}'},
                {"type": "text", "text": "Et demain ?"},
            ],
        },
    ]


async def test_anthropic_returns_tool_calls_from_the_stream() -> None:
    body = sse(
        {
            "type": "message_start",
            "message": {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5-5",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 30, "output_tokens": 1},
            },
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "tool_use",
                "id": "call_abc",
                "name": "list_doctors",
                "input": {},
            },
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"specialty": "cardiology"}'},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use", "stop_sequence": None},
            "usage": {"output_tokens": 12},
        },
        {"type": "message_stop"},
    )
    provider = AnthropicProvider(
        api_key="test", model="claude-sonnet-5-5", http_client=mock_client(body)
    )

    events = [
        e
        async for e in provider.stream(system="sys", messages=MESSAGES, max_tokens=100, tools=TOOLS)
    ]

    end = events[-1]
    assert isinstance(end, StreamEnd)
    assert (end.stop_reason, end.tool_calls) == ("tool_use", (CALL,))
