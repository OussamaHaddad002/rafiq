"""Build the knowledge-base PDFs from their Markdown sources.

Usage (from apps/api): uv run python scripts/build_kb_pdfs.py [SRC_DIR] [OUT_DIR]
Defaults: <repo>/data/clinic-src -> <repo>/data/clinic

Supports the small Markdown subset the sources use: #/##/### headings, paragraphs,
"- " bullets, **bold**, pipe tables and a `<!-- pagebreak -->` marker.
"""

import html
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Flowable,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[3]
AUTHOR = "Clinique Rafiq (fictional demo)"
PAGEBREAK = "<!-- pagebreak -->"
MARGIN = 2 * cm
CONTENT_WIDTH = A4[0] - 2 * MARGIN

STYLES = getSampleStyleSheet()
HEADINGS = {"#": STYLES["Title"], "##": STYLES["Heading2"], "###": STYLES["Heading3"]}
BODY = STYLES["BodyText"]
CELL = ParagraphStyle("Cell", parent=BODY, fontSize=9, leading=11)


def inline(text: str) -> str:
    """Escape XML and turn **bold** into <b> tags for reportlab Paragraphs."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text, quote=False))


def table(rows: list[str]) -> Table:
    cells = [
        [cell.strip() for cell in row.strip().strip("|").split("|")]
        for row in rows
        if not set(row.strip()) <= set("|:- ")  # skip the |---|---| separator
    ]
    columns = len(cells[0])
    result = Table(
        [[Paragraph(inline(cell), CELL) for cell in row] for row in cells],
        colWidths=[CONTENT_WIDTH / columns] * columns,
        repeatRows=1,
        hAlign="LEFT",
    )
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9f0ee")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9fb8b5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return result


def parse(markdown: str) -> tuple[str, list[Flowable]]:
    title = ""
    story: list[Flowable] = []
    paragraph: list[str] = []
    bullets: list[str] = []
    rows: list[str] = []

    def flush() -> None:
        if paragraph:
            story.append(Paragraph(inline(" ".join(paragraph)), BODY))
            paragraph.clear()
        if bullets:
            items = [ListItem(Paragraph(inline(b), BODY)) for b in bullets]
            story.append(ListFlowable(items, bulletType="bullet", start="•", leftIndent=12))
            bullets.clear()
        if rows:
            story.extend([table(rows), Spacer(1, 0.3 * cm)])
            rows.clear()

    for raw in markdown.splitlines():
        line = raw.strip()
        if line == PAGEBREAK:
            flush()
            story.append(PageBreak())
        elif not line:
            flush()
        elif line.startswith("#"):
            flush()
            marker, _, text = line.partition(" ")
            if marker == "#" and not title:
                title = text
            story.append(Paragraph(inline(text), HEADINGS[marker]))
        elif line.startswith("- "):
            if paragraph or rows:
                flush()
            bullets.append(line[2:])
        elif line.startswith("|"):
            if paragraph or bullets:
                flush()
            rows.append(line)
        else:
            paragraph.append(line)
    flush()
    return title, story


def build(source: Path, out_dir: Path) -> Path:
    title, story = parse(source.read_text(encoding="utf-8"))
    output = out_dir / f"{source.stem}.pdf"
    document = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        title=title,
        author=AUTHOR,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        invariant=True,  # reproducible bytes: no timestamp or random document ID
    )
    document.build(story)
    return output


def main() -> None:
    src_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "clinic-src"
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "clinic"
    out_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted(src_dir.glob("*.md")):
        print(f"{source.name} -> {build(source, out_dir).relative_to(ROOT)}")


if __name__ == "__main__":
    main()
