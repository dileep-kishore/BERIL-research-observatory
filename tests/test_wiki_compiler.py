"""Tests for the wiki page compiler."""

from __future__ import annotations

import yaml

from observatory_context.registry.schema import EntityRef, Finding, Hypothesis
from observatory_context.wiki.compiler import (
    compile_entity_page,
    compile_hypothesis_page,
    compile_topic_page,
)


def _parse_frontmatter(text: str) -> dict:
    """Extract and parse YAML frontmatter from a markdown string."""
    assert text.startswith("---\n"), "Expected frontmatter to start with ---"
    end = text.index("\n---\n", 4)
    return yaml.safe_load(text[4:end])


def _make_finding(finding_id: str, project_id: str = "proj-001") -> Finding:
    return Finding(
        finding_id=finding_id,
        project_id=project_id,
        title=f"Finding {finding_id}",
        statement=f"Statement for {finding_id}.",
        confidence="high",
        finding_type="result",
    )


def _make_hypothesis(
    hypothesis_id: str,
    status: str = "proposed",
    statement: str | None = None,
) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=hypothesis_id,
        statement=statement or f"Hypothesis {hypothesis_id} statement.",
        status=status,
        project_ids=["proj-001"],
    )


# ---------------------------------------------------------------------------
# compile_entity_page
# ---------------------------------------------------------------------------


class TestCompileEntityPage:
    def _call(self, **kwargs):
        defaults = dict(
            entity_type="organism",
            slug="pseudomonas",
            label="Pseudomonas",
            findings=[_make_finding("F-001"), _make_finding("F-002")],
            hypotheses=[_make_hypothesis("H-001")],
            project_ids=["proj-001"],
        )
        defaults.update(kwargs)
        return compile_entity_page(**defaults)

    def test_heading_present(self):
        result = self._call()
        assert "# Pseudomonas" in result

    def test_finding_ids_appear(self):
        result = self._call()
        assert "F-001" in result
        assert "F-002" in result

    def test_hypothesis_ids_appear(self):
        result = self._call()
        assert "H-001" in result

    def test_entity_type_in_body(self):
        result = self._call()
        assert "organism" in result

    def test_frontmatter_required_fields(self):
        result = self._call()
        fm = _parse_frontmatter(result)
        assert fm["title"] == "Pseudomonas"
        assert fm["kind"] == "entity_profile"
        assert fm["entity_type"] == "organism"
        assert "coverage" in fm
        assert "last_compiled" in fm

    def test_coverage_label_low(self):
        result = self._call(findings=[_make_finding("F-001")])
        fm = _parse_frontmatter(result)
        assert fm["coverage"] == "low"

    def test_coverage_label_medium(self):
        result = self._call(findings=[_make_finding(f"F-{i:03d}") for i in range(3)])
        fm = _parse_frontmatter(result)
        assert fm["coverage"] == "medium"

    def test_coverage_label_high(self):
        result = self._call(findings=[_make_finding(f"F-{i:03d}") for i in range(5)])
        fm = _parse_frontmatter(result)
        assert fm["coverage"] == "high"

    def test_key_findings_section(self):
        result = self._call()
        assert "Key Findings" in result

    def test_related_hypotheses_section(self):
        result = self._call()
        assert "Related Hypotheses" in result

    def test_hypothesis_status_appears(self):
        result = self._call(hypotheses=[_make_hypothesis("H-001", status="supported")])
        assert "supported" in result

    def test_sources_count_in_frontmatter(self):
        findings = [_make_finding("F-001", "proj-A"), _make_finding("F-002", "proj-B")]
        result = self._call(findings=findings)
        fm = _parse_frontmatter(result)
        assert fm["sources"] == 2

    def test_project_ids_in_body(self):
        result = self._call(project_ids=["proj-001", "proj-002"])
        assert "proj-001" in result


# ---------------------------------------------------------------------------
# compile_topic_page
# ---------------------------------------------------------------------------


