"""Deterministic URI helpers for observatory resources."""

from __future__ import annotations

from pathlib import PurePosixPath


_ROOT = "viking://resources/observatory"


def _normalize_segment(value: str) -> str:
    return PurePosixPath(value.replace("\\", "/")).as_posix().strip("/")


def build_project_resource_uri(project_id: str, section: str, relative_path: str) -> str:
    path = PurePosixPath(
        "projects",
        project_id,
        _normalize_segment(section),
        _normalize_segment(relative_path),
    )
    return f"{_ROOT}/{path.as_posix()}"


def build_observatory_root_uri() -> str:
    return _ROOT


def build_project_workspace_uri(project_id: str) -> str:
    path = PurePosixPath("projects", _normalize_segment(project_id))
    return f"{_ROOT}/{path.as_posix()}"


def build_figure_resource_uri(project_id: str, figure_id: str) -> str:
    path = PurePosixPath("projects", project_id, "authored", "figures", _normalize_segment(figure_id))
    return f"{_ROOT}/{path.as_posix()}"


def build_project_live_note_uri(project_id: str, resource_id: str, date: str) -> str:
    path = PurePosixPath(
        "projects",
        _normalize_segment(project_id),
        "notes",
        _normalize_segment(date),
        _normalize_segment(resource_id),
    )
    return f"{_ROOT}/{path.as_posix()}"


def build_shared_live_note_uri(resource_id: str, date: str) -> str:
    path = PurePosixPath("notes", _normalize_segment(date), _normalize_segment(resource_id))
    return f"{_ROOT}/{path.as_posix()}"


def build_project_notes_root_uri(project_id: str) -> str:
    path = PurePosixPath("projects", _normalize_segment(project_id), "notes")
    return f"{_ROOT}/{path.as_posix()}"


def build_shared_notes_root_uri() -> str:
    path = PurePosixPath("notes")
    return f"{_ROOT}/{path.as_posix()}"


_ENTITY_TYPE_PLURALS = {
    "organism": "organisms",
    "gene": "genes",
    "pathway": "pathways",
    "method": "methods",
    "concept": "concepts",
}

_MEMORY_STORE_DIRS = {
    "journal": "research-journal",
    "patterns": "patterns",
    "conversations": "conversations",
}

_OPERATIONAL_COLLECTIONS = {
    "pitfall": "pitfalls",
    "research_idea": "research-ideas",
    "discovery": "discoveries",
}


def build_knowledge_graph_uri() -> str:
    path = PurePosixPath("knowledge-graph")
    return f"{_ROOT}/{path.as_posix()}"


def build_entity_uri(entity_type: str, entity_id: str) -> str:
    plural = _ENTITY_TYPE_PLURALS[entity_type]
    path = PurePosixPath(
        "knowledge-graph",
        "entities",
        _normalize_segment(plural),
        _normalize_segment(entity_id),
    )
    return f"{_ROOT}/{path.as_posix()}"


def build_entity_relations_uri(entity_type: str, entity_id: str) -> str:
    return f"{build_entity_uri(entity_type, entity_id)}/relations"


def build_hypothesis_uri(hypothesis_id: str) -> str:
    path = PurePosixPath("knowledge-graph", "hypotheses", _normalize_segment(hypothesis_id))
    return f"{_ROOT}/{path.as_posix()}"


def build_timeline_uri() -> str:
    path = PurePosixPath("knowledge-graph", "timeline")
    return f"{_ROOT}/{path.as_posix()}"


def build_operational_collection_uri(collection: str) -> str:
    """URI for an operational knowledge collection (pitfalls, research-ideas, discoveries)."""
    dir_name = _OPERATIONAL_COLLECTIONS[collection]
    return f"{_ROOT}/{dir_name}"


def build_operational_item_uri(collection: str, item_id: str) -> str:
    """URI for a specific item in an operational knowledge collection.

    Returns a ``.md`` file URI, e.g.
    ``viking://resources/observatory/pitfalls/rest-api-reliability.md``.
    """
    dir_name = _OPERATIONAL_COLLECTIONS[collection]
    safe_id = _normalize_segment(item_id)
    path = PurePosixPath(dir_name, f"{safe_id}.md")
    return f"{_ROOT}/{path.as_posix()}"


