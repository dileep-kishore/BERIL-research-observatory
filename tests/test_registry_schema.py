"""Tests for registry Pydantic schema models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from observatory_context.registry.schema import (
    Artifact,
    EntityRef,
    Evidence,
    Figure,
    Finding,
    Hypothesis,
    Pitfall,
    Project,
    ResearchIdea,
)


# ---------------------------------------------------------------------------
# EntityRef
# ---------------------------------------------------------------------------


def test_entity_ref_minimal() -> None:
    ref = EntityRef(type="organism", label="E. coli")
    assert ref.type == "organism"
    assert ref.label == "E. coli"
    assert ref.normalized_id is None
    assert ref.namespace is None


def test_entity_ref_full() -> None:
    ref = EntityRef(
        type="gene",
        label="recA",
        normalized_id="KEGG:K03553",
        namespace="KEGG",
    )
    assert ref.normalized_id == "KEGG:K03553"
    assert ref.namespace == "KEGG"


def test_entity_ref_invalid_type() -> None:
    with pytest.raises(ValidationError):
        EntityRef(type="invalid_type", label="X")  # type: ignore[arg-type]


def test_entity_ref_yaml_roundtrip() -> None:
    ref = EntityRef(type="pathway", label="TCA cycle", normalized_id="map00020")
    assert EntityRef.model_validate(ref.model_dump()) == ref


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


def test_project_minimal() -> None:
    proj = Project(
        project_id="proj-001",
        title="Test Project",
        status="active",
        research_question="What happens?",
    )
    assert proj.project_id == "proj-001"
    assert proj.organisms == []
    assert proj.updated_at is None


def test_project_full() -> None:
    from datetime import date

    proj = Project(
        project_id="proj-002",
        title="Full Project",
        status="complete",
        research_question="Does X cause Y?",
        organisms=["E. coli", "B. subtilis"],
        conditions=["anaerobic"],
        methods=["RNA-seq"],
        datasets=["ds-001"],
        tags=["metabolism"],
        depends_on=["proj-001"],
        enables=["proj-003"],
        updated_at=date(2026, 1, 15),
    )
    assert proj.organisms == ["E. coli", "B. subtilis"]
    assert proj.updated_at == date(2026, 1, 15)


def test_project_list_defaults_are_independent() -> None:
    a = Project(project_id="a", title="A", status="active", research_question="?")
    b = Project(project_id="b", title="B", status="active", research_question="?")
    a.tags.append("x")
    assert b.tags == []


def test_project_yaml_roundtrip() -> None:
    proj = Project(
        project_id="proj-rt",
        title="RT",
        status="active",
        research_question="Round-trip?",
        tags=["foo"],
    )
    assert Project.model_validate(proj.model_dump()) == proj


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


def test_finding_minimal() -> None:
    f = Finding(
        finding_id="find-001",
        project_id="proj-001",
        title="Key result",
        statement="X causes Y under Z.",
        confidence="high",
        finding_type="result",
    )
    assert f.related_entities == []
    assert f.source_refs == []


def test_finding_full() -> None:
    ref = EntityRef(type="organism", label="E. coli")
    f = Finding(
        finding_id="find-002",
        project_id="proj-001",
        title="Pattern found",
        statement="Y correlates with Z.",
        confidence="moderate",
        finding_type="pattern",
        related_entities=[ref],
        conditions=["aerobic"],
        source_refs=["doi:10.1/x"],
        evidence_ids=["ev-001"],
        figure_ids=["fig-001"],
        artifact_ids=["art-001"],
    )
    assert len(f.related_entities) == 1
    assert f.related_entities[0].label == "E. coli"


def test_finding_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        Finding(
            finding_id="f",
            project_id="p",
            title="T",
            statement="S",
            confidence="certain",  # type: ignore[arg-type]
            finding_type="result",
        )


def test_finding_invalid_finding_type() -> None:
    with pytest.raises(ValidationError):
        Finding(
            finding_id="f",
            project_id="p",
            title="T",
            statement="S",
            confidence="high",
            finding_type="unknown_type",  # type: ignore[arg-type]
        )


def test_finding_yaml_roundtrip() -> None:
    f = Finding(
        finding_id="find-rt",
        project_id="proj-rt",
        title="RT",
        statement="Roundtrip.",
        confidence="low",
        finding_type="negative_result",
    )
    assert Finding.model_validate(f.model_dump()) == f


# ---------------------------------------------------------------------------
# Hypothesis
# ---------------------------------------------------------------------------


def test_hypothesis_minimal() -> None:
    h = Hypothesis(
        hypothesis_id="hyp-001",
        statement="X causes Y.",
        status="proposed",
    )
    assert h.scope is None
    assert h.project_ids == []


def test_hypothesis_full() -> None:
    h = Hypothesis(
        hypothesis_id="hyp-002",
        statement="A leads to B.",
        status="supported",
        scope="anaerobic growth",
        project_ids=["proj-001"],
        related_entities=[EntityRef(type="concept", label="redox balance")],
        source_ref="doi:10.1/y",
    )
    assert h.status == "supported"
    assert len(h.related_entities) == 1


def test_hypothesis_invalid_status() -> None:
    with pytest.raises(ValidationError):
        Hypothesis(
            hypothesis_id="h",
            statement="S",
            status="unknown",  # type: ignore[arg-type]
        )


def test_hypothesis_yaml_roundtrip() -> None:
    h = Hypothesis(hypothesis_id="hyp-rt", statement="Round-trip.", status="tested")
    assert Hypothesis.model_validate(h.model_dump()) == h


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def test_evidence_minimal() -> None:
    ev = Evidence(
        evidence_id="ev-001",
        project_id="proj-001",
        kind="statistical",
        summary="p < 0.05",
        source_ref="doi:10.1/z",
    )
    assert ev.linked_artifacts == []
    assert ev.statistical_support is None


def test_evidence_full() -> None:
    ev = Evidence(
        evidence_id="ev-002",
        project_id="proj-001",
        kind="comparative",
        summary="Comparison across 5 species.",
        source_ref="doi:10.1/w",
        linked_artifacts=["art-001"],
        linked_figures=["fig-001"],
        statistical_support="ANOVA p=0.001",
    )
    assert ev.statistical_support == "ANOVA p=0.001"


def test_evidence_invalid_kind() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            evidence_id="ev",
            project_id="p",
            kind="anecdotal",  # type: ignore[arg-type]
            summary="S",
            source_ref="ref",
        )


def test_evidence_yaml_roundtrip() -> None:
    ev = Evidence(
        evidence_id="ev-rt",
        project_id="proj-rt",
        kind="literature",
        summary="RT summary.",
        source_ref="doi:rt",
    )
    assert Evidence.model_validate(ev.model_dump()) == ev


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------


def test_artifact_minimal() -> None:
    art = Artifact(
        artifact_id="art-001",
        project_id="proj-001",
        kind="table",
        path="data/results/table1.csv",
        description="Main results table.",
    )
    assert art.upstream_notebooks == []
    assert art.tags == []


def test_artifact_full() -> None:
    art = Artifact(
        artifact_id="art-002",
        project_id="proj-001",
        kind="model",
        path="models/classifier.pkl",
        description="Trained classifier.",
        upstream_notebooks=["notebooks/train.ipynb"],
        upstream_datasets=["ds-001"],
        tags=["ml", "classifier"],
    )
    assert art.tags == ["ml", "classifier"]


def test_artifact_yaml_roundtrip() -> None:
    art = Artifact(
        artifact_id="art-rt",
        project_id="proj-rt",
        kind="matrix",
        path="data/matrix.npy",
        description="RT artifact.",
    )
    assert Artifact.model_validate(art.model_dump()) == art


# ---------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------


def test_figure_minimal() -> None:
    fig = Figure(
        figure_id="fig-001",
        project_id="proj-001",
        path="figures/fig1.png",
        caption="Main figure.",
    )
    assert fig.illustrates == []
    assert fig.tags == []


def test_figure_full() -> None:
    fig = Figure(
        figure_id="fig-002",
        project_id="proj-001",
        path="figures/fig2.svg",
        caption="Comparative analysis.",
        illustrates=["find-001", "hyp-001"],
        tags=["comparison", "main"],
    )
    assert fig.illustrates == ["find-001", "hyp-001"]


def test_figure_yaml_roundtrip() -> None:
    fig = Figure(
        figure_id="fig-rt",
        project_id="proj-rt",
        path="figures/rt.png",
        caption="Round-trip figure.",
    )
    assert Figure.model_validate(fig.model_dump()) == fig


# ---------------------------------------------------------------------------
# Pitfall
# ---------------------------------------------------------------------------


def test_pitfall_minimal() -> None:
    pit = Pitfall(
        pitfall_id="pit-001",
        title="Watch out for X",
        description="X causes silent failures.",
    )
    assert pit.applies_to == []
    assert pit.source_ref is None
    assert pit.category is None


def test_pitfall_full() -> None:
    pit = Pitfall(
        pitfall_id="pit-002",
        title="Memory overflow",
        description="Loading full dataset into memory fails.",
        applies_to=["RNA-seq pipeline"],
        project_ids=["proj-001"],
        source_ref="notebooks/analysis.ipynb",
        tags=["memory", "pipeline"],
        category="infrastructure",
    )
    assert pit.category == "infrastructure"
    assert "memory" in pit.tags


def test_pitfall_yaml_roundtrip() -> None:
    pit = Pitfall(
        pitfall_id="pit-rt",
        title="RT pitfall",
        description="Round-trip description.",
    )
    assert Pitfall.model_validate(pit.model_dump()) == pit


# ---------------------------------------------------------------------------
# ResearchIdea
# ---------------------------------------------------------------------------


def test_research_idea_minimal() -> None:
    idea = ResearchIdea(
        idea_id="idea-001",
        statement="Investigate X in Y.",
        motivation="X is understudied.",
        priority="medium",
    )
    assert idea.status == "proposed"
    assert idea.related_entities == []


def test_research_idea_full() -> None:
    idea = ResearchIdea(
        idea_id="idea-002",
        statement="Test new hypothesis.",
        motivation="Gap in literature.",
        priority="high",
        status="in_progress",
        related_entities=[EntityRef(type="method", label="CRISPR")],
        project_ids=["proj-001"],
    )
    assert idea.status == "in_progress"
    assert idea.priority == "high"


def test_research_idea_invalid_priority() -> None:
    with pytest.raises(ValidationError):
        ResearchIdea(
            idea_id="idea",
            statement="S",
            motivation="M",
            priority="critical",  # type: ignore[arg-type]
        )


def test_research_idea_invalid_status() -> None:
    with pytest.raises(ValidationError):
        ResearchIdea(
            idea_id="idea",
            statement="S",
            motivation="M",
            priority="low",
            status="abandoned",  # type: ignore[arg-type]
        )


def test_research_idea_yaml_roundtrip() -> None:
    idea = ResearchIdea(
        idea_id="idea-rt",
        statement="Round-trip idea.",
        motivation="RT motivation.",
        priority="low",
        status="deferred",
    )
    assert ResearchIdea.model_validate(idea.model_dump()) == idea
