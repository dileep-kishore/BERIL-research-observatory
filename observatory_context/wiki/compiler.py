"""Wiki page compiler: produces interconnected markdown with YAML frontmatter.

Pages link to each other using relative markdown links so the agent can
navigate the wiki by following connections rather than searching.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import yaml

from observatory_context._text import slugify
from observatory_context.graph.knowledge_synthesis import (
    SynthesizedEntity,
    SynthesizedHypothesis,
    SynthesizedTopic,
)
from observatory_context.registry.schema import Finding, Hypothesis
from observatory_context.uris import _ENTITY_TYPE_PLURALS


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


def _entity_link(entity_type: str, label: str) -> str:
    """Generate a relative markdown link to an entity page."""
    plural = _ENTITY_TYPE_PLURALS.get(entity_type, f"{entity_type}s")
    slug = slugify(label)
    return f"[{label}](wiki/entities/{plural}/{slug}.md)"


def _topic_link(project_id: str) -> str:
    """Generate a relative markdown link to a topic page."""
    slug = slugify(project_id)
    return f"[{project_id}](wiki/topics/{slug}.md)"


def _hypothesis_link(hypothesis_id: str) -> str:
    """Generate a relative markdown link to a hypothesis page."""
    slug = slugify(hypothesis_id)
    return f"[{hypothesis_id}](wiki/hypotheses/{slug}.md)"


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
    related_entities: list[dict[str, Any]] | None = None,
    community: dict[str, Any] | None = None,
) -> str:
    """Compile a wiki page for a named entity with cross-links.

    Parameters
    ----------
    entity_type
        The entity class (e.g. "organism", "gene", "pathway").
    slug
        URL-safe identifier for this entity.
    label
        Human-readable display name.
    findings
        Findings that mention this entity.
    hypotheses
        Hypotheses that involve this entity.
    project_ids
        Projects this entity appears in.
    related_entities
        Co-occurring entities: ``[{type, label, weight}, ...]``.
    community
        Community info: ``{name, members, ...}``.
    """
    related_entities = related_entities or []
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

    # Projects as links
    if project_ids:
        links = [_topic_link(pid) for pid in project_ids]
        lines.append(f"**Projects:** {', '.join(links)}")
        lines.append("")

    lines.append(f"**Coverage:** {coverage}")
    lines.append("")

    # Key Findings with entity cross-links
    lines.append("## Key Findings")
    lines.append("")
    if findings:
        for f in findings:
            # Link entities mentioned in the finding
            statement = f.statement
            topic = _topic_link(f.project_id)
            lines.append(f"- **{f.finding_id}**: {f.title} — {statement} ({topic})")
    else:
        lines.append("No findings recorded yet.")
    lines.append("")

    # Related Hypotheses as links
    lines.append("## Related Hypotheses")
    lines.append("")
    if hypotheses:
        for h in hypotheses:
            link = _hypothesis_link(h.hypothesis_id)
            lines.append(f"- {link} ({h.status}): {h.statement}")
    else:
        lines.append("No hypotheses recorded yet.")
    lines.append("")

    # Related Entities (from graph co-occurrence)
    if related_entities:
        lines.append("## Related Entities")
        lines.append("")
        for rel in sorted(related_entities, key=lambda r: r.get("weight", 0), reverse=True)[:10]:
            link = _entity_link(rel["type"], rel["label"])
            weight = rel.get("weight", 1)
            lines.append(f"- {link} (co-occurs in {weight} finding{'s' if weight != 1 else ''})")
        lines.append("")

    # Community membership
    if community:
        lines.append("## Community")
        lines.append("")
        lines.append(f"Member of **{community.get('name', 'unnamed')}** cluster "
                      f"({community.get('size', '?')} entities).")
        lines.append("")

    return fm + "\n".join(lines)


def compile_topic_page(
    *,
    slug: str,
    title: str,
    findings: list[Finding],
    hypotheses: list[Hypothesis],
    project_ids: list[str],
    entities_studied: list[dict[str, Any]] | None = None,
) -> str:
    """Compile a synthesis wiki page for a research topic with cross-links.

    Parameters
    ----------
    slug
        URL-safe identifier for this topic.
    title
        Human-readable topic title.
    findings
        Findings relevant to this topic.
    hypotheses
        Hypotheses relevant to this topic.
    project_ids
        Projects covering this topic.
    entities_studied
        Entities studied in this project: ``[{type, label}, ...]``.
    """
    entities_studied = entities_studied or []
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
    if project_ids:
        lines.append(f"**Projects:** {', '.join(_topic_link(project_id) for project_id in project_ids)}")
        lines.append("")

    # Entities studied (linked)
    if entities_studied:
        lines.append("## Entities Studied")
        lines.append("")
        for ent in entities_studied:
            link = _entity_link(ent["type"], ent["label"])
            lines.append(f"- {link} ({ent['type']})")
        lines.append("")

    # Key Findings with entity links
    lines.append("## Key Findings")
    lines.append("")
    if findings:
        for i, f in enumerate(findings, start=1):
            # Cross-link related entities within the finding
            entity_links = [_entity_link(ref.type, ref.label) for ref in f.related_entities]
            entity_str = f" — entities: {', '.join(entity_links)}" if entity_links else ""
            lines.append(f"{i}. **{f.finding_id}**: {f.title} — {f.statement}{entity_str}")
    else:
        lines.append("No findings recorded yet.")
    lines.append("")

    # Hypotheses table with links
    lines.append("## Hypotheses")
    lines.append("")
    lines.append("| ID | Statement | Status |")
    lines.append("|----|-----------|--------|")
    for h in hypotheses:
        link = _hypothesis_link(h.hypothesis_id)
        lines.append(f"| {link} | {h.statement} | {h.status} |")
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
    """Compile a tracker wiki page for a hypothesis with cross-links.

    Parameters
    ----------
    hypothesis
        The hypothesis record to document.
    supporting_findings
        Findings that support or test this hypothesis.
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

    # Projects as links
    if hypothesis.project_ids:
        links = [_topic_link(pid) for pid in hypothesis.project_ids]
        lines.append(f"**Projects:** {', '.join(links)}")
        lines.append("")

    lines.append(f"**Coverage:** {coverage}")
    lines.append("")

    # Related entities (linked)
    if hypothesis.related_entities:
        lines.append("## Related Entities")
        lines.append("")
        for ref in hypothesis.related_entities:
            link = _entity_link(ref.type, ref.label)
            lines.append(f"- {link} ({ref.type})")
        lines.append("")

    # Supporting Evidence with project links
    lines.append("## Supporting Evidence")
    lines.append("")
    if supporting_findings:
        for f in supporting_findings:
            topic = _topic_link(f.project_id)
            lines.append(f"- **{f.finding_id}**: {f.title} — {f.statement} ({topic})")
    else:
        lines.append("No supporting findings recorded yet.")
    lines.append("")

    return fm + "\n".join(lines)


