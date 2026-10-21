import pytest

from app.rag.text import (
    detect_language,
    guess_language,
    keyword_tokens,
    normalize,
    search_tokens,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Électrocardiogramme à jeun", "electrocardiogramme a jeun"),
        ("أَسْعَار", "اسعار"),  # tashkeel and hamza removed
        ("إستشارة", "استشاره"),  # hamza below + ta marbuta
        ("مستشفى", "مستشفي"),  # alef maqsura
        ("٤٥ دينار", "45 دينار"),  # Arabic-Indic digits
        ("مـــرحبا", "مرحبا"),  # tatweel
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_arabic_article_is_removed_so_definite_and_bare_forms_match() -> None:
    assert search_tokens("الاستشارة") == search_tokens("استشارة") == ["استشاره"]
    assert search_tokens("بالبطاقة") == ["بطاقه"]


def test_short_words_keep_their_prefix_letters() -> None:
    assert search_tokens("الم") == ["الم"]  # pain: too short to be "article + word"


def test_keyword_tokens_drop_question_words_and_duplicates() -> None:
    assert keyword_tokens("Combien coûte une consultation de cardiologie ?") == [
        "coute",
        "consultation",
        "cardiologie",
    ]
    assert keyword_tokens("بقداش الاستشارة عند طبيب الأسنان؟") == ["استشاره", "طبيب", "اسنان"]
    assert keyword_tokens("What are the opening hours? hours") == ["opening", "hours"]


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Les tarifs des consultations sont affichés à l'accueil.", "fr"),
        ("Please bring your ID card and insurance documents.", "en"),
        ("هل يجب حجز موعد مسبقًا؟", "ar"),
        ("Horaires : 8h00-19h00", "fr"),
    ],
)
def test_detect_language(text: str, language: str) -> None:
    assert detect_language(text) == language


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Mutuelle Yasmine + cardiology", None),
        ("Dr Amira Ben Salah", None),
        ("80 DT", None),
        ("What about children?", "en"),
        ("Combien pour le dentiste", "fr"),
    ],
)
def test_guess_language_is_none_without_evidence(text: str, language: str | None) -> None:
    assert guess_language(text) == language
