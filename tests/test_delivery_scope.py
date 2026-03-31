"""Tests for ContextDelivery._scope_uri scoping."""

from unittest.mock import MagicMock

import pytest

from observatory_context.delivery import ContextDelivery
from observatory_context.models import Scope
from observatory_context.uris import _ROOT, build_knowledge_graph_uri


@pytest.fixture()
def delivery():
    client = MagicMock()
    return ContextDelivery(client=client)


def test_scope_resources_targets_projects(delivery):
    uri = delivery._scope_uri(Scope.resources)
    assert uri == f"{_ROOT}/projects"


def test_scope_all_targets_root(delivery):
    uri = delivery._scope_uri(Scope.all)
    assert uri == _ROOT


def test_scope_memory_targets_memories(delivery):
    uri = delivery._scope_uri(Scope.memory)
    assert uri == f"{_ROOT}/memories"


def test_scope_graph_targets_knowledge_graph(delivery):
    uri = delivery._scope_uri(Scope.graph)
    assert uri == build_knowledge_graph_uri()
