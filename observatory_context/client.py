"""Thin wrapper around the OpenViking HTTP client."""

from __future__ import annotations

import re
import time
from pathlib import Path
from posixpath import splitext
from tempfile import NamedTemporaryFile
from typing import Any

import yaml

from observatory_context.config import ObservatoryContextSettings
from observatory_context.ingest.manifest import ResourceManifestItem


class OpenVikingObservatoryClient:
    """Lazy OpenViking client wrapper used by repo scripts."""

    _STALE_LOCK_IDLE_SECONDS = 30.0
    _TRANSIENT_RETRY_DELAYS = (1.0, 2.0, 4.0)

    def __init__(self, settings: ObservatoryContextSettings) -> None:
        self.settings = settings
        self._client: Any | None = None

    def initialize(self) -> None:
        if self._client is not None:
            return
        try:
            import openviking
        except ImportError as exc:
            raise RuntimeError(
                "openviking is not installed. Run `uv sync` or `uv run --with openviking ...`."
            ) from exc

        self._client = openviking.SyncHTTPClient(
            url=self.settings.openviking_url,
            api_key=self.settings.openviking_api_key,
            agent_id=self.settings.openviking_agent_id,
        )
        self._client.initialize()

    @property
    def client(self) -> Any:
        if self._client is None:
            self.initialize()
        assert self._client is not None
        return self._client

    def add_resource(self, path: str, uri: str, reason: str, wait: bool = True) -> dict[str, Any]:
        return self.client.add_resource(path=path, to=uri, reason=reason, wait=wait)

    def wait_until_processed(self, timeout: float | None = 1800) -> dict[str, Any]:
        """Wait for ingest locks to settle.

        OpenViking's built-in ``wait_processed`` endpoint blocks on the entire
        server queue, which can include unrelated backlog and persistent queue
        errors. For ingest flows we only need the write/point locks to clear so
        subsequent phases can proceed safely.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        stable_polls = 0
        last_active_locks = 0

        while True:
            status = self.get_status()
            last_active_locks = self._active_lock_count(status)
            if last_active_locks == 0:
                stable_polls += 1
                if stable_polls >= 2:
                    return {"status": "settled", "active_locks": 0}
            else:
                stable_polls = 0

            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(
                    "Timed out waiting for OpenViking ingest locks to clear. "
                    f"Active locks remaining: {last_active_locks}."
                )

            remaining = None if deadline is None else max(deadline - time.monotonic(), 0.0)
            time.sleep(1.0 if remaining is None else min(1.0, remaining))

    def list_resources(self, uri: str, recursive: bool = False) -> list[dict[str, Any]]:
        return self.client.ls(uri, recursive=recursive)

    def search(
        self,
        query: str,
        target_uri: str | None = None,
        limit: int = 10,
        score_threshold: float | None = None,
        filter: dict | None = None,
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {"limit": limit}
        if target_uri:
            kwargs["target_uri"] = target_uri
        if score_threshold is not None:
            kwargs["score_threshold"] = score_threshold
        if filter is not None:
            kwargs["filter"] = filter
        return self.client.find(query, **kwargs)

    def context_search(
        self,
        query: str,
        target_uri: str | None = None,
        session_id: str | None = None,
        limit: int = 10,
        score_threshold: float | None = None,
        filter: dict | None = None,
    ) -> list[dict[str, Any]]:
        """Session-aware search using OpenViking's search() (not find()).

        Uses intent analysis and session context for better relevance.
        """
        kwargs: dict[str, Any] = {"limit": limit}
        if target_uri:
            kwargs["target_uri"] = target_uri
        if session_id:
            kwargs["session_id"] = session_id
        if score_threshold is not None:
            kwargs["score_threshold"] = score_threshold
        if filter is not None:
            kwargs["filter"] = filter
        return self.client.search(query, **kwargs)

    def read_resource(self, uri: str) -> str:
        return self.client.read(uri)

    def stat_resource(self, uri: str) -> dict[str, Any]:
        return self.client.stat(uri)

    def resource_exists(self, uri: str) -> bool:
        canonical_markdown_uri = self._canonical_markdown_uri(uri)
        try:
            self.stat_resource(uri)
        except Exception as exc:
            if canonical_markdown_uri is None and not self._is_not_found_error(exc):
                raise
            if canonical_markdown_uri is None:
                return False
            try:
                self.stat_resource(canonical_markdown_uri)
            except Exception as canonical_exc:
                if self._is_not_found_error(canonical_exc):
                    return False
                if self._is_not_found_error(exc):
                    raise canonical_exc
                raise exc
        return True

    def _is_not_found_error(self, exc: Exception) -> bool:
        if any(cls.__name__ == "NotFoundError" for cls in type(exc).__mro__):
            return True
        if any(cls.__name__ == "InternalError" for cls in type(exc).__mro__):
            return "not found" in str(exc).lower()
        return False

    def _canonical_markdown_uri(self, uri: str) -> str | None:
        stem, suffix = splitext(uri)
        if suffix.lower() not in {".md", ".markdown"}:
            return None
        name = Path(uri).name
        directory = stem
        return f"{directory}/{name}"

    def make_directory(self, uri: str) -> None:
        for attempt, delay in enumerate((0.0, *self._TRANSIENT_RETRY_DELAYS), start=1):
            if delay:
                time.sleep(delay)
            try:
                self.client.mkdir(uri)
                return
            except Exception as exc:
                if self._is_already_exists_error(exc):
                    return
                if attempt <= len(self._TRANSIENT_RETRY_DELAYS) and self._is_transient_transport_error(exc):
                    continue
                raise

    def _is_already_exists_error(self, exc: Exception) -> bool:
        if any(cls.__name__ == "AlreadyExistsError" for cls in type(exc).__mro__):
            return True
        if any(cls.__name__ == "InternalError" for cls in type(exc).__mro__):
            return "already exists" in str(exc).lower()
        return False

    def _is_transient_transport_error(self, exc: Exception) -> bool:
        transient_names = {
            "ReadError",
            "WriteError",
            "ConnectError",
            "ReadTimeout",
            "WriteTimeout",
            "ConnectTimeout",
            "PoolTimeout",
            "RemoteProtocolError",
            "TransportError",
        }
        return any(cls.__name__ in transient_names for cls in type(exc).__mro__)

    def health(self) -> bool:
        return bool(self.client.health())

    def get_status(self) -> dict[str, Any]:
        return dict(self.client.get_status())

    def _active_lock_count(self, status: dict[str, Any]) -> int:
        lock_component = status.get("components", {}).get("lock", {})
        lock_status = lock_component.get("status", "")
        if "no active locks" in lock_status.lower():
            return 0
        parsed_rows = 0
        active_locks = 0

        for line in lock_status.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            columns = [column.strip() for column in stripped.strip("|").split("|")]
            if len(columns) < 5:
                continue
            handle_id = columns[0]
            if handle_id in {"Handle ID", ""} or handle_id.startswith("TOTAL"):
                continue
            parsed_rows += 1
            idle_seconds = self._parse_duration_seconds(columns[3])
            if idle_seconds is None or idle_seconds < self._STALE_LOCK_IDLE_SECONDS:
                active_locks += 1

        if parsed_rows:
            return active_locks

        match = re.search(r"TOTAL \((\d+)\)", lock_status)
        if match is None:
            raise RuntimeError("Unable to parse OpenViking lock status")
        return int(match.group(1))

    def _parse_duration_seconds(self, value: str) -> float | None:
        match = re.fullmatch(r"(?P<amount>\d+(?:\.\d+)?)(?P<unit>[smhd])", value.strip())
        if match is None:
            return None
        amount = float(match.group("amount"))
        unit = match.group("unit")
        factors = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
        return amount * factors[unit]

    def link_resources(self, from_uri: str, uris: list[str], reason: str = "") -> None:
        self.client.link(from_uri, uris=uris, reason=reason)

    def relations(self, uri: str) -> list[dict[str, Any]]:
        return self.client.relations(uri)

    def grep(self, uri: str, pattern: str, case_insensitive: bool = False) -> dict[str, Any]:
        return self.client.grep(uri, pattern, case_insensitive=case_insensitive)

    def glob(self, pattern: str, uri: str = "viking://") -> dict[str, Any]:
        return self.client.glob(pattern, uri=uri)

    def abstract(self, uri: str) -> str:
        return self.client.abstract(uri)

    def overview(self, uri: str) -> str:
        return self.client.overview(uri)

    def add_text_resource(
        self,
        uri: str,
        content: str,
        metadata: dict[str, Any],
        reason: str,
        wait: bool = True,
    ) -> dict[str, Any]:
        with NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write("---\n")
            handle.write(yaml.safe_dump(metadata, sort_keys=True))
            handle.write("---\n\n")
            handle.write(content)
        try:
            return self.add_resource(path=str(temp_path), uri=uri, reason=reason, wait=wait)
        finally:
            temp_path.unlink(missing_ok=True)

    def write_content(self, uri: str, content: str) -> None:
        """Write content directly to a URI without temp files.

        Uses the OpenViking filesystem write API when available,
        falling back to add_text_resource with a temp file.
        """
        if hasattr(self.client, 'write'):
            self.client.write(uri, content.encode("utf-8"))
        else:
            self.add_text_resource(
                uri=uri, content=content, metadata={},
                reason="Direct content write", wait=False,
            )

    def rm(self, uri: str, recursive: bool = False) -> None:
        """Remove a resource or directory."""
        self.client.rm(uri, recursive=recursive)

    def unlink_resources(self, from_uri: str, to_uri: str) -> None:
        """Remove a relation between two resources."""
        self.client.unlink(from_uri, to_uri)

    def batch_add(
        self,
        path: str,
        to: str,
        reason: str,
        wait: bool = False,
        timeout: float | None = None,
        preserve_structure: bool | None = None,
    ) -> dict[str, Any]:
        """Upload a local directory tree as a batch to a target URI."""
        if preserve_structure is None:
            return self.client.add_resource(path=path, to=to, reason=reason, wait=wait, timeout=timeout)

        from openviking_cli.utils.async_utils import run_async

        return run_async(
            self.client._async_client.add_resource(
                path=path,
                to=to,
                reason=reason,
                wait=wait,
                timeout=timeout,
                preserve_structure=preserve_structure,
            )
        )

    def create_session(self) -> Any:
        """Create a new OpenViking session object."""
        return self.client.session()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Poll a background task by ID."""
        return self.client.get_task(task_id)

    def add_manifest_resource(self, item: ResourceManifestItem, wait: bool = True) -> dict[str, Any]:
        source_path = Path(item.source_path)
        if item.kind == "figure":
            caption = item.metadata.get("caption") or item.metadata.get("title") or source_path.name
            content = f"Figure resource for {caption}\nSource artifact: {source_path}\n"
        else:
            content = source_path.read_text(encoding="utf-8")
        return self.add_text_resource(
            uri=item.uri,
            content=content,
            metadata=item.metadata,
            reason=f"Ingest {item.kind} from BERIL observatory manifest",
            wait=wait,
        )
