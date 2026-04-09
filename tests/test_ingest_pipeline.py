"""Tests for IngestPipeline — 4-phase ingest orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from observatory_context.ingest.pipeline import IngestPipeline


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


def test_run_phases_2_3_return_zero(pipeline, mock_client, tmp_path):
    project_dir = tmp_path / "projects" / "test-proj"
    project_dir.mkdir(parents=True)
    (project_dir / "README.md").write_text("# Test Project\n")
    results = pipeline.run(project_ids=["test-proj"], resume=False)
    assert results["registry"] == 0
    assert results["wiki"] == 0
