"""Export synthesized observatory knowledge into OpenViking-ready resources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import networkx as nx
import yaml

from observatory_context._text import slugify
from observatory_context.graph.knowledge_synthesis import KnowledgeSynthesisBundle
from observatory_context.uris import build_entity_uri


def _frontmatter(metadata: dict[str, Any], body: str) -> str:
    return f"---\n{yaml.safe_dump(metadata, sort_keys=True)}---\n\n{body}"


class KnowledgeGraphExporter:
    """Render synthesized knowledge into staged files and OpenViking links."""

    def __init__(
        self,
        *,
        bundle: KnowledgeSynthesisBundle,
        graph: nx.MultiDiGraph | None = None,
    ) -> None:
        self.bundle = bundle
        self.graph = graph

    def export_all(self, staging_dir: Path) -> int:
        """Stage the full knowledge-graph hierarchy under ``staging_dir``."""

        root = staging_dir / "knowledge-graph"
        root.mkdir(parents=True, exist_ok=True)
        file_count = 0

        for entity in self.bundle.entities:
            plural = self._entity_plural(entity.entity_type)
            entity_root = root / "entities" / plural / entity.slug
            entity_root.mkdir(parents=True, exist_ok=True)
            self._write_text(
                entity_root / ".abstract.md",
                _frontmatter(
                    {
                        "kind": "entity_abstract",
                        "title": entity.canonical_name,
                        "entity_type": entity.entity_type,
                        "project_ids": entity.project_ids,
                    },
                    entity.abstract,
                ),
            )
            self._write_text(
                entity_root / ".overview.md",
                _frontmatter(
                    {
                        "kind": "entity_overview",
                        "title": entity.canonical_name,
                        "entity_type": entity.entity_type,
                        "project_ids": entity.project_ids,
                    },
                    entity.overview,
                ),
            )
            self._write_text(
                entity_root / "profile.yaml",
                _frontmatter(
                    {
                        "kind": "entity_profile",
                        "title": entity.canonical_name,
                        "entity_type": entity.entity_type,
                        "project_ids": entity.project_ids,
                        "coverage": entity.coverage,
                    },
                    yaml.safe_dump(entity.profile, sort_keys=True),
                ),
            )
            file_count += 3

        for hypothesis in self.bundle.hypotheses:
            hyp_root = root / "hypotheses" / hypothesis.slug
            hyp_root.mkdir(parents=True, exist_ok=True)
            self._write_text(
                hyp_root / ".abstract.md",
                _frontmatter(
                    {
                        "kind": "hypothesis_abstract",
                        "title": hypothesis.hypothesis_id,
                        "status": hypothesis.status,
                        "project_ids": hypothesis.project_ids,
                    },
                    hypothesis.abstract,
                ),
            )
            self._write_text(
                hyp_root / ".overview.md",
                _frontmatter(
                    {
                        "kind": "hypothesis_overview",
                        "title": hypothesis.hypothesis_id,
                        "status": hypothesis.status,
                        "project_ids": hypothesis.project_ids,
                    },
                    hypothesis.overview,
                ),
            )
            self._write_text(
                hyp_root / "hypothesis.yaml",
                _frontmatter(
                    {
                        "kind": "hypothesis",
                        "title": hypothesis.hypothesis_id,
                        "status": hypothesis.status,
                        "project_ids": hypothesis.project_ids,
                        "coverage": hypothesis.coverage,
                    },
                    yaml.safe_dump(hypothesis.hypothesis, sort_keys=True),
                ),
            )
            file_count += 3

        timeline_root = root / "timeline"
        timeline_root.mkdir(parents=True, exist_ok=True)
        self._write_text(
            timeline_root / "events.yaml",
            _frontmatter(
                {"kind": "timeline", "title": "Research Timeline"},
                yaml.safe_dump(
                    {
                        "events": [event.model_dump(exclude_none=True) for event in self.bundle.timeline_events]
                    },
                    sort_keys=True,
                ),
            ),
        )
        file_count += 1

        return file_count

    def create_relations(self, client: Any) -> int:
        """Create OpenViking resource relations for graph edges."""

        if self.graph is None:
            return 0

        relation_map: dict[tuple[str, str], dict[str, Any]] = {}
        for source, target, data in self.graph.edges(data=True):
            if data.get("relation") != "RELATED_TO":
                continue
            source_data = self.graph.nodes.get(source, {})
            target_data = self.graph.nodes.get(target, {})
            if source_data.get("kind") != "entity" or target_data.get("kind") != "entity":
                continue
            key = (source, target)
            entry = relation_map.setdefault(
                key,
                {
                    "from_uri": build_entity_uri(
                        source_data.get("entity_type", "concept"),
                        slugify(source_data.get("canonical_name", source)),
                    ),
                    "to_uri": build_entity_uri(
                        target_data.get("entity_type", "concept"),
                        slugify(target_data.get("canonical_name", target)),
                    ),
                    "weight": 0,
                },
            )
            entry["weight"] += int(data.get("weight", 1))

        created = 0
        for entry in relation_map.values():
            reason = f"co-occurs in {entry['weight']} finding(s)"
            client.link_resources(entry["from_uri"], [entry["to_uri"]], reason=reason)
            client.link_resources(entry["to_uri"], [entry["from_uri"]], reason=reason)
            created += 2

        return created

    def _entity_plural(self, entity_type: str) -> str:
        return {
            "organism": "organisms",
            "gene": "genes",
            "pathway": "pathways",
            "condition": "conditions",
            "environment": "environments",
            "method": "methods",
            "dataset": "datasets",
            "concept": "concepts",
        }.get(entity_type, f"{entity_type}s")

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
