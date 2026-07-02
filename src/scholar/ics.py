"""Minimal RFC-5545 iCalendar builder for application deadlines.

Pure + dependency-free so it's trivially testable. The ``deadline_checklist``
artifact attaches the produced ``.ics`` string in its metadata so the student can
import every deadline into Google/Apple Calendar in one click.
"""
from __future__ import annotations

import hashlib


def _fold(date_iso: str) -> str:
    """'2026-09-01' -> '20260901' (all-day VEVENT date form)."""
    return date_iso.replace("-", "")[:8]


def build_ics(events: list[dict], calendar_name: str = "Scholarship Deadlines") -> str:
    """Build an iCalendar document from ``[{'title','date'(,'url')}]`` entries.

    ``date`` must be an ISO date (YYYY-MM-DD); entries without one are skipped.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//scholar-agent//EN",
        f"X-WR-CALNAME:{calendar_name}",
    ]
    for ev in events:
        date_iso = ev.get("date")
        if not date_iso:
            continue
        title = (ev.get("title") or "Deadline").replace("\n", " ")
        uid = hashlib.sha1(f"{title}{date_iso}".encode()).hexdigest()[:16]
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}@scholar-agent",
            f"DTSTART;VALUE=DATE:{_fold(date_iso)}",
            f"SUMMARY:{title}",
        ]
        if ev.get("url"):
            lines.append(f"URL:{ev['url']}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)
