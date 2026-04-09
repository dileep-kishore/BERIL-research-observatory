"""Convert CBORG EntityExtraction results to registry entries."""

from __future__ import annotations

from observatory_context.extraction import EntityExtraction
from observatory_context.registry.schema import EntityRef, Finding, Hypothesis

_STATUS_MAP: dict[str, str] = {
    "open": "proposed",
    "proposed": "proposed",
    "testing": "tested",
    "tested": "tested",
    "supported": "supported",
    "refuted": "not_supported",
    "updated": "mixed",
}


def extraction_to_registry_entries(
    extraction: EntityExtraction,
    project_id: str,
) -> list[Finding | Hypothesis]:
    """Convert a CBORG extraction into typed registry entries.

    Parameters
    ----------
    extraction:
        Parsed result from :class:`~observatory_context.extraction.CBORGExtractor`.
    project_id:
        Observatory project identifier (used for IDs and source refs).

    Returns
    -------
    list[Finding | Hypothesis]
        One :class:`Finding` per relation and one :class:`Hypothesis` per
        hypothesis update in the extraction.
    """
    entries: list[Finding | Hypothesis] = []

    # Build entity lookup for EntityRef generation.
    # Index by both bare id and "{type}s/{id}" (format used in relations).
    entity_lookup: dict[str, EntityRef] = {}
    for entity in extraction.entities:
        ref = EntityRef(type=entity.type, label=entity.name)
        entity_lookup[entity.id] = ref
        entity_lookup[f"{entity.type}s/{entity.id}"] = ref

    # Relations → Findings
    for i, rel in enumerate(extraction.relations):
        related = [
            entity_lookup[k]
            for k in (rel.subject, rel.object)
            if k in entity_lookup
        ]
        entries.append(
            Finding(
                finding_id=f"F-{project_id}-{i:03d}",
                project_id=project_id,
                title=f"{rel.subject} {rel.predicate} {rel.object}",
                statement=rel.evidence or f"{rel.subject} {rel.predicate} {rel.object}",
                confidence=rel.confidence if rel.confidence in ("high", "moderate", "low") else "moderate",
                finding_type="result",
                related_entities=related,
                source_refs=[f"corpus/{project_id}/REPORT.md"],
            )
        )

    # Hypotheses
    for hyp in extraction.hypotheses:
        entries.append(
            Hypothesis(
                hypothesis_id=hyp.id,
                statement=hyp.claim,
                status=_STATUS_MAP.get(hyp.status.lower(), "proposed"),
                project_ids=[project_id],
                source_ref=f"corpus/{project_id}/REPORT.md",
            )
        )

    return entries
