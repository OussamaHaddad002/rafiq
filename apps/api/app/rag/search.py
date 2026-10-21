"""Hybrid retrieval: vector similarity + keyword match, fused with Reciprocal Rank Fusion."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Document
from app.rag.embeddings import Embedder
from app.rag.text import keyword_tokens

CANDIDATES = 20  # per retriever, before fusion
RRF_K = 60  # standard constant from the RRF paper; dampens the weight of top ranks


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: int
    source: str
    title: str
    page: int | None
    section: str | None
    lang: str
    content: str
    score: float


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[int]], k: int = RRF_K
) -> list[tuple[int, float]]:
    """Merge ranked id lists: each list adds 1 / (k + rank) to an id's score. Best first."""
    scores: defaultdict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


async def search(
    session: AsyncSession, embedder: Embedder, queries: list[str], k: int
) -> list[RetrievedChunk]:
    """Each query (e.g. the question and its translations) adds a vector and a keyword ranking."""
    vectors = await embedder.embed(queries)
    current_model = Document.embedding_model == embedder.model
    rankings: list[list[int]] = []

    for vector in vectors:
        rankings.append(
            list(
                await session.scalars(
                    select(Chunk.id)
                    .join(Document)
                    .where(current_model)
                    .order_by(Chunk.embedding.cosine_distance(vector))
                    .limit(CANDIDATES)
                )
            )
        )

    for query in queries:
        if not (tokens := keyword_tokens(query)):
            continue
        ts_query = func.to_tsquery("simple", " | ".join(tokens))
        rankings.append(
            list(
                await session.scalars(
                    select(Chunk.id)
                    .join(Document)
                    .where(current_model, Chunk.search_vector.op("@@")(ts_query))
                    .order_by(func.ts_rank_cd(Chunk.search_vector, ts_query).desc(), Chunk.id)
                    .limit(CANDIDATES)
                )
            )
        )

    ranked = reciprocal_rank_fusion(rankings)[:k]
    if not ranked:
        return []
    rows = await session.execute(
        select(Chunk, Document.source, Document.title)
        .join(Document)
        .where(Chunk.id.in_([chunk_id for chunk_id, _ in ranked]))
    )
    by_id = {chunk.id: (chunk, source, title) for chunk, source, title in rows}
    results: list[RetrievedChunk] = []
    for chunk_id, score in ranked:
        chunk, source, title = by_id[chunk_id]
        results.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                source=source,
                title=title,
                page=chunk.page,
                section=chunk.section,
                lang=chunk.lang,
                content=chunk.content,
                score=score,
            )
        )
    return results
