from io import BytesIO

from reportlab.pdfgen.canvas import Canvas

from app.rag.chunking import chunk_document, chunk_section
from app.rag.parsing import Section, compact_layout, parse_file, parse_markdown

MARKDOWN = """---
title: Horaires et accès
---
# Horaires

Du lundi au vendredi, 8h00-19h00.

## Ramadan

Du lundi au samedi, 9h00-15h00.

# مواعيد العمل

من الاثنين إلى الجمعة.
"""


def test_markdown_sections_carry_heading_path_and_frontmatter_title() -> None:
    document = parse_markdown(MARKDOWN, "fallback")

    assert document.title == "Horaires et accès"
    assert [(s.heading, s.text) for s in document.sections] == [
        ("Horaires", "Du lundi au vendredi, 8h00-19h00."),
        ("Horaires > Ramadan", "Du lundi au samedi, 9h00-15h00."),
        ("مواعيد العمل", "من الاثنين إلى الجمعة."),
    ]


def test_markdown_title_falls_back_to_first_heading() -> None:
    assert parse_markdown("# Tarifs\n\nTexte.", "fallback").title == "Tarifs"


def make_pdf(pages: list[list[str]], title: str) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer)
    canvas.setTitle(title)
    for lines in pages:
        for i, line in enumerate(lines):
            canvas.drawString(72, 750 - 18 * i, line)
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def test_pdf_sections_are_pages_with_metadata_title() -> None:
    data = make_pdf([["Consultations"], ["Examens", "ECG"]], title="Tarifs 2026")

    document = parse_file("tarifs.pdf", data)

    assert document.title == "Tarifs 2026"
    assert [s.page for s in document.sections] == [1, 2]
    assert "ECG" in document.sections[1].text


def test_compact_layout_turns_column_padding_into_separators() -> None:
    assert compact_layout("   Cardiologie        80 DT  \n\n\n\nNote") == (
        "Cardiologie | 80 DT\n\nNote"
    )


def test_small_section_is_one_chunk() -> None:
    assert chunk_section(Section("Un paragraphe.\n\nUn autre.")) == ["Un paragraphe.\n\nUn autre."]


def test_long_section_is_split_under_the_limit_with_overlap() -> None:
    paragraphs = [f"Paragraphe {i} " + "x" * 80 for i in range(20)]

    chunks = chunk_section(Section("\n\n".join(paragraphs)), max_chars=300, overlap_chars=100)

    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)
    # The last paragraph of a chunk is repeated at the start of the next one.
    assert chunks[1].startswith(chunks[0].split("\n\n")[-1])
    assert all(any(p in c for c in chunks) for p in paragraphs)


def test_table_lines_stay_on_single_newlines_when_split() -> None:
    table = "\n".join(f"Ligne {i} | {i * 10} DT" for i in range(60))

    chunks = chunk_section(Section(table), max_chars=200, overlap_chars=0)

    assert all("\n\n" not in c for c in chunks)
    assert "\n".join(chunks) == table


def test_chunks_keep_page_section_and_language() -> None:
    document = parse_markdown(MARKDOWN, "fallback")
    drafts = chunk_document(document)
    assert [(d.section, d.lang) for d in drafts] == [
        ("Horaires", "fr"),
        ("Horaires > Ramadan", "fr"),
        ("مواعيد العمل", "ar"),
    ]
