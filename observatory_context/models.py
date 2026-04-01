"""Data models and enums for the ContextDelivery API."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Tier(StrEnum):
    """Context detail tier."""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"


class Scope(StrEnum):
    """Retrieval scope for context queries."""

    all = "all"
    resources = "resources"
    memory = "memory"
    graph = "graph"


class MemoryStore(StrEnum):
    """Supported memory store types."""

    journal = "journal"
    patterns = "patterns"
    conversations = "conversations"


class RelatedItem(BaseModel):
    """Inline relation returned by OpenViking search."""

    uri: str
    reason: str


class ContextItem(BaseModel):
    """A single context item returned by the ContextDelivery service."""

    uri: str
    title: str
    kind: str
    tier: Tier
    content: str
    project_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source_type: Literal["resource", "memory"] = "resource"
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float | None = None
    match_reason: str | None = None
    is_leaf: bool | None = None
    category: str | None = None
    related: list[RelatedItem] = Field(default_factory=list)


class SearchResults(BaseModel):
    """Results from a context search query."""

    query: str
    items: list[ContextItem]
    total_count: int
    session_id: str | None = None


class RelationEdge(BaseModel):
    """A directed relation between two context items."""

    subject_uri: str
    predicate: str
    object_uri: str
    evidence: str
    confidence: Literal["high", "moderate", "low"]


class GraphResult(BaseModel):
    """A graph traversal result rooted at a single context item."""

    root: ContextItem
    connected: list[ContextItem]
    relations: list[RelationEdge]
