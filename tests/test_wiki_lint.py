"""Tests for the wiki lint gap/contradiction detection module."""

from __future__ import annotations

import yaml

from observatory_context.registry.schema import Finding, Hypothesis, ResearchIdea
from observatory_context.wiki.lint import (
    LintIssue,
    build_gap_report,
    detect_low_coverage_topics,
    detect_orphan_ideas,
    detect_untested_hypotheses,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hypothesis(
    hypothesis_id: str,
    status: str = "proposed",
) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=hypothesis_id,
        statement=f"Statement for {hypothesis_id}.",
        status=status,
        project_ids=["proj-001"],
    )


def _make_idea(
    idea_id: str,
    status: str = "proposed",
    project_ids: list[str] | None = None,
) -> ResearchIdea:
    return ResearchIdea(
        idea_id=idea_id,
        statement=f"Idea {idea_id} statement.",
        motivation="Some motivation.",
        priority="medium",
        status=status,
        project_ids=project_ids if project_ids is not None else [],
    )


def _make_finding(finding_id: str, project_id: str = "proj-001") -> Finding:
    return Finding(
        finding_id=finding_id,
        project_id=project_id,
        title=f"Finding {finding_id}",
        statement=f"Statement for {finding_id}.",
        confidence="high",
        finding_type="result",
    )


def _parse_frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "Expected frontmatter to start with ---"
    end = text.index("\n---\n", 4)
    return yaml.safe_load(text[4:end])


# ---------------------------------------------------------------------------
# detect_untested_hypotheses
# ---------------------------------------------------------------------------


class TestDetectUntestedHypotheses:
    def test_proposed_hypothesis_flagged(self):
        h = _make_hypothesis("H-001", status="proposed")
        issues = detect_untested_hypotheses([h])
        assert len(issues) == 1
        assert issues[0].ref_id == "H-001"
        assert issues[0].kind == "untested_hypothesis"

    def test_tested_hypothesis_not_flagged(self):
        h = _make_hypothesis("H-001", status="tested")
        issues = detect_untested_hypotheses([h])
        assert issues == []

    def test_supported_hypothesis_not_flagged(self):
        h = _make_hypothesis("H-001", status="supported")
        issues = detect_untested_hypotheses([h])
        assert issues == []

    def test_multiple_proposed_returns_all(self):
        hypotheses = [
            _make_hypothesis("H-001", status="proposed"),
            _make_hypothesis("H-002", status="supported"),
            _make_hypothesis("H-003", status="proposed"),
        ]
        issues = detect_untested_hypotheses(hypotheses)
        ref_ids = [i.ref_id for i in issues]
        assert "H-001" in ref_ids
        assert "H-003" in ref_ids
        assert "H-002" not in ref_ids

    def test_severity_is_medium(self):
        h = _make_hypothesis("H-001", status="proposed")
        issues = detect_untested_hypotheses([h])
        assert issues[0].severity == "medium"

    def test_empty_list_returns_no_issues(self):
        assert detect_untested_hypotheses([]) == []

    def test_message_references_ref_id(self):
        h = _make_hypothesis("H-099", status="proposed")
        issues = detect_untested_hypotheses([h])
        assert "H-099" in issues[0].message


# ---------------------------------------------------------------------------
# detect_orphan_ideas
# ---------------------------------------------------------------------------


class TestDetectOrphanIdeas:
    def test_proposed_with_no_projects_flagged(self):
        idea = _make_idea("I-001", status="proposed", project_ids=[])
        issues = detect_orphan_ideas([idea])
        assert len(issues) == 1
        assert issues[0].ref_id == "I-001"
        assert issues[0].kind == "orphan_idea"

    def test_proposed_with_projects_not_flagged(self):
        idea = _make_idea("I-001", status="proposed", project_ids=["proj-001"])
        issues = detect_orphan_ideas([idea])
        assert issues == []

    def test_in_progress_with_no_projects_not_flagged(self):
        idea = _make_idea("I-001", status="in_progress", project_ids=[])
        issues = detect_orphan_ideas([idea])
        assert issues == []

    def test_completed_with_no_projects_not_flagged(self):
        idea = _make_idea("I-001", status="completed", project_ids=[])
        issues = detect_orphan_ideas([idea])
        assert issues == []

    def test_severity_is_low(self):
        idea = _make_idea("I-001", status="proposed", project_ids=[])
        issues = detect_orphan_ideas([idea])
        assert issues[0].severity == "low"

    def test_empty_list_returns_no_issues(self):
        assert detect_orphan_ideas([]) == []

    def test_multiple_orphans_all_returned(self):
        ideas = [
            _make_idea("I-001", status="proposed", project_ids=[]),
            _make_idea("I-002", status="proposed", project_ids=["proj-001"]),
            _make_idea("I-003", status="proposed", project_ids=[]),
        ]
        issues = detect_orphan_ideas(ideas)
        ref_ids = [i.ref_id for i in issues]
        assert "I-001" in ref_ids
        assert "I-003" in ref_ids
        assert "I-002" not in ref_ids

    def test_message_references_ref_id(self):
        idea = _make_idea("I-042", status="proposed", project_ids=[])
        issues = detect_orphan_ideas([idea])
        assert "I-042" in issues[0].message


