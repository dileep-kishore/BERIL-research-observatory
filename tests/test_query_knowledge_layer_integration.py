"""Integration tests for querying exported knowledge-layer resources."""

from __future__ import annotations

from pathlib import Path

from observatory_context.delivery import ContextDelivery
from observatory_context.graph.builder import GraphBuilder
from observatory_context.graph.knowledge_graph_export import KnowledgeGraphExporter
from observatory_context.graph.knowledge_synthesis import KnowledgeSynthesizer
from observatory_context.registry.schema import EntityRef, Finding, Hypothesis


class NotFoundError(Exception):
    """Fake OpenViking not-found error."""


class ExportedKnowledgeClient:
    def __init__(self, root: Path, relations: dict[str, list[dict[str, str]]]) -> None:
        self.root = root
        self.relations_map = relations
        self.resources: dict[str, str] = {}
        for path in sorted((root / "knowledge-graph").rglob("*")):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                uri = f"viking://resources/observatory/{rel}"
                self.resources[uri] = path.read_text(encoding="utf-8")

    def read_resource(self, uri: str) -> str:
        if uri not in self.resources:
            raise NotFoundError(uri)
        return self.resources[uri]

    def list_resources(self, uri: str, recursive: bool = False) -> list[dict[str, str]]:
        prefix = uri.rstrip("/")
        seen: set[str] = set()
        results: list[dict[str, str]] = []
        for resource_uri in sorted(self.resources):
            if not resource_uri.startswith(f"{prefix}/"):
                continue
            remainder = resource_uri[len(prefix) + 1 :]
            child = resource_uri if recursive else f"{prefix}/{remainder.split('/', 1)[0]}"
            if child in seen:
                continue
            seen.add(child)
            results.append({"uri": child})
        return results

    def relations(self, uri: str) -> list[dict[str, str]]:
        return self.relations_map.get(uri, [])


def _build_export(root: Path) -> tuple[Path, dict[str, list[dict[str, str]]]]:
    builder = GraphBuilder()
    builder.add_project("proj-a", "Project A")
    builder.add_entity("Pseudomonas putida", "organism", project_ids=["proj-a"])
    builder.add_entity("czc efflux", "concept", project_ids=["proj-a"])
    builder.G.add_edge(
        "organism/pseudomonas-putida",
        "concept/czc-efflux",
        relation="RELATED_TO",
        weight=4,
    )
    findings = [
        Finding(
            finding_id="F-001",
            project_id="proj-a",
            title="Finding",
            statement="Pseudomonas putida is relevant",
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
            statement="Example hypothesis",
            status="tested",
            project_ids=["proj-a"],
            related_entities=[
                EntityRef(type="organism", label="Pseudomonas putida"),
            ],
        )
    ]
    bundle = KnowledgeSynthesizer().synthesize(
        findings=findings,
        hypotheses=hypotheses,
        project_ids=["proj-a"],
        graph=builder.G,
        communities={},
    )
    exporter = KnowledgeGraphExporter(bundle=bundle, graph=builder.G)
    exporter.export_all(root)
    relations = {
        "viking://resources/observatory/knowledge-graph/entities/organisms/pseudomonas-putida": [
            {
                "uri": "viking://resources/observatory/knowledge-graph/entities/concepts/czc-efflux",
                "reason": "co-occurs in 4 finding(s)",
            }
        ]
    }
    return root, relations


def test_delivery_uses_exported_metadata_and_relations_fallback(tmp_path: Path) -> None:
    export_root, relations = _build_export(tmp_path)
    delivery = ContextDelivery(client=ExportedKnowledgeClient(export_root, relations))

    hypotheses = delivery.hypotheses(status="tested")
    assert len(hypotheses) == 1
    assert hypotheses[0].metadata["status"] == "tested"

    root_uri = "viking://resources/observatory/knowledge-graph/entities/organisms/pseudomonas-putida"
    result = delivery.traverse(root_uri)
    assert result.relations[0].predicate == "related_to"
    assert result.connected[0].uri.endswith("/concepts/czc-efflux")
