"""Live "Hands-minus-Brains" demo — runs the real-world parts of the pipeline
on YOUR machine, with NO LLM and NO GPU required.

What it exercises for real (all CPU / free APIs):
  1. CV PDF  -> text                         (pypdf, the ingestion step)
  2. naive keyword extraction (NO LLM)        (stands in for Profiler/Scout)
  3. OpenAlex papers                          (live, free, no key)
  4. NSF + NIH funding                        (live, free, no key)
  5. web page -> clean text                   (trafilatura scraper)
  6. local embeddings + cosine similarity     (fastembed ONNX, CPU)

What it does NOT do (these genuinely need a model): turn the CV into a structured
profile, plan smart queries, score 0-100, or write the email/SOP.

Usage:
    python scripts/demo_online.py /path/to/your_cv.pdf
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from collections import Counter

# Use the small embedding model so the first-run download is ~130MB, not ~1.2GB.
os.environ.setdefault("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

from scholar.ingest import load_document  # noqa: E402
from scholar.kb.embeddings import Embedder  # noqa: E402
from scholar.tools.funding import search_nih, search_nsf  # noqa: E402
from scholar.tools.openalex import openalex_works  # noqa: E402
from scholar.tools.scraper import fetch_clean_text  # noqa: E402

_STOP = set(
    "the a an and or of to in for with on at by from as is are was were be been being this that "
    "these those i you he she it we they my your our their cv resume experience education skills "
    "project projects university college bsc msc phd gpa cgpa year years using used use based "
    "research interest interests email github http https www com edu org".split()
)


def banner(title: str) -> None:
    print(f"\n{'=' * 70}\n  {title}\n{'=' * 70}")


def extract_keywords(text: str, k: int = 8) -> list[str]:
    """Heuristic, NO-LLM keyword pull. A crude placeholder for the real Profiler.

    First tries to read an explicit 'Research Interests' / 'Skills' section; if
    that's thin, falls back to top frequent content words.
    """
    phrases: list[str] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.search(r"\b(research interest|interests|skills|expertise)\b", line, re.I):
            # grab this line's tail + the next couple of lines
            chunk = " ".join(lines[i : i + 3])
            chunk = re.split(r":", chunk, maxsplit=1)[-1]
            for p in re.split(r"[,;|/•]", chunk):
                p = p.strip(" .-\t").lower()
                if 3 < len(p) < 40 and not p.isdigit():
                    phrases.append(p)
    # de-dupe, keep order
    seen, ordered = set(), []
    for p in phrases:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    if len(ordered) >= 3:
        return ordered[:k]

    # frequency fallback
    words = re.findall(r"[a-zA-Z][a-zA-Z+#-]{3,}", text.lower())
    freq = Counter(w for w in words if w not in _STOP)
    return [w for w, _ in freq.most_common(k)]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def main(pdf_path: str) -> None:
    # 1. Ingest -------------------------------------------------------------
    banner("1. INGEST  —  CV PDF -> text")
    text = load_document(pdf_path)
    print(f"  file        : {pdf_path}")
    print(f"  chars       : {len(text):,}")
    print(f"  preview     : {' '.join(text.split())[:240]} ...")

    # 2. Keyword extraction (no LLM) ---------------------------------------
    banner("2. KEYWORDS  —  heuristic, NO model (placeholder for Profiler)")
    topics = extract_keywords(text)
    print("  topics      :", topics or "(none found)")
    if not topics:
        print("  -> couldn't pull topics; is this a CV/resume PDF?")
        topics = ["machine learning"]
    primary = topics[:3]

    # 3. OpenAlex (live) ----------------------------------------------------
    banner("3. OPENALEX  —  live papers for your top topics")
    for t in primary:
        try:
            works = await openalex_works(t, per_page=3)
            print(f"\n  topic: {t!r}  ->  {len(works)} works")
            for w in works:
                inst = (w.get("institutions") or ["?"])[0]
                print(f"    - ({w.get('year')}) {str(w.get('title'))[:70]}  [{inst}]")
        except Exception as e:  # noqa: BLE001
            print(f"  topic {t!r}: ERROR {e}")

    # 4. Funding (live) -----------------------------------------------------
    banner("4. FUNDING  —  live NSF + NIH awards")
    q = primary[0]
    try:
        nsf = await search_nsf(q, n=3)
        print(f"\n  NSF awards for {q!r}: {len(nsf)}")
        for a in nsf:
            print(f"    - ${a.get('amount')}  {str(a.get('title'))[:60]}  (PI {a.get('pi')})")
    except Exception as e:  # noqa: BLE001
        print(f"  NSF ERROR {e}")
    try:
        nih = await search_nih(q, n=3)
        print(f"\n  NIH projects for {q!r}: {len(nih)}")
        for p in nih:
            print(f"    - ${p.get('amount')}  {str(p.get('title'))[:60]}  ({p.get('institution')})")
    except Exception as e:  # noqa: BLE001
        print(f"  NIH ERROR {e}")

    # 5. Scraper (live) -----------------------------------------------------
    banner("5. SCRAPER  —  URL -> clean main text (trafilatura)")
    demo_url = f"https://en.wikipedia.org/wiki/{primary[0].split()[0].title()}"
    clean = await fetch_clean_text(demo_url, max_chars=400)
    print(f"  url         : {demo_url}")
    print(f"  extracted   : {' '.join(clean.split())[:300] or '(nothing — try another url)'} ...")

    # 6. Local embeddings (CPU) --------------------------------------------
    banner("6. EMBEDDINGS  —  local CPU vectors + semantic similarity (no GPU)")
    print("  (first run downloads a ~130MB ONNX model, then it's cached)")
    emb = Embedder()
    cv_vec = emb.embed_one(" ".join(text.split())[:2000])
    print(f"  vector dim  : {len(cv_vec)}")
    print("  CV-vs-topic cosine similarity (previews the Matchmaker's semantic leg):")
    for t in topics:
        sim = cosine(cv_vec, emb.embed_one(t))
        bar = "#" * int(sim * 40)
        print(f"    {sim:5.3f}  {bar:<40} {t}")

    banner("DONE")
    print("  Everything above ran with NO model and NO GPU.")
    print("  To get a scored shortlist + drafted email/SOP, point LLM_BASE_URL")
    print("  at any OpenAI-compatible endpoint and run:  scholar run <cv.pdf>")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/demo_online.py /path/to/your_cv.pdf")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
