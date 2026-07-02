"""Candidate-page ranking for the Scout / Deep Scout.

Each search hit is scored by two orthogonal, principled signals — no vague
keyword guessing:

* relevance  — a **cross-encoder** re-scores the page's actual text against the
               applicant's profile/query. This is the semantic stage of modern
               retrieval and is *stronger* than HNSW dense recall: HNSW finds
               approximate nearest neighbours in embedding space (good for recall
               over millions of vectors), whereas a cross-encoder reads the
               (query, document) pair together and judges true relevance. We only
               have a handful of candidates per round, so we skip ANN recall and
               go straight to the precise stage. Meaning, not URL strings, decides
               ranking — an off-topic page on a "good" domain sinks, an on-topic
               page on an unknown domain rises.
* reputation — derived from the REAL hostname (parsed with urlsplit, not substring
               matched): academic/government TLDs (.edu, .ac.<cc>, .gov[.<cc>])
               and known scholarship registries score high; social/video/forum
               hosts score low.

    final = W_RELEVANCE * relevance_norm + W_REPUTATION * reputation

Sorted descending. If the cross-encoder can't load (e.g. offline, no model),
we degrade to reputation-only ordering so the pipeline never breaks.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from ..observability import get_logger

log = get_logger("tool.ranking")

W_RELEVANCE = 0.7
W_REPUTATION = 0.3

# Known scholarship / research registries (matched against the parsed host).
_REGISTRY_HOSTS = (
    "daad.de", "euraxess", "findaphd.com", "scholarshipportal.com",
    "mastersportal.com", "phdportal.com", "chevening.org", "cordis.europa.eu",
    "jobs.ac.uk", "academicpositions.com", "postgraduatestudentships.co.uk",
    "scholars4dev",
)
# Social / video / forum hosts — almost never the real call page.
_NOISE_HOSTS = (
    "instagram.com", "facebook.com", "twitter.com", "x.com", "tiktok.com",
    "youtube.com", "youtu.be", "reddit.com", "pinterest.com", "t.me", "medium.com",
)


def _host(url: str) -> str:
    host = urlsplit(url or "").hostname or ""
    return host.lower().lstrip(".")


def reputation_score(url: str) -> float:
    """Trust score in [0, 1] from the parsed hostname (no substring false hits)."""
    host = _host(url)
    if not host:
        return 0.3
    if any(host == n or host.endswith("." + n) for n in _NOISE_HOSTS):
        return 0.05
    labels = host.split(".")
    tld = labels[-1] if labels else ""
    sld = labels[-2] if len(labels) >= 2 else ""
    if tld in ("edu", "gov") or sld in ("edu", "ac", "gov"):  # .edu, .gov, .ac.uk, .edu.au, .gov.xx
        return 0.95
    if any(host == r or host.endswith("." + r) or r in host for r in _REGISTRY_HOSTS):
        return 0.85
    return 0.5


def _doc_text(hit: dict) -> str:
    """Compact text for the cross-encoder: title + snippet + head of page body."""
    parts = [hit.get("title", ""), hit.get("snippet", "")]
    raw = (hit.get("raw_content") or "")[:1200]
    if raw:
        parts.append(raw)
    return "\n".join(p for p in parts if p)[:2000]


def _minmax(scores: list[float]) -> list[float]:
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        return [0.5] * len(scores)
    return [(s - lo) / (hi - lo) for s in scores]


def _relevance_scores(query_text: str, hits: list[dict]) -> list[float] | None:
    """Normalised [0,1] cross-encoder relevance, or None if unavailable."""
    try:
        from ..kb.embeddings import get_embedder

        raw = get_embedder().rerank(query_text, [_doc_text(h) for h in hits])
        return _minmax([float(s) for s in raw])
    except Exception as exc:  # noqa: BLE001 - never let ranking break discovery
        log.warning("relevance_rank_unavailable", error=str(exc))
        return None


def rank_hits(query_text: str, hits: list[dict]) -> list[dict]:
    """Order search hits by ``W_RELEVANCE*relevance + W_REPUTATION*reputation``.

    Falls back to reputation-only ordering if the cross-encoder can't load.
    """
    if not hits:
        return []
    reps = [reputation_score(h.get("url", "")) for h in hits]
    rels = _relevance_scores(query_text, hits) if query_text else None
    if rels is None:
        ranked = sorted(zip(hits, reps), key=lambda t: t[1], reverse=True)
        return [h for h, _ in ranked]
    finals = [W_RELEVANCE * rels[i] + W_REPUTATION * reps[i] for i in range(len(hits))]
    ranked = sorted(zip(hits, finals), key=lambda t: t[1], reverse=True)
    return [h for h, _ in ranked]
