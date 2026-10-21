import json
from pathlib import Path

import pytest

from app.agent.history import normalize_history
from app.agent.prompts import BUTTON_LABELS, build_system_prompt, reply_language
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


def test_button_labels_match_the_card_translations() -> None:
    """The prompt names the card's buttons; they must say exactly what the UI shows."""
    locales = Path(__file__).resolve().parents[2] / "web/src/i18n/locales"
    for language, (confirm, cancel) in BUTTON_LABELS.items():
        card = json.loads((locales / f"{language}.json").read_text(encoding="utf-8"))["card"]
        assert (card["confirm"]["book"], card["confirm"]["cancel"]) == (confirm, cancel)


def test_prompt_names_buttons_in_the_interface_language() -> None:
    prompt = build_system_prompt("en", ui_language="fr")
    assert 'press "Confirmer"' in prompt
    assert "Reply in English" in prompt
