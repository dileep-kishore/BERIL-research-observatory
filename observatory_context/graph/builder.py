"""NetworkX-based knowledge graph builder for the research observatory."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import networkx as nx

from observatory_context.registry.schema import Finding, Hypothesis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Lowercase, replace spaces/underscores with hyphens, strip specials.

    Parameters
    ----------
    text
        Raw string to slugify.

    Returns
    -------
    str
        URL-safe slug.
    """
    slug = text.lower().strip()
    slug = re.sub(r"[_\s]+", "-", slug)
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


def _entity_node_id(entity_type: str, canonical_name: str) -> str:
    return f"{_slugify(entity_type)}/{_slugify(canonical_name)}"


def _finding_node_id(finding_id: str) -> str:
    return f"finding/{_slugify(finding_id)}"


def _hypothesis_node_id(hypothesis_id: str) -> str:
    return f"hypothesis/{_slugify(hypothesis_id)}"


def _project_node_id(project_id: str) -> str:
    return f"project/{_slugify(project_id)}"


# ---------------------------------------------------------------------------
# Community detection
# ---------------------------------------------------------------------------

def _detect_communities_leiden(G: nx.Graph) -> dict[str, int]:
    """Try hierarchical Leiden via graspologic."""
    from graspologic.partition import hierarchical_leiden

    result = hierarchical_leiden(G, max_cluster_size=50)
    return {node: comm for node, comm in ((r.node, r.cluster) for r in result)}


def _detect_communities_louvain(G: nx.Graph) -> dict[str, int]:
    """Fallback Louvain via networkx."""
    communities = nx.community.louvain_communities(G, seed=42)
    mapping: dict[str, int] = {}
    for idx, community in enumerate(communities):
        for node in community:
            mapping[node] = idx
    return mapping


# ---------------------------------------------------------------------------
# GraphBuilder
# ---------------------------------------------------------------------------

