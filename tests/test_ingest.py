"""Layout-aware PDF ingestion tests: multi-column reading order + single column."""
from __future__ import annotations

import fitz  # PyMuPDF

from scholar.ingest import extract_pdf_text


def _pdf(coords: list[tuple[float, float, str]]) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=600, height=400)
    for x, y, text in coords:
        page.insert_text((x, y), text)
    return doc.tobytes()


def test_two_column_reading_order():
    # Left column (skills) and right column (experience) interleaved by row.
    data = _pdf([
        (50, 80, "Skills"), (50, 110, "Python"), (50, 140, "PyTorch"),
        (340, 80, "Experience"), (340, 110, "ResearchAssistant"), (340, 140, "BuiltIoT"),
    ])
    text = extract_pdf_text(data)
    # The whole LEFT column must be read before the RIGHT column — not row-wise.
    assert text.index("Skills") < text.index("Experience")
    assert text.index("PyTorch") < text.index("Experience")


def test_single_column_extraction():
    data = _pdf([(50, 80, "Ada Lovelace"), (50, 110, "PhD applicant"), (50, 140, "EdgeAI")])
    text = extract_pdf_text(data)
    for token in ("Ada", "Lovelace", "PhD", "EdgeAI"):
        assert token in text


def test_empty_pdf_returns_empty():
    doc = fitz.open()
    doc.new_page(width=600, height=400)
    assert extract_pdf_text(doc.tobytes()).strip() == ""
