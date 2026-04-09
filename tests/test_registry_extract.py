"""Tests for CBORG extraction → registry entry conversion."""

from __future__ import annotations


from observatory_context.extraction import (
    Entity,
    EntityExtraction,
    HypothesisUpdate,
    Relation,
)
from observatory_context.registry.extract import extraction_to_registry_entries
from observatory_context.registry.schema import Finding, Hypothesis


def _make_extraction(
    entities: list[Entity] | None = None,
    relations: list[Relation] | None = None,
    hypotheses: list[HypothesisUpdate] | None = None,
) -> EntityExtraction:
    return EntityExtraction(
        entities=entities or [],
        relations=relations or [],
        hypotheses=hypotheses or [],
    )


# ---------------------------------------------------------------------------
# Empty extraction
# ---------------------------------------------------------------------------


def test_empty_extraction_returns_empty_list():
    result = extraction_to_registry_entries(_make_extraction(), project_id="proj-001")
    assert result == []


# ---------------------------------------------------------------------------
# Finding generation from relations
# ---------------------------------------------------------------------------


def test_relation_produces_finding():
    extraction = _make_extraction(
        relations=[
            Relation(
                subject="ecoli",
                predicate="inhibits",
                object="bacillus",
                evidence="See Figure 3",
                confidence="high",
            )
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="proj-001")
    assert len(entries) == 1
    finding = entries[0]
    assert isinstance(finding, Finding)
    assert finding.project_id == "proj-001"
    assert finding.confidence == "high"
    assert finding.finding_type == "result"
    assert "ecoli" in finding.title
    assert "bacillus" in finding.title


def test_finding_id_format():
    extraction = _make_extraction(
        relations=[
            Relation(subject="a", predicate="p", object="b", evidence="e", confidence="moderate"),
            Relation(subject="c", predicate="q", object="d", evidence="f", confidence="low"),
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="my-proj")
    finding_ids = [e.finding_id for e in entries if isinstance(e, Finding)]
    assert finding_ids == ["F-my-proj-000", "F-my-proj-001"]


def test_finding_statement_uses_evidence():
    extraction = _make_extraction(
        relations=[
            Relation(
                subject="geneA",
                predicate="activates",
                object="pathwayX",
                evidence="Observed in experiment 2",
                confidence="moderate",
            )
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="p")
    assert entries[0].statement == "Observed in experiment 2"


def test_finding_source_ref_contains_project_id():
    extraction = _make_extraction(
        relations=[
            Relation(subject="a", predicate="b", object="c", evidence="e", confidence="low")
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="proj-xyz")
    assert any("proj-xyz" in ref for ref in entries[0].source_refs)


# ---------------------------------------------------------------------------
# Entity lookup → related_entities on Finding
# ---------------------------------------------------------------------------


def test_finding_related_entities_resolved_from_entity_list():
    extraction = _make_extraction(
        entities=[
            Entity(type="organism", id="ecoli", name="E. coli"),
            Entity(type="pathway", id="tca", name="TCA cycle"),
        ],
        relations=[
            Relation(
                subject="ecoli",
                predicate="uses",
                object="tca",
                evidence="",
                confidence="high",
            )
        ],
    )
    entries = extraction_to_registry_entries(extraction, project_id="p")
    finding = entries[0]
    assert isinstance(finding, Finding)
    labels = {r.label for r in finding.related_entities}
    assert "E. coli" in labels
    assert "TCA cycle" in labels


def test_finding_related_entities_empty_when_no_match():
    extraction = _make_extraction(
        entities=[],
        relations=[
            Relation(subject="unknown-a", predicate="x", object="unknown-b", evidence="", confidence="low")
        ],
    )
    entries = extraction_to_registry_entries(extraction, project_id="p")
    assert entries[0].related_entities == []


# ---------------------------------------------------------------------------
# Hypothesis conversion
# ---------------------------------------------------------------------------


def test_hypothesis_produces_hypothesis_entry():
    extraction = _make_extraction(
        hypotheses=[
            HypothesisUpdate(
                id="H-001",
                status="supported",
                claim="Gene X drives biofilm formation.",
                evidence_delta="Confirmed in 3 strains.",
            )
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="proj-a")
    assert len(entries) == 1
    hyp = entries[0]
    assert isinstance(hyp, Hypothesis)
    assert hyp.hypothesis_id == "H-001"
    assert hyp.statement == "Gene X drives biofilm formation."
    assert hyp.status == "supported"
    assert "proj-a" in hyp.project_ids


def test_hypothesis_status_mapping():
    status_cases = [
        ("open", "proposed"),
        ("proposed", "proposed"),
        ("testing", "tested"),
        ("tested", "tested"),
        ("supported", "supported"),
        ("refuted", "not_supported"),
        ("updated", "mixed"),
        ("SUPPORTED", "supported"),  # case-insensitive
        ("unknown_status", "proposed"),  # fallback
    ]
    for raw_status, expected in status_cases:
        extraction = _make_extraction(
            hypotheses=[
                HypothesisUpdate(id="H-x", status=raw_status, claim="claim", evidence_delta="")
            ]
        )
        entries = extraction_to_registry_entries(extraction, project_id="p")
        hyp = entries[0]
        assert isinstance(hyp, Hypothesis)
        assert hyp.status == expected, f"status={raw_status!r} → expected {expected!r}, got {hyp.status!r}"


def test_hypothesis_source_ref():
    extraction = _make_extraction(
        hypotheses=[
            HypothesisUpdate(id="H-2", status="open", claim="c", evidence_delta="")
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="proj-b")
    hyp = entries[0]
    assert hyp.source_ref == "corpus/proj-b/REPORT.md"


# ---------------------------------------------------------------------------
# Mixed extraction
# ---------------------------------------------------------------------------


def test_mixed_extraction_returns_both_types():
    extraction = _make_extraction(
        relations=[
            Relation(subject="a", predicate="b", object="c", evidence="e", confidence="high")
        ],
        hypotheses=[
            HypothesisUpdate(id="H-1", status="open", claim="claim", evidence_delta="")
        ],
    )
    entries = extraction_to_registry_entries(extraction, project_id="p")
    types = {type(e).__name__ for e in entries}
    assert types == {"Finding", "Hypothesis"}
