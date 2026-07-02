"""Junk-page filter tests — must NOT drop legit pages for cookie banners, and
must drop bot-walls / error stubs."""
from __future__ import annotations

from scholar.tools.scraper import _is_junk


def test_cookie_banner_page_is_kept():
    # A real, substantial page that happens to carry a GDPR cookie banner up top.
    page = "We use cookies. Cookie policy. " + ("Fully funded PhD in ML at TU Munich. " * 30)
    assert _is_junk(page) is False


def test_too_short_page_is_junk():
    assert _is_junk("Apply now.") is True


def test_bot_wall_is_junk():
    assert _is_junk("Just a moment... checking your browser before you continue.") is True
    assert _is_junk("Access Denied. 403 Forbidden.") is True


def test_long_page_with_footer_phrase_is_kept():
    # A wall phrase buried in a long page's footer must not sink the whole page.
    page = ("Funded PhD position in federated learning. " * 60) + " please enable javascript to view"
    assert _is_junk(page) is False
