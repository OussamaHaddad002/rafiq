"""Load the knowledge base into Postgres: parse -> chunk -> embed -> store.

Run: python -m app.rag.ingest [DIRECTORY] [--keep-missing]
"""

import argparse
import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import SessionFactory, engine
from app.core.logging import configure_logging
from app.models import Chunk, Document
from app.rag.chunking import ChunkDraft, chunk_document
from app.rag.embeddings import Embedder, get_embedder
from app.rag.parsing import parse_file
from app.rag.text import to_search_text

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".md", ".pdf"}
# Bump when parsing or chunking changes, so unchanged files are re-processed too.
PIPELINE_VERSION = "3"


@dataclass
class IngestReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    chunks: int = 0


def _context(title: str, draft: ChunkDraft) -> str:
    """Title and heading path give short chunks the context they need to be found."""
    return "\n".join(part for part in (title, draft.section, draft.content) if part)


def _read_files(directory: Path) -> list[tuple[str, bytes]]:
    paths = sorted(
        p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )
    return [(p.name, p.read_bytes()) for p in paths]


async def ingest_directory(
    session: AsyncSession, embedder: Embedder, directory: Path, prune: bool = True
) -> IngestReport:
    report = IngestReport()
    files = await asyncio.to_thread(_read_files, directory)
    existing = {d.source: d for d in await session.scalars(select(Document))}

    for name, data in files:
        digest = hashlib.sha256(PIPELINE_VERSION.encode() + data).hexdigest()
        previous = existing.pop(name, None)
        if (
            previous is not None
            and previous.content_hash == digest
            and previous.embedding_model == embedder.model
        ):
            report.unchanged.append(name)
            continue

        parsed = parse_file(name, data)
        drafts = chunk_document(parsed)
        # Embed before touching the database, so a failed API call leaves the old version intact.
        vectors = await embedder.embed([_context(parsed.title, d) for d in drafts])

        if previous is not None:
            await session.delete(previous)  # chunks go with it (ON DELETE CASCADE)
            await session.flush()
        document = Document(
            source=name,
            title=parsed.title,
            content_hash=digest,
            embedding_model=embedder.model,
        )
        session.add(document)
        await session.flush()
        session.add_all(
            Chunk(
                document_id=document.id,
                position=position,
                page=draft.page,
                section=draft.section,
                lang=draft.lang,
                content=draft.content,
                search_text=to_search_text(_context(parsed.title, draft)),
                embedding=vector,
            )
            for position, (draft, vector) in enumerate(zip(drafts, vectors, strict=True))
        )
        (report.updated if previous is not None else report.added).append(name)
        report.chunks += len(drafts)

    if prune:
        for document in existing.values():
            await session.delete(document)
            report.removed.append(document.source)

    await session.commit()
    logger.info(
        "ingest_done",
        extra={
            "fields": {
                "added": report.added,
                "updated": report.updated,
                "unchanged": len(report.unchanged),
                "removed": report.removed,
                "chunks": report.chunks,
                "embedding_model": embedder.model,
            }
        },
    )
    return report


async def _main(directory: Path, prune: bool) -> IngestReport:
    try:
        async with SessionFactory() as session:
            return await ingest_directory(session, get_embedder(), directory, prune)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Ingest the clinic knowledge base.")
    parser.add_argument("directory", nargs="?", default=settings.knowledge_base_dir, type=Path)
    parser.add_argument(
        "--keep-missing", action="store_true", help="keep documents whose file was deleted"
    )
    args = parser.parse_args()
    configure_logging(settings.log_level)
    result = asyncio.run(_main(args.directory, prune=not args.keep_missing))
    print(
        f"added={len(result.added)} updated={len(result.updated)} "
        f"unchanged={len(result.unchanged)} removed={len(result.removed)} chunks={result.chunks}"
    )
