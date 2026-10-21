"""Language-aware text helpers shared by ingestion and search (Arabic, French, English)."""

import re
import unicodedata
from typing import Literal

Language = Literal["ar", "fr", "en"]

_ARABIC_CHAR = re.compile(r"[؀-ۿ]")
_LATIN_CHAR = re.compile(r"[a-zà-ÿ]", re.IGNORECASE)
_WORD = re.compile(r"\w+")
_TATWEEL = "ـ"
_FRENCH_ACCENTS = set("éèêëàâîïôûùç")

# Alef maqsura -> ya, ta marbuta -> ha, Arabic-Indic digits -> ASCII digits.
_LETTER_MAP = str.maketrans(
    {
        "ى": "ي",
        "ة": "ه",
        **{chr(0x0660 + i): str(i) for i in range(10)},
        **{chr(0x06F0 + i): str(i) for i in range(10)},
    }
)
_ARABIC_PREFIXES = ("وال", "بال", "كال", "فال", "ال", "لل")

_FRENCH_HINTS = frozenset(
    "le la les des est et pour vous une du de au aux avec sur pas que qui dans votre nous "
    "sont ou par il elle je mon ma mes combien quel quelle quels quelles comment quand".split()
)
_ENGLISH_HINTS = frozenset(
    "the and is for you your are with of to in we our be not at from this that it "
    "what how much when where which can do does i my me about".split()
)

# Question words and function words that carry no topic. Stored in normalized form.
STOPWORDS = frozenset(
    # French
    "le la les l un une des du de d et ou a au aux en dans pour par sur avec est sont que qui "
    "quoi quel quelle quels quelles comment combien je j vous nous il elle on ce c ca cette ces "
    "mon ma mes votre vos y ne pas plus se s qu me m t te est-ce faut peut puis "
    # English
    "the an and or of to in on for with is are be do does what which how much many when where "
    "who can could i my me you your it this that at from there any"
    # Arabic (MSA and Tunisian Darija), already normalized
    " في من على الي الى عن ما ماذا هل كم كيف متي اين هو هي انا انت انتم هذا هذه ذلك التي الذي "
    "و او ثم مع عند لا نعم يا لي بقداش قداش شنوه شنوة اشنوه وقتاش فما نحب نجم ممكن".split()
)


def normalize(text: str) -> str:
    """Lowercase and fold away differences that should not matter for matching.

    Removes French accents and Arabic diacritics (tashkeel, hamza marks: أ/إ/آ -> ا),
    tatweel, and unifies ى/ي, ة/ه and Arabic-Indic digits.
    """
    decomposed = unicodedata.normalize("NFKD", text.lower().replace(_TATWEEL, ""))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", stripped).translate(_LETTER_MAP)


def _strip_arabic_article(word: str) -> str:
    for prefix in _ARABIC_PREFIXES:
        if word.startswith(prefix) and len(word) - len(prefix) >= 3:
            return word[len(prefix) :]
    return word


def search_tokens(text: str) -> list[str]:
    """Normalized word tokens, with the Arabic definite article removed (الاستشارة -> استشاره)."""
    return [_strip_arabic_article(word) for word in _WORD.findall(normalize(text))]


def to_search_text(text: str) -> str:
    return " ".join(search_tokens(text))


def keyword_tokens(query: str) -> list[str]:
    """Distinct topic words of a query, for keyword search."""
    seen: dict[str, None] = {}
    for token in search_tokens(query):
        if token not in STOPWORDS and (len(token) > 1 or token.isdigit()):
            seen.setdefault(token, None)
    return list(seen)


def guess_language(text: str) -> Language | None:
    """The language of a message, or None without evidence (only names, numbers, shorthand)."""
    arabic = len(_ARABIC_CHAR.findall(text))
    latin = len(_LATIN_CHAR.findall(text))
    if arabic > latin:
        return "ar"
    words = _WORD.findall(text.lower())
    french = sum(w in _FRENCH_HINTS for w in words) + 2 * any(
        c in _FRENCH_ACCENTS for c in text.lower()
    )
    english = sum(w in _ENGLISH_HINTS for w in words)
    if french == english:
        return None
    return "fr" if french > english else "en"


def detect_language(text: str) -> Language:
    """Like guess_language, defaulting to French (the knowledge base's main language)."""
    return guess_language(text) or "fr"
