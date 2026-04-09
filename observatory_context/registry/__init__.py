"""Structured knowledge registry backed by OpenViking."""

from observatory_context.registry.schema import (
    Artifact, Discovery, EntityRef, Evidence, Figure, Finding,
    Hypothesis, Pitfall, Project, ResearchIdea,
)
from observatory_context.registry.store import RegistryStore

__all__ = [
    "Artifact", "Discovery", "EntityRef", "Evidence", "Figure", "Finding",
    "Hypothesis", "Pitfall", "Project", "RegistryStore", "ResearchIdea",
]
