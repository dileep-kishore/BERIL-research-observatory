"""Tests for CBORG extraction -> registry entry conversion."""

from __future__ import annotations


from observatory_context.extraction import (
    Entity,
    EntityExtraction,
    HypothesisUpdate,
    Relation,
    TimelineEvent,
)
from observatory_context.registry.extract import extraction_to_registry_entries
from observatory_context.registry.schema import Evidence, Finding, Hypothesis


def _make_extraction(
    entities: list[Entity] | None = None,
    relations: list[Relation] | None = None,
    hypotheses: list[HypothesisUpdate] | None = None,
    timeline_events: list[TimelineEvent] | None = None,
) -> EntityExtraction:
    return EntityExtraction(
        entities=entities or [],
        relations=relations or [],
        hypotheses=hypotheses or [],
        timeline_events=timeline_events or [],
    )


def _findings(entries):
    return [e for e in entries if isinstance(e, Finding)]


def _evidences(entries):
    return [e for e in entries if isinstance(e, Evidence)]


def _hypotheses(entries):
    return [e for e in entries if isinstance(e, Hypothesis)]


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
    findings = _findings(entries)
    assert len(findings) == 1
    finding = findings[0]
    assert isinstance(finding, Finding)
    assert finding.project_id == "proj-001"
    assert finding.confidence == "high"
    assert finding.finding_type == "result"
    assert "ecoli" in finding.title
    assert "bacillus" in finding.title


def test_finding_id_format():
    extraction = _make_extraction(
        relations=[
            Relation(subject="a", predicate="associated_with", object="b", evidence="e", confidence="moderate"),
            Relation(subject="c", predicate="correlated_with", object="d", evidence="f", confidence="low"),
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="my-proj")
    finding_ids = [e.finding_id for e in _findings(entries)]
    assert finding_ids == ["F-my-proj-000", "F-my-proj-001"]


def test_finding_statement_uses_evidence():
    extraction = _make_extraction(
        relations=[
            Relation(
                subject="geneA",
                predicate="regulates",
                object="pathwayX",
                evidence="Observed in experiment 2",
                confidence="moderate",
            )
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="p")
    assert _findings(entries)[0].statement == "Observed in experiment 2"


def test_finding_source_ref_contains_project_id():
    extraction = _make_extraction(
        relations=[
            Relation(subject="a", predicate="supports", object="c", evidence="e", confidence="low")
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="proj-xyz")
    assert any("proj-xyz" in ref for ref in _findings(entries)[0].source_refs)


# ---------------------------------------------------------------------------
# Entity lookup -> related_entities on Finding
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
                predicate="associated_with",
                object="tca",
                evidence="",
                confidence="high",
            )
        ],
    )
    entries = extraction_to_registry_entries(extraction, project_id="p")
    finding = _findings(entries)[0]
    assert isinstance(finding, Finding)
    labels = {r.label for r in finding.related_entities}
    assert "E. coli" in labels
    assert "TCA cycle" in labels


def test_finding_related_entities_empty_when_no_match():
    extraction = _make_extraction(
        entities=[],
        relations=[
            Relation(subject="unknown-a", predicate="associated_with", object="unknown-b", evidence="", confidence="low")
        ],
    )
    entries = extraction_to_registry_entries(extraction, project_id="p")
    assert _findings(entries)[0].related_entities == []


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
    hyps = _hypotheses(entries)
    assert len(hyps) == 1
    hyp = hyps[0]
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
        hyp = _hypotheses(entries)[0]
        assert isinstance(hyp, Hypothesis)
        assert hyp.status == expected, f"status={raw_status!r} -> expected {expected!r}, got {hyp.status!r}"


