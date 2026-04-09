"""Tests for V2 URI builders (wiki/, registry/, corpus/ namespaces)."""

from __future__ import annotations

import pytest

from observatory_context.uris import (
    build_corpus_uri,
    build_registry_artifact_uri,
    build_registry_evidence_uri,
    build_registry_figure_uri,
    build_registry_finding_uri,
    build_registry_hypothesis_uri,
    build_registry_idea_uri,
    build_registry_pitfall_uri,
    build_registry_project_uri,
    build_registry_uri,
    build_wiki_entity_uri,
    build_wiki_gaps_uri,
    build_wiki_hypothesis_uri,
    build_wiki_index_uri,
    build_wiki_log_uri,
    build_wiki_topic_uri,
    build_wiki_uri,
)

_ROOT = "viking://resources/observatory"


def test_build_corpus_uri_no_file():
    assert build_corpus_uri("proj-01") == f"{_ROOT}/corpus/proj-01"


def test_build_corpus_uri_with_file():
    assert build_corpus_uri("proj-01", "REPORT.md") == f"{_ROOT}/corpus/proj-01/REPORT.md"


def test_build_wiki_uri():
    assert build_wiki_uri() == f"{_ROOT}/wiki"


def test_build_wiki_index_uri():
    assert build_wiki_index_uri() == f"{_ROOT}/wiki/index.md"


def test_build_wiki_log_uri():
    assert build_wiki_log_uri() == f"{_ROOT}/wiki/log.md"


def test_build_wiki_topic_uri():
    assert build_wiki_topic_uri("nitrogen-stress") == f"{_ROOT}/wiki/topics/nitrogen-stress.md"


def test_build_wiki_entity_uri():
    assert (
        build_wiki_entity_uri("organism", "pseudomonas-putida")
        == f"{_ROOT}/wiki/entities/organisms/pseudomonas-putida.md"
    )


def test_build_wiki_hypothesis_uri():
    assert (
        build_wiki_hypothesis_uri("hyp-metal-cross-resistance")
        == f"{_ROOT}/wiki/hypotheses/hyp-metal-cross-resistance.md"
    )


def test_build_wiki_gaps_uri():
    assert build_wiki_gaps_uri() == f"{_ROOT}/wiki/gaps/latest.md"


def test_build_registry_uri():
    assert build_registry_uri() == f"{_ROOT}/registry"


def test_build_registry_project_uri():
    assert build_registry_project_uri("proj-01") == f"{_ROOT}/registry/projects/proj-01.yaml"


def test_build_registry_finding_uri():
    assert build_registry_finding_uri("F-023") == f"{_ROOT}/registry/findings/F-023.yaml"


def test_build_registry_hypothesis_uri():
    assert build_registry_hypothesis_uri("HYP-007") == f"{_ROOT}/registry/hypotheses/HYP-007.yaml"


def test_build_registry_evidence_uri():
    assert build_registry_evidence_uri("E-023a") == f"{_ROOT}/registry/evidence/E-023a.yaml"


def test_build_registry_artifact_uri():
    assert (
        build_registry_artifact_uri("ART-metal-001")
        == f"{_ROOT}/registry/artifacts/ART-metal-001.yaml"
    )


def test_build_registry_figure_uri():
    assert (
        build_registry_figure_uri("FIG-metal-001")
        == f"{_ROOT}/registry/figures/FIG-metal-001.yaml"
    )


def test_build_registry_pitfall_uri():
    assert (
        build_registry_pitfall_uri("PIT-spark-timeout")
        == f"{_ROOT}/registry/pitfalls/PIT-spark-timeout.yaml"
    )


def test_build_registry_idea_uri():
    assert (
        build_registry_idea_uri("IDEA-marine-metal")
        == f"{_ROOT}/registry/ideas/IDEA-marine-metal.yaml"
    )
