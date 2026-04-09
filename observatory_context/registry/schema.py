"""Pydantic v2 models for the structured knowledge registry."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class EntityRef(BaseModel):
    """Reference to a typed entity in the knowledge graph."""

    type: Literal[
        "organism",
        "gene",
        "pathway",
        "condition",
        "environment",
        "method",
        "dataset",
        "concept",
    ]
    label: str
    normalized_id: str | None = None
    namespace: str | None = None


class Project(BaseModel):
    """Project metadata."""

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
    """Reusable claim from a project."""

    finding_id: str
    project_id: str
    title: str
    statement: str
    confidence: Literal["high", "moderate", "low"]
    finding_type: Literal[
        "result", "pattern", "negative_result", "methodological", "operational"
    ]
    related_entities: list[EntityRef] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    figure_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    """Testable claim tracked across projects."""

    hypothesis_id: str
    statement: str
    status: Literal[
        "proposed", "tested", "supported", "mixed", "not_supported", "superseded"
    ]
    scope: str | None = None
    project_ids: list[str] = Field(default_factory=list)
    related_entities: list[EntityRef] = Field(default_factory=list)
    source_ref: str | None = None


class Evidence(BaseModel):
    """Support for a hypothesis or finding."""

    evidence_id: str
    project_id: str
    kind: Literal[
        "statistical", "comparative", "biogeographic", "literature", "manual_review"
    ]
    summary: str
    source_ref: str
    linked_artifacts: list[str] = Field(default_factory=list)
    linked_figures: list[str] = Field(default_factory=list)
    statistical_support: str | None = None


class Artifact(BaseModel):
    """Reusable data product."""

    artifact_id: str
    project_id: str
    kind: str
    path: str
    description: str
    upstream_notebooks: list[str] = Field(default_factory=list)
    upstream_datasets: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class Figure(BaseModel):
    """Visual output."""

    figure_id: str
    project_id: str
    path: str
    caption: str
    illustrates: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class Pitfall(BaseModel):
    """Operational knowledge."""

    pitfall_id: str
    title: str
    description: str
    applies_to: list[str] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)
    source_ref: str | None = None
    tags: list[str] = Field(default_factory=list)
    category: str | None = None


class Discovery(BaseModel):
    """Serendipitous finding or unexpected pattern."""

    discovery_id: str
    title: str
    description: str
    significance: str | None = None
    project_ids: list[str] = Field(default_factory=list)
    related_entities: list[EntityRef] = Field(default_factory=list)
    source_ref: str | None = None
    tags: list[str] = Field(default_factory=list)


class ResearchIdea(BaseModel):
    """Future research direction."""

    idea_id: str
    statement: str
    motivation: str
    priority: Literal["high", "medium", "low"]
    status: Literal["proposed", "in_progress", "completed", "deferred"] = "proposed"
    related_entities: list[EntityRef] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)
