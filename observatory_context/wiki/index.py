"""Wiki index generator and parser."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Section display metadata: (key, heading label)
_SECTION_ORDER: list[tuple[str, str]] = [
    ("topics", "Topics"),
    ("entities/organisms", "Entities — Organisms"),
    ("entities/genes", "Entities — Genes"),
    ("entities/pathways", "Entities — Pathways"),
    ("entities/methods", "Entities — Methods"),
    ("entities/concepts", "Entities — Concepts"),
    ("hypotheses", "Hypotheses"),
    ("gaps", "Gaps"),
    ("connections", "Connections"),
]

_SECTION_HEADINGS: dict[str, str] = {k: v for k, v in _SECTION_ORDER}
_SECTION_KEYS: list[str] = [k for k, _ in _SECTION_ORDER]

# Pattern for a single entry line
_ENTRY_RE = re.compile(
    r"^\- \[(?P<slug>[^\]]+)\]\(wiki/(?P<section>[^/][^)]+?)/(?P<slug2>[^/)]+)\.md\)"
    r" — (?P<summary>.+?) \((?P<count>\d+) sources?, coverage: (?P<coverage>\w+)\)$"
)


@dataclass
class WikiEntry:
    slug: str
    section: str  # e.g. "topics", "entities/organisms", "hypotheses"
    summary: str
    source_count: int = 0
    coverage: str = "low"  # low, medium, high


def build_index_markdown(entries: list[WikiEntry]) -> str:
    """Return markdown for wiki/index.md grouped by section."""
    lines: list[str] = ["# Observatory Wiki Index", ""]

    if not entries:
        lines.append("No entries yet.")
        return "\n".join(lines)

    # Group entries by section
    grouped: dict[str, list[WikiEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.section, []).append(entry)

    # Sort entries within each group alphabetically by slug
    for group in grouped.values():
        group.sort(key=lambda e: e.slug)

    wrote_any = False
    for section_key, heading in _SECTION_ORDER:
        if section_key not in grouped:
            continue
        if wrote_any:
            lines.append("")
        lines.append(f"## {heading}")
        lines.append("")
        for entry in grouped[section_key]:
            source_word = "source" if entry.source_count == 1 else "sources"
            lines.append(
                f"- [{entry.slug}](wiki/{section_key}/{entry.slug}.md)"
                f" — {entry.summary}"
                f" ({entry.source_count} {source_word}, coverage: {entry.coverage})"
            )
        wrote_any = True

    # Append any sections not in the canonical order
    for section_key, group in grouped.items():
        if section_key in _SECTION_HEADINGS:
            continue
        if wrote_any:
            lines.append("")
        lines.append(f"## {section_key.title()}")
        lines.append("")
        for entry in group:
            source_word = "source" if entry.source_count == 1 else "sources"
            lines.append(
                f"- [{entry.slug}](wiki/{section_key}/{entry.slug}.md)"
                f" — {entry.summary}"
                f" ({entry.source_count} {source_word}, coverage: {entry.coverage})"
            )
        wrote_any = True

    return "\n".join(lines)


def parse_index_markdown(content: str) -> list[WikiEntry]:
    """Parse a wiki index markdown string back into WikiEntry objects."""
    entries: list[WikiEntry] = []
    for line in content.splitlines():
        m = _ENTRY_RE.match(line.strip())
        if not m:
            continue
        slug = m.group("slug")
        # The section is everything in the path between "wiki/" and the final "/slug.md"
        # The regex captures "section/slug2" where slug2 == slug, so derive section:
        full_path_section = m.group("section")
        # full_path_section already excludes the final slug segment because the
        # regex anchors on /slug2.md at the end.  However, the path in the link
        # is  wiki/<section>/<slug>.md  so section is captured correctly.
        entries.append(
            WikiEntry(
                slug=slug,
                section=full_path_section,
                summary=m.group("summary"),
                source_count=int(m.group("count")),
                coverage=m.group("coverage"),
            )
        )
    return entries