# ---------------------------------------------------------------------------
# detect_low_coverage_topics
# ---------------------------------------------------------------------------


class TestDetectLowCoverageTopics:
    def test_single_project_topic_flagged(self):
        findings = {"nitrogen-cycling": [_make_finding("F-001", "proj-A")]}
        issues = detect_low_coverage_topics(findings)
        assert len(issues) == 1
        assert issues[0].kind == "low_coverage"
        assert "nitrogen-cycling" in issues[0].ref_id

    def test_two_project_topic_not_flagged(self):
        findings = {
            "nitrogen-cycling": [
                _make_finding("F-001", "proj-A"),
                _make_finding("F-002", "proj-B"),
            ]
        }
        issues = detect_low_coverage_topics(findings)
        assert issues == []

    def test_same_project_multiple_findings_counts_as_one(self):
        findings = {
            "carbon-cycling": [
                _make_finding("F-001", "proj-A"),
                _make_finding("F-002", "proj-A"),
                _make_finding("F-003", "proj-A"),
            ]
        }
        issues = detect_low_coverage_topics(findings)
        assert len(issues) == 1

    def test_empty_findings_list_flagged(self):
        findings = {"orphan-topic": []}
        issues = detect_low_coverage_topics(findings)
        assert len(issues) == 1
        assert "orphan-topic" in issues[0].ref_id

    def test_severity_is_low(self):
        findings = {"topic-a": [_make_finding("F-001", "proj-A")]}
        issues = detect_low_coverage_topics(findings)
        assert issues[0].severity == "low"

    def test_empty_dict_returns_no_issues(self):
        assert detect_low_coverage_topics({}) == []

    def test_mixed_topics(self):
        findings = {
            "topic-good": [
                _make_finding("F-001", "proj-A"),
                _make_finding("F-002", "proj-B"),
            ],
            "topic-bad": [_make_finding("F-003", "proj-A")],
        }
        issues = detect_low_coverage_topics(findings)
        assert len(issues) == 1
        assert "topic-bad" in issues[0].ref_id

    def test_message_references_topic(self):
        findings = {"my-topic": [_make_finding("F-001", "proj-A")]}
        issues = detect_low_coverage_topics(findings)
        assert "my-topic" in issues[0].message


# ---------------------------------------------------------------------------
# build_gap_report
# ---------------------------------------------------------------------------


class TestBuildGapReport:
    def _make_issues(self) -> list[LintIssue]:
        return [
            LintIssue(kind="untested_hypothesis", ref_id="H-001", message="Needs testing.", severity="medium"),
            LintIssue(kind="orphan_idea", ref_id="I-001", message="No project linked.", severity="low"),
            LintIssue(kind="low_coverage", ref_id="topic-a", message="Only 1 project.", severity="low"),
            LintIssue(kind="untested_hypothesis", ref_id="H-002", message="Another untested.", severity="medium"),
        ]

    def test_has_frontmatter(self):
        report = build_gap_report(self._make_issues())
        assert report.startswith("---\n")
        assert "\n---\n" in report

    def test_frontmatter_title(self):
        report = build_gap_report(self._make_issues())
        fm = _parse_frontmatter(report)
        assert "title" in fm

    def test_frontmatter_kind_is_gap_report(self):
        report = build_gap_report(self._make_issues())
        fm = _parse_frontmatter(report)
        assert fm["kind"] == "gap_report"

    def test_frontmatter_issue_count(self):
        issues = self._make_issues()
        report = build_gap_report(issues)
        fm = _parse_frontmatter(report)
        assert fm["issue_count"] == len(issues)

    def test_frontmatter_last_compiled(self):
        report = build_gap_report(self._make_issues())
        fm = _parse_frontmatter(report)
        assert "last_compiled" in fm

    def test_issues_grouped_by_kind(self):
        report = build_gap_report(self._make_issues())
        # Both untested hypotheses H-001 and H-002 should appear under the same section
        assert "untested_hypothesis" in report
        assert "orphan_idea" in report
        assert "low_coverage" in report

    def test_ref_ids_appear_in_body(self):
        report = build_gap_report(self._make_issues())
        assert "H-001" in report
        assert "I-001" in report
        assert "topic-a" in report

    def test_high_severity_icon(self):
        issues = [LintIssue(kind="untested_hypothesis", ref_id="H-001", message="msg", severity="high")]
        report = build_gap_report(issues)
        assert "!!!" in report

    def test_medium_severity_icon(self):
        issues = [LintIssue(kind="untested_hypothesis", ref_id="H-001", message="msg", severity="medium")]
        report = build_gap_report(issues)
        assert "!!" in report

    def test_low_severity_icon(self):
        issues = [LintIssue(kind="orphan_idea", ref_id="I-001", message="msg", severity="low")]
        report = build_gap_report(issues)
        assert "!" in report

    def test_empty_issues_returns_valid_report(self):
        report = build_gap_report([])
        fm = _parse_frontmatter(report)
        assert fm["issue_count"] == 0

    def test_messages_appear_in_body(self):
        issues = [LintIssue(kind="low_coverage", ref_id="topic-x", message="Only 1 project.", severity="low")]
        report = build_gap_report(issues)
        assert "Only 1 project." in report
