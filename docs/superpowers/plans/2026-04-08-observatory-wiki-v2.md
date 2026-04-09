# Observatory Wiki V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the observatory knowledge layer as an LLM-optimized wiki backed by OpenViking, with a structured YAML registry and modernized batch ingest.

**Architecture:** Three-layer system — immutable source corpus in Git, LLM-compiled wiki pages in OpenViking for agent navigation, and a structured YAML registry for typed knowledge objects. OpenViking is modernized to use batch uploads, native tier generation, and reranking.

**Tech Stack:** Python 3.11+, OpenViking (SyncHTTPClient), Pydantic v2, PyYAML, CBORG API (gpt-5.4-mini), pytest, uv

**Spec:** `docs/superpowers/specs/2026-04-08-observatory-wiki-v2-design.md`

---

## File Structure

### New files to create

| File | Responsibility |
|------|---------------|
| `observatory_context/registry/__init__.py` | Registry subpackage exports |
| `observatory_context/registry/schema.py` | Pydantic models for all registry types (Project, Finding, Hypothesis, Evidence, Artifact, Figure, Pitfall, ResearchIdea) |
| `observatory_context/registry/store.py` | Read/write registry YAML via OpenViking write API |
| `observatory_context/registry/extract.py` | CBORG EntityExtraction → registry entries pipeline |
| `observatory_context/wiki/__init__.py` | Wiki subpackage exports |
| `observatory_context/wiki/compiler.py` | Generate/update topic, entity, hypothesis wiki pages |
| `observatory_context/wiki/index.py` | Maintain wiki/index.md master catalog |
| `observatory_context/wiki/lint.py` | Contradiction/gap/staleness/orphan detection |
| `observatory_context/wiki/compound.py` | Persist novel query synthesis as wiki pages |
| `observatory_context/ingest/batch.py` | Batch upload orchestration (stage + upload + wait) |
| `observatory_context/ingest/pipeline.py` | 4-phase ingest pipeline (corpus, registry, wiki, index) |
| `tests/test_registry_schema.py` | Registry schema validation tests |
| `tests/test_registry_store.py` | Registry store read/write tests |
| `tests/test_wiki_index.py` | Wiki index generation tests |
| `tests/test_wiki_compiler.py` | Wiki page compilation tests |
| `tests/test_wiki_lint.py` | Lint detection tests |
| `tests/test_ingest_batch.py` | Batch upload tests |
| `tests/test_ingest_pipeline.py` | Pipeline orchestration tests |
| `tests/test_uris_v2.py` | New URI builder tests |

### Files to modify

| File | Changes |
|------|---------|
| `observatory_context/uris.py` | Add wiki/, registry/, corpus/ URI builders |
| `observatory_context/models.py` | Add Scope.wiki, Scope.registry |
| `observatory_context/client.py` | Add `write_content()` method, modernize `add_text_resource()` |
| `observatory_context/config.py` | No changes needed (rerank is server-side config) |
| `observatory_context/delivery.py` | Simplify: delegate operational knowledge to registry, add wiki-first navigation |
| `observatory_context/runtime.py` | Update build helpers for new modules |
| `scripts/viking_setup.py` | Add rerank section to ov.conf generation |

---

## Task 1: URI Builders for New Hierarchy

**Files:**
- Modify: `observatory_context/uris.py`
- Create: `tests/test_uris_v2.py`

- [ ] **Step 1: Write failing tests for new URI builders**

```python
"""Tests for V2 URI builders (wiki, registry, corpus namespaces)."""

from observatory_context.uris import (
    build_corpus_uri,
    build_registry_uri,
    build_wiki_uri,
    build_wiki_topic_uri,
    build_wiki_entity_uri,
    build_wiki_hypothesis_uri,
    build_wiki_gaps_uri,
    build_wiki_index_uri,
    build_wiki_log_uri,
    build_registry_finding_uri,
    build_registry_hypothesis_uri,
    build_registry_evidence_uri,
    build_registry_artifact_uri,
    build_registry_figure_uri,
    build_registry_pitfall_uri,
    build_registry_idea_uri,
    build_registry_project_uri,
)


def test_corpus_uri():
    assert build_corpus_uri("proj-01") == "viking://resources/observatory/corpus/proj-01"


def test_corpus_uri_with_file():
    assert (
        build_corpus_uri("proj-01", "REPORT.md")
        == "viking://resources/observatory/corpus/proj-01/REPORT.md"
    )


def test_wiki_uri():
    assert build_wiki_uri() == "viking://resources/observatory/wiki"


def test_wiki_index_uri():
    assert build_wiki_index_uri() == "viking://resources/observatory/wiki/index.md"


def test_wiki_log_uri():
    assert build_wiki_log_uri() == "viking://resources/observatory/wiki/log.md"


def test_wiki_topic_uri():
    assert (
        build_wiki_topic_uri("nitrogen-stress")
        == "viking://resources/observatory/wiki/topics/nitrogen-stress.md"
    )


def test_wiki_entity_uri():
    assert (
        build_wiki_entity_uri("organism", "pseudomonas-putida")
        == "viking://resources/observatory/wiki/entities/organisms/pseudomonas-putida.md"
    )


def test_wiki_hypothesis_uri():
    assert (
        build_wiki_hypothesis_uri("hyp-metal-cross-resistance")
        == "viking://resources/observatory/wiki/hypotheses/hyp-metal-cross-resistance.md"
    )


def test_wiki_gaps_uri():
    assert build_wiki_gaps_uri() == "viking://resources/observatory/wiki/gaps/latest.md"


def test_registry_uri():
    assert build_registry_uri() == "viking://resources/observatory/registry"


def test_registry_project_uri():
    assert (
        build_registry_project_uri("proj-01")
        == "viking://resources/observatory/registry/projects/proj-01.yaml"
    )


def test_registry_finding_uri():
    assert (
        build_registry_finding_uri("F-023")
        == "viking://resources/observatory/registry/findings/F-023.yaml"
    )


def test_registry_hypothesis_uri():
    assert (
        build_registry_hypothesis_uri("HYP-007")
        == "viking://resources/observatory/registry/hypotheses/HYP-007.yaml"
    )


def test_registry_evidence_uri():
    assert (
        build_registry_evidence_uri("E-023a")
        == "viking://resources/observatory/registry/evidence/E-023a.yaml"
    )


def test_registry_artifact_uri():
    assert (
        build_registry_artifact_uri("ART-metal-001")
        == "viking://resources/observatory/registry/artifacts/ART-metal-001.yaml"
    )


def test_registry_figure_uri():
    assert (
        build_registry_figure_uri("FIG-metal-001")
        == "viking://resources/observatory/registry/figures/FIG-metal-001.yaml"
    )


def test_registry_pitfall_uri():
    assert (
        build_registry_pitfall_uri("PIT-spark-timeout")
        == "viking://resources/observatory/registry/pitfalls/PIT-spark-timeout.yaml"
    )


def test_registry_idea_uri():
    assert (
        build_registry_idea_uri("IDEA-marine-metal")
        == "viking://resources/observatory/registry/ideas/IDEA-marine-metal.yaml"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_uris_v2.py -v`
Expected: ImportError — functions don't exist yet

- [ ] **Step 3: Implement the new URI builders**

Add to `observatory_context/uris.py` (append after existing functions):

```python
# --- V2 URI builders (wiki, registry, corpus) ---


def build_corpus_uri(project_id: str, file_path: str | None = None) -> str:
    """URI for a source document in the corpus."""
    parts = ["corpus", _normalize_segment(project_id)]
    if file_path:
        parts.append(_normalize_segment(file_path))
    path = PurePosixPath(*parts)
    return f"{_ROOT}/{path.as_posix()}"


def build_wiki_uri() -> str:
    """Root URI for the observatory wiki."""
    return f"{_ROOT}/wiki"


def build_wiki_index_uri() -> str:
    """URI for the wiki master index."""
    return f"{_ROOT}/wiki/index.md"


def build_wiki_log_uri() -> str:
    """URI for the wiki activity log."""
    return f"{_ROOT}/wiki/log.md"


def build_wiki_topic_uri(slug: str) -> str:
    """URI for a wiki topic synthesis page."""
    return f"{_ROOT}/wiki/topics/{_normalize_segment(slug)}.md"


def build_wiki_entity_uri(entity_type: str, slug: str) -> str:
    """URI for a wiki entity profile page."""
    plural = _ENTITY_TYPE_PLURALS[entity_type]
    return f"{_ROOT}/wiki/entities/{plural}/{_normalize_segment(slug)}.md"


def build_wiki_hypothesis_uri(hypothesis_id: str) -> str:
    """URI for a wiki hypothesis tracker page."""
    return f"{_ROOT}/wiki/hypotheses/{_normalize_segment(hypothesis_id)}.md"


def build_wiki_gaps_uri() -> str:
    """URI for the latest gap analysis page."""
    return f"{_ROOT}/wiki/gaps/latest.md"


def build_registry_uri() -> str:
    """Root URI for the structured knowledge registry."""
    return f"{_ROOT}/registry"


def build_registry_project_uri(project_id: str) -> str:
    return f"{_ROOT}/registry/projects/{_normalize_segment(project_id)}.yaml"


def build_registry_finding_uri(finding_id: str) -> str:
    return f"{_ROOT}/registry/findings/{_normalize_segment(finding_id)}.yaml"


def build_registry_hypothesis_uri(hypothesis_id: str) -> str:
    return f"{_ROOT}/registry/hypotheses/{_normalize_segment(hypothesis_id)}.yaml"


def build_registry_evidence_uri(evidence_id: str) -> str:
    return f"{_ROOT}/registry/evidence/{_normalize_segment(evidence_id)}.yaml"


def build_registry_artifact_uri(artifact_id: str) -> str:
    return f"{_ROOT}/registry/artifacts/{_normalize_segment(artifact_id)}.yaml"


def build_registry_figure_uri(figure_id: str) -> str:
    return f"{_ROOT}/registry/figures/{_normalize_segment(figure_id)}.yaml"


def build_registry_pitfall_uri(pitfall_id: str) -> str:
    return f"{_ROOT}/registry/pitfalls/{_normalize_segment(pitfall_id)}.yaml"


def build_registry_idea_uri(idea_id: str) -> str:
    return f"{_ROOT}/registry/ideas/{_normalize_segment(idea_id)}.yaml"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_uris_v2.py -v`
