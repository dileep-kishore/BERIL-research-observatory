"""Deterministic synthesis of observatory knowledge from registry and graph state."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import networkx as nx
from pydantic import BaseModel, Field

from observatory_context._text import slugify
from observatory_context.registry.schema import Finding, Hypothesis


def _coverage_label(count: int) -> str:
    if count >= 5:
        return "high"
    if count >= 2:
        return "medium"
    return "low"


def _frontmatter_kind(kind: str, title: str, project_ids: list[str] | None = None) -> dict[str, Any]:
    metadata: dict[str, Any] = {"kind": kind, "title": title}
    if project_ids:
        metadata["project_ids"] = project_ids
    return metadata


class RelatedEntitySummary(BaseModel):
    """Aggregated relation between two synthesized entities."""

    canonical_name: str
    entity_type: str
    slug: str
    weight: int = 1
    project_ids: list[str] = Field(default_factory=list)


class SynthesizedEntity(BaseModel):
    """Cross-project summary for an entity."""

    canonical_name: str
    entity_type: str
    slug: str
    aliases: list[str] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)
    hypothesis_ids: list[str] = Field(default_factory=list)
    related_entities: list[RelatedEntitySummary] = Field(default_factory=list)
    community_id: int | None = None
    community_name: str | None = None
    community_size: int | None = None
    coverage: str = "low"
    abstract: str = ""
    overview: str = ""
    profile: dict[str, Any] = Field(default_factory=dict)


class SynthesizedHypothesis(BaseModel):
    """Cross-project summary for a hypothesis."""

    hypothesis_id: str
    slug: str
    statement: str
    status: str
    project_ids: list[str] = Field(default_factory=list)
    supporting_findings: list[str] = Field(default_factory=list)
    related_entities: list[RelatedEntitySummary] = Field(default_factory=list)
    coverage: str = "low"
    abstract: str = ""
    overview: str = ""
    hypothesis: dict[str, Any] = Field(default_factory=dict)


class SynthesizedTopic(BaseModel):
    """Cross-project synthesis page."""

    topic_id: str
    slug: str
    title: str
    project_ids: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)
    hypothesis_ids: list[str] = Field(default_factory=list)
    entity_refs: list[dict[str, Any]] = Field(default_factory=list)
    abstract: str = ""
    overview: str = ""
    topic: dict[str, Any] = Field(default_factory=dict)


class SynthesizedCommunity(BaseModel):
    """Graph-cluster summary."""

    community_id: int
    name: str
    members: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    summary: str = ""
    entities: list[dict[str, Any]] = Field(default_factory=list)


class SynthesizedTimelineEvent(BaseModel):
    """Timeline entry derived from the synthesized observatory state."""

    event_id: str
    label: str
    sort_key: str
    project_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    kind: str = "knowledge_snapshot"


class KnowledgeSynthesisBundle(BaseModel):
    """Structured outputs from the knowledge synthesis layer."""

    entities: list[SynthesizedEntity] = Field(default_factory=list)
    hypotheses: list[SynthesizedHypothesis] = Field(default_factory=list)
    topics: list[SynthesizedTopic] = Field(default_factory=list)
    communities: list[SynthesizedCommunity] = Field(default_factory=list)
    timeline_events: list[SynthesizedTimelineEvent] = Field(default_factory=list)


class KnowledgeSynthesizer:
    """Aggregate registry entries and graph structure into synthesis objects."""

    def synthesize(
        self,
        *,
        findings: list[Finding],
        hypotheses: list[Hypothesis],
        project_ids: list[str] | None = None,
        graph: nx.MultiDiGraph | None = None,
        communities: dict[int, dict[str, Any]] | None = None,
    ) -> KnowledgeSynthesisBundle:
        """Build a deterministic synthesis bundle."""

        selected_projects = sorted(set(project_ids or self._collect_projects(findings, hypotheses)))
        finding_by_id = {finding.finding_id: finding for finding in findings}
        hypothesis_by_id = {hypothesis.hypothesis_id: hypothesis for hypothesis in hypotheses}

        entity_nodes = self._collect_entity_nodes(graph)
        entity_lookup = {node_id: data for node_id, data in entity_nodes}
        entity_order = sorted(
            entity_lookup,
            key=lambda node_id: slugify(str(entity_lookup[node_id].get("canonical_name", node_id))),
        )

        community_lookup = self._build_community_lookup(communities or {})

        entity_summaries: list[SynthesizedEntity] = []
        for node_id in entity_order:
            data = entity_lookup[node_id]
            summary = self._build_entity_summary(
                node_id=node_id,
                data=data,
                findings=findings,
                hypotheses=hypotheses,
                graph=graph,
                community_lookup=community_lookup,
            )
            entity_summaries.append(summary)

        hypothesis_summaries = [
            self._build_hypothesis_summary(
                hypothesis=hypothesis_by_id[hypothesis_id],
                findings=findings,
                graph=graph,
            )
            for hypothesis_id in sorted(hypothesis_by_id)
        ]

        if communities:
            topic_summaries = [
                self._build_community_topic_summary(
                    community_id=community_id,
                    data=data,
                    findings=findings,
                    hypotheses=hypotheses,
                    graph=graph,
                )
                for community_id, data in sorted((int(k), v) for k, v in communities.items())
            ]
        else:
            topic_summaries = [
                self._build_project_topic_summary(
                    project_id=project_id,
                    findings=findings,
                    hypotheses=hypotheses,
                    graph=graph,
                )
                for project_id in selected_projects
            ]

        community_summaries = [
            self._build_community_summary(
                community_id=community_id,
                data=data,
                graph=graph,
            )
            for community_id, data in sorted((int(k), v) for k, v in (communities or {}).items())
        ]

        timeline_events = self._build_timeline_events(
            selected_projects=selected_projects,
            findings=findings,
            hypotheses=hypotheses,
            communities=community_summaries,
        )

        return KnowledgeSynthesisBundle(
            entities=entity_summaries,
            hypotheses=hypothesis_summaries,
            topics=topic_summaries,
            communities=community_summaries,
            timeline_events=timeline_events,
        )

    def _collect_projects(
        self,
        findings: list[Finding],
        hypotheses: list[Hypothesis],
    ) -> list[str]:
        projects = {finding.project_id for finding in findings}
        for hypothesis in hypotheses:
            projects.update(hypothesis.project_ids)
        return sorted(projects)

    def _collect_entity_nodes(
        self, graph: nx.MultiDiGraph | None
    ) -> list[tuple[str, dict[str, Any]]]:
        if graph is None:
            return []
        entity_nodes: list[tuple[str, dict[str, Any]]] = []
        for node_id, data in graph.nodes(data=True):
            if data.get("kind") == "entity":
                entity_nodes.append((node_id, dict(data)))
        return entity_nodes

    def _build_community_lookup(
        self,
        communities: dict[int, dict[str, Any]],
    ) -> dict[str, tuple[int, dict[str, Any]]]:
        lookup: dict[str, tuple[int, dict[str, Any]]] = {}
        for community_id, data in communities.items():
            members = data.get("members", [])
            for member in members:
                lookup[member] = (community_id, data)
        return lookup

    def _related_entities_from_graph(
        self,
        graph: nx.MultiDiGraph | None,
        node_id: str,
    ) -> list[RelatedEntitySummary]:
        if graph is None or node_id not in graph:
            return []

        neighbors: dict[str, dict[str, Any]] = {}
        for source, target, data in graph.edges(node_id, data=True):
            if data.get("relation") != "RELATED_TO":
                continue
            target_data = graph.nodes.get(target, {})
            if target_data.get("kind") != "entity":
                continue
            key = target
            neighbors.setdefault(
                key,
                {
                    "canonical_name": target_data.get("canonical_name", target),
                    "entity_type": target_data.get("entity_type", "concept"),
                    "slug": slugify(target_data.get("canonical_name", target)),
                    "weight": 0,
                    "project_ids": set(),
                },
            )
            neighbors[key]["weight"] += int(data.get("weight", 1))
            neighbors[key]["project_ids"].update(target_data.get("project_ids", []))

        for source, target, data in graph.in_edges(node_id, data=True):
            if data.get("relation") != "RELATED_TO":
                continue
            source_data = graph.nodes.get(source, {})
            if source_data.get("kind") != "entity":
                continue
            key = source
            neighbors.setdefault(
                key,
                {
                    "canonical_name": source_data.get("canonical_name", source),
                    "entity_type": source_data.get("entity_type", "concept"),
                    "slug": slugify(source_data.get("canonical_name", source)),
                    "weight": 0,
                    "project_ids": set(),
                },
            )
            neighbors[key]["weight"] += int(data.get("weight", 1))
            neighbors[key]["project_ids"].update(source_data.get("project_ids", []))

        result = [
            RelatedEntitySummary(
                canonical_name=value["canonical_name"],
                entity_type=value["entity_type"],
                slug=value["slug"],
                weight=int(value["weight"]),
                project_ids=sorted(value["project_ids"]),
            )
            for value in sorted(
                neighbors.values(),
                key=lambda item: (-int(item["weight"]), item["slug"]),
            )
        ]
        return result

    def _matching_findings(
        self,
        *,
        entity_type: str,
        canonical_name: str,
        project_ids: list[str],
        findings: list[Finding],
    ) -> list[Finding]:
        matches: list[Finding] = []
        canonical_lower = canonical_name.lower()
        for finding in findings:
            if finding.project_id not in project_ids:
                continue
            if any(
                ref.type == entity_type and ref.label.lower() == canonical_lower
                for ref in finding.related_entities
            ):
                matches.append(finding)
        return matches

    def _matching_hypotheses(
        self,
        *,
        entity_type: str,
        canonical_name: str,
        project_ids: list[str],
        hypotheses: list[Hypothesis],
    ) -> list[Hypothesis]:
        matches: list[Hypothesis] = []
        canonical_lower = canonical_name.lower()
        for hypothesis in hypotheses:
            if not set(hypothesis.project_ids).intersection(project_ids):
                continue
            if any(
                ref.type == entity_type and ref.label.lower() == canonical_lower
                for ref in hypothesis.related_entities
            ):
                matches.append(hypothesis)
                continue
            if not hypothesis.related_entities:
                matches.append(hypothesis)
        return matches

    def _entity_projects(
        self,
        *,
        node_data: dict[str, Any],
        findings: list[Finding],
        hypotheses: list[Hypothesis],
    ) -> list[str]:
        project_ids = set(node_data.get("project_ids", []))
        if not project_ids:
            project_ids.update(finding.project_id for finding in findings)
            for hypothesis in hypotheses:
                project_ids.update(hypothesis.project_ids)
        return sorted(project_ids)

    def _build_entity_summary(
        self,
        *,
        node_id: str,
        data: dict[str, Any],
        findings: list[Finding],
        hypotheses: list[Hypothesis],
        graph: nx.MultiDiGraph | None,
        community_lookup: dict[str, tuple[int, dict[str, Any]]],
    ) -> SynthesizedEntity:
        canonical_name = data.get("canonical_name", node_id.rsplit("/", 1)[-1])
        entity_type = data.get("entity_type", "concept")
        slug = slugify(canonical_name)
        aliases = sorted(set(data.get("aliases", [])))
        project_ids = self._entity_projects(
            node_data=data,
            findings=findings,
            hypotheses=hypotheses,
        )

        matching_findings = self._matching_findings(
            entity_type=entity_type,
            canonical_name=canonical_name,
            project_ids=project_ids,
            findings=findings,
        )
        matching_hypotheses = self._matching_hypotheses(
            entity_type=entity_type,
            canonical_name=canonical_name,
            project_ids=project_ids,
            hypotheses=hypotheses,
        )
        related_entities = self._related_entities_from_graph(graph, node_id)

        community_id: int | None = None
        community_name: str | None = None
        community_size: int | None = None
        if node_id in community_lookup:
            community_id, community_data = community_lookup[node_id]
            community_name = community_data.get("name")
            community_size = len(community_data.get("members", []))

        coverage = _coverage_label(len(matching_findings))
        abstract = (
            f"{canonical_name} — studied in {len(project_ids)} project(s) "
            f"across {len(matching_findings)} finding(s)."
        )
        overview = self._render_entity_overview(
            canonical_name=canonical_name,
            entity_type=entity_type,
            project_ids=project_ids,
            findings=matching_findings,
            hypotheses=matching_hypotheses,
            related_entities=related_entities,
            community_name=community_name,
            community_size=community_size,
            coverage=coverage,
        )
        profile = {
            "canonical_name": canonical_name,
            "entity_type": entity_type,
            "aliases": aliases,
            "project_ids": project_ids,
            "finding_ids": [finding.finding_id for finding in matching_findings],
            "hypothesis_ids": [hypothesis.hypothesis_id for hypothesis in matching_hypotheses],
            "related_entities": [entity.model_dump(exclude_none=True) for entity in related_entities],
            "community": {
                "id": community_id,
                "name": community_name,
                "size": community_size,
            }
            if community_id is not None
            else None,
            "coverage": coverage,
        }

        return SynthesizedEntity(
            canonical_name=canonical_name,
            entity_type=entity_type,
            slug=slug,
            aliases=aliases,
            project_ids=project_ids,
            finding_ids=[finding.finding_id for finding in matching_findings],
            hypothesis_ids=[hypothesis.hypothesis_id for hypothesis in matching_hypotheses],
            related_entities=related_entities,
            community_id=community_id,
            community_name=community_name,
            community_size=community_size,
            coverage=coverage,
            abstract=abstract,
            overview=overview,
            profile=profile,
        )

    def _render_entity_overview(
        self,
        *,
        canonical_name: str,
        entity_type: str,
        project_ids: list[str],
        findings: list[Finding],
        hypotheses: list[Hypothesis],
        related_entities: list[RelatedEntitySummary],
        community_name: str | None,
        community_size: int | None,
        coverage: str,
    ) -> str:
        lines = [f"# {canonical_name}", ""]
        lines.append(f"**Entity type:** {entity_type} | **Projects:** {len(project_ids)} | **Findings:** {len(findings)} | **Coverage:** {coverage}")
        lines.append("")
        lines.append("## Key Findings")
        if findings:
            for finding in findings:
                lines.append(f"- {finding.finding_id}: {finding.title}")
        else:
            lines.append("- No findings recorded yet.")
        lines.append("")
        lines.append("## Related Entities")
        if related_entities:
            for related in related_entities:
                lines.append(f"- {related.canonical_name} ({related.weight})")
        else:
            lines.append("- No related entities recorded yet.")
        lines.append("")
        lines.append("## Hypotheses")
        if hypotheses:
            for hypothesis in hypotheses:
                lines.append(f"- {hypothesis.hypothesis_id}: {hypothesis.status}")
        else:
            lines.append("- No hypotheses recorded yet.")
        if community_name:
            lines.append("")
            lines.append("## Community")
            lines.append(f"- {community_name} ({community_size} entities)")
        return "\n".join(lines)

    def _build_hypothesis_summary(
        self,
        *,
        hypothesis: Hypothesis,
        findings: list[Finding],
        graph: nx.MultiDiGraph | None,
    ) -> SynthesizedHypothesis:
        supporting_findings = [
            finding.finding_id
            for finding in findings
            if finding.project_id in hypothesis.project_ids
        ]
        related_entities = self._hypothesis_related_entities(graph, hypothesis.hypothesis_id)
        coverage = _coverage_label(len(supporting_findings))
        abstract = (
            f"{hypothesis.hypothesis_id} — {hypothesis.status} across "
            f"{len(hypothesis.project_ids)} project(s)."
        )
        overview = self._render_hypothesis_overview(
            hypothesis=hypothesis,
            supporting_findings=supporting_findings,
            related_entities=related_entities,
            coverage=coverage,
        )
        return SynthesizedHypothesis(
            hypothesis_id=hypothesis.hypothesis_id,
            slug=slugify(hypothesis.hypothesis_id),
            statement=hypothesis.statement,
            status=hypothesis.status,
            project_ids=sorted(hypothesis.project_ids),
            supporting_findings=supporting_findings,
            related_entities=related_entities,
            coverage=coverage,
            abstract=abstract,
            overview=overview,
            hypothesis={
                "hypothesis_id": hypothesis.hypothesis_id,
                "statement": hypothesis.statement,
                "status": hypothesis.status,
                "project_ids": sorted(hypothesis.project_ids),
            },
        )

    def _hypothesis_related_entities(
        self,
        graph: nx.MultiDiGraph | None,
        hypothesis_id: str,
    ) -> list[RelatedEntitySummary]:
        if graph is None:
            return []
        node_id = f"hypothesis/{slugify(hypothesis_id)}"
        if node_id not in graph:
            return []
        related: list[RelatedEntitySummary] = []
        for _, target, data in graph.edges(node_id, data=True):
            if data.get("relation") != "ABOUT":
                continue
            target_data = graph.nodes.get(target, {})
            if target_data.get("kind") != "entity":
                continue
            related.append(
                RelatedEntitySummary(
                    canonical_name=target_data.get("canonical_name", target),
                    entity_type=target_data.get("entity_type", "concept"),
                    slug=slugify(target_data.get("canonical_name", target)),
                    weight=1,
                    project_ids=sorted(target_data.get("project_ids", [])),
                )
            )
        return sorted(related, key=lambda item: item.slug)

    def _render_hypothesis_overview(
        self,
        *,
        hypothesis: Hypothesis,
        supporting_findings: list[str],
        related_entities: list[RelatedEntitySummary],
        coverage: str,
    ) -> str:
        lines = [f"# {hypothesis.hypothesis_id}", ""]
        lines.append(f"**Status:** {hypothesis.status} | **Coverage:** {coverage}")
        lines.append("")
        lines.append("## Supporting Findings")
        if supporting_findings:
            for finding_id in supporting_findings:
                lines.append(f"- {finding_id}")
        else:
            lines.append("- No supporting findings recorded yet.")
        lines.append("")
        lines.append("## Related Entities")
        if related_entities:
            for entity in related_entities:
                lines.append(f"- {entity.canonical_name}")
        else:
            lines.append("- No related entities recorded yet.")
        return "\n".join(lines)

    def _build_project_topic_summary(
        self,
        *,
        project_id: str,
        findings: list[Finding],
        hypotheses: list[Hypothesis],
        graph: nx.MultiDiGraph | None,
    ) -> SynthesizedTopic:
        topic_findings = [finding.finding_id for finding in findings if finding.project_id == project_id]
        topic_hypotheses = [
            hypothesis.hypothesis_id
            for hypothesis in hypotheses
            if project_id in hypothesis.project_ids
        ]
        entity_refs = self._project_entity_refs(project_id=project_id, findings=findings, graph=graph)
        abstract = (
            f"{project_id} — {len(topic_findings)} finding(s), "
            f"{len(topic_hypotheses)} hypothesis/hypotheses."
        )
        overview = self._render_topic_overview(
            project_id=project_id,
            findings=topic_findings,
            hypotheses=topic_hypotheses,
            entity_refs=entity_refs,
        )
        return SynthesizedTopic(
            topic_id=project_id,
            slug=slugify(project_id),
            title=project_id,
            project_ids=[project_id],
            finding_ids=topic_findings,
            hypothesis_ids=topic_hypotheses,
            entity_refs=entity_refs,
            abstract=abstract,
            overview=overview,
            topic={
                "topic_id": project_id,
                "project_id": project_id,
                "finding_ids": topic_findings,
                "hypothesis_ids": topic_hypotheses,
                "entity_refs": entity_refs,
            },
        )

    def _build_community_topic_summary(
        self,
        *,
        community_id: int,
        data: dict[str, Any],
        findings: list[Finding],
        hypotheses: list[Hypothesis],
        graph: nx.MultiDiGraph | None,
    ) -> SynthesizedTopic:
        members = set(data.get("members", []))
        project_ids = sorted(data.get("projects", []))
        entity_refs: list[dict[str, Any]] = []
        related_entity_keys: set[tuple[str, str]] = set()
        if graph is not None:
            for member in members:
                node_data = graph.nodes.get(member, {})
                if node_data.get("kind") != "entity":
                    continue
                key = (
                    str(node_data.get("entity_type", "concept")),
                    str(node_data.get("canonical_name", member)),
                )
                if key in related_entity_keys:
                    continue
                related_entity_keys.add(key)
                entity_refs.append({"type": key[0], "label": key[1]})

        finding_ids: list[str] = []
        for finding in findings:
            if project_ids and finding.project_id not in project_ids:
                continue
            if not graph:
                continue
            for ref in finding.related_entities:
                candidate = f"{ref.type}/{slugify(ref.label)}"
                if candidate in members:
                    finding_ids.append(finding.finding_id)
                    break

        hypothesis_ids: list[str] = []
        for hypothesis in hypotheses:
            if project_ids and not set(hypothesis.project_ids).intersection(project_ids):
                continue
            for ref in hypothesis.related_entities:
                candidate = f"{ref.type}/{slugify(ref.label)}"
                if candidate in members:
                    hypothesis_ids.append(hypothesis.hypothesis_id)
                    break

        title = str(data.get("name", f"Community {community_id}"))
        abstract = (
            f"{title} — synthesized across {len(project_ids)} project(s), "
            f"{len(finding_ids)} finding(s), and {len(hypothesis_ids)} hypothesis/hypotheses."
        )
        overview = self._render_topic_overview(
            project_id=title,
            findings=sorted(set(finding_ids)),
            hypotheses=sorted(set(hypothesis_ids)),
            entity_refs=sorted(entity_refs, key=lambda item: (item["type"], item["label"])),
        )
        return SynthesizedTopic(
            topic_id=f"community-{community_id}",
            slug=slugify(title) or f"community-{community_id}",
            title=title,
            project_ids=project_ids,
            finding_ids=sorted(set(finding_ids)),
            hypothesis_ids=sorted(set(hypothesis_ids)),
            entity_refs=sorted(entity_refs, key=lambda item: (item["type"], item["label"])),
            abstract=abstract,
            overview=overview,
            topic={
                "topic_id": f"community-{community_id}",
                "community_id": community_id,
                "name": title,
                "project_ids": project_ids,
                "finding_ids": sorted(set(finding_ids)),
                "hypothesis_ids": sorted(set(hypothesis_ids)),
                "entity_refs": sorted(entity_refs, key=lambda item: (item["type"], item["label"])),
            },
        )

    def _project_entity_refs(
        self,
        *,
        project_id: str,
        findings: list[Finding],
        graph: nx.MultiDiGraph | None,
    ) -> list[dict[str, Any]]:
        refs: dict[str, dict[str, Any]] = {}
        for finding in findings:
            if finding.project_id != project_id:
                continue
            for ref in finding.related_entities:
                key = (ref.type, ref.label)
                refs.setdefault(
                    str(key),
                    {"type": ref.type, "label": ref.label},
                )
        if graph is not None:
            for node_id, data in graph.nodes(data=True):
                if data.get("kind") != "entity":
                    continue
                project_ids = set(data.get("project_ids", []))
                if project_id not in project_ids:
                    continue
                refs.setdefault(
                    node_id,
                    {
                        "type": data.get("entity_type", "concept"),
                        "label": data.get("canonical_name", node_id),
                    },
                )
        return [refs[key] for key in sorted(refs)]

    def _render_topic_overview(
        self,
        *,
        project_id: str,
        findings: list[str],
        hypotheses: list[str],
        entity_refs: list[dict[str, Any]],
    ) -> str:
        lines = [f"# {project_id}", ""]
        lines.append(f"**Findings:** {len(findings)} | **Hypotheses:** {len(hypotheses)}")
        lines.append("")
        lines.append("## Entities Studied")
        if entity_refs:
            for ref in entity_refs:
                lines.append(f"- {ref['label']} ({ref['type']})")
        else:
            lines.append("- No entities recorded yet.")
        return "\n".join(lines)

    def _build_community_summary(
        self,
        *,
        community_id: int,
        data: dict[str, Any],
        graph: nx.MultiDiGraph | None,
    ) -> SynthesizedCommunity:
        members = sorted(data.get("members", []))
        projects = sorted(data.get("projects", []))
        entities: list[dict[str, Any]] = []
        if graph is not None:
            for member in members:
                node_data = graph.nodes.get(member, {})
                if node_data.get("kind") == "entity":
                    entities.append(
                        {
                            "canonical_name": node_data.get("canonical_name", member),
                            "entity_type": node_data.get("entity_type", "concept"),
                            "slug": slugify(node_data.get("canonical_name", member)),
                        }
                    )
        return SynthesizedCommunity(
            community_id=community_id,
            name=data.get("name", f"Community {community_id}"),
            members=members,
            projects=projects,
            summary=data.get("summary", f"{len(members)} entities"),
            entities=entities,
        )

    def _build_timeline_events(
        self,
        *,
        selected_projects: list[str],
        findings: list[Finding],
        hypotheses: list[Hypothesis],
        communities: list[SynthesizedCommunity],
    ) -> list[SynthesizedTimelineEvent]:
        events: list[SynthesizedTimelineEvent] = []
        total_findings = len(findings)
        total_hypotheses = len(hypotheses)
        events.append(
            SynthesizedTimelineEvent(
                event_id="knowledge-snapshot",
                label="Observatory knowledge snapshot",
                sort_key="0000",
                project_ids=selected_projects,
                summary=(
                    f"{total_findings} finding(s), {total_hypotheses} hypothesis/hypotheses, "
                    f"{len(communities)} community/communities."
                ),
                kind="aggregate",
            )
        )
        for project_id in selected_projects:
            project_findings = [finding for finding in findings if finding.project_id == project_id]
            project_hypotheses = [
                hypothesis for hypothesis in hypotheses if project_id in hypothesis.project_ids
            ]
            events.append(
                SynthesizedTimelineEvent(
                    event_id=f"{slugify(project_id)}-summary",
                    label=project_id,
                    sort_key=project_id,
                    project_ids=[project_id],
                    summary=(
                        f"{len(project_findings)} finding(s), "
                        f"{len(project_hypotheses)} hypothesis/hypotheses."
                    ),
                    kind="project_summary",
                )
            )
        return events
