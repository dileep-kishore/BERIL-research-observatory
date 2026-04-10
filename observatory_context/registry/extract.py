"""Convert CBORG EntityExtraction results to registry entries."""

from __future__ import annotations

from observatory_context.extraction import EntityExtraction
from observatory_context.registry.schema import (
    EntityRef,
    Evidence,
    Finding,
    Hypothesis,
)

_STATUS_MAP: dict[str, str] = {
    "open": "proposed",
    "proposed": "proposed",
    "testing": "tested",
    "tested": "tested",
    "supported": "supported",
    "refuted": "not_supported",
    "updated": "mixed",
}

# Valid finding_type values in the registry schema.
_VALID_FINDING_TYPES = {"result", "pattern", "negative_result", "methodological", "operational"}


def extraction_to_registry_entries(
    extraction: EntityExtraction,
    project_id: str,
    figure_manifest: dict[str, str] | None = None,
) -> list[Finding | Hypothesis | Evidence]:
    """Convert a CBORG extraction into typed registry entries.

    Parameters
    ----------
    extraction:
        Parsed result from :class:`~observatory_context.extraction.CBORGExtractor`.
    project_id:
        Observatory project identifier (used for IDs and source refs).
    figure_manifest:
        Optional mapping of figure filenames (e.g. ``"heatmap.png"``) to
        figure IDs. Used to resolve ``figure_refs`` from the extraction
        into ``figure_ids`` on :class:`Finding`.

    Returns
    -------
    list[Finding | Hypothesis | Evidence]
        One :class:`Finding` per relation, one :class:`Hypothesis` per
        hypothesis update, and one :class:`Evidence` per relation that
        has a source_span.
    """
    entries: list[Finding | Hypothesis | Evidence] = []
    fig_manifest = figure_manifest or {}

    # Build entity lookup for EntityRef generation.
    # Map the extraction's 8 entity types to the registry's EntityRef.
    entity_lookup: dict[str, EntityRef] = {}
    for entity in extraction.entities:
        ref = EntityRef(type=entity.type, label=entity.name)
        entity_lookup[entity.id] = ref
        entity_lookup[f"{entity.type}s/{entity.id}"] = ref

    # Relations -> Findings + Evidence
    for i, rel in enumerate(extraction.relations):
        related = [
            entity_lookup[k]
            for k in (rel.subject, rel.object)
            if k in entity_lookup
        ]

        # Resolve figure_refs to figure_ids via manifest.
        figure_ids: list[str] = []
        figure_refs: list[str] = list(rel.figure_refs)
        for ref_path in rel.figure_refs:
            # Extract bare filename from paths like "figures/heatmap.png"
            fname = ref_path.rsplit("/", 1)[-1] if "/" in ref_path else ref_path
            if fname in fig_manifest:
                figure_ids.append(fig_manifest[fname])

        # Normalize finding_type from extraction.
        finding_type = rel.finding_type if rel.finding_type in _VALID_FINDING_TYPES else "result"

        finding_id = f"F-{project_id}-{i:03d}"

        # Create Evidence entry when we have a source_span.
        evidence_ids: list[str] = []
        if rel.source_span:
            evi_id = f"E-{project_id}-{i:03d}"
            evidence_ids.append(evi_id)
            entries.append(
                Evidence(
                    evidence_id=evi_id,
                    project_id=project_id,
                    kind="statistical" if finding_type == "result" else "manual_review",
                    summary=rel.source_span,
                    source_ref=f"corpus/{project_id}/REPORT.md",
                    linked_figures=[fig_manifest[f.rsplit("/", 1)[-1]]
                                   for f in rel.figure_refs
                                   if f.rsplit("/", 1)[-1] in fig_manifest],
                )
            )

        entries.append(
            Finding(
                finding_id=finding_id,
                project_id=project_id,
                title=f"{rel.subject} {rel.predicate} {rel.object}",
                statement=rel.evidence or f"{rel.subject} {rel.predicate} {rel.object}",
                confidence=rel.confidence if rel.confidence in ("high", "moderate", "low") else "moderate",
                finding_type=finding_type,
                conditions=list(rel.conditions),
                source_span=rel.source_span,
                figure_refs=figure_refs,
                related_entities=related,
                source_refs=[f"corpus/{project_id}/REPORT.md"],
                evidence_ids=evidence_ids,
                figure_ids=figure_ids,
            )
        )

    # Hypotheses
    for hyp in extraction.hypotheses:
        entries.append(
            Hypothesis(
                hypothesis_id=hyp.id,
                statement=hyp.claim,
                status=_STATUS_MAP.get(hyp.status.lower(), "proposed"),
                scope=hyp.scope,
                project_ids=[project_id],
                source_ref=f"corpus/{project_id}/REPORT.md",
            )
        )

    # Timeline events -> Findings with finding_type="methodological"
    # These were previously silently dropped; now we preserve them as
    # findings so they appear in the registry.
    for j, evt in enumerate(extraction.timeline_events):
        entries.append(
            Finding(
                finding_id=f"F-{project_id}-T{j:03d}",
                project_id=project_id,
                title=f"[{evt.date}] {evt.event}",
                statement=evt.event,
                confidence="high",
                finding_type="methodological",
                conditions=[],
                source_refs=[f"corpus/{project_id}/REPORT.md"],
            )
        )

    return entries
