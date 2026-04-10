"""Tests for the observatory knowledge synthesis layer."""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from observatory_context.graph.builder import GraphBuilder
from observatory_context.graph.knowledge_synthesis import KnowledgeSynthesizer
from observatory_context.registry.schema import Finding, Hypothesis


def _finding(
    finding_id: str,
    project_id: str,
    entity_label: str,
    entity_type: str = "organism",
    confidence: str = "high",
) -> Finding:
    return Finding(
        finding_id=finding_id,
        project_id=project_id,
        title=finding_id,
        statement=f"{entity_label} is relevant",
        confidence=confidence,  # type: ignore[arg-type]
        related_entities=[],
    )


def _hypothesis(
    hypothesis_id: str,
    project_ids: list[str],
    status: str = "tested",
) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=hypothesis_id,
        statement=f"{hypothesis_id} statement",
        status=status,  # type: ignore[arg-type]
        project_ids=project_ids,
    )


def _graph() -> nx.MultiDiGraph:
    builder = GraphBuilder()
    builder.add_project("proj-a", "Project A")
    builder.add_project("proj-b", "Project B")
    builder.add_entity("Pseudomonas putida", "organism", aliases=["P. putida"], project_ids=["proj-a", "proj-b"])
    builder.add_entity("czc efflux", "concept", project_ids=["proj-a", "proj-b"])
    builder.add_entity("Cupriavidus metallidurans", "organism", project_ids=["proj-b"])
    builder.G.add_edge(
        "organism/pseudomonas-putida",
        "concept/czc-efflux",
        relation="RELATED_TO",
        weight=3,
    )
    builder.G.add_edge(
        "organism/pseudomonas-putida",
        "organism/cupriavidus-metallidurans",
        relation="RELATED_TO",
        weight=2,
    )
    return builder.G


def test_synthesizer_builds_deterministic_bundle() -> None:
    findings = [
        _finding("F-001", "proj-a", "Pseudomonas putida"),
        _finding("F-002", "proj-b", "Pseudomonas putida"),
    ]
    hypotheses = [
        _hypothesis("H-001", ["proj-a", "proj-b"], status="supported"),
    ]
    communities = {
        7: {
            "name": "Metal stress cluster",
            "members": [
                "organism/pseudomonas-putida",
                "concept/czc-efflux",
            ],
            "summary": "2 entities",
            "projects": ["proj-a", "proj-b"],
        }
    }

    bundle = KnowledgeSynthesizer().synthesize(
        findings=findings,
        hypotheses=hypotheses,
        project_ids=["proj-a", "proj-b"],
        graph=_graph(),
        communities=communities,
    )

    assert [entity.slug for entity in bundle.entities] == ["cupriavidus-metallidurans", "czc-efflux", "pseudomonas-putida"]
    pseudomonas = next(entity for entity in bundle.entities if entity.slug == "pseudomonas-putida")
    assert pseudomonas.project_ids == ["proj-a", "proj-b"]
    assert pseudomonas.related_entities[0].canonical_name == "czc efflux"
    assert pseudomonas.community_id == 7
    assert "studied in 2 project" in pseudomonas.abstract

    hypothesis = bundle.hypotheses[0]
    assert hypothesis.hypothesis_id == "H-001"
    assert hypothesis.project_ids == ["proj-a", "proj-b"]
    assert hypothesis.supporting_findings == ["F-001", "F-002"]

    assert [topic.topic_id for topic in bundle.topics] == ["community-7"]
    assert bundle.topics[0].title == "Metal stress cluster"
    assert bundle.topics[0].project_ids == ["proj-a", "proj-b"]
    assert bundle.communities[0].community_id == 7
    assert bundle.timeline_events[0].project_ids == ["proj-a", "proj-b"]


def test_synthesizer_is_stable_for_same_inputs() -> None:
    findings = [_finding("F-001", "proj-a", "Pseudomonas putida")]
    bundle_a = KnowledgeSynthesizer().synthesize(
        findings=findings,
        hypotheses=[],
        project_ids=["proj-a"],
        graph=_graph(),
        communities={},
    )
    bundle_b = KnowledgeSynthesizer().synthesize(
        findings=findings,
        hypotheses=[],
        project_ids=["proj-a"],
        graph=_graph(),
        communities={},
    )

    assert bundle_a.model_dump() == bundle_b.model_dump()