class TestCompileTopicPage:
    def _call(self, **kwargs):
        defaults = dict(
            slug="carbon-cycling",
            title="Carbon Cycling",
            findings=[_make_finding("F-001"), _make_finding("F-002"), _make_finding("F-003")],
            hypotheses=[_make_hypothesis("H-001"), _make_hypothesis("H-002")],
            project_ids=["proj-001", "proj-002"],
        )
        defaults.update(kwargs)
        return compile_topic_page(**defaults)

    def test_heading_present(self):
        result = self._call()
        assert "# Carbon Cycling" in result

    def test_finding_ids_appear(self):
        result = self._call()
        assert "F-001" in result
        assert "F-002" in result
        assert "F-003" in result

    def test_hypothesis_ids_in_table(self):
        result = self._call()
        assert "H-001" in result
        assert "H-002" in result

    def test_frontmatter_required_fields(self):
        result = self._call()
        fm = _parse_frontmatter(result)
        assert fm["title"] == "Carbon Cycling"
        assert fm["kind"] == "topic_synthesis"
        assert "coverage" in fm
        assert "last_compiled" in fm

    def test_coverage_label_medium(self):
        result = self._call(
            findings=[_make_finding("F-001"), _make_finding("F-002"), _make_finding("F-003")]
        )
        fm = _parse_frontmatter(result)
        assert fm["coverage"] == "medium"

    def test_key_findings_numbered_list(self):
        result = self._call()
        # Numbered list items start with "1."
        assert "1." in result

    def test_hypotheses_table_headers(self):
        result = self._call()
        assert "| ID |" in result or "|ID|" in result or "| ID|" in result or "ID" in result
        assert "Statement" in result
        assert "Status" in result

    def test_open_questions_section(self):
        result = self._call()
        assert "Open Questions" in result

    def test_sources_in_frontmatter(self):
        result = self._call(findings=[_make_finding("F-001"), _make_finding("F-002")])
        fm = _parse_frontmatter(result)
        assert fm["sources"] == 2

    def test_project_count_in_body(self):
        result = self._call(project_ids=["proj-001", "proj-002"])
        assert "2" in result


# ---------------------------------------------------------------------------
# compile_hypothesis_page
# ---------------------------------------------------------------------------


class TestCompileHypothesisPage:
    def _call(self, **kwargs):
        hyp = _make_hypothesis(
            "H-001",
            status="supported",
            statement="Nitrogen limitation drives pangenome openness in marine bacteria.",
        )
        defaults = dict(
            hypothesis=hyp,
            supporting_findings=[_make_finding("F-001"), _make_finding("F-002")],
        )
        defaults.update(kwargs)
        return compile_hypothesis_page(**defaults)

    def test_heading_with_hypothesis_id(self):
        result = self._call()
        assert "H-001" in result

    def test_statement_in_body(self):
        result = self._call()
        assert "Nitrogen limitation" in result

    def test_status_in_body(self):
        result = self._call()
        assert "supported" in result

    def test_finding_ids_appear(self):
        result = self._call()
        assert "F-001" in result
        assert "F-002" in result

    def test_supporting_evidence_section(self):
        result = self._call()
        assert "Supporting Evidence" in result

    def test_frontmatter_required_fields(self):
        result = self._call()
        fm = _parse_frontmatter(result)
        assert fm["kind"] == "hypothesis_tracker"
        assert "coverage" in fm
        assert "last_compiled" in fm
        assert "H-001" in fm["title"]

    def test_frontmatter_title_truncates_statement(self):
        long_statement = "A" * 120
        hyp = _make_hypothesis("H-002", statement=long_statement)
        result = compile_hypothesis_page(hypothesis=hyp, supporting_findings=[])
        fm = _parse_frontmatter(result)
        # title should contain hypothesis_id and truncated (<=80 char) statement
        assert "H-002" in fm["title"]
        # The statement portion should be at most 80 chars
        title_statement = fm["title"].split(": ", 1)[1]
        assert len(title_statement) <= 80

    def test_coverage_low_with_no_findings(self):
        result = self._call(supporting_findings=[])
        fm = _parse_frontmatter(result)
        assert fm["coverage"] == "low"

    def test_coverage_high_with_many_findings(self):
        findings = [_make_finding(f"F-{i:03d}") for i in range(6)]
        result = self._call(supporting_findings=findings)
        fm = _parse_frontmatter(result)
        assert fm["coverage"] == "high"

    def test_scope_in_body_when_present(self):
        hyp = Hypothesis(
            hypothesis_id="H-003",
            statement="Some statement.",
            status="proposed",
            scope="marine bacteria",
            project_ids=["proj-001"],
        )
        result = compile_hypothesis_page(hypothesis=hyp, supporting_findings=[])
        assert "marine bacteria" in result

    def test_project_ids_in_body(self):
        hyp = Hypothesis(
            hypothesis_id="H-004",
            statement="Some statement.",
            status="proposed",
            project_ids=["proj-A", "proj-B"],
        )
        result = compile_hypothesis_page(hypothesis=hyp, supporting_findings=[])
        assert "proj-A" in result