def compile_entity_page_from_synthesis(
    entity: SynthesizedEntity,
    *,
    findings_by_id: dict[str, Finding],
    hypotheses_by_id: dict[str, Hypothesis],
) -> str:
    """Compile an entity page from synthesis-layer summaries."""
    return compile_entity_page(
        entity_type=entity.entity_type,
        slug=entity.slug,
        label=entity.canonical_name,
        findings=[findings_by_id[finding_id] for finding_id in entity.finding_ids if finding_id in findings_by_id],
        hypotheses=[
            hypotheses_by_id[hypothesis_id]
            for hypothesis_id in entity.hypothesis_ids
            if hypothesis_id in hypotheses_by_id
        ],
        project_ids=entity.project_ids,
        related_entities=[
            {
                "type": related.entity_type,
                "label": related.canonical_name,
                "weight": related.weight,
            }
            for related in entity.related_entities
        ],
        community=(
            {
                "name": entity.community_name,
                "size": entity.community_size,
            }
            if entity.community_name
            else None
        ),
    )


def compile_hypothesis_page_from_synthesis(
    hypothesis: SynthesizedHypothesis,
    *,
    findings_by_id: dict[str, Finding],
    hypotheses_by_id: dict[str, Hypothesis],
) -> str:
    """Compile a hypothesis page from synthesis-layer summaries."""
    hypothesis_model = hypotheses_by_id[hypothesis.hypothesis_id]
    return compile_hypothesis_page(
        hypothesis=hypothesis_model,
        supporting_findings=[
            findings_by_id[finding_id]
            for finding_id in hypothesis.supporting_findings
            if finding_id in findings_by_id
        ],
    )


def compile_topic_page_from_synthesis(
    topic: SynthesizedTopic,
    *,
    findings_by_id: dict[str, Finding],
    hypotheses_by_id: dict[str, Hypothesis],
) -> str:
    """Compile a topic page from synthesis-layer summaries."""
    return compile_topic_page(
        slug=topic.slug,
        title=topic.title,
        findings=[findings_by_id[finding_id] for finding_id in topic.finding_ids if finding_id in findings_by_id],
        hypotheses=[
            hypotheses_by_id[hypothesis_id]
            for hypothesis_id in topic.hypothesis_ids
            if hypothesis_id in hypotheses_by_id
        ],
        project_ids=topic.project_ids,
        entities_studied=topic.entity_refs,
    )
