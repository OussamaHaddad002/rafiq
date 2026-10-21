import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

import yaml
from pypdf import PdfReader

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_HTML_COMMENT = re.compile(r"^\s*<!--.*-->\s*$")
_COLUMN_GAP = re.compile(r" {3,}")


@dataclass(frozen=True, slots=True)
class Section:
    text: str
    page: int | None = None
    heading: str | None = None  # heading path, e.g. "Tarifs > Consultations"


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    title: str
    sections: list[Section]


def parse_markdown(raw: str, fallback_title: str) -> ParsedDocument:
    """Split Markdown into sections at headings. Optional YAML frontmatter may set `title`."""
    raw = raw.replace("\r\n", "\n")
    frontmatter: dict[str, object] = {}
    if raw.startswith("---\n"):
        end = raw.find("\n---", 4)
        if end != -1:
            loaded = yaml.safe_load(raw[4:end])
            frontmatter = loaded if isinstance(loaded, dict) else {}
            raw = raw[end + 4 :].partition("\n")[2]  # skip the rest of the closing --- line

    sections: list[Section] = []
    headings: list[tuple[int, str]] = []  # open headings as (level, text)
    first_h1: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            path = " > ".join(heading for _, heading in headings) or None
            sections.append(Section(text=text, heading=path))
        buffer.clear()

    for line in raw.splitlines():
        if _HTML_COMMENT.match(line):
            continue
        match = _HEADING.match(line)
        if not match:
            buffer.append(line)
            continue
        flush()
        level, heading = len(match.group(1)), match.group(2).strip()
        if level == 1 and first_h1 is None:
            first_h1 = heading
        while headings and headings[-1][0] >= level:
            headings.pop()
        headings.append((level, heading))
    flush()

    title = str(frontmatter.get("title") or first_h1 or fallback_title)
    return ParsedDocument(title=title, sections=sections)


def compact_layout(text: str) -> str:
    """pypdf's layout mode keeps each table row on one line but pads columns with spaces.

    Turn the padding into " | " so "Cardiologie      80 DT" reads "Cardiologie | 80 DT".
    """
    lines = [_COLUMN_GAP.sub(" | ", line.strip()) for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def parse_pdf(data: bytes, fallback_title: str) -> ParsedDocument:
    """One section per page, so citations can point to the exact page."""
    reader = PdfReader(BytesIO(data))
    title = (reader.metadata.title if reader.metadata else None) or fallback_title
    sections = [
        Section(text=text, page=number)
        for number, page in enumerate(reader.pages, start=1)
        if (text := compact_layout(page.extract_text(extraction_mode="layout") or ""))
    ]
    return ParsedDocument(title=str(title), sections=sections)


def parse_file(name: str, data: bytes) -> ParsedDocument:
    path = PurePath(name)
    fallback_title = path.stem.replace("-", " ").replace("_", " ").capitalize()
    if path.suffix.lower() == ".pdf":
        return parse_pdf(data, fallback_title)
    return parse_markdown(data.decode("utf-8"), fallback_title)
