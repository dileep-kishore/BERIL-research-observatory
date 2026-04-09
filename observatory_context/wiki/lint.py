"""Wiki lint: gap, orphan, and coverage detection for the knowledge registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import yaml

from observatory_context.registry.schema import Finding, Hypothesis, ResearchIdea


@dataclass
class LintIssue:
    kind: str  # untested_hypothesis, orphan_idea, low_coverage, contradiction, stale_page
    ref_id: str
    message: str
    severity: str = "medium"  # low, medium, high


# ---------------------------------------------------------------------------
# Detection functions
# ---------------------------------------------------------------------------


def detect_untested_hypotheses(hypotheses: list[Hypothesis]) -> list[LintIssue]:
    """Find hypotheses with status == "proposed" that have not been tested.

    Parameters
    ----------
    hypotheses:
        List of Hypothesis records to inspect.

    Returns
    -------
    list[LintIssue]
        One issue per untested hypothesis, severity="medium".
    """
    issues: list[LintIssue] = []
    for h in hypotheses:
        if h.status == "proposed":
            issues.append(
                LintIssue(
                    kind="untested_hypothesis",
                    ref_id=h.hypothesis_id,
                    message=f"{h.hypothesis_id} has status 'proposed' and has not been tested.",
                    severity="medium",
                )
            )
    return issues


def detect_orphan_ideas(ideas: list[ResearchIdea]) -> list[LintIssue]:
    """Find proposed ideas with no linked projects.

    Parameters
    ----------
    ideas:
        List of ResearchIdea records to inspect.

    Returns
    -------
    list[LintIssue]
        One issue per orphan idea, severity="low".
    """
    issues: list[LintIssue] = []
    for idea in ideas:
        if idea.status == "proposed" and not idea.project_ids:
            issues.append(
                LintIssue(
                    kind="orphan_idea",
                    ref_id=idea.idea_id,
                    message=f"{idea.idea_id} is proposed but not linked to any project.",
                    severity="low",
                )
            )
    return issues


def detect_low_coverage_topics(findings_by_topic: dict[str, list[Finding]]) -> list[LintIssue]:
    """Find topics covered by fewer than 2 unique projects.

    Parameters
    ----------
    findings_by_topic:
        Mapping of topic slug to the findings relevant to that topic.

    Returns
    -------
    list[LintIssue]
        One issue per under-covered topic, severity="low".
    """
    issues: list[LintIssue] = []
    for topic, findings in findings_by_topic.items():
        project_count = len({f.project_id for f in findings})
        if project_count < 2:
            issues.append(
                LintIssue(
                    kind="low_coverage",
                    ref_id=topic,
                    message=(
                        f"Topic '{topic}' is covered by {project_count} project(s); "
                        "at least 2 recommended."
                    ),
                    severity="low",
                )
            )
    return issues


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

_SEVERITY_ICONS: dict[str, str] = {
    "high": "!!!",
    "medium": "!!",
    "low": "!",
}


def build_gap_report(issues: list[LintIssue]) -> str:
    """Build a markdown gap report with YAML frontmatter.

    Parameters
    ----------
    issues:
        All lint issues to include in the report.

    Returns
    -------
    str
        Markdown string with YAML frontmatter and issues grouped by kind.
    """
    today = date.today().isoformat()

    frontmatter = yaml.dump(
        {
            "title": "Observatory Gap Report",
            "kind": "gap_report",
            "last_compiled": today,
            "issue_count": len(issues),
        },
        default_flow_style=False,
        sort_keys=True,
    ).rstrip()

    lines: list[str] = [f"---\n{frontmatter}\n---\n", "# Observatory Gap Report", ""]

    # Group by kind
    by_kind: dict[str, list[LintIssue]] = {}
    for issue in issues:
        by_kind.setdefault(issue.kind, []).append(issue)

    if not issues:
        lines.append("No issues detected.")
    else:
        for kind, kind_issues in by_kind.items():
            lines.append(f"## {kind}")
            lines.append("")
            for issue in kind_issues:
                icon = _SEVERITY_ICONS.get(issue.severity, "!")
                lines.append(f"- [{icon}] **{issue.ref_id}**: {issue.message}")
            lines.append("")

    return "\n".join(lines)
