"""Candidate-ranking tests: reputation via real hostname parsing + fallback order.

The cross-encoder relevance path is exercised live (it loads a model), so here we
test the deterministic pieces: reputation scoring and the reputation-only fallback
ordering used when no query text / no model is available.
"""
from __future__ import annotations

from scholar.tools.ranking import _minmax, rank_hits, reputation_score


def test_reputation_academic_and_gov_tlds():
    assert reputation_score("https://www.tum.edu/phd") == 0.95
    assert reputation_score("https://www.ed.ac.uk/funding") == 0.95
    assert reputation_score("https://www.gov.uk/scholarships") == 0.95


def test_reputation_registry_and_noise():
    assert reputation_score("https://www.daad.de/en") == 0.85
    assert reputation_score("https://www.instagram.com/reel/x") == 0.05
    assert reputation_score("https://www.facebook.com/posts/1") == 0.05


def test_reputation_uses_hostname_not_substring():
    # A spoofed '.edu' inside a longer host, or '.edu' only in the path, must NOT
    # count as authoritative — this is the bug the substring approach had.
    assert reputation_score("https://notreal.edu.spam-site.com/x") == 0.5
    assert reputation_score("https://example.com/path/edu/page") == 0.5
    assert reputation_score("https://random-blog.com/phd-tips") == 0.5


def test_reputation_empty_url():
    assert reputation_score("") == 0.3


def test_rank_hits_empty():
    assert rank_hits("query", []) == []


def test_rank_hits_reputation_fallback_order():
    # Empty query -> no cross-encoder -> reputation-only ordering.
    hits = [
        {"url": "https://blog.com/a", "title": "", "snippet": "", "raw_content": ""},
        {"url": "https://www.tum.edu/a", "title": "", "snippet": "", "raw_content": ""},
        {"url": "https://facebook.com/a", "title": "", "snippet": "", "raw_content": ""},
    ]
    ranked = rank_hits("", hits)
    assert ranked[0]["url"].endswith("tum.edu/a")     # authoritative first
    assert ranked[-1]["url"].startswith("https://facebook.com")  # noise last


def test_minmax_normalisation():
    assert _minmax([1.0, 1.0]) == [0.5, 0.5]        # degenerate -> neutral
    out = _minmax([0.0, 5.0, 10.0])
    assert out[0] == 0.0 and out[-1] == 1.0
