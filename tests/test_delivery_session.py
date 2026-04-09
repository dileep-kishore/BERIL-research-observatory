"""Tests for ContextDelivery session-aware search."""

from unittest.mock import MagicMock

import pytest

from observatory_context.delivery import ContextDelivery


@pytest.fixture()
def mock_client():
    client = MagicMock()
    client.search.return_value = []
    client.context_search.return_value = []
    return client


@pytest.fixture()
def delivery(mock_client):
    return ContextDelivery(client=mock_client)


def test_search_without_session_uses_find(delivery, mock_client):
    """Without session_id, search delegates to client.search (find)."""
    delivery.search("test query")
    mock_client.search.assert_called_once()
    mock_client.context_search.assert_not_called()


def test_search_with_session_uses_context_search(delivery, mock_client):
    """With session_id, search delegates to client.context_search."""
    delivery.search("test query", session_id="sess-123")
    mock_client.context_search.assert_called_once()
    args = mock_client.context_search.call_args
    assert args.kwargs["session_id"] == "sess-123"
    mock_client.search.assert_not_called()