Expected: All 15 tests PASS

- [ ] **Step 5: Commit**

```bash
git add observatory_context/uris.py tests/test_uris_v2.py
git commit -m "feat: add V2 URI builders for wiki, registry, corpus namespaces"
```

---

## Task 2: Registry Schema (Pydantic Models)

**Files:**
- Create: `observatory_context/registry/__init__.py`
- Create: `observatory_context/registry/schema.py`
- Create: `tests/test_registry_schema.py`

- [ ] **Step 1: Create registry package init**

```python
"""Structured knowledge registry backed by OpenViking."""
```

- [ ] **Step 2: Write failing tests for registry schema**

```python
"""Tests for registry Pydantic models."""

from datetime import date

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


class TestEntityRef:
    def test_minimal(self):
        ref = EntityRef(type="organism", label="Pseudomonas putida")
        assert ref.type == "organism"
        assert ref.label == "Pseudomonas putida"
        assert ref.normalized_id is None

    def test_with_normalization(self):
        ref = EntityRef(
            type="organism",
            label="Pseudomonas putida",
            normalized_id="NCBI:160488",
            namespace="NCBI",
        )
        assert ref.normalized_id == "NCBI:160488"


class TestProject:
    def test_minimal(self):
        p = Project(
            project_id="proj-01",
            title="Test Project",
            status="complete",
            research_question="Does X cause Y?",
        )
        assert p.project_id == "proj-01"
        assert p.organisms == []
        assert p.tags == []

    def test_full(self):
        p = Project(
            project_id="proj-01",
            title="Test Project",
            status="in-progress",
            research_question="Does X cause Y?",
            organisms=["P. putida"],
            conditions=["zinc stress"],
            methods=["pangenome analysis"],
            datasets=["BERDL pangenome_analysis"],
            tags=["metal-stress"],
            updated_at=date(2026, 4, 8),
        )
        assert len(p.organisms) == 1
        assert p.updated_at == date(2026, 4, 8)


class TestFinding:
    def test_minimal(self):
        f = Finding(
            finding_id="F-001",
            project_id="proj-01",
            title="Test finding",
            statement="We found X.",
            confidence="high",
            finding_type="result",
        )
        assert f.finding_id == "F-001"
        assert f.evidence_ids == []

    def test_invalid_confidence(self):
        with pytest.raises(ValidationError):
            Finding(
                finding_id="F-001",
                project_id="proj-01",
                title="Test",
                statement="X",
                confidence="very_high",
                finding_type="result",
            )


class TestHypothesis:
    def test_minimal(self):
        h = Hypothesis(
            hypothesis_id="HYP-001",
            statement="X causes Y",
            status="proposed",
        )
        assert h.project_ids == []

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            Hypothesis(
                hypothesis_id="HYP-001",
                statement="X",
                status="maybe",
            )


class TestEvidence:
    def test_minimal(self):
        e = Evidence(
            evidence_id="E-001",
            project_id="proj-01",
            kind="statistical",
            summary="p < 0.01",
            source_ref="corpus/proj-01/REPORT.md",
        )
        assert e.evidence_id == "E-001"


class TestArtifact:
    def test_minimal(self):
        a = Artifact(
            artifact_id="ART-001",
            project_id="proj-01",
            kind="dataset",
            path="exports/data.tsv",
            description="Exported data",
        )
        assert a.tags == []


class TestFigure:
    def test_minimal(self):
        f = Figure(
            figure_id="FIG-001",
            project_id="proj-01",
            path="projects/proj-01/figures/fig1.png",
            caption="Test figure",
        )
        assert f.illustrates == []


class TestPitfall:
    def test_minimal(self):
        p = Pitfall(
            pitfall_id="PIT-001",
            title="Watch out",
            description="Things break",
        )
        assert p.applies_to == []


class TestResearchIdea:
    def test_minimal(self):
        r = ResearchIdea(
            idea_id="IDEA-001",
            statement="Study X",
            motivation="Because gap",
            priority="medium",
        )
        assert r.status == "proposed"


class TestYAMLRoundTrip:
    def test_finding_to_yaml_dict(self):
        f = Finding(
            finding_id="F-001",
            project_id="proj-01",
            title="Test",
            statement="Found X",
            confidence="high",
            finding_type="result",
            related_entities=[
                EntityRef(type="organism", label="P. putida"),
            ],
        )
        d = f.model_dump(mode="json", exclude_none=True)
        assert d["finding_id"] == "F-001"
        assert d["related_entities"][0]["type"] == "organism"
        # Verify round-trip
        f2 = Finding.model_validate(d)
        assert f2.finding_id == f.finding_id
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_registry_schema.py -v`
Expected: ImportError — schema.py doesn't exist

- [ ] **Step 4: Implement registry schema**

Create `observatory_context/registry/schema.py`:

```python
"""Pydantic models for the structured knowledge registry.

Each model represents a typed knowledge object extracted from project
reports. All models serialize to YAML for storage in OpenViking.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class EntityRef(BaseModel):
    """Reference to a typed entity with optional normalization."""

    type: Literal["organism", "gene", "pathway", "condition", "environment", "method", "dataset", "concept"]
    label: str
    normalized_id: str | None = None
    namespace: str | None = None


class Project(BaseModel):
    """High-level metadata about a research project."""

    project_id: str
    title: str
    status: str
    research_question: str
    organisms: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    enables: list[str] = Field(default_factory=list)
    updated_at: date | None = None


class Finding(BaseModel):
    """A reusable claim or conclusion extracted from a project report."""

    finding_id: str
    project_id: str
    title: str
    statement: str
    confidence: Literal["high", "moderate", "low"]
    finding_type: Literal["result", "pattern", "negative_result", "methodological", "operational"]
    related_entities: list[EntityRef] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    figure_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    """A testable claim tracked across projects."""

    hypothesis_id: str
    statement: str
    status: Literal["proposed", "tested", "supported", "mixed", "not_supported", "superseded"]
    scope: str | None = None
    project_ids: list[str] = Field(default_factory=list)
    related_entities: list[EntityRef] = Field(default_factory=list)
    source_ref: str | None = None


class Evidence(BaseModel):
    """Concrete support for a hypothesis or finding."""

    evidence_id: str
    project_id: str
    kind: Literal["statistical", "comparative", "biogeographic", "literature", "manual_review"]
    summary: str
    source_ref: str
    linked_artifacts: list[str] = Field(default_factory=list)
    linked_figures: list[str] = Field(default_factory=list)
    statistical_support: str | None = None


class Artifact(BaseModel):
    """A reusable data product or output."""

    artifact_id: str
    project_id: str
    kind: str
    path: str
    description: str
    upstream_notebooks: list[str] = Field(default_factory=list)
    upstream_datasets: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class Figure(BaseModel):
    """Structured access to a visual output."""

    figure_id: str
    project_id: str
    path: str
    caption: str
    illustrates: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class Pitfall(BaseModel):
    """Operational knowledge that prevents future rediscovery."""

    pitfall_id: str
    title: str
    description: str
    applies_to: list[str] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)
    source_ref: str | None = None
    tags: list[str] = Field(default_factory=list)
    category: str | None = None


class ResearchIdea(BaseModel):
    """A future research direction."""

    idea_id: str
    statement: str
    motivation: str
    priority: Literal["high", "medium", "low"]
    status: Literal["proposed", "in_progress", "completed", "deferred"] = "proposed"
    related_entities: list[EntityRef] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_registry_schema.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add observatory_context/registry/__init__.py observatory_context/registry/schema.py tests/test_registry_schema.py
git commit -m "feat: add registry Pydantic schema for structured knowledge objects"
```

