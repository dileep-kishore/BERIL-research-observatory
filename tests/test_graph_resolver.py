"""Tests for entity resolution behavior."""

from __future__ import annotations

from typing import Any

from observatory_context.graph.resolver import EntityResolver


def test_resolver_accepts_dataset_entity_type() -> None:
    resolver = EntityResolver(aliases={})

    resolved = resolver.resolve("dataset", "BERDL fitness data")

    assert resolved.entity_type == "dataset"
    assert resolved.canonical == "BERDL fitness data"


def test_resolve_batch_prefetches_embeddings_in_batches() -> None:
    resolver = EntityResolver(
        aliases={
            "Pseudomonas putida": [],
            "Escherichia coli": [],
        },
        openai_api_key="test-key",
    )

    calls: list[list[str]] = []

    class _Response:
        def __init__(self, inputs: list[str]) -> None:
            self._inputs = inputs

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            vectors = {
                "Pseudomonas putida": [1.0, 0.0],
                "Escherichia coli": [0.0, 1.0],
                "Pseudomonas putda": [1.0, 0.0],
                "Escherichia col": [0.0, 1.0],
            }
            return {
                "data": [
                    {"index": idx, "embedding": vectors[text]}
                    for idx, text in enumerate(self._inputs)
                ]
            }

    class _Client:
        def post(self, url: str, json: dict[str, Any]) -> _Response:
            assert url == "https://api.openai.com/v1/embeddings"
            inputs = json["input"]
            if isinstance(inputs, str):
                inputs = [inputs]
            calls.append(list(inputs))
            return _Response(list(inputs))

        def close(self) -> None:
            return None

    resolver._embedding_client = _Client()  # type: ignore[assignment]

    resolved = resolver.resolve_batch(
        [
            ("organism", "Pseudomonas putda"),
            ("organism", "Escherichia col"),
        ]
    )

    assert resolved["Pseudomonas putda"].canonical == "Pseudomonas putida"
    assert resolved["Escherichia col"].canonical == "Escherichia coli"
    assert len(calls) == 1
    assert calls[0] == [
        "Pseudomonas putida",
        "Escherichia coli",
        "Pseudomonas putda",
        "Escherichia col",
    ]


def test_resolve_batch_reuses_embedding_cache_for_canonicals() -> None:
    resolver = EntityResolver(
        aliases={
            "Pseudomonas putida": [],
            "Escherichia coli": [],
        },
        openai_api_key="test-key",
    )

    calls: list[list[str]] = []

    class _Response:
        def __init__(self, inputs: list[str]) -> None:
            self._inputs = inputs

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            vectors = {
                "Pseudomonas putida": [1.0, 0.0],
                "Escherichia coli": [0.0, 1.0],
                "Pseudomonas putda": [1.0, 0.0],
                "Escherichia col": [0.0, 1.0],
            }
            return {
                "data": [
                    {"index": idx, "embedding": vectors[text]}
                    for idx, text in enumerate(self._inputs)
                ]
            }

    class _Client:
        def post(self, url: str, json: dict[str, Any]) -> _Response:
            inputs = json["input"]
            if isinstance(inputs, str):
                inputs = [inputs]
            calls.append(list(inputs))
            return _Response(list(inputs))

        def close(self) -> None:
            return None

    resolver._embedding_client = _Client()  # type: ignore[assignment]

    resolver.resolve_batch([("organism", "Pseudomonas putda")])
    resolver.resolve_batch([("organism", "Escherichia col")])

    assert calls == [
        ["Pseudomonas putida", "Escherichia coli", "Pseudomonas putda"],
        ["Escherichia col"],
    ]
