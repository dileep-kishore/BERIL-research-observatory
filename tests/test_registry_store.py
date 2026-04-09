"""Tests for RegistryStore — OpenViking-backed YAML read/write."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import yaml

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
from observatory_context.registry.store import RegistryStore
from observatory_context.uris import (
    build_registry_finding_uri,
    build_registry_hypothesis_uri,
    build_registry_project_uri,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_client():
    return MagicMock()


@pytest.fixture()
def store(mock_client):
    return RegistryStore(client=mock_client)


def _make_finding(**kwargs) -> Finding:
    defaults = dict(
        finding_id="find-001",
        project_id="proj-001",
        title="Key result",
        statement="X causes Y.",
        confidence="high",
        finding_type="result",
    )
    defaults.update(kwargs)
    return Finding(**defaults)


def _make_project(**kwargs) -> Project:
    defaults = dict(
        project_id="proj-001",
        title="Test Project",
        status="active",
        research_question="What happens?",
    )
    defaults.update(kwargs)
    return Project(**defaults)


def _make_hypothesis(**kwargs) -> Hypothesis:
    defaults = dict(
        hypothesis_id="hyp-001",
        statement="X causes Y.",
        status="proposed",
    )
    defaults.update(kwargs)
    return Hypothesis(**defaults)


# ---------------------------------------------------------------------------
# write_finding
# ---------------------------------------------------------------------------


def test_write_finding_calls_add_text_resource(store, mock_client):
    finding = _make_finding()
    store.write_finding(finding)

    mock_client.add_text_resource.assert_called_once()
    _, kwargs = mock_client.add_text_resource.call_args
    assert kwargs["uri"] == build_registry_finding_uri("find-001")
    assert "find-001" in kwargs["content"]


def test_write_finding_uri_contains_finding_id(store, mock_client):
    finding = _make_finding(finding_id="find-abc")
    store.write_finding(finding)

    _, kwargs = mock_client.add_text_resource.call_args
    assert "find-abc" in kwargs["uri"]


def test_write_finding_content_is_valid_yaml(store, mock_client):
    finding = _make_finding()
    store.write_finding(finding)

    _, kwargs = mock_client.add_text_resource.call_args
    parsed = yaml.safe_load(kwargs["content"])
    assert parsed["finding_id"] == "find-001"
    assert parsed["confidence"] == "high"


def test_write_finding_passes_wait(store, mock_client):
    finding = _make_finding()
    store.write_finding(finding, wait=False)

    _, kwargs = mock_client.add_text_resource.call_args
    assert kwargs["wait"] is False


# ---------------------------------------------------------------------------
# write_project
# ---------------------------------------------------------------------------


def test_write_project_calls_add_text_resource(store, mock_client):
    project = _make_project()
    store.write_project(project)

    mock_client.add_text_resource.assert_called_once()
    _, kwargs = mock_client.add_text_resource.call_args
    assert kwargs["uri"] == build_registry_project_uri("proj-001")


def test_write_project_content_is_valid_yaml(store, mock_client):
    project = _make_project()
    store.write_project(project)

    _, kwargs = mock_client.add_text_resource.call_args
    parsed = yaml.safe_load(kwargs["content"])
    assert parsed["project_id"] == "proj-001"
    assert parsed["status"] == "active"


# ---------------------------------------------------------------------------
# write_hypothesis
# ---------------------------------------------------------------------------


def test_write_hypothesis_calls_add_text_resource(store, mock_client):
    hyp = _make_hypothesis()
    store.write_hypothesis(hyp)

    mock_client.add_text_resource.assert_called_once()
    _, kwargs = mock_client.add_text_resource.call_args
    assert kwargs["uri"] == build_registry_hypothesis_uri("hyp-001")


# ---------------------------------------------------------------------------
# write_evidence, write_artifact, write_figure, write_pitfall, write_idea
# ---------------------------------------------------------------------------


def test_write_evidence_calls_add_text_resource(store, mock_client):
    from observatory_context.uris import build_registry_evidence_uri

    ev = Evidence(
        evidence_id="ev-001",
        project_id="proj-001",
        kind="statistical",
        summary="p < 0.05",
        source_ref="doi:10.1/z",
    )
    store.write_evidence(ev)

    _, kwargs = mock_client.add_text_resource.call_args
    assert kwargs["uri"] == build_registry_evidence_uri("ev-001")


def test_write_artifact_calls_add_text_resource(store, mock_client):
    from observatory_context.uris import build_registry_artifact_uri

    art = Artifact(
        artifact_id="art-001",
        project_id="proj-001",
        kind="table",
        path="data/results.csv",
        description="Main table.",
    )
    store.write_artifact(art)

    _, kwargs = mock_client.add_text_resource.call_args
    assert kwargs["uri"] == build_registry_artifact_uri("art-001")


def test_write_figure_calls_add_text_resource(store, mock_client):
    from observatory_context.uris import build_registry_figure_uri

    fig = Figure(
        figure_id="fig-001",
        project_id="proj-001",
        path="figures/fig1.png",
        caption="Main figure.",
    )
    store.write_figure(fig)

    _, kwargs = mock_client.add_text_resource.call_args
    assert kwargs["uri"] == build_registry_figure_uri("fig-001")


def test_write_pitfall_calls_add_text_resource(store, mock_client):
    from observatory_context.uris import build_registry_pitfall_uri

    pit = Pitfall(
        pitfall_id="pit-001",
        title="Watch out",
        description="Silent failure.",
    )
    store.write_pitfall(pit)

    _, kwargs = mock_client.add_text_resource.call_args
    assert kwargs["uri"] == build_registry_pitfall_uri("pit-001")


def test_write_idea_calls_add_text_resource(store, mock_client):
    from observatory_context.uris import build_registry_idea_uri

    idea = ResearchIdea(
        idea_id="idea-001",
        statement="Investigate X.",
        motivation="Gap in literature.",
        priority="medium",
    )
    store.write_idea(idea)

    _, kwargs = mock_client.add_text_resource.call_args
    assert kwargs["uri"] == build_registry_idea_uri("idea-001")


# ---------------------------------------------------------------------------
# read_finding
# ---------------------------------------------------------------------------


def _yaml_content(model) -> str:
    return yaml.safe_dump(model.model_dump(mode="json", exclude_none=True))


def test_read_finding_returns_finding(store, mock_client):
    finding = _make_finding()
    mock_client.read_resource.return_value = _yaml_content(finding)

    result = store.read_finding("find-001")

    assert result is not None
    assert result.finding_id == "find-001"
    assert result.confidence == "high"
    mock_client.read_resource.assert_called_once_with(build_registry_finding_uri("find-001"))


def test_read_finding_returns_none_on_not_found(store, mock_client):
    class NotFoundError(Exception):
        pass

    mock_client.read_resource.side_effect = NotFoundError("not found")

    result = store.read_finding("missing-id")

    assert result is None


def test_read_finding_re_raises_other_errors(store, mock_client):
    mock_client.read_resource.side_effect = ConnectionError("server down")

    with pytest.raises(ConnectionError):
        store.read_finding("find-001")


# ---------------------------------------------------------------------------
# read_project
# ---------------------------------------------------------------------------


def test_read_project_returns_project(store, mock_client):
    project = _make_project()
    mock_client.read_resource.return_value = _yaml_content(project)

    result = store.read_project("proj-001")

    assert result is not None
    assert result.project_id == "proj-001"


def test_read_project_returns_none_on_not_found(store, mock_client):
    class NotFoundError(Exception):
        pass

    mock_client.read_resource.side_effect = NotFoundError("not found")

    result = store.read_project("missing")

    assert result is None


# ---------------------------------------------------------------------------
# read_hypothesis
# ---------------------------------------------------------------------------


def test_read_hypothesis_returns_hypothesis(store, mock_client):
    hyp = _make_hypothesis()
    mock_client.read_resource.return_value = _yaml_content(hyp)

    result = store.read_hypothesis("hyp-001")

    assert result is not None
    assert result.hypothesis_id == "hyp-001"
    assert result.status == "proposed"


def test_read_hypothesis_returns_none_on_not_found(store, mock_client):
    class NotFoundError(Exception):
        pass

    mock_client.read_resource.side_effect = NotFoundError("not found")

    result = store.read_hypothesis("missing")

    assert result is None


# ---------------------------------------------------------------------------
# list_findings
# ---------------------------------------------------------------------------


def test_list_findings_returns_list(store, mock_client):
    finding = _make_finding()
    mock_client.list_resources.return_value = [
        {"uri": build_registry_finding_uri("find-001"), "name": "find-001.yaml"},
    ]
    mock_client.read_resource.return_value = _yaml_content(finding)

    results = store.list_findings()

    assert len(results) == 1
    assert results[0].finding_id == "find-001"


def test_list_findings_filters_by_project_id(store, mock_client):
    f1 = _make_finding(finding_id="find-001", project_id="proj-A")
    f2 = _make_finding(finding_id="find-002", project_id="proj-B")
    mock_client.list_resources.return_value = [
        {"uri": build_registry_finding_uri("find-001"), "name": "find-001.yaml"},
        {"uri": build_registry_finding_uri("find-002"), "name": "find-002.yaml"},
    ]
    mock_client.read_resource.side_effect = [
        _yaml_content(f1),
        _yaml_content(f2),
    ]

    results = store.list_findings(project_id="proj-A")

    assert len(results) == 1
    assert results[0].project_id == "proj-A"


def test_list_findings_empty(store, mock_client):
    mock_client.list_resources.return_value = []

    results = store.list_findings()

    assert results == []


# ---------------------------------------------------------------------------
# list_hypotheses
# ---------------------------------------------------------------------------


def test_list_hypotheses_returns_list(store, mock_client):
    hyp = _make_hypothesis()
    mock_client.list_resources.return_value = [
        {"uri": build_registry_hypothesis_uri("hyp-001"), "name": "hyp-001.yaml"},
    ]
    mock_client.read_resource.return_value = _yaml_content(hyp)

    results = store.list_hypotheses()

    assert len(results) == 1
    assert results[0].hypothesis_id == "hyp-001"


def test_list_hypotheses_filters_by_status(store, mock_client):
    h1 = _make_hypothesis(hypothesis_id="hyp-001", status="proposed")
    h2 = _make_hypothesis(hypothesis_id="hyp-002", status="supported")
    mock_client.list_resources.return_value = [
        {"uri": build_registry_hypothesis_uri("hyp-001"), "name": "hyp-001.yaml"},
        {"uri": build_registry_hypothesis_uri("hyp-002"), "name": "hyp-002.yaml"},
    ]
    mock_client.read_resource.side_effect = [
        _yaml_content(h1),
        _yaml_content(h2),
    ]

    results = store.list_hypotheses(status="proposed")

    assert len(results) == 1
    assert results[0].status == "proposed"


# ---------------------------------------------------------------------------
# list_projects
# ---------------------------------------------------------------------------


def test_list_projects_returns_list(store, mock_client):
    project = _make_project()
    mock_client.list_resources.return_value = [
        {"uri": build_registry_project_uri("proj-001"), "name": "proj-001.yaml"},
    ]
    mock_client.read_resource.return_value = _yaml_content(project)

    results = store.list_projects()

    assert len(results) == 1
    assert results[0].project_id == "proj-001"


# ---------------------------------------------------------------------------
# batch_write_findings
# ---------------------------------------------------------------------------


def test_batch_write_findings_stages_files_and_calls_batch_add(
    store, mock_client, tmp_path
):
    findings = [
        _make_finding(finding_id="find-001"),
        _make_finding(finding_id="find-002"),
    ]
    store.batch_write_findings(findings, staging_dir=tmp_path)

    # Staged files should exist
    staged = list(tmp_path.glob("**/*.yaml"))
    assert len(staged) == 2

    # batch_add should have been called once
    mock_client.batch_add.assert_called_once()
    _, kwargs = mock_client.batch_add.call_args
    assert kwargs["to"] is not None or len(mock_client.batch_add.call_args.args) >= 2


def test_batch_write_findings_file_content_is_valid_yaml(
    store, mock_client, tmp_path
):
    findings = [_make_finding(finding_id="find-001")]
    store.batch_write_findings(findings, staging_dir=tmp_path)

    yaml_files = list(tmp_path.glob("**/*.yaml"))
    assert len(yaml_files) == 1
    parsed = yaml.safe_load(yaml_files[0].read_text())
    assert parsed["finding_id"] == "find-001"