---

## Task 3: Registry Store (OpenViking-backed YAML Read/Write)

**Files:**
- Create: `observatory_context/registry/store.py`
- Create: `tests/test_registry_store.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for registry store (OpenViking-backed YAML read/write)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import yaml

from observatory_context.registry.schema import Finding, EntityRef, Project
from observatory_context.registry.store import RegistryStore


@pytest.fixture()
def mock_client():
    return MagicMock()


@pytest.fixture()
def store(mock_client):
    return RegistryStore(client=mock_client)


class TestWriteEntry:
    def test_write_finding(self, store, mock_client):
        finding = Finding(
            finding_id="F-001",
            project_id="proj-01",
            title="Test finding",
            statement="We found X.",
            confidence="high",
            finding_type="result",
        )
        store.write_finding(finding)

        mock_client.add_text_resource.assert_called_once()
        call_kwargs = mock_client.add_text_resource.call_args
        assert "registry/findings/F-001.yaml" in call_kwargs.kwargs["uri"]

    def test_write_project(self, store, mock_client):
        project = Project(
            project_id="proj-01",
            title="Test",
            status="complete",
            research_question="Q?",
        )
        store.write_project(project)

        mock_client.add_text_resource.assert_called_once()
        call_kwargs = mock_client.add_text_resource.call_args
        assert "registry/projects/proj-01.yaml" in call_kwargs.kwargs["uri"]


class TestReadEntry:
    def test_read_finding(self, store, mock_client):
        finding_data = {
            "finding_id": "F-001",
            "project_id": "proj-01",
            "title": "Test",
            "statement": "Found X",
            "confidence": "high",
            "finding_type": "result",
        }
        mock_client.read_resource.return_value = yaml.safe_dump(finding_data)

        result = store.read_finding("F-001")
        assert result.finding_id == "F-001"
        assert result.confidence == "high"

    def test_read_missing_returns_none(self, store, mock_client):
        # Simulate NotFoundError by class name check
        exc = type("NotFoundError", (Exception,), {})()
        mock_client.read_resource.side_effect = exc
        result = store.read_finding("F-999")
        assert result is None


class TestListEntries:
    def test_list_findings(self, store, mock_client):
        mock_client.list_resources.return_value = [
            {"uri": "viking://resources/observatory/registry/findings/F-001.yaml"},
            {"uri": "viking://resources/observatory/registry/findings/F-002.yaml"},
        ]
        mock_client.read_resource.side_effect = [
            yaml.safe_dump({
                "finding_id": "F-001", "project_id": "p1",
                "title": "A", "statement": "X",
                "confidence": "high", "finding_type": "result",
            }),
            yaml.safe_dump({
                "finding_id": "F-002", "project_id": "p2",
                "title": "B", "statement": "Y",
                "confidence": "moderate", "finding_type": "pattern",
            }),
        ]

        results = store.list_findings()
        assert len(results) == 2
        assert results[0].finding_id == "F-001"


class TestBatchWrite:
    def test_batch_write_findings(self, store, mock_client, tmp_path):
        findings = [
            Finding(
                finding_id=f"F-{i:03d}",
                project_id="proj-01",
                title=f"Finding {i}",
                statement=f"Found {i}",
                confidence="high",
                finding_type="result",
            )
            for i in range(3)
        ]
        store.batch_write_findings(findings, staging_dir=tmp_path)

        # Should have staged 3 files and called batch_add once
        mock_client.batch_add.assert_called_once()
        staged_files = list(tmp_path.rglob("*.yaml"))
        assert len(staged_files) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_registry_store.py -v`
Expected: ImportError — store.py doesn't exist

- [ ] **Step 3: Implement registry store**

Create `observatory_context/registry/store.py`:

```python
"""Read/write registry YAML entries via OpenViking."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypeVar

import yaml

from observatory_context.client import OpenVikingObservatoryClient
from observatory_context.registry.schema import (
    Artifact,
    Evidence,
    Figure,
    Finding,
    Hypothesis,
    Pitfall,
    Project,
    ResearchIdea,
)
from observatory_context.staging import write_staged_file
from observatory_context.uris import (
    build_registry_artifact_uri,
    build_registry_evidence_uri,
    build_registry_figure_uri,
    build_registry_finding_uri,
    build_registry_hypothesis_uri,
    build_registry_idea_uri,
    build_registry_pitfall_uri,
    build_registry_project_uri,
    build_registry_uri,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _is_not_found(exc: Exception) -> bool:
    return any(cls.__name__ == "NotFoundError" for cls in type(exc).__mro__)


class RegistryStore:
    """OpenViking-backed store for structured knowledge objects."""

    def __init__(self, client: OpenVikingObservatoryClient) -> None:
        self.client = client

    # --- Single writes ---

    def _write_entry(self, uri: str, data: dict, reason: str, wait: bool = False) -> None:
        content = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        self.client.add_text_resource(
            uri=uri, content=content, metadata={}, reason=reason, wait=wait,
        )

    def write_project(self, project: Project, wait: bool = False) -> None:
        uri = build_registry_project_uri(project.project_id)
        self._write_entry(uri, project.model_dump(mode="json", exclude_none=True), f"Registry: project {project.project_id}", wait)

    def write_finding(self, finding: Finding, wait: bool = False) -> None:
        uri = build_registry_finding_uri(finding.finding_id)
        self._write_entry(uri, finding.model_dump(mode="json", exclude_none=True), f"Registry: finding {finding.finding_id}", wait)

    def write_hypothesis(self, hypothesis: Hypothesis, wait: bool = False) -> None:
        uri = build_registry_hypothesis_uri(hypothesis.hypothesis_id)
        self._write_entry(uri, hypothesis.model_dump(mode="json", exclude_none=True), f"Registry: hypothesis {hypothesis.hypothesis_id}", wait)

    def write_evidence(self, evidence: Evidence, wait: bool = False) -> None:
        uri = build_registry_evidence_uri(evidence.evidence_id)
        self._write_entry(uri, evidence.model_dump(mode="json", exclude_none=True), f"Registry: evidence {evidence.evidence_id}", wait)

    def write_artifact(self, artifact: Artifact, wait: bool = False) -> None:
        uri = build_registry_artifact_uri(artifact.artifact_id)
        self._write_entry(uri, artifact.model_dump(mode="json", exclude_none=True), f"Registry: artifact {artifact.artifact_id}", wait)

    def write_figure(self, figure: Figure, wait: bool = False) -> None:
        uri = build_registry_figure_uri(figure.figure_id)
        self._write_entry(uri, figure.model_dump(mode="json", exclude_none=True), f"Registry: figure {figure.figure_id}", wait)

    def write_pitfall(self, pitfall: Pitfall, wait: bool = False) -> None:
        uri = build_registry_pitfall_uri(pitfall.pitfall_id)
        self._write_entry(uri, pitfall.model_dump(mode="json", exclude_none=True), f"Registry: pitfall {pitfall.pitfall_id}", wait)

    def write_idea(self, idea: ResearchIdea, wait: bool = False) -> None:
        uri = build_registry_idea_uri(idea.idea_id)
        self._write_entry(uri, idea.model_dump(mode="json", exclude_none=True), f"Registry: idea {idea.idea_id}", wait)

    # --- Reads ---

    def _read_entry(self, uri: str, model_cls: type[T]) -> T | None:
        try:
            raw = self.client.read_resource(uri)
            data = yaml.safe_load(raw)
            return model_cls.model_validate(data)
        except Exception as exc:
            if _is_not_found(exc):
                return None
            raise

    def read_finding(self, finding_id: str) -> Finding | None:
        return self._read_entry(build_registry_finding_uri(finding_id), Finding)

    def read_project(self, project_id: str) -> Project | None:
        return self._read_entry(build_registry_project_uri(project_id), Project)

    def read_hypothesis(self, hypothesis_id: str) -> Hypothesis | None:
        return self._read_entry(build_registry_hypothesis_uri(hypothesis_id), Hypothesis)

    # --- List ---

    def _list_entries(self, uri: str, model_cls: type[T]) -> list[T]:
        entries = self.client.list_resources(uri)
        results = []
        for entry in entries:
            try:
                raw = self.client.read_resource(entry["uri"])
                data = yaml.safe_load(raw)
                results.append(model_cls.model_validate(data))
            except Exception:
                logger.warning("Failed to read registry entry %s", entry.get("uri"))
        return results

    def list_findings(self, project_id: str | None = None) -> list[Finding]:
        findings = self._list_entries(f"{build_registry_uri()}/findings", Finding)
        if project_id:
            findings = [f for f in findings if f.project_id == project_id]
        return findings

    def list_hypotheses(self, status: str | None = None) -> list[Hypothesis]:
        hyps = self._list_entries(f"{build_registry_uri()}/hypotheses", Hypothesis)
        if status:
            hyps = [h for h in hyps if h.status == status]
        return hyps

    def list_projects(self) -> list[Project]:
        return self._list_entries(f"{build_registry_uri()}/projects", Project)

    # --- Batch writes ---

    def batch_write_findings(self, findings: list[Finding], staging_dir: Path) -> None:
        for finding in findings:
            rel_path = f"registry/findings/{finding.finding_id}.yaml"
            content = yaml.safe_dump(finding.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=True)
            write_staged_file(staging_dir, rel_path, content)
        self.client.batch_add(
            path=str(staging_dir),
            to=build_registry_uri(),
            reason="Batch registry ingest",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_registry_store.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add observatory_context/registry/store.py tests/test_registry_store.py
git commit -m "feat: add registry store for OpenViking-backed YAML read/write"
```

