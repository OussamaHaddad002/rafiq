import pytest

from app.agent.chat import normalize_history
from app.agent.prompts import build_system_prompt, reply_language
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


def test_system_prompt_names_the_reply_language() -> None:
    assert "Reply in Arabic" in build_system_prompt("ar")
    assert "Reply in English" in build_system_prompt("xx")


@pytest.mark.parametrize(
    ("message", "ui", "expected"),
    [
        ("بقداش الاستشارة عند طبيب الأسنان؟", "en", "ar"),
        ("Et pour une échographie ?", "en", "fr"),
        ("How much is a dentist?", "fr", "en"),
        # Shorthand with only names and a medical term: follow the interface language.
        ("Mutuelle Yasmine + cardiology", "en", "en"),
        ("Mutuelle Yasmine + cardiology", "ar", "ar"),
        ("ECG ?", "fr", "fr"),
    ],
)
def test_reply_language(message: str, ui: str, expected: str) -> None:
    assert reply_language(message, ui) == expected
