"""Tests for the wiki index generator and parser."""

from __future__ import annotations

from observatory_context.wiki.index import WikiEntry, build_index_markdown, parse_index_markdown


def test_build_index_empty() -> None:
    result = build_index_markdown([])
    assert "# Observatory Wiki Index" in result
    assert "No entries yet." in result


def test_build_index_with_entries() -> None:
    entries = [
        WikiEntry(slug="pseudomonas", section="entities/organisms", summary="A genus of bacteria", source_count=3, coverage="high"),
        WikiEntry(slug="carbon-cycling", section="topics", summary="Carbon cycle processes", source_count=5, coverage="medium"),
        WikiEntry(slug="nitrogen-fixation-hypothesis", section="hypotheses", summary="Hypothesis about N-fixation", source_count=1, coverage="low"),
    ]
    result = build_index_markdown(entries)

    assert "# Observatory Wiki Index" in result
    assert "Topics" in result
    assert "Entities — Organisms" in result
    assert "Hypotheses" in result
    assert "[carbon-cycling](wiki/topics/carbon-cycling.md)" in result
    assert "[pseudomonas](wiki/entities/organisms/pseudomonas.md)" in result
    assert "[nitrogen-fixation-hypothesis](wiki/hypotheses/nitrogen-fixation-hypothesis.md)" in result
    assert "3 sources" in result
    assert "coverage: high" in result


def test_build_index_sorts_within_sections() -> None:
    entries = [
        WikiEntry(slug="zinc-metabolism", section="topics", summary="Zinc stuff", source_count=2, coverage="low"),
        WikiEntry(slug="alpha-diversity", section="topics", summary="Alpha diversity metric", source_count=1, coverage="low"),
    ]
    result = build_index_markdown(entries)
    alpha_pos = result.index("alpha-diversity")
    zinc_pos = result.index("zinc-metabolism")
    assert alpha_pos < zinc_pos


def test_parse_index_roundtrip() -> None:
    entries = [
        WikiEntry(slug="pseudomonas", section="entities/organisms", summary="A genus of bacteria", source_count=3, coverage="high"),
        WikiEntry(slug="carbon-cycling", section="topics", summary="Carbon cycle processes", source_count=5, coverage="medium"),
        WikiEntry(slug="nitrogen-fixation-hypothesis", section="hypotheses", summary="Hypothesis about N-fixation", source_count=1, coverage="low"),
        WikiEntry(slug="gyrb", section="entities/genes", summary="DNA gyrase subunit B", source_count=2, coverage="medium"),
    ]
    markdown = build_index_markdown(entries)
    parsed = parse_index_markdown(markdown)

    assert len(parsed) == len(entries)
    by_slug = {e.slug: e for e in parsed}

    assert by_slug["pseudomonas"].section == "entities/organisms"
    assert by_slug["pseudomonas"].summary == "A genus of bacteria"
    assert by_slug["pseudomonas"].source_count == 3
    assert by_slug["pseudomonas"].coverage == "high"

    assert by_slug["carbon-cycling"].section == "topics"
    assert by_slug["carbon-cycling"].source_count == 5

    assert by_slug["nitrogen-fixation-hypothesis"].section == "hypotheses"
    assert by_slug["gyrb"].section == "entities/genes"