---

## Task 4: Wiki Index Generator

**Files:**
- Create: `observatory_context/wiki/__init__.py`
- Create: `observatory_context/wiki/index.py`
- Create: `tests/test_wiki_index.py`

- [ ] **Step 1: Create wiki package init**

```python
"""LLM-optimized wiki compilation layer."""
```

- [ ] **Step 2: Write failing tests**

```python
"""Tests for wiki index generation."""

from observatory_context.wiki.index import WikiEntry, build_index_markdown, parse_index_markdown


def test_build_index_empty():
    result = build_index_markdown([])
    assert "# Observatory Wiki Index" in result
    assert "No entries yet" in result


def test_build_index_with_entries():
    entries = [
        WikiEntry(slug="nitrogen-stress", section="topics", summary="N-stress across 3 organisms", source_count=5, coverage="high"),
        WikiEntry(slug="pseudomonas-putida", section="entities/organisms", summary="Soil bacterium, model organism", source_count=8, coverage="high"),
        WikiEntry(slug="HYP-007", section="hypotheses", summary="Metal cross-resistance", source_count=2, coverage="medium"),
    ]
    result = build_index_markdown(entries)

    assert "## Topics" in result
    assert "nitrogen-stress" in result
    assert "(5 sources, coverage: high)" in result
    assert "## Entities" in result
    assert "pseudomonas-putida" in result
    assert "## Hypotheses" in result
    assert "HYP-007" in result


def test_build_index_sorts_within_sections():
    entries = [
        WikiEntry(slug="zinc", section="topics", summary="Zinc", source_count=3, coverage="medium"),
        WikiEntry(slug="alpha", section="topics", summary="Alpha", source_count=1, coverage="low"),
    ]
    result = build_index_markdown(entries)
    # alpha should come before zinc
    assert result.index("alpha") < result.index("zinc")


def test_parse_index_roundtrip():
    entries = [
        WikiEntry(slug="test-topic", section="topics", summary="A test topic", source_count=3, coverage="high"),
    ]
    md = build_index_markdown(entries)
    parsed = parse_index_markdown(md)
    assert len(parsed) == 1
    assert parsed[0].slug == "test-topic"
    assert parsed[0].source_count == 3
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_wiki_index.py -v`
Expected: ImportError

- [ ] **Step 4: Implement wiki index**

Create `observatory_context/wiki/index.py`:

```python
"""Generate and parse the wiki master index (wiki/index.md)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class WikiEntry:
    """A single entry in the wiki index."""

    slug: str
    section: str  # e.g. "topics", "entities/organisms", "hypotheses"
    summary: str
    source_count: int = 0
    coverage: str = "low"  # low, medium, high


_SECTION_ORDER = [
    "topics",
    "entities/organisms",
    "entities/genes",
    "entities/pathways",
    "entities/methods",
    "entities/concepts",
    "hypotheses",
    "gaps",
    "connections",
]

_SECTION_HEADINGS = {
    "topics": "Topics",
    "entities/organisms": "Entities — Organisms",
    "entities/genes": "Entities — Genes",
    "entities/pathways": "Entities — Pathways",
    "entities/methods": "Entities — Methods",
    "entities/concepts": "Entities — Concepts",
    "hypotheses": "Hypotheses",
    "gaps": "Gaps",
    "connections": "Connections",
}


def build_index_markdown(entries: list[WikiEntry]) -> str:
    """Build the wiki/index.md content from a list of entries."""
    lines = ["# Observatory Wiki Index", ""]

    if not entries:
        lines.append("No entries yet.")
        return "\n".join(lines) + "\n"

    # Group by section
    by_section: dict[str, list[WikiEntry]] = {}
    for entry in entries:
        by_section.setdefault(entry.section, []).append(entry)

    # Render in section order
    for section in _SECTION_ORDER:
        if section not in by_section:
            continue
        heading = _SECTION_HEADINGS.get(section, section.replace("/", " — ").title())
        lines.append(f"## {heading}")
        lines.append("")
        for entry in sorted(by_section[section], key=lambda e: e.slug):
            lines.append(
                f"- [{entry.slug}](wiki/{section}/{entry.slug}.md)"
                f" — {entry.summary}"
                f" ({entry.source_count} sources, coverage: {entry.coverage})"
            )
        lines.append("")

    # Any sections not in _SECTION_ORDER
    for section, section_entries in sorted(by_section.items()):
        if section in _SECTION_ORDER:
            continue
        heading = _SECTION_HEADINGS.get(section, section.replace("/", " — ").title())
        lines.append(f"## {heading}")
        lines.append("")
        for entry in sorted(section_entries, key=lambda e: e.slug):
            lines.append(
                f"- [{entry.slug}](wiki/{section}/{entry.slug}.md)"
                f" — {entry.summary}"
                f" ({entry.source_count} sources, coverage: {entry.coverage})"
            )
        lines.append("")

    return "\n".join(lines)


_INDEX_LINE_RE = re.compile(
    r"^- \[(?P<slug>[^\]]+)\]\(wiki/(?P<section>[^/]+(?:/[^/]+)*)/[^)]+\)"
    r" — (?P<summary>.+?)"
    r" \((?P<count>\d+) sources?, coverage: (?P<coverage>\w+)\)$"
)


def parse_index_markdown(content: str) -> list[WikiEntry]:
    """Parse wiki/index.md back into WikiEntry objects."""
    entries = []
    for line in content.splitlines():
        m = _INDEX_LINE_RE.match(line.strip())
        if m:
            entries.append(
                WikiEntry(
                    slug=m.group("slug"),
                    section=m.group("section"),
                    summary=m.group("summary"),
                    source_count=int(m.group("count")),
                    coverage=m.group("coverage"),
                )
            )
    return entries
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_wiki_index.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add observatory_context/wiki/__init__.py observatory_context/wiki/index.py tests/test_wiki_index.py
git commit -m "feat: add wiki index generator and parser"
```

---

## Task 5: Wiki Page Compiler

**Files:**
- Create: `observatory_context/wiki/compiler.py`
- Create: `tests/test_wiki_compiler.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for wiki page compilation."""

from observatory_context.registry.schema import Finding, Hypothesis, EntityRef, Project
from observatory_context.wiki.compiler import (
    compile_entity_page,
    compile_topic_page,
    compile_hypothesis_page,
)


def test_compile_entity_page_minimal():
    findings = [
        Finding(
            finding_id="F-001",
            project_id="proj-01",
            title="Czc efflux is conserved",
            statement="Found in 44/47 strains",
            confidence="high",
            finding_type="result",
            related_entities=[EntityRef(type="organism", label="Pseudomonas putida")],
        ),
    ]
    result = compile_entity_page(
        entity_type="organism",
        slug="pseudomonas-putida",
        label="Pseudomonas putida",
        findings=findings,
        hypotheses=[],
        project_ids=["proj-01"],
    )
    assert "# Pseudomonas putida" in result
    assert "Czc efflux is conserved" in result
    assert "coverage:" in result
    assert "sources:" in result


def test_compile_entity_page_with_hypothesis():
    findings = [
        Finding(
            finding_id="F-001", project_id="proj-01", title="Test",
            statement="X", confidence="high", finding_type="result",
        ),
    ]
    hypotheses = [
        Hypothesis(
            hypothesis_id="HYP-001", statement="X causes Y",
            status="supported", project_ids=["proj-01"],
        ),
    ]
    result = compile_entity_page(
        entity_type="organism", slug="test-org", label="Test Org",
        findings=findings, hypotheses=hypotheses, project_ids=["proj-01"],
    )
    assert "HYP-001" in result
    assert "supported" in result


def test_compile_topic_page():
    findings = [
        Finding(
            finding_id="F-001", project_id="proj-01", title="Finding A",
            statement="Found X under stress", confidence="high",
            finding_type="result",
        ),
        Finding(
            finding_id="F-002", project_id="proj-02", title="Finding B",
            statement="Also found Y", confidence="moderate",
            finding_type="pattern",
        ),
    ]
    result = compile_topic_page(
        slug="nitrogen-stress",
        title="Nitrogen Stress Responses",
        findings=findings,
        hypotheses=[],
        project_ids=["proj-01", "proj-02"],
    )
    assert "# Nitrogen Stress Responses" in result
    assert "Finding A" in result
    assert "Finding B" in result
    assert "proj-01" in result
    assert "coverage:" in result


def test_compile_hypothesis_page():
    hyp = Hypothesis(
        hypothesis_id="HYP-007",
        statement="Metal cross-resistance via shared regulation",
        status="tested",
        scope="soil Pseudomonas",
        project_ids=["proj-01", "proj-02"],
    )
    findings = [
        Finding(
            finding_id="F-041", project_id="proj-02", title="Shared regulation",
            statement="Cu and Zn stress share regulatory elements",
            confidence="moderate", finding_type="result",
        ),
    ]
    result = compile_hypothesis_page(hypothesis=hyp, supporting_findings=findings)
    assert "# HYP-007" in result
    assert "Metal cross-resistance" in result
    assert "tested" in result
    assert "F-041" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_wiki_compiler.py -v`
