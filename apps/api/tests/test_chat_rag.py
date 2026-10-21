from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.config import Settings, get_settings
from app.core.db import SessionFactory
from app.llm import get_provider
from app.llm.base import ChatMessage, StreamEnd, StreamEvent, TextDelta, Usage
from app.main import app
from app.rag.embeddings import EmbeddingError, FakeEmbedder, get_embedder
from app.rag.ingest import ingest_directory
from app.rag.query import QUERY_PROMPT, build_query_request, parse_queries
from app.rag.retrieve import retrieval_query
from tests.conftest import parse_sse

TARIFS = """---
title: Tarifs
---
# Consultations

Cardiologie : 80 DT. Médecine générale : 45 DT.
"""


class CapturingProvider:
    """Records system prompts; answers query translation with `translation`, else cites [1]."""

    def __init__(self, translation: str = "not json") -> None:
        self.systems: list[str] = []
        self.translation = translation

    @property
    def answer_system(self) -> str:
        [system] = [s for s in self.systems if s != QUERY_PROMPT]
        return system

    async def stream(
        self, *, system: str, messages: Sequence[ChatMessage], max_tokens: int
    ) -> AsyncIterator[StreamEvent]:
        self.systems.append(system)
        reply = self.translation if system == QUERY_PROMPT else "La cardiologie coûte 80 DT [1]."
        yield TextDelta(reply)
        yield StreamEnd(model="capture", usage=Usage(10, 5), stop_reason="end_turn")


@pytest.fixture
async def ingested(tmp_path: Path) -> None:
    (tmp_path / "tarifs.md").write_text(TARIFS, encoding="utf-8")
    async with SessionFactory() as session:
        await ingest_directory(session, FakeEmbedder(), tmp_path)


async def test_chat_streams_sources_and_grounds_the_prompt(
    client: AsyncClient, ingested: None
) -> None:
    provider = CapturingProvider()
    app.dependency_overrides[get_provider] = lambda: provider

    response = await client.post(
        "/api/chat", json={"message": "Combien coûte la cardiologie ?", "language": "fr"}
    )
    events = parse_sse(response.text)

    assert [e.event for e in events][:2] == ["meta", "sources"]
    [source] = events[1].data
    assert source["n"] == 1
    assert (source["source"], source["section"], source["lang"]) == (
        "tarifs.md",
        "Consultations",
        "fr",
    )
    assert "80 DT" in source["excerpt"]

    system = provider.answer_system
    assert "<documents>\n[1] tarifs.md (Consultations)\n" in system
    assert "80 DT" in system

    conversation_id = events[0].data["conversation_id"]
    conversation = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assistant = conversation["messages"][1]
    assert assistant["sources"] == events[1].data
    assert conversation["messages"][0]["sources"] is None


async def test_chat_without_knowledge_base_sends_no_sources(client: AsyncClient) -> None:
    provider = CapturingProvider()
    app.dependency_overrides[get_provider] = lambda: provider

    response = await client.post("/api/chat", json={"message": "Bonjour"})

    assert "sources" not in [e.event for e in parse_sse(response.text)]
    assert "(no matching excerpts)" in provider.answer_system


async def test_retrieval_failure_degrades_to_no_sources(
    client: AsyncClient, ingested: None
) -> None:
    class BrokenEmbedder(FakeEmbedder):
        async def embed(self, texts: Sequence[str]) -> list[list[float]]:
            raise EmbeddingError("down")

    app.dependency_overrides[get_embedder] = BrokenEmbedder
    response = await client.post("/api/chat", json={"message": "cardiologie"})

    kinds = [e.event for e in parse_sse(response.text)]
    assert "sources" not in kinds
    assert kinds[-1] == "done"


def test_short_follow_up_reuses_the_previous_question() -> None:
    history = [
        ChatMessage("user", "Combien coûte une consultation de cardiologie ?"),
        ChatMessage("assistant", "80 DT [1]."),
        ChatMessage("user", "Et en pédiatrie ?"),
    ]
    assert retrieval_query(history, "Et en pédiatrie ?") == (
        "Combien coûte une consultation de cardiologie ?\nEt en pédiatrie ?"
    )
    long_question = "Quels documents faut-il apporter pour une première consultation ?"
    assert retrieval_query([*history, ChatMessage("user", long_question)], long_question) == (
        long_question
    )


FAQ_AR = """---
title: الأسئلة الشائعة
---
# هل يجب استشارة طبيب قبل التحليل؟

نعم، يُنصح باستشارة طبيب قبل التحليل.
"""

ARABIC_PRICE_QUESTION = "بقداش الاستشارة عند طبيب القلب؟"
TRANSLATION = (
    '{"fr": "Combien coûte la cardiologie ?", "en": "How much does cardiologie cost?", '
    f'"ar": "{ARABIC_PRICE_QUESTION}"}}'
)


@pytest.fixture
async def bilingual_kb(tmp_path: Path) -> None:
    (tmp_path / "tarifs.md").write_text(TARIFS, encoding="utf-8")
    (tmp_path / "faq.md").write_text(FAQ_AR, encoding="utf-8")
    async with SessionFactory() as session:
        await ingest_directory(session, FakeEmbedder(), tmp_path)


async def first_source(client: AsyncClient, provider: CapturingProvider) -> str:
    app.dependency_overrides[get_provider] = lambda: provider
    response = await client.post(
        "/api/chat", json={"message": ARABIC_PRICE_QUESTION, "language": "ar"}
    )
    [sources] = [e.data for e in parse_sse(response.text) if e.event == "sources"]
    return str(sources[0]["source"])


async def test_query_translation_finds_french_facts_for_arabic_questions(
    client: AsyncClient, bilingual_kb: None
) -> None:
    assert await first_source(client, CapturingProvider(translation=TRANSLATION)) == "tarifs.md"


async def test_without_translation_the_arabic_question_stays_in_arabic_documents(
    client: AsyncClient, bilingual_kb: None
) -> None:
    settings = Settings(_env_file=None, llm_provider="fake", rag_translate_queries=False)
    app.dependency_overrides[get_settings] = lambda: settings
    provider = CapturingProvider(translation=TRANSLATION)

    assert await first_source(client, provider) == "faq.md"
    assert QUERY_PROMPT not in provider.systems


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (
            '{"fr": "Prix ?", "en": "Price?", "ar": "السعر؟"}',
            {"fr": "Prix ?", "en": "Price?", "ar": "السعر؟"},
        ),
        ('```json\n{"fr": "Prix ?", "en": " "}\n```', {"fr": "Prix ?"}),  # fenced, blank dropped
        ('{"fr": "Prix ?", "en": "Prix ?"}', {"fr": "Prix ?"}),  # duplicates dropped
        ("Sorry, I can't help.", {}),
        ('{"fr": 3}', {}),
        ("[1, 2]", {}),
    ],
)
def test_parse_queries(reply: str, expected: dict[str, str]) -> None:
    assert parse_queries(reply) == expected


def test_query_request_separates_the_latest_message_from_the_context() -> None:
    history = [
        ChatMessage("user", "Combien coûte le dentiste ?"),
        ChatMessage("assistant", "50 DT [1]."),
        ChatMessage("user", "Mutuelle Yasmine + cardiology"),
    ]
    request = build_query_request(history)
    context, latest = request.split("Latest message to rewrite:")
    assert "Patient: Combien coûte le dentiste ?" in context
    assert "Receptionist: 50 DT [1]." in context
    assert latest.strip() == "Mutuelle Yasmine + cardiology"
    assert "(none)" in build_query_request([ChatMessage("user", "Bonjour")])
