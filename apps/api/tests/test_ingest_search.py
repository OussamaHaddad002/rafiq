from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionFactory
from app.models import Chunk, Document
from app.rag.embeddings import FakeEmbedder
from app.rag.ingest import ingest_directory
from app.rag.search import reciprocal_rank_fusion, search

TARIFS = """---
title: Tarifs
---
# Consultations

Cardiologie : 80 DT. Médecine générale : 45 DT.
"""

FAQ = """---
title: الأسئلة الشائعة
---
# هل يوجد واي فاي؟

نعم، شبكة الواي فاي المجانية اسمها Rafiq-Patients.
"""

POLICIES = """# Cancellation policy

Cancel at least 24 hours before your appointment. Late cancellations cost 20 DT.
"""


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as s:
        yield s


@pytest.fixture
def kb(tmp_path: Path) -> Path:
    (tmp_path / "tarifs.md").write_text(TARIFS, encoding="utf-8")
    (tmp_path / "faq.md").write_text(FAQ, encoding="utf-8")
    (tmp_path / "policies.md").write_text(POLICIES, encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored: unsupported type", encoding="utf-8")
    return tmp_path


def test_rrf_rewards_items_ranked_high_by_both_retrievers() -> None:
    fused = reciprocal_rank_fusion([[1, 2, 3], [3, 1]])
    assert [item for item, _ in fused] == [1, 3, 2]


async def test_ingest_is_idempotent_and_tracks_changes(kb: Path, session: AsyncSession) -> None:
    embedder = FakeEmbedder()

    first = await ingest_directory(session, embedder, kb)
    assert sorted(first.added) == ["faq.md", "policies.md", "tarifs.md"]
    assert first.chunks == 3

    second = await ingest_directory(session, embedder, kb)
    assert (second.added, second.updated, len(second.unchanged)) == ([], [], 3)

    (kb / "tarifs.md").write_text(TARIFS.replace("80 DT", "85 DT"), encoding="utf-8")
    (kb / "policies.md").unlink()
    third = await ingest_directory(session, embedder, kb)
    assert (third.updated, third.removed) == (["tarifs.md"], ["policies.md"])

    assert await session.scalar(select(func.count()).select_from(Document)) == 2
    assert await session.scalar(select(func.count()).select_from(Chunk)) == 2
    contents = list(await session.scalars(select(Chunk.content)))
    assert any("85 DT" in c for c in contents)
    assert not any("80 DT" in c for c in contents)


async def test_search_finds_the_matching_document_in_each_language(
    kb: Path, session: AsyncSession
) -> None:
    embedder = FakeEmbedder()
    await ingest_directory(session, embedder, kb)

    cases = {
        "Combien coûte la cardiologie ?": "tarifs.md",
        "هل يوجد واي فاي في العيادة؟": "faq.md",
        "What is the late cancellation fee?": "policies.md",
    }
    for query, expected in cases.items():
        results = await search(session, embedder, [query], k=1)
        assert results[0].source == expected, query


async def test_search_returns_citation_metadata(kb: Path, session: AsyncSession) -> None:
    await ingest_directory(session, FakeEmbedder(), kb)

    [top] = await search(session, FakeEmbedder(), ["cardiologie"], k=1)

    assert (top.source, top.title, top.section, top.lang) == (
        "tarifs.md",
        "Tarifs",
        "Consultations",
        "fr",
    )
    assert "80 DT" in top.content
    assert top.score > 0


async def test_search_ignores_chunks_from_another_embedding_model(
    kb: Path, session: AsyncSession
) -> None:
    await ingest_directory(session, FakeEmbedder(), kb)

    class OtherModel(FakeEmbedder):
        model = "other-model"

    assert await search(session, OtherModel(), ["cardiologie"], k=3) == []