Expected: ImportError

- [ ] **Step 3: Implement wiki compiler**

Create `observatory_context/wiki/compiler.py`:

```python
"""Compile wiki pages from registry data.

Each function produces a markdown string with YAML frontmatter suitable
for upload to OpenViking.  The pages are deterministic given the same
input so they can be diffed and only updated when content changes.
"""

from __future__ import annotations

from datetime import date

import yaml

from observatory_context.registry.schema import Finding, Hypothesis


def _coverage_label(source_count: int) -> str:
    if source_count >= 5:
        return "high"
    if source_count >= 2:
        return "medium"
    return "low"


def _frontmatter(metadata: dict) -> str:
    return "---\n" + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + "---\n\n"


def compile_entity_page(
    *,
    entity_type: str,
    slug: str,
    label: str,
    findings: list[Finding],
    hypotheses: list[Hypothesis],
    project_ids: list[str],
) -> str:
    """Compile a wiki entity profile page."""
    source_count = len(set(f.project_id for f in findings))
    coverage = _coverage_label(source_count)
    today = date.today().isoformat()

    meta = {
        "title": label,
        "kind": "entity_profile",
        "entity_type": entity_type,
        "sources": sorted(set(f"corpus/{f.project_id}/REPORT.md" for f in findings)),
        "coverage": coverage,
        "last_compiled": today,
    }

    lines = [_frontmatter(meta), f"# {label}\n"]

    # Summary
    lines.append(f"Entity type: {entity_type}  ")
    lines.append(f"Projects: {', '.join(sorted(set(project_ids)))}  ")
    lines.append(f"[coverage: {coverage}]\n")

    # Findings
    if findings:
        lines.append("## Key Findings\n")
        for f in findings:
            lines.append(
                f"- **{f.title}** — {f.statement} "
                f"({f.project_id}, {f.finding_id}). "
                f"Confidence: {f.confidence}."
            )
        lines.append("")

    # Hypotheses
    if hypotheses:
        lines.append("## Related Hypotheses\n")
        for h in hypotheses:
            lines.append(f"- **{h.hypothesis_id}**: {h.statement} — status: {h.status}")
        lines.append("")

    return "\n".join(lines)


def compile_topic_page(
    *,
    slug: str,
    title: str,
    findings: list[Finding],
    hypotheses: list[Hypothesis],
    project_ids: list[str],
) -> str:
    """Compile a wiki topic synthesis page."""
    source_count = len(set(f.project_id for f in findings))
    coverage = _coverage_label(source_count)
    today = date.today().isoformat()

    meta = {
        "title": title,
        "kind": "topic_synthesis",
        "sources": sorted(set(f"corpus/{f.project_id}/REPORT.md" for f in findings)),
        "coverage": coverage,
        "last_compiled": today,
    }

    lines = [_frontmatter(meta), f"# {title}\n"]

    # Summary
    lines.append(f"Cross-project synthesis across {len(set(project_ids))} projects.  ")
    lines.append(f"[coverage: {coverage}]\n")

    # Findings by project
    if findings:
        lines.append("## Key Findings\n")
        for i, f in enumerate(findings, 1):
            lines.append(
                f"{i}. **{f.title}** — {f.statement} "
                f"({f.project_id}, {f.finding_id}). "
                f"Confidence: {f.confidence}."
            )
        lines.append("")

    # Hypotheses
    if hypotheses:
        lines.append("## Hypotheses\n")
        lines.append("| ID | Statement | Status |")
        lines.append("|---|---|---|")
        for h in hypotheses:
            lines.append(f"| {h.hypothesis_id} | {h.statement} | {h.status} |")
        lines.append("")

    # Open questions placeholder
    lines.append("## Open Questions\n")
    lines.append("_(To be populated by lint operation)_\n")

    return "\n".join(lines)


def compile_hypothesis_page(
    *,
    hypothesis: Hypothesis,
    supporting_findings: list[Finding],
) -> str:
    """Compile a wiki hypothesis tracker page."""
    source_count = len(set(f.project_id for f in supporting_findings))
    coverage = _coverage_label(source_count)
    today = date.today().isoformat()

    meta = {
        "title": f"{hypothesis.hypothesis_id}: {hypothesis.statement[:80]}",
        "kind": "hypothesis_tracker",
        "coverage": coverage,
        "last_compiled": today,
    }

    lines = [_frontmatter(meta), f"# {hypothesis.hypothesis_id}\n"]
    lines.append(f"**Statement:** {hypothesis.statement}\n")
    lines.append(f"**Status:** {hypothesis.status}  ")
    if hypothesis.scope:
        lines.append(f"**Scope:** {hypothesis.scope}  ")
    if hypothesis.project_ids:
        lines.append(f"**Projects:** {', '.join(hypothesis.project_ids)}  ")
    lines.append(f"[coverage: {coverage}]\n")

    if supporting_findings:
        lines.append("## Supporting Evidence\n")
        for f in supporting_findings:
            lines.append(
                f"- **{f.finding_id}**: {f.title} — {f.statement} "
                f"(confidence: {f.confidence}, project: {f.project_id})"
            )
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_wiki_compiler.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add observatory_context/wiki/compiler.py tests/test_wiki_compiler.py
git commit -m "feat: add wiki page compiler for entity, topic, and hypothesis pages"
```

---

## Task 6: Wiki Lint (Gap/Contradiction Detection)

**Files:**
- Create: `observatory_context/wiki/lint.py`
- Create: `tests/test_wiki_lint.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for wiki lint (gap/contradiction/staleness detection)."""

from observatory_context.registry.schema import Finding, Hypothesis, ResearchIdea
from observatory_context.wiki.lint import (
    LintIssue,
    detect_untested_hypotheses,
    detect_orphan_ideas,
    detect_low_coverage_topics,
    build_gap_report,
)


def test_detect_untested_hypotheses():
    hypotheses = [
        Hypothesis(hypothesis_id="H-1", statement="A", status="proposed"),
        Hypothesis(hypothesis_id="H-2", statement="B", status="supported"),
        Hypothesis(hypothesis_id="H-3", statement="C", status="proposed"),
    ]
    issues = detect_untested_hypotheses(hypotheses)
    assert len(issues) == 2
    assert all(i.kind == "untested_hypothesis" for i in issues)
    ids = {i.ref_id for i in issues}
    assert "H-1" in ids
    assert "H-3" in ids


def test_detect_orphan_ideas():
    ideas = [
        ResearchIdea(idea_id="I-1", statement="X", motivation="Y", priority="high", status="proposed", project_ids=[]),
        ResearchIdea(idea_id="I-2", statement="X", motivation="Y", priority="medium", status="proposed", project_ids=["p1"]),
        ResearchIdea(idea_id="I-3", statement="X", motivation="Y", priority="low", status="proposed", project_ids=[]),
    ]
    issues = detect_orphan_ideas(ideas)
    assert len(issues) == 2
    assert {i.ref_id for i in issues} == {"I-1", "I-3"}


def test_detect_low_coverage_topics():
    findings_by_topic = {
        "nitrogen-stress": [
            Finding(finding_id="F-1", project_id="p1", title="A", statement="X", confidence="high", finding_type="result"),
        ],
        "metal-stress": [
            Finding(finding_id="F-2", project_id="p1", title="B", statement="Y", confidence="high", finding_type="result"),
            Finding(finding_id="F-3", project_id="p2", title="C", statement="Z", confidence="moderate", finding_type="result"),
            Finding(finding_id="F-4", project_id="p3", title="D", statement="W", confidence="high", finding_type="result"),
        ],
    }
    issues = detect_low_coverage_topics(findings_by_topic)
    # nitrogen-stress has 1 project → low coverage
    assert len(issues) == 1
    assert issues[0].ref_id == "nitrogen-stress"


def test_build_gap_report():
    issues = [
        LintIssue(kind="untested_hypothesis", ref_id="H-1", message="Hypothesis H-1 is still proposed", severity="medium"),
        LintIssue(kind="orphan_idea", ref_id="I-1", message="Idea I-1 has no project", severity="low"),
    ]
    report = build_gap_report(issues)
    assert "# Gap Analysis" in report
    assert "H-1" in report
    assert "I-1" in report
    assert "untested_hypothesis" in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_wiki_lint.py -v`