def test_hypothesis_source_ref():
    extraction = _make_extraction(
        hypotheses=[
            HypothesisUpdate(id="H-2", status="open", claim="c", evidence_delta="")
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="proj-b")
    hyp = _hypotheses(entries)[0]
    assert hyp.source_ref == "corpus/proj-b/REPORT.md"


def test_hypothesis_scope_propagated():
    extraction = _make_extraction(
        hypotheses=[
            HypothesisUpdate(
                id="H-3", status="open", claim="c", evidence_delta="",
                scope="Pseudomonas putida under zinc stress",
            )
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="p")
    hyp = _hypotheses(entries)[0]
    assert hyp.scope == "Pseudomonas putida under zinc stress"


# ---------------------------------------------------------------------------
# New fields: conditions, finding_type, source_span, figure_refs
# ---------------------------------------------------------------------------


def test_finding_conditions_from_relation():
    extraction = _make_extraction(
        relations=[
            Relation(
                subject="geneA",
                predicate="enriched_in",
                object="condX",
                evidence="Significant enrichment",
                confidence="high",
                conditions=["zinc stress", "aerobic"],
            )
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="p")
    finding = _findings(entries)[0]
    assert finding.conditions == ["zinc stress", "aerobic"]


def test_finding_type_from_relation():
    extraction = _make_extraction(
        relations=[
            Relation(
                subject="a",
                predicate="associated_with",
                object="b",
                evidence="No effect observed",
                confidence="moderate",
                finding_type="negative_result",
            )
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="p")
    finding = _findings(entries)[0]
    assert finding.finding_type == "negative_result"


def test_finding_source_span_and_evidence_created():
    extraction = _make_extraction(
        relations=[
            Relation(
                subject="a",
                predicate="depleted_in",
                object="b",
                evidence="Gene depleted under stress",
                confidence="high",
                source_span="The gene was depleted 5-fold under zinc stress (p<0.001).",
            )
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="p")
    finding = _findings(entries)[0]
    assert finding.source_span == "The gene was depleted 5-fold under zinc stress (p<0.001)."
    assert len(finding.evidence_ids) == 1

    evidences = _evidences(entries)
    assert len(evidences) == 1
    assert evidences[0].evidence_id == finding.evidence_ids[0]
    assert evidences[0].summary == finding.source_span


def test_figure_refs_resolved_via_manifest():
    extraction = _make_extraction(
        relations=[
            Relation(
                subject="a",
                predicate="correlated_with",
                object="b",
                evidence="See figure",
                confidence="moderate",
                figure_refs=["figures/heatmap.png", "figures/unknown.svg"],
            )
        ]
    )
    manifest = {"heatmap.png": "FIG-001"}
    entries = extraction_to_registry_entries(extraction, project_id="p", figure_manifest=manifest)
    finding = _findings(entries)[0]
    assert finding.figure_refs == ["figures/heatmap.png", "figures/unknown.svg"]
    assert finding.figure_ids == ["FIG-001"]  # only the matched one


# ---------------------------------------------------------------------------
# Timeline events -> methodological findings
# ---------------------------------------------------------------------------


def test_timeline_events_converted_to_findings():
    extraction = _make_extraction(
        timeline_events=[
            TimelineEvent(date="2026-03-15", event="Completed RB-TnSeq library", type="milestone", project="proj-a"),
            TimelineEvent(date="2026-04-01", event="Submitted manuscript", type="publication"),
        ]
    )
    entries = extraction_to_registry_entries(extraction, project_id="proj-a")
    findings = _findings(entries)
    assert len(findings) == 2
    assert findings[0].finding_id == "F-proj-a-T000"
    assert findings[0].finding_type == "methodological"
    assert "[2026-03-15]" in findings[0].title
    assert findings[1].finding_id == "F-proj-a-T001"


# ---------------------------------------------------------------------------
# Mixed extraction
# ---------------------------------------------------------------------------


def test_mixed_extraction_returns_all_types():
    extraction = _make_extraction(
        relations=[
            Relation(
                subject="a", predicate="supports", object="c", evidence="e", confidence="high",
                source_span="Some evidence text.",
            )
        ],
        hypotheses=[
            HypothesisUpdate(id="H-1", status="open", claim="claim", evidence_delta="")
        ],
        timeline_events=[
            TimelineEvent(date="2026-01-01", event="Started", type="milestone"),
        ],
    )
    entries = extraction_to_registry_entries(extraction, project_id="p")
    types = {type(e).__name__ for e in entries}
    assert types == {"Finding", "Hypothesis", "Evidence"}
