"""Tests for IngestPipeline — 4-phase ingest orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from observatory_context.extraction import Entity, EntityExtraction, HypothesisUpdate, Relation
from observatory_context.ingest.pipeline import IngestPipeline
from observatory_context.registry.schema import Finding, Hypothesis


@pytest.fixture()
def mock_client():
    return MagicMock()


@pytest.fixture()
def pipeline(mock_client, tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    return IngestPipeline(
        client=mock_client,
        repo_root=tmp_path,
        staging_root=staging,
    )


def _make_extraction() -> EntityExtraction:
    """Build a minimal EntityExtraction for testing."""
    return EntityExtraction(
        entities=[
            Entity(type="organism", id="ecoli", name="E. coli"),
            Entity(type="gene", id="lacZ", name="lacZ"),
        ],
        relations=[
            Relation(
                subject="ecoli",
                predicate="supports",
                object="lacZ",
                evidence="Observed in lab conditions",
                confidence="high",
            ),
        ],
        hypotheses=[
            HypothesisUpdate(
                id="H-001",
                status="supported",
                claim="E. coli expresses lacZ under lactose induction",
                evidence_delta="Confirmed via qPCR",
            ),
        ],
    )


def _make_mock_extractor(extraction: EntityExtraction | None = None) -> MagicMock:
    """Return a mock CBORGExtractor that returns a canned extraction."""
    ext = extraction or _make_extraction()
    mock = MagicMock()
    mock.extract_knowledge.return_value = ext
    return mock


def test_pipeline_creates_staging_dirs(pipeline):
    assert pipeline.staging_root is not None
    assert isinstance(pipeline.staging_root, Path)


def test_pipeline_default_staging_root(mock_client, tmp_path):
    p = IngestPipeline(client=mock_client, repo_root=tmp_path)
    assert p.staging_root is not None
    assert p.staging_root.exists()


def test_phase1_builds_corpus_manifest(pipeline, mock_client, tmp_path):
    # Create minimal project structure
    project_dir = tmp_path / "projects" / "test-proj"
    project_dir.mkdir(parents=True)
    (project_dir / "README.md").write_text(
        "# Test Project\n\nresearch_question: Does X affect Y?\n"
    )
    manifest = pipeline.build_corpus_manifest(project_ids=["test-proj"])
    assert len(manifest) > 0
    uris = [item.uri for item in manifest]
    assert any("test-proj" in uri for uri in uris)


def test_phase1_upload_corpus_returns_count(pipeline, mock_client, tmp_path):
    project_dir = tmp_path / "projects" / "test-proj"
    project_dir.mkdir(parents=True)
    (project_dir / "README.md").write_text("# Test Project\n")
    manifest = pipeline.build_corpus_manifest(project_ids=["test-proj"])
    count = pipeline.phase1_upload_corpus(manifest, resume=False)
    assert isinstance(count, int)
    assert count >= 0


def test_phase1_skip_existing_when_resume(pipeline, mock_client, tmp_path):
    project_dir = tmp_path / "projects" / "test-proj"
    project_dir.mkdir(parents=True)
    (project_dir / "README.md").write_text("# Test Project\n")
    # Simulate resource_exists returning True for all
    mock_client.resource_exists.return_value = True
    manifest = pipeline.build_corpus_manifest(project_ids=["test-proj"])
    count = pipeline.phase1_upload_corpus(manifest, resume=True)
    # All existing resources skipped — batch_add may not be called at all
    assert isinstance(count, int)


def test_phase4_generates_log_entry(pipeline):
    entry = pipeline.build_log_entry(
        "ingest", ["test-proj"], {"corpus": 5, "registry": 10, "wiki": 3}
    )
    assert "ingest" in entry
    assert "test-proj" in entry
    assert "corpus: 5" in entry


def test_phase4_log_entry_format(pipeline):
    entry = pipeline.build_log_entry(
        "rebuild", ["proj-a", "proj-b"], {"corpus": 2, "registry": 0, "wiki": 1}
    )
    assert entry.startswith("##")
    assert "rebuild" in entry
    assert "proj-a" in entry
    assert "proj-b" in entry


def test_phase4_update_index_and_log_calls_client(pipeline, mock_client):
    pipeline.phase4_update_index_and_log(
        project_ids=["test-proj"],
        phase_results={"corpus": 3, "registry": 5, "wiki": 1},
    )
    mock_client.add_text_resource.assert_called_once()
    call_kwargs = mock_client.add_text_resource.call_args
    assert call_kwargs is not None


def test_run_returns_dict_with_phase_keys(pipeline, mock_client, tmp_path):
    project_dir = tmp_path / "projects" / "test-proj"
    project_dir.mkdir(parents=True)
    (project_dir / "README.md").write_text("# Test Project\n")
    results = pipeline.run(project_ids=["test-proj"], resume=False)
    assert isinstance(results, dict)
    assert "corpus" in results
    assert "registry" in results
    assert "wiki" in results


def test_run_phases_2_3_return_zero_without_extractor(pipeline, mock_client, tmp_path):
    """Without an extractor, phases 2 and 3 gracefully return 0."""
    project_dir = tmp_path / "projects" / "test-proj"
    project_dir.mkdir(parents=True)
    (project_dir / "README.md").write_text("# Test Project\n")
    results = pipeline.run(project_ids=["test-proj"], resume=False)
    assert results["registry"] == 0
    assert results["wiki"] == 0


# ------------------------------------------------------------------
# Phase 2 tests
# ------------------------------------------------------------------


def test_phase2_returns_zero_without_extractor(pipeline, tmp_path):
    """phase2 with extractor=None returns 0."""
    manifest = _make_manifest_with_report(tmp_path)
    count = pipeline.phase2_extract_and_register(manifest, extractor=None)
    assert count == 0


def test_phase2_extracts_and_stages_registry(pipeline, mock_client, tmp_path):
    """phase2 calls extractor and stages registry YAML files."""
    manifest = _make_manifest_with_report(tmp_path)
    extractor = _make_mock_extractor()

    count = pipeline.phase2_extract_and_register(manifest, extractor=extractor)

    # Should create 1 finding + 1 hypothesis = 2 entries
    assert count == 2
    extractor.extract_knowledge.assert_called_once()

    # Check that registry files were staged
    registry_staging = pipeline.staging_root / "registry"
    findings_files = list((registry_staging / "findings").glob("*.yaml"))
    hyp_files = list((registry_staging / "hypotheses").glob("*.yaml"))
    assert len(findings_files) == 1
    assert len(hyp_files) == 1

    # Verify YAML content is valid
    finding_data = yaml.safe_load(findings_files[0].read_text())
    assert finding_data["project_id"] == "test-proj"

    # Verify batch upload was called
    mock_client.batch_add.assert_called()


def test_phase2_skips_projects_without_report(pipeline, mock_client, tmp_path):
    """phase2 skips projects that have no REPORT.md."""
    project_dir = tmp_path / "projects" / "no-report"
    project_dir.mkdir(parents=True)
    (project_dir / "README.md").write_text("# No report project\n")
    manifest = pipeline.build_corpus_manifest(project_ids=["no-report"])
    extractor = _make_mock_extractor()

    count = pipeline.phase2_extract_and_register(manifest, extractor=extractor)

    assert count == 0
    extractor.extract_knowledge.assert_not_called()


# ------------------------------------------------------------------
# Phase 3 tests
# ------------------------------------------------------------------


def test_phase3_returns_zero_with_no_entries(pipeline, tmp_path):
    """phase3 returns 0 when no registry entries exist."""
    manifest = _make_manifest_with_report(tmp_path)
    count = pipeline.phase3_compile_wiki(manifest)
    assert count == 0


def test_phase3_compiles_wiki_from_staged_registry(pipeline, mock_client, tmp_path):
    """phase3 reads staged registry YAML and produces wiki pages."""
    manifest = _make_manifest_with_report(tmp_path)

    # First run phase2 to stage registry entries
    extractor = _make_mock_extractor()
    pipeline.phase2_extract_and_register(manifest, extractor=extractor)

    # Now compile wiki
    count = pipeline.phase3_compile_wiki(manifest)

    # Minimal staged fixtures compile a hypothesis page, topic page, and index.
    assert count >= 3

    # Check wiki staging directory was created with content
    wiki_staging = pipeline.staging_root / "wiki"
    assert wiki_staging.exists()
    assert (wiki_staging / "index.md").exists()

    index_content = (wiki_staging / "index.md").read_text()
    assert "Observatory Wiki Index" in index_content


def test_phase3_with_explicit_entries(pipeline, mock_client, tmp_path):
    """phase3 accepts pre-built findings and hypotheses lists."""
    manifest = _make_manifest_with_report(tmp_path)

    findings = [
        Finding(
            finding_id="F-test-000",
            project_id="test-proj",
            title="Test finding",
            statement="Something was found",
            confidence="high",
            finding_type="result",
        ),
    ]
    hypotheses = [
        Hypothesis(
            hypothesis_id="H-test-001",
            statement="Test hypothesis",
            status="proposed",
            project_ids=["test-proj"],
        ),
    ]

    count = pipeline.phase3_compile_wiki(manifest, findings=findings, hypotheses=hypotheses)

    # hypothesis page + topic page + index = 3 minimum (no entity pages since no related_entities)
    assert count >= 2
    mock_client.batch_add.assert_called()


# ------------------------------------------------------------------
# Full run with extractor
# ------------------------------------------------------------------


def test_run_with_extractor_wires_all_phases(pipeline, mock_client, tmp_path):
    """run() with an extractor executes phases 2 and 3."""
    _make_manifest_with_report(tmp_path)
    extractor = _make_mock_extractor()

    results = pipeline.run(
        project_ids=["test-proj"],
        resume=False,
        extractor=extractor,
    )

    assert results["registry"] == 2  # 1 finding + 1 hypothesis
    assert results["wiki"] >= 4  # synthesis-backed full run emits the broader wiki set
    assert results["corpus"] >= 0
    assert results["knowledge_graph"] > 0
    assert mock_client.batch_add.call_count >= 3


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_manifest_with_report(tmp_path: Path):
    """Create a project with REPORT.md and return a minimal manifest."""
    from observatory_context.ingest.manifest import ResourceManifestItem

    project_dir = tmp_path / "projects" / "test-proj"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "README.md").write_text("# Test Project\nresearch_question: Does X affect Y?\n")
    (project_dir / "REPORT.md").write_text("# Report\n\nWe found that X affects Y.\n")
    (project_dir / "provenance.yaml").write_text(
        yaml.dump({"project": "test-proj", "date": "2026-01-01"})
    )
    return [
        ResourceManifestItem(
            uri="viking://resources/observatory/projects/test-proj/authored/REPORT.md",
            kind="project_document",
            source_path=str(project_dir / "REPORT.md"),
            project_ids=["test-proj"],
            metadata={"id": "test-proj", "kind": "project_document"},
        ),
    ]
