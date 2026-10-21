import hashlib
import logging
import math
from collections.abc import Sequence
from functools import lru_cache
from itertools import batched
from typing import Annotated, Protocol

import httpx2
import openai
from fastapi import Depends

from app.core.config import get_settings
from app.llm import require_key
from app.models import EMBEDDING_DIM
from app.rag.text import search_tokens

logger = logging.getLogger(__name__)

_BATCH_SIZE = 128


class EmbeddingError(Exception):
    pass


class Embedder(Protocol):
    model: str

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    def __init__(
        self, *, api_key: str, model: str, http_client: httpx2.AsyncClient | None = None
    ) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key, http_client=http_client)
        self.model = model

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        try:
            for batch in batched(texts, _BATCH_SIZE, strict=False):
                response = await self._client.embeddings.create(
                    model=self.model, input=list(batch), dimensions=EMBEDDING_DIM
                )
                vectors.extend(
                    item.embedding for item in sorted(response.data, key=lambda d: d.index)
                )
                logger.info(
                    "embeddings",
                    extra={"fields": {"model": self.model, "tokens": response.usage.total_tokens}},
                )
        except openai.OpenAIError as exc:
            raise EmbeddingError("Embedding request failed") from exc
        return vectors


class FakeEmbedder:
    """Hashed bag of words: offline and deterministic, yet texts sharing words still rank close.

    Used in tests, CI and keyless demos. It has no cross-lingual ability.
    """

    model = "fake-hashed-bow-v1"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    @staticmethod
    def _vector(text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIM
        for token in search_tokens(text):
            digest = hashlib.blake2b(token.encode(), digest_size=4).digest()
            vector[int.from_bytes(digest) % EMBEDDING_DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0:  # cosine distance is undefined for the zero vector
            vector[0], norm = 1.0, 1.0
        return [x / norm for x in vector]


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    if settings.resolved_embedding_provider == "fake":
        return FakeEmbedder()
    return OpenAIEmbedder(
        api_key=require_key(settings.openai_api_key, "OPENAI_API_KEY", "embeddings"),
        model=settings.embedding_model,
    )


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