class GraphBuilder:
    """Build and query the observatory knowledge graph.

    Parameters
    ----------
    graph
        Optional pre-existing graph for incremental builds.
    """

    def __init__(self, graph: nx.MultiDiGraph | None = None) -> None:
        self.G: nx.MultiDiGraph = graph if graph is not None else nx.MultiDiGraph()

    # -- Mutations ----------------------------------------------------------

    def add_project(
        self,
        project_id: str,
        title: str,
        research_question: str = "",
    ) -> None:
        """Add a project node.

        Parameters
        ----------
        project_id
            Unique project identifier.
        title
            Human-readable project title.
        research_question
            Primary research question the project addresses.
        """
        nid = _project_node_id(project_id)
        self.G.add_node(
            nid,
            kind="project",
            project_id=project_id,
            title=title,
            research_question=research_question,
        )

    def add_entity(
        self,
        canonical_name: str,
        entity_type: str,
        aliases: list[str] | None = None,
        project_ids: list[str] | None = None,
    ) -> str:
        """Add an entity node, merging if it already exists.

        Parameters
        ----------
        canonical_name
            Canonical display name.
        entity_type
            One of the EntityRef types (organism, gene, etc.).
        aliases
            Alternative names for the entity.
        project_ids
            Projects where this entity appears.

        Returns
        -------
        str
            The node ID (type-prefixed slug).
        """
        aliases = aliases or []
        project_ids = project_ids or []
        nid = _entity_node_id(entity_type, canonical_name)

        if nid in self.G:
            # Merge aliases and project_ids
            existing = self.G.nodes[nid]
            existing_aliases: set[str] = set(existing.get("aliases", []))
            existing_aliases.update(aliases)
            existing["aliases"] = sorted(existing_aliases)
            existing_pids: set[str] = set(existing.get("project_ids", []))
            existing_pids.update(project_ids)
            existing["project_ids"] = sorted(existing_pids)
        else:
            self.G.add_node(
                nid,
                kind="entity",
                entity_type=entity_type,
                canonical_name=canonical_name,
                aliases=sorted(set(aliases)),
                project_ids=sorted(set(project_ids)),
            )
        return nid

    def add_finding(
        self,
        finding: Finding,
        resolved_entities: dict[str, str],
    ) -> None:
        """Add a finding node and wire it to entities and its project.

        Parameters
        ----------
        finding
            The Finding model instance.
        resolved_entities
            Maps raw entity label to canonical node ID.
        """
        fnid = _finding_node_id(finding.finding_id)
        self.G.add_node(
            fnid,
            kind="finding",
            finding_id=finding.finding_id,
            title=finding.title,
            statement=finding.statement,
            confidence=finding.confidence,
            finding_type=finding.finding_type,
            project_id=finding.project_id,
        )

        # finding → FROM → project
        pnid = _project_node_id(finding.project_id)
        if pnid in self.G:
            self.G.add_edge(fnid, pnid, relation="FROM")

        # finding → ABOUT → entity
        entity_nids: list[str] = []
        for _label, canon_nid in resolved_entities.items():
            if canon_nid in self.G:
                self.G.add_edge(fnid, canon_nid, relation="ABOUT")
                entity_nids.append(canon_nid)
                # project → STUDIES → entity
                if pnid in self.G:
                    self.G.add_edge(pnid, canon_nid, relation="STUDIES")

        # entity → RELATED_TO → entity (co-occurrence)
        for a, b in combinations(sorted(entity_nids), 2):
            existing = [
                k
                for k, d in self.G[a][b].items()
                if d.get("relation") == "RELATED_TO"
            ] if self.G.has_edge(a, b) else []
            if existing:
                self.G[a][b][existing[0]]["weight"] = (
                    self.G[a][b][existing[0]].get("weight", 1) + 1
                )
            else:
                self.G.add_edge(a, b, relation="RELATED_TO", weight=1)

    def add_hypothesis(
        self,
        hypothesis: Hypothesis,
        resolved_entities: dict[str, str],
    ) -> None:
        """Add a hypothesis node and wire it to entities and projects.

        Parameters
        ----------
        hypothesis
            The Hypothesis model instance.
        resolved_entities
            Maps raw entity label to canonical node ID.
        """
        hnid = _hypothesis_node_id(hypothesis.hypothesis_id)
        self.G.add_node(
            hnid,
            kind="hypothesis",
            hypothesis_id=hypothesis.hypothesis_id,
            statement=hypothesis.statement,
            status=hypothesis.status,
            project_ids=hypothesis.project_ids,
        )

        # hypothesis → TESTED_IN → project
        for pid in hypothesis.project_ids:
            pnid = _project_node_id(pid)
            if pnid in self.G:
                self.G.add_edge(hnid, pnid, relation="TESTED_IN")

        # hypothesis → ABOUT → entity
        for _label, canon_nid in resolved_entities.items():
            if canon_nid in self.G:
                self.G.add_edge(hnid, canon_nid, relation="ABOUT")

    # -- Link findings to hypotheses ----------------------------------------

    def link_finding_to_hypothesis(
        self, finding_id: str, hypothesis_id: str
    ) -> None:
        """Create a SUPPORTS edge from a finding to a hypothesis.

        Parameters
        ----------
        finding_id
            The finding's raw ID.
        hypothesis_id
            The hypothesis's raw ID.
        """
        fnid = _finding_node_id(finding_id)
        hnid = _hypothesis_node_id(hypothesis_id)
        if fnid in self.G and hnid in self.G:
            self.G.add_edge(fnid, hnid, relation="SUPPORTS")

    # -- Analysis -----------------------------------------------------------

    def build_communities(self) -> dict[int, dict[str, Any]]:
        """Run community detection on entity co-occurrence subgraph.

        Tries graspologic Leiden first, falls back to networkx Louvain.

        Returns
        -------
        dict[int, dict]
            community_id to ``{name, members, summary, projects}``.
        """
        entity_nodes = [
            n for n, d in self.G.nodes(data=True) if d.get("kind") == "entity"
        ]
        if not entity_nodes:
            return {}

        # Build undirected projection of entity nodes connected by RELATED_TO
        sub = nx.Graph()
        sub.add_nodes_from(entity_nodes)
        for u, v, d in self.G.edges(data=True):
            if d.get("relation") == "RELATED_TO" and u in sub and v in sub:
                w = sub[u][v]["weight"] + d.get("weight", 1) if sub.has_edge(u, v) else d.get("weight", 1)
                sub.add_edge(u, v, weight=w)

        # Run community detection
        try:
            membership = _detect_communities_leiden(sub)
        except Exception:
            membership = _detect_communities_louvain(sub)

        # Store assignments as node attributes
        for node, comm_id in membership.items():
            if node in self.G:
                self.G.nodes[node]["community"] = comm_id

        # Summarise communities
        comm_members: dict[int, list[str]] = defaultdict(list)
        for node, cid in membership.items():
            comm_members[cid].append(node)

        communities: dict[int, dict[str, Any]] = {}
        for cid, members in comm_members.items():
            types = Counter(
                self.G.nodes[m].get("entity_type", "unknown") for m in members
            )
            projects: set[str] = set()
            for m in members:
                projects.update(self.G.nodes[m].get("project_ids", []))
            top_types = ", ".join(t for t, _ in types.most_common(3))
            name = f"{top_types} cluster"
            communities[cid] = {
                "name": name,
                "members": sorted(members),
                "summary": f"{len(members)} entities ({top_types})",
                "projects": sorted(projects),
            }

        return communities

    def detect_contradictions(self) -> list[dict[str, Any]]:
        """Find entities whose findings from different projects may conflict.

        A contradiction is flagged when two findings about the same entity
        come from different projects and have opposite confidence levels
        (high vs low) or opposing finding types (result vs negative_result).

        Returns
        -------
        list[dict]
            Each dict has ``entity``, ``finding_a``, ``finding_b``, ``reason``.
        """
        contradictions: list[dict[str, Any]] = []
        entity_nodes = [
            n for n, d in self.G.nodes(data=True) if d.get("kind") == "entity"
        ]

        for ent in entity_nodes:
            # Collect findings pointing ABOUT this entity
            findings: list[dict[str, Any]] = []
            for pred in self.G.predecessors(ent):
                edge_data = self.G.get_edge_data(pred, ent)
                if edge_data and any(
                    d.get("relation") == "ABOUT" for d in edge_data.values()
                ):
                    nd = self.G.nodes[pred]
                    if nd.get("kind") == "finding":
                        findings.append(nd)

            # Compare pairs from different projects
            for i, fa in enumerate(findings):
                for fb in findings[i + 1 :]:
                    if fa.get("project_id") == fb.get("project_id"):
                        continue
                    reasons: list[str] = []
                    # Opposite confidence
                    if {fa.get("confidence"), fb.get("confidence")} == {
                        "high",
                        "low",
                    }:
                        reasons.append("opposite confidence (high vs low)")
                    # Result vs negative_result
                    if {fa.get("finding_type"), fb.get("finding_type")} == {
                        "result",
                        "negative_result",
                    }:
                        reasons.append("result vs negative_result")
                    if reasons:
                        contradictions.append(
                            {
                                "entity": self.G.nodes[ent].get(
                                    "canonical_name", ent
                                ),
                                "finding_a": fa.get("finding_id", "?"),
                                "finding_b": fb.get("finding_id", "?"),
                                "reason": "; ".join(reasons),
                            }
                        )

        return contradictions

    def detect_gaps(self) -> list[dict[str, Any]]:
        """Identify research gaps in the knowledge graph.

        Detects:
        - Entities in findings but with no hypothesis link.
        - Hypotheses that are proposed but never tested (no SUPPORTS edge).
        - Organisms mentioned but not studied as a primary subject.

        Returns
        -------
        list[dict]
            Each dict has ``gap_type``, ``id``, ``detail``.
        """
        gaps: list[dict[str, Any]] = []

        # Entities with findings but no hypothesis connection
        entity_nodes = [
            n for n, d in self.G.nodes(data=True) if d.get("kind") == "entity"
        ]
        hypothesis_nodes = {
            n for n, d in self.G.nodes(data=True) if d.get("kind") == "hypothesis"
        }

        for ent in entity_nodes:
            has_finding = False
            has_hypothesis = False
            for pred in self.G.predecessors(ent):
                nd = self.G.nodes[pred]
                edge_data = self.G.get_edge_data(pred, ent)
                if edge_data and any(
                    d.get("relation") == "ABOUT" for d in edge_data.values()
                ):
                    if nd.get("kind") == "finding":
                        has_finding = True
                    if nd.get("kind") == "hypothesis":
                        has_hypothesis = True
            if has_finding and not has_hypothesis:
                gaps.append(
                    {
                        "gap_type": "no_hypothesis",
                        "id": ent,
                        "detail": (
                            f"{self.G.nodes[ent].get('canonical_name', ent)}: "
                            "mentioned in findings but no hypothesis"
                        ),
                    }
                )

        # Hypotheses proposed but never tested (no SUPPORTS edge incoming)
        for hn in hypothesis_nodes:
            nd = self.G.nodes[hn]
            if nd.get("status") != "proposed":
                continue
            has_support = any(
                any(
                    d.get("relation") == "SUPPORTS"
                    for d in self.G.get_edge_data(pred, hn).values()
                )
                for pred in self.G.predecessors(hn)
                if self.G.get_edge_data(pred, hn)
            )
            if not has_support:
                gaps.append(
                    {
                        "gap_type": "untested_hypothesis",
                        "id": hn,
                        "detail": (
                            f"{nd.get('hypothesis_id', hn)}: "
                            "proposed but never tested"
                        ),
                    }
                )

        # Organisms mentioned but not primary subject (appear in < 2 findings)
        for ent in entity_nodes:
            nd = self.G.nodes[ent]
            if nd.get("entity_type") != "organism":
                continue
            finding_count = sum(
                1
                for pred in self.G.predecessors(ent)
                if self.G.nodes[pred].get("kind") == "finding"
                and self.G.get_edge_data(pred, ent)
                and any(
                    d.get("relation") == "ABOUT"
                    for d in self.G.get_edge_data(pred, ent).values()
                )
            )
            if finding_count == 1:
                gaps.append(
                    {
                        "gap_type": "low_coverage_organism",
                        "id": ent,
                        "detail": (
                            f"{nd.get('canonical_name', ent)}: "
                            "mentioned but not studied as primary subject"
                        ),
                    }
                )

        return gaps

    def get_cross_project_entities(
        self, min_projects: int = 2
    ) -> list[dict[str, Any]]:
        """Find entities appearing in multiple projects.

        Parameters
        ----------
        min_projects
            Minimum number of projects for an entity to be included.

        Returns
        -------
        list[dict]
            Each dict has ``entity``, ``entity_type``, ``projects``, ``count``.
        """
        results: list[dict[str, Any]] = []
        for n, d in self.G.nodes(data=True):
            if d.get("kind") != "entity":
                continue
            pids = d.get("project_ids", [])
            if len(pids) >= min_projects:
                results.append(
                    {
                        "entity": d.get("canonical_name", n),
                        "entity_type": d.get("entity_type", "unknown"),
                        "projects": pids,
                        "count": len(pids),
                    }
                )
        results.sort(key=lambda x: x["count"], reverse=True)
        return results

    # -- Serialisation ------------------------------------------------------

    def serialize(self, path: Path) -> None:
        """Save graph to JSON in node-link format.

        Parameters
        ----------
        path
            Destination file path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self.G)
        path.write_text(json.dumps(data, indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> GraphBuilder:
        """Load graph from a node-link JSON file.

        Parameters
        ----------
        path
            Source file path.

        Returns
        -------
        GraphBuilder
            Builder wrapping the loaded graph.
        """
        data = json.loads(path.read_text())
        G = nx.node_link_graph(data, directed=True, multigraph=True)
        return cls(graph=G)

    # -- Stats --------------------------------------------------------------

    @property
    def stats(self) -> dict[str, Any]:
        """Return summary statistics about the graph.

        Returns
        -------
        dict
            Keys: ``nodes``, ``edges``, ``projects``, ``entities``,
            ``findings``, ``hypotheses``, ``entity_types``.
        """
        kinds = Counter(d.get("kind") for _, d in self.G.nodes(data=True))
        entity_types = Counter(
            d.get("entity_type")
            for _, d in self.G.nodes(data=True)
            if d.get("kind") == "entity"
        )
        relation_types = Counter(
            d.get("relation") for _, _, d in self.G.edges(data=True)
        )
        return {
            "nodes": self.G.number_of_nodes(),
            "edges": self.G.number_of_edges(),
            "projects": kinds.get("project", 0),
            "entities": kinds.get("entity", 0),
            "findings": kinds.get("finding", 0),
            "hypotheses": kinds.get("hypothesis", 0),
            "entity_types": dict(entity_types),
            "relation_types": dict(relation_types),
        }
