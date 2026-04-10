"""Generate a 1-page markdown report from the observatory knowledge graph."""

from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from observatory_context.graph.builder import GraphBuilder


def generate_graph_report(builder: GraphBuilder) -> str:
    """Produce a concise markdown report for agent navigation.

    The report summarises entity counts by type, top communities,
    cross-project connections, research gaps, and potential contradictions
    in roughly 300-500 words.

    Parameters
    ----------
    builder
        A populated ``GraphBuilder`` instance.

    Returns
    -------
    str
        Markdown-formatted report.
    """
    G = builder.G
    stats = builder.stats
    today = date.today().isoformat()

    # -- Entity summary by type ---------------------------------------------
    entity_type_counts: Counter[str] = Counter()
    entity_type_examples: dict[str, list[str]] = {}
    for _n, d in G.nodes(data=True):
        if d.get("kind") != "entity":
            continue
        etype = d.get("entity_type", "unknown")
        entity_type_counts[etype] += 1
        examples = entity_type_examples.setdefault(etype, [])
        if len(examples) < 3:
            examples.append(d.get("canonical_name", "?"))

    entity_rows = ""
    for etype, count in entity_type_counts.most_common():
        examples_str = ", ".join(entity_type_examples.get(etype, []))
        entity_rows += f"| {etype.capitalize()} | {count} | {examples_str} |\n"

    # -- Communities --------------------------------------------------------
    communities = builder.build_communities()
    community_lines = ""
    for cid, info in sorted(
        communities.items(), key=lambda x: len(x[1]["members"]), reverse=True
    )[:5]:
        projects_str = ", ".join(info["projects"][:4])
        # Grab top findings connected to community members
        top_findings: list[str] = []
        for member in info["members"][:10]:
            for pred in G.predecessors(member):
                nd = G.nodes[pred]
                if nd.get("kind") == "finding" and nd.get("title"):
                    title = nd["title"]
                    if title not in top_findings:
                        top_findings.append(title)
                    if len(top_findings) >= 3:
                        break
            if len(top_findings) >= 3:
                break
        findings_str = "; ".join(top_findings) if top_findings else "—"
        community_lines += (
            f"{cid + 1}. **{info['name']}** ({len(info['members'])} entities) "
            f"— {projects_str}\n"
            f"   Key findings: {findings_str}\n"
        )

    if not community_lines:
        community_lines = "_No communities detected (too few entity connections)._\n"

    # -- Cross-project connections ------------------------------------------
    cross = builder.get_cross_project_entities(min_projects=2)
    cross_lines = ""
    for item in cross[:8]:
        plist = ", ".join(item["projects"])
        cross_lines += (
            f"- **{item['entity']}** ({item['entity_type']}): "
            f"studied in {item['count']} projects ({plist})\n"
        )
    if not cross_lines:
        cross_lines = "_No cross-project entities found yet._\n"

    # -- Gaps ---------------------------------------------------------------
    gaps = builder.detect_gaps()
    gap_counts: Counter[str] = Counter(g["gap_type"] for g in gaps)
    gap_lines = ""
    if gap_counts.get("low_coverage_organism", 0):
        gap_lines += (
            f"- {gap_counts['low_coverage_organism']} organisms mentioned "
            "but not primary subject\n"
        )
    if gap_counts.get("untested_hypothesis", 0):
        gap_lines += (
            f"- {gap_counts['untested_hypothesis']} hypotheses proposed "
            "but never tested\n"
        )
    if gap_counts.get("no_hypothesis", 0):
        gap_lines += (
            f"- {gap_counts['no_hypothesis']} entities with findings "
            "but no linked hypothesis (low coverage)\n"
        )
    if not gap_lines:
        gap_lines = "_No research gaps detected._\n"

    # -- Contradictions -----------------------------------------------------
    contradictions = builder.detect_contradictions()
    contradiction_lines = ""
    for c in contradictions[:5]:
        contradiction_lines += (
            f"- **{c['entity']}**: {c['finding_a']} vs {c['finding_b']} "
            f"({c['reason']})\n"
        )
    if not contradiction_lines:
        contradiction_lines = "_No contradictions detected._\n"

    # -- Assemble -----------------------------------------------------------
    num_communities = len(communities)
    report = f"""\
# Observatory Knowledge Graph

**Last built**: {today} | **Entities**: {stats['entities']} | **Relations**: {stats['edges']} | **Projects**: {stats['projects']} | **Communities**: {num_communities}

## Entity Summary

| Type | Count | Examples |
|------|-------|----------|
{entity_rows.rstrip()}

## Top Communities

{community_lines.rstrip()}

## Cross-Project Connections

{cross_lines.rstrip()}

## Research Gaps

{gap_lines.rstrip()}

## Potential Contradictions

{contradiction_lines.rstrip()}
"""
    return report


def save_report(content: str, path: Path) -> None:
    """Write the report markdown to disk.

    Parameters
    ----------
    content
        Markdown string (from ``generate_graph_report``).
    path
        Destination file path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
