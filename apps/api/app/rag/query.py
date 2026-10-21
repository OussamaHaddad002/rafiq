"""Query translation: search in every knowledge-base language, not just the patient's.

Embeddings rank documents in the query's own language first, so an Arabic question about a
price that only appears in a French PDF tends to retrieve the Arabic FAQ instead. A small LLM
call rewrites the latest message as a standalone question in French, English and Arabic, and
search then fuses the results of all versions.
"""

import json
import logging
from collections.abc import Sequence

from app.llm.base import ChatMessage, LLMError, LLMProvider, complete
from app.rag.text import Language

logger = logging.getLogger(__name__)

QUERY_PROMPT = """\
You prepare search queries for a clinic's documents, which are written in French, English \
and Arabic.

Rewrite ONLY the patient's latest message as one standalone question. Use the earlier \
conversation only to fill in what the latest message leaves implicit (the insurer, the \
specialty, the exam...); never rewrite an earlier question instead. Understand Maghrebi Arabic \
dialect and shorthand. Keep names, numbers and medical terms. Then translate the question.

Examples:
- Latest "Mutuelle Yasmine + cardiology" -> "How much do I pay for a cardiology consultation \
with Mutuelle Yasmine?"
- After a question about Mutuelle Yasmine, latest "and for an ultrasound?" -> "How much do I \
pay for an ultrasound with Mutuelle Yasmine?"
- After a question about cardiology prices, latest "and for children?" -> "How much is a \
paediatric consultation?"

Reply with JSON only, no other text: {"fr": "...", "en": "...", "ar": "..."}
"""

_LANGUAGES: tuple[Language, ...] = ("fr", "en", "ar")
_EARLIER_TURNS = 4  # messages before the latest one, used to resolve follow-ups
_MAX_CHARS_PER_TURN = 300


def build_query_request(history: Sequence[ChatMessage]) -> str:
    """Earlier turns as context, then the latest user message, clearly separated."""
    *earlier, latest = history
    lines = []
    for message in earlier[-_EARLIER_TURNS:]:
        speaker = "Patient" if message.role == "user" else "Receptionist"
        lines.append(f"{speaker}: {message.content[:_MAX_CHARS_PER_TURN]}")
    context = "\n".join(lines) or "(none)"
    return f"Earlier conversation:\n{context}\n\nLatest message to rewrite:\n{latest.content}"


def parse_queries(text: str) -> dict[Language, str]:
    """Question per language from the model's JSON reply; empty if it is not valid."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    queries: dict[Language, str] = {}
    for language in _LANGUAGES:
        value = data.get(language)
        if isinstance(value, str) and value.strip() and value.strip() not in queries.values():
            queries[language] = value.strip()
    return queries


async def translate_query(
    provider: LLMProvider, history: Sequence[ChatMessage]
) -> dict[Language, str]:
    """Standalone versions of the latest user message in fr/en/ar; empty on any failure."""
    try:
        text, end = await complete(
            provider,
            system=QUERY_PROMPT,
            messages=[ChatMessage("user", build_query_request(history))],
            max_tokens=300,
        )
    except LLMError:
        logger.warning("query_translation_failed", exc_info=True)
        return {}
    queries = parse_queries(text)
    logger.info(
        "query_translation",
        extra={
            "fields": {
                "queries": queries,
                "input_tokens": end.usage.input_tokens if end else None,
                "output_tokens": end.usage.output_tokens if end else None,
            }
        },
    )
    return queries
