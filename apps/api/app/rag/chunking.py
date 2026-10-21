import re
from dataclasses import dataclass

from app.rag.parsing import ParsedDocument, Section
from app.rag.text import Language, detect_language

# ~300 tokens: small enough to cite precisely, big enough to keep a price table together.
MAX_CHARS = 1200
# Text repeated from the end of the previous chunk, so a table row or sentence cut at a
# boundary still appears whole in one chunk.
OVERLAP_CHARS = 200

_SENTENCE_END = re.compile(r"(?<=[.!?؟])\s+")
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    content: str
    page: int | None
    section: str | None
    lang: Language


@dataclass(frozen=True, slots=True)
class _Piece:
    text: str
    separator: str  # placed before this piece when it follows another one in a chunk


def _pieces(text: str, max_chars: int) -> list[_Piece]:
    """Paragraphs, falling back to lines, sentences and finally hard cuts for oversized ones."""
    pieces: list[_Piece] = []
    for paragraph in _PARAGRAPH_BREAK.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            pieces.append(_Piece(paragraph, "\n\n"))
            continue
        separator = "\n\n"  # first piece of a paragraph starts a new paragraph
        for line in paragraph.splitlines():
            parts = [line] if len(line) <= max_chars else _SENTENCE_END.split(line)
            for part in parts:
                for start in range(0, len(part), max_chars):
                    pieces.append(_Piece(part[start : start + max_chars], separator))
                    separator = "\n"
    return pieces


def _join(pieces: list[_Piece]) -> str:
    return "".join((p.separator if i else "") + p.text for i, p in enumerate(pieces))


def _tail(pieces: list[_Piece], limit: int) -> list[_Piece]:
    """The longest run of trailing pieces that fits in `limit` characters."""
    tail: list[_Piece] = []
    for piece in reversed(pieces):
        if len(_join([piece, *tail])) > limit:
            break
        tail.insert(0, piece)
    return tail


def chunk_section(
    section: Section, max_chars: int = MAX_CHARS, overlap_chars: int = OVERLAP_CHARS
) -> list[str]:
    """Greedily pack pieces into chunks. Chunks never cross a section or page boundary."""
    chunks: list[str] = []
    current: list[_Piece] = []
    for piece in _pieces(section.text, max_chars):
        if current and len(_join([*current, piece])) > max_chars:
            chunks.append(_join(current))
            overlap = _tail(current, overlap_chars)
            current = overlap if len(_join([*overlap, piece])) <= max_chars else []
        current.append(piece)
    if current:
        chunks.append(_join(current))
    return chunks


def chunk_document(document: ParsedDocument, max_chars: int = MAX_CHARS) -> list[ChunkDraft]:
    return [
        ChunkDraft(
            content=text,
            page=section.page,
            section=section.heading,
            lang=detect_language(text),
        )
        for section in document.sections
        for text in chunk_section(section, max_chars)
    ]
