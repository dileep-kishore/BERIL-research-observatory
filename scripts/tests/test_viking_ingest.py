"""Tests for the OpenViking ingest script."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from observatory_context.ingest.manifest import ResourceManifestItem


def _manifest_item(tmp_path: Path, name: str) -> ResourceManifestItem:
    source_path = tmp_path / name
    source_path.write_text(f"# {name}\n", encoding="utf-8")
    return ResourceManifestItem(
        uri=f"viking://resources/observatory/projects/{name}/authored/README.md",
        kind="project",
        source_path=str(source_path),
        project_ids=[name],
        metadata={"id": name, "kind": "project"},
    )


def test_ingest_skips_existing_resources_by_default(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from scripts import viking_ingest

    existing = _manifest_item(tmp_path, "existing")
    missing = _manifest_item(tmp_path, "missing")
    run_calls: list[dict] = []

    class FakePipeline:
        def __init__(self, client, repo_root):
            self.client = client
            self.repo_root = repo_root

        def run(self, project_ids=None, resume=True, extractor=None):
            run_calls.append(
                {"project_ids": project_ids, "resume": resume, "extractor": extractor}
            )
            return {"corpus": 1, "registry": 0, "graph": 0, "knowledge_graph": 0, "wiki": 0}

    monkeypatch.setattr(
        viking_ingest,
        "build_resource_manifest",
        lambda repo_root, project_ids=None: [existing, missing],
    )
    monkeypatch.setattr(viking_ingest, "OpenVikingObservatoryClient", lambda settings: SimpleNamespace())
    monkeypatch.setattr(viking_ingest, "ObservatoryContextSettings", lambda: SimpleNamespace(cborg_api_key=None))
    monkeypatch.setattr(
        viking_ingest,
        "build_resource_manifest",
        lambda repo_root, project_ids=None: [existing, missing],
    )
    import observatory_context.ingest.pipeline as pipeline_module
    monkeypatch.setattr(pipeline_module, "IngestPipeline", FakePipeline)

    assert viking_ingest.main([]) == 0

    assert run_calls == [{"project_ids": None, "resume": True, "extractor": None}]
    output = capsys.readouterr().out
    assert "Done!" in output


def test_ingest_handles_wait_timeout_gracefully(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from scripts import viking_ingest

    item = _manifest_item(tmp_path, "alpha")
    wait_calls: list[float | None] = []

    class FakePipeline:
        def __init__(self, client, repo_root):
            self.client = client
            self.repo_root = repo_root

        def run(self, project_ids=None, resume=True, extractor=None):
            return {"corpus": 1, "registry": 0, "graph": 0, "knowledge_graph": 0, "wiki": 0}

    class FakeClient:
        def wait_until_processed(self, timeout: float | None = None) -> None:
            wait_calls.append(timeout)
            raise TimeoutError("Timed out waiting for OpenViking to confirm processing. Resources were queued — processing may still be in progress.")

    monkeypatch.setattr(
        viking_ingest,
        "build_resource_manifest",
        lambda repo_root, project_ids=None: [item],
    )
    monkeypatch.setattr(viking_ingest, "OpenVikingObservatoryClient", lambda settings: FakeClient())
    monkeypatch.setattr(viking_ingest, "ObservatoryContextSettings", lambda: SimpleNamespace(cborg_api_key=None))
    import observatory_context.ingest.pipeline as pipeline_module
    monkeypatch.setattr(pipeline_module, "IngestPipeline", FakePipeline)

    assert viking_ingest.main(["--wait"]) == 0

    output = capsys.readouterr().out
    assert "Warning:" in output
    assert "processing may still be in progress" in output
    assert wait_calls == [None]


def test_ingest_waits_once_after_queueing_when_requested(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from scripts import viking_ingest

    item = _manifest_item(tmp_path, "alpha")
    wait_calls: list[float | None] = []

    class FakePipeline:
        def __init__(self, client, repo_root):
            self.client = client
            self.repo_root = repo_root

        def run(self, project_ids=None, resume=True, extractor=None):
            return {"corpus": 1, "registry": 0, "graph": 0, "knowledge_graph": 0, "wiki": 0}

    class FakeClient:
        def wait_until_processed(self, timeout: float | None = None) -> None:
            wait_calls.append(timeout)

    monkeypatch.setattr(
        viking_ingest,
        "build_resource_manifest",
        lambda repo_root, project_ids=None: [item],
    )
    monkeypatch.setattr(viking_ingest, "OpenVikingObservatoryClient", lambda settings: FakeClient())
    monkeypatch.setattr(viking_ingest, "ObservatoryContextSettings", lambda: SimpleNamespace(cborg_api_key=None))
    import observatory_context.ingest.pipeline as pipeline_module
    monkeypatch.setattr(pipeline_module, "IngestPipeline", FakePipeline)

    assert viking_ingest.main(["--wait", "--wait-timeout", "900"]) == 0

    assert wait_calls == [900.0]
    output = capsys.readouterr().out
    assert "All resources processed." in output


def test_ingest_can_limit_to_specific_project_ids(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from scripts import viking_ingest

    alpha = _manifest_item(tmp_path, "alpha_proj")
    beta = _manifest_item(tmp_path, "beta_proj")
    run_calls: list[dict] = []

    class FakePipeline:
        def __init__(self, client, repo_root):
            self.client = client
            self.repo_root = repo_root

        def run(self, project_ids=None, resume=True, extractor=None):
            run_calls.append(
                {"project_ids": project_ids, "resume": resume, "extractor": extractor}
            )
            return {"corpus": 1, "registry": 0, "graph": 0, "knowledge_graph": 0, "wiki": 0}

    def fake_manifest(repo_root, project_ids=None):
        items = [alpha, beta]
        if project_ids:
            items = [item for item in items if project_ids.intersection(set(item.project_ids))]
        return items

    monkeypatch.setattr(viking_ingest, "build_resource_manifest", fake_manifest)
    monkeypatch.setattr(viking_ingest, "OpenVikingObservatoryClient", lambda settings: SimpleNamespace())
    monkeypatch.setattr(viking_ingest, "ObservatoryContextSettings", lambda: SimpleNamespace(cborg_api_key=None))
    import observatory_context.ingest.pipeline as pipeline_module
    monkeypatch.setattr(pipeline_module, "IngestPipeline", FakePipeline)

    assert viking_ingest.main(["--project", "alpha_proj"]) == 0

    assert run_calls == [{"project_ids": ["alpha_proj"], "resume": True, "extractor": None}]
    output = capsys.readouterr().out
    assert "Done!" in output
