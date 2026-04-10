"""Tests for exporting the synthesized knowledge graph."""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from observatory_context.graph.builder import GraphBuilder
from observatory_context.graph.knowledge_graph_export import KnowledgeGraphExporter
from observatory_context.graph.knowledge_synthesis import KnowledgeSynthesizer
from observatory_context.registry.schema import Finding, Hypothesis


class FakeClient:
    def __init__(self) -> None:
        self.links: list[tuple[str, list[str], str]] = []

    def link_resources(self, from_uri: str, uris: list[str], reason: str = "") -> None:
        self.links.append((from_uri, uris, reason))


def _bundle() -> tuple[object, nx.MultiDiGraph]:
    builder = GraphBuilder()
    builder.add_project("proj-a", "Project A")
    builder.add_entity("Pseudomonas putida", "organism", aliases=["P. putida"], project_ids=["proj-a"])
    builder.add_entity("czc efflux", "concept", project_ids=["proj-a"])
    builder.add_hypothesis(
        Hypothesis(
            hypothesis_id="H-001",
            statement="Example hypothesis",
            status="tested",
            project_ids=["proj-a"],
        ),
        {"Pseudomonas putida": "organism/pseudomonas-putida"},
    )
    builder.G.add_edge(
        "organism/pseudomonas-putida",
        "concept/czc-efflux",
        relation="RELATED_TO",
        weight=4,
    )

    bundle = KnowledgeSynthesizer().synthesize(
        findings=[Finding(
            finding_id="F-001",
            project_id="proj-a",
            title="Finding",
            statement="Pseudomonas putida is relevant",
            confidence="high",
        )],
        hypotheses=[Hypothesis(
            hypothesis_id="H-001",
            statement="Example hypothesis",
            status="tested",
            project_ids=["proj-a"],
        )],
        project_ids=["proj-a"],
        graph=builder.G,
        communities={},
    )
    return bundle, builder.G


def test_exporter_stages_knowledge_graph_resources(tmp_path: Path) -> None:
    bundle, graph = _bundle()
    exporter = KnowledgeGraphExporter(bundle=bundle, graph=graph)

    count = exporter.export_all(tmp_path)

    assert count > 0
    entity_root = tmp_path / "knowledge-graph" / "entities" / "organisms" / "pseudomonas-putida"
    assert (entity_root / ".abstract.md").exists()
    assert (entity_root / ".overview.md").exists()
    assert (entity_root / "profile.yaml").exists()

    hyp_root = tmp_path / "knowledge-graph" / "hypotheses" / "h-001"
    assert (hyp_root / ".abstract.md").exists()
    assert (hyp_root / ".overview.md").exists()
    assert (hyp_root / "hypothesis.yaml").exists()

    timeline_path = tmp_path / "knowledge-graph" / "timeline" / "events.yaml"
    assert timeline_path.exists()


def test_exporter_creates_relations_from_related_entities(tmp_path: Path) -> None:
    bundle, graph = _bundle()
    client = FakeClient()
    exporter = KnowledgeGraphExporter(bundle=bundle, graph=graph)

    count = exporter.create_relations(client)

    assert count == 2
    assert client.links == [
        (
            "viking://resources/observatory/knowledge-graph/entities/organisms/pseudomonas-putida",
            ["viking://resources/observatory/knowledge-graph/entities/concepts/czc-efflux"],
            "co-occurs in 4 finding(s)",
        ),
        (
            "viking://resources/observatory/knowledge-graph/entities/concepts/czc-efflux",
            ["viking://resources/observatory/knowledge-graph/entities/organisms/pseudomonas-putida"],
            "co-occurs in 4 finding(s)",
        ),
    ]
