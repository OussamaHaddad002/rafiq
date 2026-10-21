from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import ChatMessage, LLMProvider
from app.rag.embeddings import Embedder
from app.rag.query import translate_query
from app.rag.search import RetrievedChunk, search
from app.rag.text import detect_language


def retrieval_query(history: Sequence[ChatMessage], user_text: str) -> str:
    """Short follow-ups ("and for children?") borrow context from the previous question."""
    if len(user_text.split()) < 6:
        earlier = [m.content for m in history[:-1] if m.role == "user"]
        if earlier:
            return f"{earlier[-1]}\n{user_text}"
    return user_text


async def retrieve(
    *,
    session: AsyncSession,
    embedder: Embedder,
    provider: LLMProvider,
    history: Sequence[ChatMessage],
    user_text: str,
    k: int,
    translate: bool,
) -> list[RetrievedChunk]:
    """Search with one standalone question per language (fr/en/ar) when translation is on.

    The rewrite in the patient's own language replaces their raw words: it resolves
    follow-ups, and keeping both would give that language two votes in the fusion and drown
    out documents written in the other languages. `history` ends with the latest user message.
    """
    original = retrieval_query(history, user_text)
    translations = await translate_query(provider, history) if translate else {}
    if not translations:
        return await search(session, embedder, [original], k)
    own_language = detect_language(user_text)
    queries = [translations.get(own_language, original)]
    queries += [q for language, q in translations.items() if language != own_language]
    return await search(session, embedder, queries, k)
