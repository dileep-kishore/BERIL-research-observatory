"""Tests for BatchUploader — batch upload orchestration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from observatory_context.ingest.batch import BatchUploader


@pytest.fixture()
def mock_client():
    return MagicMock()


@pytest.fixture()
def uploader(mock_client):
    return BatchUploader(client=mock_client)


def test_stage_file(uploader, tmp_path):
    staged = uploader.stage(tmp_path, "notes/entry.md", "# Hello")
    assert staged == tmp_path / "notes/entry.md"
    assert staged.exists()
    assert "# Hello" in staged.read_text()


def test_stage_file_with_metadata(uploader, tmp_path):
    staged = uploader.stage(
        tmp_path,
        "notes/entry.md",
        "Body text",
        metadata={"title": "Test Entry", "kind": "note"},
    )
    content = staged.read_text()
    assert "---" in content
    assert "title: Test Entry" in content
    assert "kind: note" in content
    assert "Body text" in content


def test_upload_calls_batch_add(uploader, mock_client, tmp_path):
    uploader.stage(tmp_path, "a.md", "content A")
    uploader.upload(tmp_path, "viking://resources/observatory/projects/p1", "test upload")
    mock_client.batch_add.assert_called_once_with(
        path=str(tmp_path),
        to="viking://resources/observatory/projects/p1",
        reason="test upload",
        wait=False,
        timeout=None,
        preserve_structure=None,
    )
    mock_client.wait_until_processed.assert_not_called()


def test_upload_and_wait(uploader, mock_client, tmp_path):
    uploader.stage(tmp_path, "b.md", "content B")
    uploader.upload(
        tmp_path,
        "viking://resources/observatory/projects/p1",
        "test upload with wait",
        wait=True,
        timeout=30.0,
    )
    mock_client.batch_add.assert_called_once_with(
        path=str(tmp_path),
        to="viking://resources/observatory/projects/p1",
        reason="test upload with wait",
        wait=False,
        timeout=30.0,
        preserve_structure=None,
    )
    mock_client.wait_until_processed.assert_called_once_with(timeout=30.0)


def test_upload_retries_on_lock_contention(uploader, mock_client, tmp_path, monkeypatch):
    import observatory_context.ingest.batch as batch_module

    sleeps: list[int] = []
    uploader.stage(tmp_path, "c.md", "content C")
    mock_client.batch_add.side_effect = [
        RuntimeError("Failed to acquire point lock for ['/local/default/resources/observatory']"),
        None,
    ]
    monkeypatch.setattr(batch_module.time, "sleep", sleeps.append)

    uploader.upload(tmp_path, "viking://resources/observatory/wiki", "retry upload")

    assert mock_client.batch_add.call_count == 2
    assert sleeps == [1]