Expected: ImportError

- [ ] **Step 3: Implement wiki lint**

Create `observatory_context/wiki/lint.py`:

```python
"""Lint the wiki: detect contradictions, gaps, staleness, orphans."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import yaml

from observatory_context.registry.schema import Finding, Hypothesis, ResearchIdea


@dataclass
class LintIssue:
    """A single lint finding."""

    kind: str  # untested_hypothesis, orphan_idea, low_coverage, contradiction, stale_page
    ref_id: str
    message: str
    severity: str = "medium"  # low, medium, high


def detect_untested_hypotheses(hypotheses: list[Hypothesis]) -> list[LintIssue]:
    """Find hypotheses that are still in 'proposed' status."""
    return [
        LintIssue(
            kind="untested_hypothesis",
            ref_id=h.hypothesis_id,
            message=f"Hypothesis {h.hypothesis_id} is still proposed: {h.statement[:80]}",
            severity="medium",
        )
        for h in hypotheses
        if h.status == "proposed"
    ]


def detect_orphan_ideas(ideas: list[ResearchIdea]) -> list[LintIssue]:
    """Find research ideas with no associated project."""
    return [
        LintIssue(
            kind="orphan_idea",
            ref_id=idea.idea_id,
            message=f"Idea {idea.idea_id} has no associated project: {idea.statement[:80]}",
            severity="low",
        )
        for idea in ideas
        if not idea.project_ids and idea.status == "proposed"
    ]


def detect_low_coverage_topics(
    findings_by_topic: dict[str, list[Finding]],
) -> list[LintIssue]:
    """Find topics with findings from only one project."""
    issues = []
    for topic, findings in findings_by_topic.items():
        project_count = len(set(f.project_id for f in findings))
        if project_count < 2:
            issues.append(
                LintIssue(
                    kind="low_coverage",
                    ref_id=topic,
                    message=f"Topic '{topic}' has findings from only {project_count} project(s)",
                    severity="low",
                )
            )
    return issues


def build_gap_report(issues: list[LintIssue]) -> str:
    """Build the wiki/gaps/latest.md markdown content."""
    today = date.today().isoformat()

    meta = {
        "title": "Gap Analysis",
        "kind": "gap_report",
        "last_compiled": today,
        "issue_count": len(issues),
    }

    lines = [
        "---",
        yaml.safe_dump(meta, sort_keys=False).rstrip(),
        "---",
        "",
        "# Gap Analysis",
        "",
        f"Generated: {today}  ",
        f"Issues found: {len(issues)}",
        "",
    ]

    if not issues:
        lines.append("No gaps detected.")
        return "\n".join(lines) + "\n"

    # Group by kind
    by_kind: dict[str, list[LintIssue]] = {}
    for issue in issues:
        by_kind.setdefault(issue.kind, []).append(issue)

    for kind, kind_issues in sorted(by_kind.items()):
        heading = kind.replace("_", " ").title()
        lines.append(f"## {heading}")
        lines.append("")
        for issue in kind_issues:
            icon = {"high": "!!!", "medium": "!!", "low": "!"}.get(issue.severity, "!")
            lines.append(f"- [{icon}] **{issue.ref_id}**: {issue.message}")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_wiki_lint.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add observatory_context/wiki/lint.py tests/test_wiki_lint.py
git commit -m "feat: add wiki lint for gap, orphan, and coverage detection"
```

---

## Task 7: Batch Upload Orchestration

**Files:**
- Create: `observatory_context/ingest/batch.py`
- Create: `tests/test_ingest_batch.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for batch upload orchestration."""

from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from observatory_context.ingest.batch import BatchUploader


@pytest.fixture()
def mock_client():
    return MagicMock()


@pytest.fixture()
def uploader(mock_client):
    return BatchUploader(client=mock_client)


def test_stage_file(uploader, tmp_path):
    uploader.stage(tmp_path, "wiki/topics/test.md", "# Test\n\nContent")
    staged = tmp_path / "wiki" / "topics" / "test.md"
    assert staged.exists()
    assert staged.read_text() == "# Test\n\nContent"


def test_stage_file_with_metadata(uploader, tmp_path):
    uploader.stage(tmp_path, "registry/findings/F-001.yaml", "content", metadata={"title": "Test"})
    staged = tmp_path / "registry" / "findings" / "F-001.yaml"
    text = staged.read_text()
    assert "---" in text
    assert "title: Test" in text
    assert "content" in text


def test_upload_stages_then_batch_adds(uploader, mock_client, tmp_path):
    # Stage some files
    uploader.stage(tmp_path, "wiki/index.md", "# Index")
    uploader.stage(tmp_path, "wiki/topics/test.md", "# Test")

    target_uri = "viking://resources/observatory"
    uploader.upload(tmp_path, target_uri, reason="test upload")

    mock_client.batch_add.assert_called_once_with(
        path=str(tmp_path), to=target_uri, reason="test upload", wait=False,
    )


def test_upload_and_wait(uploader, mock_client, tmp_path):
    uploader.stage(tmp_path, "test.md", "content")
    uploader.upload(tmp_path, "viking://resources/observatory", reason="test", wait=True)

    mock_client.batch_add.assert_called_once()
    mock_client.wait_until_processed.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ingest_batch.py -v`
Expected: ImportError

- [ ] **Step 3: Implement batch uploader**

Create `observatory_context/ingest/batch.py`:

```python
"""Batch upload orchestration for OpenViking.

Stages files locally into a temp directory tree, then uploads the
entire tree in one ``add_resource()`` call to avoid lock contention.
"""

from __future__ import annotations

import logging
from pathlib import Path

from observatory_context.client import OpenVikingObservatoryClient
from observatory_context.staging import write_staged_file

logger = logging.getLogger(__name__)


class BatchUploader:
    """Stage files locally and upload as a single batch."""

    def __init__(self, client: OpenVikingObservatoryClient) -> None:
        self.client = client

    def stage(
        self,
        staging_dir: Path,
        rel_path: str,
        content: str,
        metadata: dict | None = None,
    ) -> Path:
        """Stage a file for batch upload.

        Parameters
        ----------
        staging_dir
            Root of the local staging area.
        rel_path
            Path relative to staging_dir (determines URI structure).
        content
            File content.
        metadata
            Optional YAML frontmatter metadata.

        Returns
        -------
        Path
            Absolute path to the staged file.
        """
        write_staged_file(staging_dir, rel_path, content, metadata)
        return staging_dir / rel_path

    def upload(
        self,
        staging_dir: Path,
        target_uri: str,
        reason: str,
        wait: bool = False,
        timeout: float | None = None,
    ) -> None:
        """Upload the staging directory to OpenViking as a batch.

        Parameters
        ----------
        staging_dir
            Root of the staging area (uploaded recursively).
        target_uri
            Target Viking URI for the upload.
        reason
            Reason string for the upload.
        wait
            If True, block until processing completes.
        timeout
            Timeout for wait (seconds).
        """
        self.client.batch_add(
            path=str(staging_dir),
            to=target_uri,
            reason=reason,
            wait=False,  # Always upload without inline wait
        )
        if wait:
            self.client.wait_until_processed(timeout=timeout)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ingest_batch.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add observatory_context/ingest/batch.py tests/test_ingest_batch.py
git commit -m "feat: add batch upload orchestration for lock-free OpenViking ingest"
```

---

## Task 8: Ingest Pipeline (4-Phase Orchestrator)

**Files:**
- Create: `observatory_context/ingest/pipeline.py`
- Create: `tests/test_ingest_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for the 4-phase ingest pipeline."""

from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import pytest

from observatory_context.ingest.pipeline import IngestPipeline


@pytest.fixture()
def mock_client():
    client = MagicMock()
    client.resource_exists.return_value = False
    return client


@pytest.fixture()
def pipeline(mock_client, tmp_path):
    return IngestPipeline(
        client=mock_client,
        repo_root=tmp_path,
        staging_root=tmp_path / "_staging",
    )


def test_pipeline_creates_staging_dirs(pipeline):
    assert pipeline.staging_root is not None


def test_phase1_builds_corpus_manifest(pipeline, mock_client, tmp_path):
    # Create a minimal project structure
    proj_dir = tmp_path / "projects" / "test-proj"
    proj_dir.mkdir(parents=True)
    (proj_dir / "README.md").write_text("---\ntitle: Test\n---\n# Test Project\n")

    manifest = pipeline.build_corpus_manifest(project_ids=["test-proj"])
    assert len(manifest) >= 1
    assert any(item.kind == "project" or "README" in item.source_path for item in manifest)


def test_phase4_generates_log_entry(pipeline):
    entry = pipeline.build_log_entry(
        action="ingest",
        project_ids=["test-proj"],
        phase_results={"corpus": 5, "registry": 10, "wiki": 3},
    )
    assert "ingest" in entry
    assert "test-proj" in entry
    assert "corpus: 5" in entry
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ingest_pipeline.py -v`
Expected: ImportError

