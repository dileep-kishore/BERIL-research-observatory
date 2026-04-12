"""Essential tests for CBORG extraction models and prompt generation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from observatory_context.extraction import CBORGExtractor, Entity, EntityExtraction, Relation


def _make_extractor() -> CBORGExtractor:
    return CBORGExtractor(
        api_url="https://api.cborg.lbl.gov/v1",
        model="openai/gpt-5.4-mini",
        api_key="test-key",
    )


def test_entity_rejects_invalid_type() -> None:
    with pytest.raises(ValidationError):
        Entity(type="invalid", id="x", name="X")  # type: ignore[arg-type]


def test_relation_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        Relation(
            subject="s",
            predicate="p",
            object="o",
            evidence="e",
            confidence="unknown",  # type: ignore[arg-type]
        )


def test_entity_extraction_uses_independent_defaults() -> None:
    left = EntityExtraction()
    right = EntityExtraction()

    left.entities.append(Entity(type="gene", id="g1", name="Gene A"))

    assert right.entities == []
    assert right.relations == []


def test_build_extraction_prompt_includes_report_and_provenance() -> None:
    extractor = _make_extractor()

    prompt = extractor._build_extraction_prompt(
        report="Gene X knockout reduced fitness.",
        provenance={"project": "essential_genome", "date": "2024-01-01"},
    )

    assert "Gene X knockout reduced fitness." in prompt
    assert "essential_genome" in prompt
    assert "2024-01-01" in prompt


def test_extract_knowledge_normalizes_known_predicates_and_skips_invalid_ones() -> None:
    extractor = _make_extractor()
    extractor._chat = lambda **_: """
{
  "entities": [
    {"type": "gene", "id": "gene-a", "name": "Gene A"},
    {"type": "pathway", "id": "pathway-b", "name": "Pathway B"},
    {"type": "concept", "id": "concept-c", "name": "Concept C"}
  ],
  "relations": [
    {
      "subject": "gene-a",
      "predicate": "requires",
      "object": "pathway-b",
      "evidence": "Required in assay",
      "confidence": "high"
    },
    {
      "subject": "gene-a",
      "predicate": "does_not_exist",
      "object": "concept-c",
      "evidence": "Bad predicate",
      "confidence": "low"
    }
  ],
  "hypotheses": [],
  "timeline_events": []
}
"""

    extraction = extractor.extract_knowledge("report", {"project": "x"})

    assert len(extraction.relations) == 1
    assert extraction.relations[0].predicate == "required_for"


def test_extract_knowledge_normalizes_requires_for_predicate() -> None:
    extractor = _make_extractor()
    extractor._chat = lambda **_: """
{
  "entities": [
    {"type": "gene", "id": "gene-a", "name": "Gene A"},
    {"type": "pathway", "id": "pathway-b", "name": "Pathway B"}
  ],
  "relations": [
    {
      "subject": "gene-a",
      "predicate": "requires_for",
      "object": "pathway-b",
      "evidence": "Required in assay",
      "confidence": "high"
    }
  ],
  "hypotheses": [],
  "timeline_events": []
}
"""

    extraction = extractor.extract_knowledge("report", {"project": "x"})

    assert len(extraction.relations) == 1
    assert extraction.relations[0].predicate == "required_for"


def test_extract_knowledge_normalizes_support_finding_type() -> None:
    extractor = _make_extractor()
    extractor._chat = lambda **_: """
{
  "entities": [
    {"type": "gene", "id": "gene-a", "name": "Gene A"},
    {"type": "concept", "id": "concept-b", "name": "Concept B"}
  ],
  "relations": [
    {
      "subject": "gene-a",
      "predicate": "supports",
      "object": "concept-b",
      "evidence": "Gene A supports Concept B",
      "confidence": "high",
      "finding_type": "support"
    }
  ],
  "hypotheses": [],
  "timeline_events": []
}
"""

    extraction = extractor.extract_knowledge("report", {"project": "x"})

    assert len(extraction.relations) == 1
    assert extraction.relations[0].finding_type == "result"


def test_extract_knowledge_hard_skips_when_prompt_exceeds_headroom() -> None:
    extractor = _make_extractor()

    report = "A" * 1_100_000

    with pytest.raises(ValueError, match="hard skip limit"):
        extractor.extract_knowledge(report, {"project": "proj-a"})


def test_haiku_model_clamps_default_output_limit() -> None:
    extractor = CBORGExtractor(
        api_url="https://api.cborg.lbl.gov/v1",
        model="claude-haiku-4-5",
        api_key="test-key",
    )

    assert extractor._max_input_tokens == 200_000
    assert extractor._max_output_tokens == 8_192


def test_chat_raises_when_response_hits_output_limit() -> None:
    extractor = _make_extractor()

    class _Response:
        status_code = 200
        headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": "{}"},
                    }
                ]
            }

    extractor._client.post = lambda *args, **kwargs: _Response()  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="max output tokens"):
        extractor._chat(
            system="system",
            user="user",
            max_tokens=extractor._max_output_tokens,
        )


def test_extract_knowledge_remains_per_project_only() -> None:
    extractor = _make_extractor()

    assert extractor.supports_batch_extraction is False


def test_gpt_54_mini_model_uses_live_cborg_caps() -> None:
    extractor = _make_extractor()

    assert extractor._max_input_tokens == 272_000
    assert extractor._max_output_tokens == 16_384


def test_hard_skip_limit_keeps_headroom_below_model_cap() -> None:
    extractor = _make_extractor()

    assert extractor._hard_input_limit_tokens() == 244_800


def test_max_output_tokens_can_be_lowered_explicitly() -> None:
    extractor = CBORGExtractor(
        api_url="https://api.cborg.lbl.gov/v1",
        model="openai/gpt-5.4-mini",
        api_key="test-key",
        max_output_tokens=4096,
    )

    assert extractor._max_output_tokens == 4096
