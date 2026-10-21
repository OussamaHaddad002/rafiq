"""Stored messages -> model input, including past tool calls and Confirm / Cancel presses."""

import json
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import ChatMessage, ToolCall
from app.models import Message


def _is_plain(message: ChatMessage) -> bool:
    return message.role != "tool" and not message.tool_calls


def normalize_history(messages: Sequence[ChatMessage]) -> list[ChatMessage]:
    """Make stored history valid model input.

    The history must start with a user turn (truncation can cut it mid-exchange), and
    consecutive plain turns from the same role are merged (a failed or interrupted reply
    leaves two user messages in a row). Tool calls and results are never merged.
    """
    normalized: list[ChatMessage] = []
    for message in messages:
        if not normalized and message.role != "user":
            continue
        previous = normalized[-1] if normalized else None
        if (
            previous
            and previous.role == message.role
            and _is_plain(previous)
            and _is_plain(message)
        ):
            normalized[-1] = ChatMessage(message.role, f"{previous.content}\n\n{message.content}")
            continue
        normalized.append(message)
    return normalized


def action_note(result: dict[str, Any]) -> str:
    """What the model learns when the patient presses Confirm / Cancel on a card."""
    pressed = "Confirm" if result.get("decision") == "confirm" else "Cancel"
    outcome = {k: v for k, v in result.items() if k not in ("action_id", "decision")}
    return (
        f"[In the app, the patient pressed {pressed} on the {result.get('kind', '')} card. "
        f"Result: {json.dumps(outcome, ensure_ascii=False)}]"
    )


def expand(message: Message) -> list[ChatMessage]:
    if message.role == "user":
        content = message.content
        if message.action_result:
            content = f"{content}\n\n{action_note(message.action_result)}"
        return [ChatMessage("user", content)]
    items: list[ChatMessage] = []
    if message.tool_calls:
        items.append(
            ChatMessage(
                "assistant",
                tool_calls=tuple(
                    ToolCall(c["id"], c["name"], c["arguments"]) for c in message.tool_calls
                ),
            )
        )
        items.extend(
            ChatMessage("tool", json.dumps(c["result"], ensure_ascii=False), tool_call_id=c["id"])
            for c in message.tool_calls
        )
    if message.content:
        items.append(ChatMessage("assistant", message.content))
    return items


async def load_history(
    session: AsyncSession, conversation_id: uuid.UUID, limit: int
) -> list[ChatMessage]:
    """The last `limit` stored messages, expanded. Limits apply to whole stored messages,
    so a tool call is never separated from its result."""
    rows = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )
    return normalize_history([item for m in reversed(rows.all()) for item in expand(m)])