- [ ] **Step 3: Implement ingest pipeline**

Create `observatory_context/ingest/pipeline.py`:

```python
"""Four-phase ingest pipeline for the observatory wiki.

Phase 1: Upload source corpus (project documents)
Phase 2: Extract structured registry entries via CBORG
Phase 3: Compile wiki pages from registry data
Phase 4: Update wiki index and activity log
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp

from observatory_context.client import OpenVikingObservatoryClient
from observatory_context.ingest.batch import BatchUploader
from observatory_context.ingest.manifest import ResourceManifestItem, build_resource_manifest
from observatory_context.uris import build_corpus_uri, build_observatory_root_uri

logger = logging.getLogger(__name__)


class IngestPipeline:
    """Orchestrate the 4-phase ingest pipeline."""

    def __init__(
        self,
        client: OpenVikingObservatoryClient,
        repo_root: Path,
        staging_root: Path | None = None,
    ) -> None:
        self.client = client
        self.repo_root = repo_root
        self.staging_root = staging_root or Path(mkdtemp(prefix="observatory-ingest-"))
        self.uploader = BatchUploader(client)

    def build_corpus_manifest(
        self, project_ids: list[str] | None = None,
    ) -> list[ResourceManifestItem]:
        """Build manifest of source documents to upload."""
        return build_resource_manifest(self.repo_root, project_ids=project_ids)

    def phase1_upload_corpus(
        self,
        manifest: list[ResourceManifestItem],
        resume: bool = True,
    ) -> int:
        """Phase 1: Upload source documents to corpus/ namespace.

        Returns the number of resources staged.
        """
        staging = self.staging_root / "corpus"
        staging.mkdir(parents=True, exist_ok=True)
        count = 0

        for item in manifest:
            corpus_uri = build_corpus_uri(
                item.project_ids[0] if item.project_ids else "shared",
                Path(item.source_path).name,
            )
            if resume and self.client.resource_exists(corpus_uri):
                continue

            source = Path(item.source_path)
            if source.exists():
                content = source.read_text(encoding="utf-8")
                self.uploader.stage(
                    staging,
                    f"{item.project_ids[0] if item.project_ids else 'shared'}/{source.name}",
                    content,
                    metadata=item.metadata,
                )
                count += 1

        if count > 0:
            target = f"{build_observatory_root_uri()}/corpus"
            self.uploader.upload(staging, target, reason="Phase 1: corpus upload")
            logger.info("Phase 1: staged %d corpus resources", count)

        return count

    def phase4_update_index_and_log(
        self,
        project_ids: list[str],
        phase_results: dict[str, int],
    ) -> None:
        """Phase 4: Update wiki/index.md and wiki/log.md."""
        # Log entry
        log_entry = self.build_log_entry("ingest", project_ids, phase_results)
        # For now, we append to the log via add_text_resource
        from observatory_context.uris import build_wiki_log_uri

        try:
            existing_log = self.client.read_resource(build_wiki_log_uri())
        except Exception:
            existing_log = "# Observatory Activity Log\n\n"

        updated_log = existing_log.rstrip() + "\n\n" + log_entry + "\n"
        self.client.add_text_resource(
            uri=build_wiki_log_uri(),
            content=updated_log,
            metadata={},
            reason="Phase 4: update activity log",
            wait=False,
        )
        logger.info("Phase 4: updated wiki log")

    def build_log_entry(
        self,
        action: str,
        project_ids: list[str],
        phase_results: dict[str, int],
    ) -> str:
        """Build a single log entry string."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        projects_str = ", ".join(project_ids) if project_ids else "all"
        results_str = ", ".join(f"{k}: {v}" for k, v in sorted(phase_results.items()))
        return f"## {now} — {action}\n\nProjects: {projects_str}  \nResults: {results_str}"

    def run(
        self,
        project_ids: list[str] | None = None,
        resume: bool = True,
    ) -> dict[str, int]:
        """Run the full 4-phase pipeline.

        Parameters
        ----------
        project_ids
            Specific projects to ingest. None = all.
        resume
            Skip existing resources.

        Returns
        -------
        dict
            Phase results: {phase_name: count}.
        """
        manifest = self.build_corpus_manifest(project_ids)
        results: dict[str, int] = {}

        # Phase 1
        results["corpus"] = self.phase1_upload_corpus(manifest, resume=resume)
        self.client.wait_until_processed()

        # Phase 2 + 3 will be added in future tasks (require CBORG + wiki compiler integration)
        results["registry"] = 0
        results["wiki"] = 0

        # Phase 4
        all_project_ids = sorted(set(
            pid for item in manifest for pid in item.project_ids
        ))
        self.phase4_update_index_and_log(all_project_ids, results)

        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ingest_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add observatory_context/ingest/pipeline.py tests/test_ingest_pipeline.py
git commit -m "feat: add 4-phase ingest pipeline with corpus upload and log"
```

---

## Task 9: Client Modernization

**Files:**
- Modify: `observatory_context/client.py`
- Modify: `scripts/viking_setup.py`

- [ ] **Step 1: Add write_content method to client**

Add to `observatory_context/client.py` after `add_text_resource`:

```python
    def write_content(self, uri: str, content: str) -> None:
        """Write content directly to a URI without temp files.

        Uses the OpenViking filesystem write API when available,
        falling back to add_text_resource with a temp file.
        """
        if hasattr(self.client, 'write'):
            self.client.write(uri, content.encode("utf-8"))
        else:
            # Fallback for older OpenViking versions
            self.add_text_resource(
                uri=uri, content=content, metadata={},
                reason="Direct content write", wait=False,
            )
```

- [ ] **Step 2: Add rerank section to viking_setup.py config generation**

In `scripts/viking_setup.py`, add after the `vlm` section in the config dict:

```python
        # Add rerank configuration if available
        config["rerank"] = {
            "provider": provider,
            "api_key": api_key,
            "model": os.environ.get("OPENVIKING_RERANK_MODEL", "gpt-4o-mini"),
        }
```

- [ ] **Step 3: Run existing tests to verify nothing is broken**

Run: `uv run pytest tests/ -v`
Expected: All existing tests still PASS

- [ ] **Step 4: Commit**

```bash
git add observatory_context/client.py scripts/viking_setup.py
git commit -m "feat: add write_content method and rerank config to OpenViking setup"
```

---

## Task 10: Update Models and Runtime

**Files:**
- Modify: `observatory_context/models.py`
- Modify: `observatory_context/runtime.py`

- [ ] **Step 1: Add wiki and registry scopes to models**

In `observatory_context/models.py`, update the `Scope` enum:

```python
class Scope(StrEnum):
    """Retrieval scope for context queries."""

    all = "all"
    resources = "resources"
    memory = "memory"
    graph = "graph"
    wiki = "wiki"
    registry = "registry"
    corpus = "corpus"
```

- [ ] **Step 2: Update runtime.py to expose new modules**

In `observatory_context/runtime.py`, add builder functions:

```python
def build_registry_store(
    client: OpenVikingObservatoryClient | None = None,
) -> "RegistryStore":
    """Build a RegistryStore instance."""
    from observatory_context.registry.store import RegistryStore

    if client is None:
        settings = ObservatoryContextSettings()
        client = build_client(settings)
    return RegistryStore(client=client)


def build_ingest_pipeline(
    repo_root: Path | None = None,
    client: OpenVikingObservatoryClient | None = None,
) -> "IngestPipeline":
    """Build an IngestPipeline instance."""
    from observatory_context.ingest.pipeline import IngestPipeline

    if client is None:
        settings = ObservatoryContextSettings()
        client = build_client(settings)
    if repo_root is None:
        repo_root = Path.cwd()
    return IngestPipeline(client=client, repo_root=repo_root)
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add observatory_context/models.py observatory_context/runtime.py
git commit -m "feat: add wiki/registry scopes and runtime builders for new modules"
```

---

## Task 11: Integration Test — End-to-End Wiki Generation

**Files:**
- Create: `tests/test_integration_wiki.py`

- [ ] **Step 1: Write integration test**