def build_memory_uri(store: str, slug: str | None = None) -> str:
    store_dir = _MEMORY_STORE_DIRS[store]
    if slug is None:
        path = PurePosixPath("memories", _normalize_segment(store_dir))
    else:
        path = PurePosixPath("memories", _normalize_segment(store_dir), _normalize_segment(slug))
    return f"{_ROOT}/{path.as_posix()}"


# ---------------------------------------------------------------------------
# V2 URI builders — corpus/, wiki/, registry/ namespaces
# ---------------------------------------------------------------------------


def build_corpus_uri(project_id: str, file_path: str | None = None) -> str:
    if file_path is None:
        path = PurePosixPath("corpus", _normalize_segment(project_id))
    else:
        path = PurePosixPath("corpus", _normalize_segment(project_id), _normalize_segment(file_path))
    return f"{_ROOT}/{path.as_posix()}"


def build_wiki_uri() -> str:
    return f"{_ROOT}/wiki"


def build_wiki_index_uri() -> str:
    return f"{_ROOT}/wiki/index.md"


def build_wiki_log_uri() -> str:
    return f"{_ROOT}/wiki/log.md"


def build_wiki_topic_uri(slug: str) -> str:
    path = PurePosixPath("wiki", "topics", f"{_normalize_segment(slug)}.md")
    return f"{_ROOT}/{path.as_posix()}"


def build_wiki_entity_uri(entity_type: str, slug: str) -> str:
    plural = _ENTITY_TYPE_PLURALS[entity_type]
    path = PurePosixPath("wiki", "entities", plural, f"{_normalize_segment(slug)}.md")
    return f"{_ROOT}/{path.as_posix()}"


def build_wiki_hypothesis_uri(hypothesis_id: str) -> str:
    path = PurePosixPath("wiki", "hypotheses", f"{_normalize_segment(hypothesis_id)}.md")
    return f"{_ROOT}/{path.as_posix()}"


def build_wiki_gaps_uri() -> str:
    return f"{_ROOT}/wiki/gaps/latest.md"


def build_registry_uri() -> str:
    return f"{_ROOT}/registry"


def build_registry_project_uri(project_id: str) -> str:
    path = PurePosixPath("registry", "projects", f"{_normalize_segment(project_id)}.yaml")
    return f"{_ROOT}/{path.as_posix()}"


def build_registry_finding_uri(finding_id: str) -> str:
    path = PurePosixPath("registry", "findings", f"{_normalize_segment(finding_id)}.yaml")
    return f"{_ROOT}/{path.as_posix()}"


def build_registry_hypothesis_uri(hypothesis_id: str) -> str:
    path = PurePosixPath("registry", "hypotheses", f"{_normalize_segment(hypothesis_id)}.yaml")
    return f"{_ROOT}/{path.as_posix()}"


def build_registry_evidence_uri(evidence_id: str) -> str:
    path = PurePosixPath("registry", "evidence", f"{_normalize_segment(evidence_id)}.yaml")
    return f"{_ROOT}/{path.as_posix()}"


def build_registry_artifact_uri(artifact_id: str) -> str:
    path = PurePosixPath("registry", "artifacts", f"{_normalize_segment(artifact_id)}.yaml")
    return f"{_ROOT}/{path.as_posix()}"


def build_registry_figure_uri(figure_id: str) -> str:
    path = PurePosixPath("registry", "figures", f"{_normalize_segment(figure_id)}.yaml")
    return f"{_ROOT}/{path.as_posix()}"


def build_registry_pitfall_uri(pitfall_id: str) -> str:
    path = PurePosixPath("registry", "pitfalls", f"{_normalize_segment(pitfall_id)}.yaml")
    return f"{_ROOT}/{path.as_posix()}"


def build_registry_idea_uri(idea_id: str) -> str:
    path = PurePosixPath("registry", "ideas", f"{_normalize_segment(idea_id)}.yaml")
    return f"{_ROOT}/{path.as_posix()}"


def build_registry_discovery_uri(discovery_id: str) -> str:
    path = PurePosixPath("registry", "discoveries", f"{_normalize_segment(discovery_id)}.yaml")
    return f"{_ROOT}/{path.as_posix()}"
