from app.agent.chat import normalize_history
from app.agent.prompts import build_system_prompt
from app.llm.base import ChatMessage


def test_drops_leading_assistant_turns() -> None:
    history = [ChatMessage("assistant", "cut off"), ChatMessage("user", "hi")]
    assert normalize_history(history) == [ChatMessage("user", "hi")]


def test_merges_consecutive_turns_from_same_role() -> None:
    history = [
        ChatMessage("user", "first"),
        ChatMessage("user", "second"),
        ChatMessage("assistant", "reply"),
    ]
    assert normalize_history(history) == [
        ChatMessage("user", "first\n\nsecond"),
        ChatMessage("assistant", "reply"),
    ]


def test_keeps_valid_alternating_history() -> None:
    history = [ChatMessage("user", "a"), ChatMessage("assistant", "b"), ChatMessage("user", "c")]
    assert normalize_history(history) == history


def test_system_prompt_uses_ui_language_as_fallback() -> None:
    assert "reply in Arabic" in build_system_prompt("ar")
    assert "reply in English" in build_system_prompt("xx")
