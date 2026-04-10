"""Observatory knowledge graph — entity resolution and graph utilities."""

from observatory_context.graph.aliases import load_aliases, save_aliases
from observatory_context.graph.builder import GraphBuilder
from observatory_context.graph.knowledge_graph_export import KnowledgeGraphExporter
from observatory_context.graph.knowledge_synthesis import (
    KnowledgeSynthesisBundle,
    KnowledgeSynthesizer,
    RelatedEntitySummary,
    SynthesizedCommunity,
    SynthesizedEntity,
    SynthesizedHypothesis,
    SynthesizedTimelineEvent,
    SynthesizedTopic,
)
from observatory_context.graph.report import generate_graph_report, save_report
from observatory_context.graph.resolver import EntityResolver, ResolvedEntity

__all__ = [
    "EntityResolver",
    "GraphBuilder",
    "KnowledgeGraphExporter",
    "KnowledgeSynthesisBundle",
    "KnowledgeSynthesizer",
    "ResolvedEntity",
    "RelatedEntitySummary",
    "SynthesizedCommunity",
    "SynthesizedEntity",
    "SynthesizedHypothesis",
    "SynthesizedTimelineEvent",
    "SynthesizedTopic",
    "generate_graph_report",
    "load_aliases",
    "save_aliases",
    "save_report",
]
