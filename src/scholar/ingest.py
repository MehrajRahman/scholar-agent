"""Context ingestion (blueprint step 1): turn messy CV/transcript files into text.

Kept deliberately dumb — it only extracts raw text. *Understanding* that text is
the Profiler agent's job, so this layer has no LLM dependency and is trivially
testable.

PDF extraction is *layout-aware*: academic CVs are frequently multi-column, and a
naive linear extractor reads straight across columns, splicing unrelated lines
together (e.g. a skill from the sidebar into the middle of a project bullet).
That scrambles the Profiler's input. We use PyMuPDF block geometry to recover the
real reading order (column by column, top to bottom), falling back to pypdf if
PyMuPDF is unavailable or errors.
"""
from __future__ import annotations

from pathlib import Path

from .observability import get_logger

log = get_logger("ingest")

# Multi-column detection tuning. A gutter (vertical whitespace band) only counts
# as a real column boundary if it is at least this fraction of page width wide and
# its centre falls in the central region of the page.
_MIN_GUTTER_FRAC = 0.04
_GUTTER_REGION = (0.30, 0.70)


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def _find_gutter(words: list[tuple], page_width: float) -> float | None:
    """Return the x of a clean vertical gutter splitting two columns, else None.

    Words are PyMuPDF tuples ``(x0, y0, x1, y1, text, ...)``. We merge all word
    x-spans, then look for the widest uncovered vertical strip whose centre sits
    near the page middle — that strip is the column gutter.
    """
    covered = _merge_intervals([(w[0], w[2]) for w in words])
    best: tuple[float, float] | None = None  # (width, centre)
    for (_, left_end), (right_start, _) in zip(covered, covered[1:]):
        width = right_start - left_end
        centre = (left_end + right_start) / 2
        in_region = _GUTTER_REGION[0] * page_width <= centre <= _GUTTER_REGION[1] * page_width
        if width >= _MIN_GUTTER_FRAC * page_width and in_region and (best is None or width > best[0]):
            best = (width, centre)
    return best[1] if best else None


def _column_text(words: list[tuple]) -> str:
    """Reconstruct text for one column: group words into lines by y, then read
    each line left→right, lines top→bottom."""
    if not words:
        return ""
    heights = sorted(w[3] - w[1] for w in words)
    tol = max(heights[len(heights) // 2] * 0.6, 2.0)  # ~60% of median line height
    lines: list[list[tuple]] = []
    last_y: float | None = None
    for w in sorted(words, key=lambda w: (w[1], w[0])):
        if last_y is None or abs(w[1] - last_y) > tol:
            lines.append([w])
            last_y = w[1]
        else:
            lines[-1].append(w)
    return "\n".join(
        " ".join(w[4] for w in sorted(line, key=lambda w: w[0])) for line in lines
    )


def _reading_order(words: list[tuple], page_width: float) -> str:
    """Order words into human reading order, handling a 1- or 2-column layout."""
    words = [w for w in words if (w[4] or "").strip()]
    if not words:
        return ""
    gutter = _find_gutter(words, page_width)
    if gutter is None:
        return _column_text(words)
    left = [w for w in words if (w[0] + w[2]) / 2 < gutter]
    right = [w for w in words if (w[0] + w[2]) / 2 >= gutter]
    return _column_text(left) + "\n" + _column_text(right)


def extract_pdf_text(data: bytes) -> str:
    """Layout-aware PDF → text from raw bytes, with a linear pypdf fallback."""
    try:
        import fitz  # PyMuPDF

        out: list[str] = []
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                out.append(_reading_order(page.get_text("words"), page.rect.width))
        text = "\n\n".join(out).strip()
        if text:
            return text
        log.warning("pdf_empty_via_pymupdf", fallback="pypdf")
    except Exception as exc:  # noqa: BLE001 - never let parsing kill ingestion
        log.warning("pymupdf_failed", error=str(exc), fallback="pypdf")

    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def load_document(path: str | Path) -> str:
    """Extract plain text from a PDF / txt / md file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    if path.suffix.lower() == ".pdf":
        return extract_pdf_text(path.read_bytes())

    return path.read_text(encoding="utf-8", errors="ignore")


def load_documents(paths: list[str | Path]) -> list[str]:
    docs = []
    for p in paths:
        try:
            docs.append(load_document(p))
        except Exception as exc:  # noqa: BLE001
            log.warning("ingest_failed", path=str(p), error=str(exc))
    return docs
