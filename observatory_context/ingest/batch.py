"""Batch upload orchestration for lock-free OpenViking ingest."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from observatory_context.staging import write_staged_file

logger = logging.getLogger(__name__)


class BatchUploader:
    """Stage files locally, then upload them as a single batch to OpenViking.

    Parameters
    ----------
    client
        An ``OpenVikingObservatoryClient`` instance (or compatible mock).
    """

    def __init__(self, client: object) -> None:
        self.client = client

    def stage(
        self,
        staging_dir: Path,
        rel_path: str,
        content: str,
        metadata: dict | None = None,
    ) -> Path:
        """Write a file into the staging area.

        Parameters
        ----------
        staging_dir
            Root directory of the staging area.
        rel_path
            Relative path within the staging area.
        content
            File content.
        metadata
            Optional metadata rendered as YAML frontmatter.

        Returns
        -------
        Path
            Absolute path to the staged file.
        """
        write_staged_file(staging_dir, rel_path, content, metadata)
        return staging_dir / rel_path

    def upload(
        self,
        staging_dir: Path,
        target_uri: str,
        reason: str,
        wait: bool = False,
        timeout: float | None = None,
        preserve_structure: bool | None = None,
    ) -> None:
        """Upload the staging directory to OpenViking.

        Parameters
        ----------
        staging_dir
            Local directory containing staged files.
        target_uri
            Destination URI in the OpenViking namespace.
        reason
            Human-readable reason for this ingest operation.
        wait
            If ``True``, block until OpenViking confirms processing.
        timeout
            Maximum seconds to wait when ``wait=True``.
        """
        retry_delays = (1, 2, 4, 8, 16, 30, 30, 30, 30, 30, 30, 30)
        for attempt, delay in enumerate((0, *retry_delays), start=1):
            if delay:
                logger.warning(
                    "Batch upload lock contention for %s, retrying in %ds (attempt %d/%d)",
                    target_uri,
                    delay,
                    attempt,
                    len(retry_delays) + 1,
                )
                time.sleep(delay)
            try:
                self.client.batch_add(
                    path=str(staging_dir),
                    to=target_uri,
                    reason=reason,
                    wait=False,
                    timeout=timeout,
                    preserve_structure=preserve_structure,
                )
                break
            except Exception as exc:
                if "lock" in str(exc).lower() and attempt <= len(retry_delays):
                    continue
                raise
        if wait:
            self.client.wait_until_processed(timeout=timeout)
