"""Tests for entity resolution behavior."""

from __future__ import annotations

from observatory_context.graph.resolver import EntityResolver


def test_resolver_accepts_dataset_entity_type() -> None:
    resolver = EntityResolver(aliases={})

    resolved = resolver.resolve("dataset", "BERDL fitness data")

    assert resolved.entity_type == "dataset"
    assert resolved.canonical == "BERDL fitness data"
