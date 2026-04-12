"""Tests for the synthesis-backed knowledge-layer export pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from observatory_context.graph.builder import GraphBuilder
from observatory_context.ingest.manifest import ResourceManifestItem
from observatory_context.ingest.pipeline import IngestPipeline
from observatory_context.registry.schema import EntityRef, Finding, Hypothesis


def _manifest(tmp_path: Path) -> list[ResourceManifestItem]:
    return [
        ResourceManifestItem(
            uri="viking://resources/observatory/projects/proj-a/authored/README.md",
            kind="project",
            source_path=str(tmp_path / "projects" / "proj-a" / "README.md"),
            project_ids=["proj-a"],
            metadata={},
        ),
        ResourceManifestItem(
            uri="viking://resources/observatory/projects/proj-b/authored/README.md",
            kind="project",
            source_path=str(tmp_path / "projects" / "proj-b" / "README.md"),
            project_ids=["proj-b"],
            metadata={},
        ),
    ]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_pipeline_builds_synthesis_and_exports_to_observatory_root(tmp_path: Path) -> None:
    _write(tmp_path / "projects" / "proj-a" / "README.md", "# Project A\n")
    _write(tmp_path / "projects" / "proj-b" / "README.md", "# Project B\n")
    _write(tmp_path / "projects" / "proj-a" / "provenance.yaml", "created_at: 2026-04-01\n")
    _write(tmp_path / "projects" / "proj-b" / "provenance.yaml", "created_at: 2026-04-02\n")

    builder = GraphBuilder()
    builder.add_project("proj-a", "Project A")
    builder.add_project("proj-b", "Project B")
    builder.add_entity("Pseudomonas putida", "organism", project_ids=["proj-a", "proj-b"])
    builder.add_entity("czc efflux", "concept", project_ids=["proj-a", "proj-b"])
    builder.G.add_edge(
        "organism/pseudomonas-putida",
        "concept/czc-efflux",
        relation="RELATED_TO",
        weight=3,
    )
    graph_dir = tmp_path / "data" / "graph"
    graph_dir.mkdir(parents=True, exist_ok=True)
    builder.serialize(graph_dir / "graph.json")
    (graph_dir / "communities.json").write_text(
        json.dumps(
            {
                "1": {
                    "name": "Metal Stress Cluster",
                    "members": ["organism/pseudomonas-putida", "concept/czc-efflux"],
                    "projects": ["proj-a", "proj-b"],
                    "summary": "Cross-project metal stress cluster",
                }
            }
        ),
        encoding="utf-8",
    )

    findings = [
        Finding(
            finding_id="F-001",
            project_id="proj-a",
            title="Metal pattern",
            statement="Metal stress links to efflux conservation.",
            confidence="high",
            finding_type="result",
            related_entities=[
                EntityRef(type="organism", label="Pseudomonas putida"),
                EntityRef(type="concept", label="czc efflux"),
            ],
        )
    ]
    hypotheses = [
        Hypothesis(
            hypothesis_id="H-001",
            statement="Efflux conservation tracks metal stress.",
            status="supported",
            project_ids=["proj-a", "proj-b"],
            related_entities=[
                EntityRef(type="organism", label="Pseudomonas putida"),
                EntityRef(type="concept", label="czc efflux"),
            ],
        )
    ]

    client = MagicMock()
    pipeline = IngestPipeline(client=client, repo_root=tmp_path, staging_root=tmp_path / "staging")
    bundle, graph = pipeline.build_synthesis_bundle(_manifest(tmp_path), findings=findings, hypotheses=hypotheses)

    assert bundle.topics[0].topic_id == "community-1"
    assert bundle.topics[0].project_ids == ["proj-a", "proj-b"]

    count = pipeline.phase4_export_knowledge_graph(bundle, graph)

    assert count > 0
    assert client.batch_add.call_args.kwargs["to"] == "viking://resources/observatory"
    assert client.batch_add.call_args.kwargs["wait"] is False
    client.wait_until_processed.assert_called_once()
    assert client.link_resources.call_count == 2
