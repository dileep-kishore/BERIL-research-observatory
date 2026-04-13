"""Tests for the OpenViking client wrapper."""

from __future__ import annotations

from collections import deque

import pytest
from openviking_cli.exceptions import AlreadyExistsError, InternalError

from observatory_context.client import OpenVikingObservatoryClient
from observatory_context.config import ObservatoryContextSettings


class _FakeMkdirClient:
    def __init__(self, exc: Exception | None = None, exceptions: list[Exception] | None = None) -> None:
        self.exc = exc
        self.exceptions = deque(exceptions or [])
        self.calls: list[str] = []

    def mkdir(self, uri: str) -> None:
        self.calls.append(uri)
        if self.exceptions:
            raise self.exceptions.popleft()
        if self.exc is not None:
            raise self.exc


class _FakeStatClient:
    def __init__(self, responses: dict[str, dict[str, str] | Exception] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[str] = []

    def stat(self, uri: str) -> dict[str, str]:
        self.calls.append(uri)
        response = self.responses.get(uri, {"uri": uri})
        if isinstance(response, Exception):
            raise response
        return response


class _FakeStatusClient:
    def __init__(self, lock_counts: list[int]) -> None:
        self.lock_counts = deque(lock_counts)

    def get_status(self) -> dict[str, object]:
        count = self.lock_counts[0] if len(self.lock_counts) == 1 else self.lock_counts.popleft()
        return {
            "components": {
                "lock": {
                    "status": f"| TOTAL ({count}) |",
                }
            }
        }


def _make_client(fake: object) -> OpenVikingObservatoryClient:
    client = OpenVikingObservatoryClient(
        ObservatoryContextSettings(openviking_url="http://localhost:1933")
    )
    client._client = fake
    return client


@pytest.mark.parametrize(
    "exc",
    [
        AlreadyExistsError("viking://resources/observatory/example", "resource"),
        InternalError("already exists: /default/resources/observatory/example"),
    ],
)
def test_make_directory_ignores_already_exists_errors(exc: Exception) -> None:
    fake = _FakeMkdirClient(exc=exc)
    client = _make_client(fake)

    client.make_directory("viking://resources/observatory/example")

    assert fake.calls == ["viking://resources/observatory/example"]


def test_make_directory_reraises_other_internal_errors() -> None:
    fake = _FakeMkdirClient(exc=InternalError("database unavailable"))
    client = _make_client(fake)

    with pytest.raises(InternalError, match="database unavailable"):
        client.make_directory("viking://resources/observatory/example")


def test_make_directory_retries_transient_read_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReadError(Exception):
        pass

    fake = _FakeMkdirClient(exceptions=[ReadError("boom"), ReadError("boom")])
    client = _make_client(fake)
    sleeps: list[float] = []

    monkeypatch.setattr("observatory_context.client.time.sleep", sleeps.append)

    client.make_directory("viking://resources/observatory/example")

    assert fake.calls == [
        "viking://resources/observatory/example",
        "viking://resources/observatory/example",
        "viking://resources/observatory/example",
    ]
    assert sleeps == [1.0, 2.0]


@pytest.mark.parametrize(
    "exc",
    [
        InternalError("not found: /default/resources/observatory/example"),
    ],
)
def test_resource_exists_handles_internal_not_found_as_false(exc: Exception) -> None:
    fake = _FakeStatClient(
        responses={"viking://resources/observatory/example": exc}
    )
    client = _make_client(fake)

    assert client.resource_exists("viking://resources/observatory/example") is False
    assert fake.calls == ["viking://resources/observatory/example"]


def test_resource_exists_handles_canonical_markdown_path() -> None:
    fake = _FakeStatClient(
        responses={
            "viking://resources/observatory/projects/proj/authored/README.md": InternalError(
                "not found: /default/resources/observatory/projects/proj/authored/README.md"
            ),
            "viking://resources/observatory/projects/proj/authored/README/README.md": {
                "uri": "viking://resources/observatory/projects/proj/authored/README/README.md"
            },
        }
    )
    client = _make_client(fake)

    assert client.resource_exists(
        "viking://resources/observatory/projects/proj/authored/README.md"
    ) is True
    assert fake.calls == [
        "viking://resources/observatory/projects/proj/authored/README.md",
        "viking://resources/observatory/projects/proj/authored/README/README.md",
    ]


def test_wait_until_processed_waits_for_lock_settlement(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeStatusClient([2, 1, 0, 0])
    client = _make_client(fake)
    sleeps: list[float] = []

    monkeypatch.setattr("observatory_context.client.time.sleep", sleeps.append)

    result = client.wait_until_processed(timeout=10)

    assert result == {"status": "settled", "active_locks": 0}
    assert sleeps == [1.0, 1.0, 1.0]


def test_wait_until_processed_times_out_when_locks_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeStatusClient([1])
    client = _make_client(fake)
    monotonic_values = iter([0.0, 0.0, 1.0, 1.0, 2.0, 2.0])

    monkeypatch.setattr("observatory_context.client.time.sleep", lambda _: None)
    monkeypatch.setattr("observatory_context.client.time.monotonic", lambda: next(monotonic_values))

    with pytest.raises(TimeoutError, match="ingest locks to clear"):
        client.wait_until_processed(timeout=1)


def test_active_lock_count_ignores_stale_idle_locks() -> None:
    client = _make_client(object())

    status = {
        "components": {
            "lock": {
                "status": (
                    "+-------------+-------+----------+--------+----------+\n"
                    "|  Handle ID  | Locks | Duration |  Idle  | Created  |\n"
                    "+-------------+-------+----------+--------+----------+\n"
                    "| 22deb416... |   1   |  845.7s  | 95.1s  | 21:08:47 |\n"
                    "| a60d0ad1... |   1   |  284.3s  | 12.3s  | 21:18:09 |\n"
                    "|  TOTAL (2)  |   2   |          |        |          |\n"
                    "+-------------+-------+----------+--------+----------+"
                )
            }
        }
    }

    assert client._active_lock_count(status) == 1


def test_active_lock_count_handles_no_active_locks_message() -> None:
    client = _make_client(object())

    status = {"components": {"lock": {"status": "No active locks."}}}

    assert client._active_lock_count(status) == 0
