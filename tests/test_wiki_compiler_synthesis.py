"""Tests for wiki compilation from synthesized knowledge objects."""

from __future__ import annotations

from observatory_context.graph.knowledge_synthesis import (
    RelatedEntitySummary,
    SynthesizedEntity,
    SynthesizedHypothesis,
    SynthesizedTopic,
)
from observatory_context.registry.schema import Finding, Hypothesis
from observatory_context.wiki.compiler import (
    compile_entity_page_from_synthesis,
    compile_hypothesis_page_from_synthesis,
    compile_topic_page_from_synthesis,
)


def test_synthesis_compilers_render_cross_project_sections() -> None:
    finding = Finding(
        finding_id="F-001",
        project_id="proj-a",
        title="Metal fitness pattern",
        statement="Metal stress links to czc efflux conservation.",
        confidence="high",
        finding_type="result",
    )
    hypothesis = Hypothesis(
        hypothesis_id="H-001",
        statement="Metal stress is linked to efflux conservation.",
        status="supported",
        project_ids=["proj-a", "proj-b"],
    )

    entity_page = compile_entity_page_from_synthesis(
        SynthesizedEntity(
            canonical_name="Pseudomonas putida",
            entity_type="organism",
            slug="pseudomonas-putida",
            project_ids=["proj-a", "proj-b"],
            finding_ids=["F-001"],
            hypothesis_ids=["H-001"],
            related_entities=[
                RelatedEntitySummary(
                    canonical_name="czc efflux",
                    entity_type="concept",
                    slug="czc-efflux",
                    weight=3,
                )
            ],
            community_id=1,
            community_name="Metal Stress Cluster",
            community_size=4,
        ),
        findings_by_id={"F-001": finding},
        hypotheses_by_id={"H-001": hypothesis},
    )
    assert "Pseudomonas putida" in entity_page
    assert "czc efflux" in entity_page
    assert "Metal Stress Cluster" in entity_page

    hypothesis_page = compile_hypothesis_page_from_synthesis(
        SynthesizedHypothesis(
            hypothesis_id="H-001",
            slug="h-001",
            statement=hypothesis.statement,
            status=hypothesis.status,
            project_ids=["proj-a", "proj-b"],
            supporting_findings=["F-001"],
            coverage="low",
            hypothesis=hypothesis.model_dump(),
        ),
        findings_by_id={"F-001": finding},
        hypotheses_by_id={"H-001": hypothesis},
    )
    assert "Supporting Evidence" in hypothesis_page
    assert "F-001" in hypothesis_page

    topic_page = compile_topic_page_from_synthesis(
        SynthesizedTopic(
            topic_id="community-1",
            slug="metal-stress-cluster",
            title="Metal Stress Cluster",
            project_ids=["proj-a", "proj-b"],
            finding_ids=["F-001"],
            hypothesis_ids=["H-001"],
            entity_refs=[{"type": "organism", "label": "Pseudomonas putida"}],
        ),
        findings_by_id={"F-001": finding},
        hypotheses_by_id={"H-001": hypothesis},
    )
    assert "Metal Stress Cluster" in topic_page
    assert "supported" in topic_page
    assert "Pseudomonas putida" in topic_page