```python
"""Integration test: registry → wiki compilation → index generation."""

from observatory_context.registry.schema import (
    EntityRef, Finding, Hypothesis, Project,
)
from observatory_context.wiki.compiler import (
    compile_entity_page,
    compile_hypothesis_page,
    compile_topic_page,
)
from observatory_context.wiki.index import WikiEntry, build_index_markdown
from observatory_context.wiki.lint import (
    detect_untested_hypotheses,
    detect_low_coverage_topics,
    build_gap_report,
)


def test_full_wiki_generation_flow():
    """End-to-end: create registry entries → compile wiki pages → generate index → lint."""

    # 1. Create registry entries
    project = Project(
        project_id="metal-stress-eco",
        title="Metal stress ecotype analysis",
        status="complete",
        research_question="Do metal stress genes define ecotypes?",
        organisms=["Pseudomonas putida"],
        tags=["metal-stress", "pangenome"],
    )

    findings = [
        Finding(
            finding_id="F-023",
            project_id="metal-stress-eco",
            title="Czc efflux conserved",
            statement="44/47 strains carry czc operon",
            confidence="high",
            finding_type="result",
            related_entities=[
                EntityRef(type="organism", label="Pseudomonas putida"),
                EntityRef(type="pathway", label="czc efflux"),
            ],
        ),
    ]

    hypotheses = [
        Hypothesis(
            hypothesis_id="HYP-007",
            statement="Metal cross-resistance via shared regulation",
            status="proposed",
            project_ids=["metal-stress-eco"],
        ),
    ]

    # 2. Compile wiki pages
    entity_page = compile_entity_page(
        entity_type="organism",
        slug="pseudomonas-putida",
        label="Pseudomonas putida",
        findings=findings,
        hypotheses=hypotheses,
        project_ids=["metal-stress-eco"],
    )
    assert "Pseudomonas putida" in entity_page
    assert "F-023" in entity_page

    topic_page = compile_topic_page(
        slug="metal-stress",
        title="Metal Stress Responses",
        findings=findings,
        hypotheses=hypotheses,
        project_ids=["metal-stress-eco"],
    )
    assert "Metal Stress Responses" in topic_page

    hyp_page = compile_hypothesis_page(
        hypothesis=hypotheses[0],
        supporting_findings=findings,
    )
    assert "HYP-007" in hyp_page

    # 3. Generate index
    entries = [
        WikiEntry(slug="metal-stress", section="topics", summary="Metal stress across organisms", source_count=1, coverage="low"),
        WikiEntry(slug="pseudomonas-putida", section="entities/organisms", summary="Soil model organism", source_count=1, coverage="low"),
        WikiEntry(slug="HYP-007", section="hypotheses", summary="Metal cross-resistance", source_count=1, coverage="low"),
    ]
    index_md = build_index_markdown(entries)
    assert "metal-stress" in index_md
    assert "pseudomonas-putida" in index_md

    # 4. Run lint
    untested = detect_untested_hypotheses(hypotheses)
    assert len(untested) == 1  # HYP-007 is proposed

    low_coverage = detect_low_coverage_topics({"metal-stress": findings})
    assert len(low_coverage) == 1  # Only 1 project

    gap_report = build_gap_report(untested + low_coverage)
    assert "HYP-007" in gap_report
    assert "metal-stress" in gap_report
```

- [ ] **Step 2: Run integration test**

Run: `uv run pytest tests/test_integration_wiki.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_wiki.py
git commit -m "test: add end-to-end integration test for wiki generation flow"
```

---

## Task 12: Registry Extract (CBORG → Registry Entries)

**Files:**
- Create: `observatory_context/registry/extract.py`
- Create: `tests/test_registry_extract.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for CBORG extraction → registry entry conversion."""

from observatory_context.extraction import EntityExtraction, Entity, Relation, HypothesisUpdate, TimelineEvent
from observatory_context.registry.extract import extraction_to_registry_entries
from observatory_context.registry.schema import Finding, Hypothesis, Evidence


def test_extraction_to_registry_entries():
    extraction = EntityExtraction(
        entities=[
            Entity(type="organism", id="pseudomonas-putida", name="Pseudomonas putida", metadata={}),
            Entity(type="pathway", id="czc-efflux", name="czc efflux system", metadata={}),
        ],
        relations=[
            Relation(
                subject="organisms/pseudomonas-putida",
                predicate="has_pathway",
                object="pathways/czc-efflux",
                evidence="Found in 44/47 strains",
                confidence="high",
            ),
        ],
        hypotheses=[
            HypothesisUpdate(
                id="HYP-007",
                status="tested",
                claim="Metal cross-resistance via shared regulation",
                evidence_delta="Cu and Zn share regulatory elements",
            ),
        ],
        timeline_events=[
            TimelineEvent(
                date="2026-03-15",
                event="Completed pangenome analysis",
                type="milestone",
                project="metal-stress-eco",
            ),
        ],
    )

    entries = extraction_to_registry_entries(extraction, project_id="metal-stress-eco")

    # Should produce findings from relations
    assert any(isinstance(e, Finding) for e in entries)
    # Should produce hypotheses
    assert any(isinstance(e, Hypothesis) for e in entries)

    findings = [e for e in entries if isinstance(e, Finding)]
    assert len(findings) >= 1
    assert findings[0].project_id == "metal-stress-eco"

    hyps = [e for e in entries if isinstance(e, Hypothesis)]
    assert len(hyps) == 1
    assert hyps[0].status == "tested"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_registry_extract.py -v`
Expected: ImportError

- [ ] **Step 3: Implement extraction converter**

Create `observatory_context/registry/extract.py`:

```python
"""Convert CBORG EntityExtraction results to registry entries."""

from __future__ import annotations

from observatory_context._text import slugify
from observatory_context.extraction import EntityExtraction
from observatory_context.registry.schema import (
    EntityRef,
    Finding,
    Hypothesis,
)


def extraction_to_registry_entries(
    extraction: EntityExtraction,
    project_id: str,
) -> list[Finding | Hypothesis]:
    """Convert a CBORG extraction into typed registry entries.

    Each relation becomes a Finding. Each hypothesis update becomes
    a Hypothesis entry.
    """
    entries: list[Finding | Hypothesis] = []

    # Build entity lookup for EntityRef generation
    entity_lookup: dict[str, EntityRef] = {}
    for entity in extraction.entities:
        entity_lookup[f"{entity.type}s/{entity.id}"] = EntityRef(
            type=entity.type,
            label=entity.name,
        )
        # Also index without plural
        entity_lookup[entity.id] = EntityRef(
            type=entity.type,
            label=entity.name,
        )

    # Relations → Findings
    for i, rel in enumerate(extraction.relations):
        finding_id = f"F-{project_id}-{i:03d}"
        related = []
        for ref_key in [rel.subject, rel.object]:
            if ref_key in entity_lookup:
                related.append(entity_lookup[ref_key])

        entries.append(
            Finding(
                finding_id=finding_id,
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
                status=_map_status(hyp.status),
                project_ids=[project_id],
                source_ref=f"corpus/{project_id}/REPORT.md",
            )
        )

    return entries


def _map_status(raw: str) -> str:
    """Map extraction status to registry hypothesis status."""
    mapping = {
        "open": "proposed",
        "proposed": "proposed",
        "testing": "tested",
        "tested": "tested",
        "supported": "supported",
        "refuted": "not_supported",
        "updated": "mixed",
    }
    return mapping.get(raw.lower(), "proposed")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_registry_extract.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add observatory_context/registry/extract.py tests/test_registry_extract.py
git commit -m "feat: add CBORG extraction → registry entry converter"
```

---

## Task 13: Final — Run Full Suite, Update Exports, Clean Up

**Files:**
- Modify: `observatory_context/__init__.py`
- Modify: `observatory_context/registry/__init__.py`
- Modify: `observatory_context/wiki/__init__.py`

- [ ] **Step 1: Update package exports**

Update `observatory_context/registry/__init__.py`:

```python
"""Structured knowledge registry backed by OpenViking."""

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
from observatory_context.registry.store import RegistryStore

__all__ = [
    "Artifact",
    "EntityRef",
    "Evidence",
    "Figure",
    "Finding",
    "Hypothesis",
    "Pitfall",
    "Project",
    "RegistryStore",
    "ResearchIdea",
]
```

Update `observatory_context/wiki/__init__.py`:

```python
"""LLM-optimized wiki compilation layer."""

from observatory_context.wiki.compiler import (
    compile_entity_page,
    compile_hypothesis_page,
    compile_topic_page,
)
from observatory_context.wiki.index import WikiEntry, build_index_markdown, parse_index_markdown
from observatory_context.wiki.lint import LintIssue, build_gap_report

__all__ = [
    "LintIssue",
    "WikiEntry",
    "build_gap_report",
    "build_index_markdown",
    "compile_entity_page",
    "compile_hypothesis_page",
    "compile_topic_page",
    "parse_index_markdown",
]
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Run ruff lint**

Run: `uv run ruff check observatory_context/ tests/`
Expected: No errors (or only pre-existing ones)

- [ ] **Step 4: Commit**

```bash
git add observatory_context/registry/__init__.py observatory_context/wiki/__init__.py
git commit -m "chore: update package exports for registry and wiki subpackages"
```
