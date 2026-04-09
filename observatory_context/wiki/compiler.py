"""Wiki page compiler: produces markdown with YAML frontmatter from registry data."""

from __future__ import annotations

from datetime import date

import yaml

from observatory_context.registry.schema import Finding, Hypothesis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coverage_label(source_count: int) -> str:
    """Map a source count to a coverage label."""
    if source_count >= 5:
        return "high"
    if source_count >= 2:
        return "medium"
    return "low"


def _frontmatter(metadata: dict) -> str:
    """Render a YAML frontmatter block."""
    return f"---\n{yaml.dump(metadata, default_flow_style=False, sort_keys=True).rstrip()}\n---\n\n"


def _today() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Compilers
# ---------------------------------------------------------------------------


def compile_entity_page(
    *,
    entity_type: str,
    slug: str,
    label: str,
    findings: list[Finding],
    hypotheses: list[Hypothesis],
    project_ids: list[str],
) -> str:
    """Compile a wiki page for a named entity.

    Parameters
    ----------
    entity_type:
        The entity class (e.g. "organism", "gene", "pathway").
    slug:
        URL-safe identifier for this entity.
    label:
        Human-readable display name.
    findings:
        Findings that mention this entity.
    hypotheses:
        Hypotheses that involve this entity.
    project_ids:
        Projects this entity appears in.

    Returns
    -------
    str
        Markdown string with YAML frontmatter.
    """
    source_count = len(findings)
    coverage = _coverage_label(source_count)

    fm = _frontmatter(
        {
            "title": label,
            "kind": "entity_profile",
            "entity_type": entity_type,
            "sources": source_count,
            "coverage": coverage,
            "last_compiled": _today(),
        }
    )

    lines: list[str] = [f"# {label}", ""]
    lines.append(f"**Entity type:** {entity_type}")
    lines.append("")

    if project_ids:
        lines.append(f"**Projects:** {', '.join(project_ids)}")
        lines.append("")

    lines.append(f"**Coverage:** {coverage}")
    lines.append("")

    # Key Findings
    lines.append("## Key Findings")
    lines.append("")
    if findings:
        for f in findings:
            lines.append(f"- **{f.finding_id}**: {f.title} — {f.statement}")
    else:
        lines.append("No findings recorded yet.")
    lines.append("")

    # Related Hypotheses
    lines.append("## Related Hypotheses")
    lines.append("")
    if hypotheses:
        for h in hypotheses:
            lines.append(f"- **{h.hypothesis_id}** ({h.status}): {h.statement}")
    else:
        lines.append("No hypotheses recorded yet.")
    lines.append("")

    return fm + "\n".join(lines)


def compile_topic_page(
    *,
    slug: str,
    title: str,
    findings: list[Finding],
    hypotheses: list[Hypothesis],
    project_ids: list[str],
) -> str:
    """Compile a synthesis wiki page for a research topic.

    Parameters
    ----------
    slug:
        URL-safe identifier for this topic.
    title:
        Human-readable topic title.
    findings:
        Findings relevant to this topic.
    hypotheses:
        Hypotheses relevant to this topic.
    project_ids:
        Projects covering this topic.

    Returns
    -------
    str
        Markdown string with YAML frontmatter.
    """
    source_count = len(findings)
    coverage = _coverage_label(source_count)

    fm = _frontmatter(
        {
            "title": title,
            "kind": "topic_synthesis",
            "sources": source_count,
            "coverage": coverage,
            "last_compiled": _today(),
        }
    )

    lines: list[str] = [f"# {title}", ""]
    lines.append(
        f"Topic synthesis across {len(project_ids)} project(s). Coverage: **{coverage}**."
    )
    lines.append("")

    # Key Findings — numbered list
    lines.append("## Key Findings")
    lines.append("")
    if findings:
        for i, f in enumerate(findings, start=1):
            lines.append(f"{i}. **{f.finding_id}**: {f.title} — {f.statement}")
    else:
        lines.append("No findings recorded yet.")
    lines.append("")

    # Hypotheses table
    lines.append("## Hypotheses")
    lines.append("")
    lines.append("| ID | Statement | Status |")
    lines.append("|----|-----------|--------|")
    for h in hypotheses:
        lines.append(f"| {h.hypothesis_id} | {h.statement} | {h.status} |")
    if not hypotheses:
        lines.append("| — | No hypotheses yet. | — |")
    lines.append("")

    # Open Questions
    lines.append("## Open Questions")
    lines.append("")
    lines.append("_Placeholder: add open questions as the topic develops._")
    lines.append("")

    return fm + "\n".join(lines)


def compile_hypothesis_page(
    *,
    hypothesis: Hypothesis,
    supporting_findings: list[Finding],
) -> str:
    """Compile a tracker wiki page for a hypothesis.

    Parameters
    ----------
    hypothesis:
        The hypothesis record to document.
    supporting_findings:
        Findings that support or test this hypothesis.

    Returns
    -------
    str
        Markdown string with YAML frontmatter.
    """
    source_count = len(supporting_findings)
    coverage = _coverage_label(source_count)

    statement_excerpt = hypothesis.statement[:80]
    fm_title = f"{hypothesis.hypothesis_id}: {statement_excerpt}"

    fm = _frontmatter(
        {
            "title": fm_title,
            "kind": "hypothesis_tracker",
            "coverage": coverage,
            "last_compiled": _today(),
        }
    )

    lines: list[str] = [f"# {hypothesis.hypothesis_id}", ""]
    lines.append(f"**Statement:** {hypothesis.statement}")
    lines.append("")
    lines.append(f"**Status:** {hypothesis.status}")
    lines.append("")

    if hypothesis.scope:
        lines.append(f"**Scope:** {hypothesis.scope}")
        lines.append("")

    if hypothesis.project_ids:
        lines.append(f"**Projects:** {', '.join(hypothesis.project_ids)}")
        lines.append("")

    lines.append(f"**Coverage:** {coverage}")
    lines.append("")

    # Supporting Evidence
    lines.append("## Supporting Evidence")
    lines.append("")
    if supporting_findings:
        for f in supporting_findings:
            lines.append(f"- **{f.finding_id}**: {f.title} — {f.statement}")
    else:
        lines.append("No supporting findings recorded yet.")
    lines.append("")

    return fm + "\n".join(lines)
