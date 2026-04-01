"""Shared staging utilities for OpenViking batch uploads."""

from __future__ import annotations

from pathlib import Path

import yaml


def write_staged_file(
    base: Path,
    rel_path: str,
    content: str,
    metadata: dict | None = None,
) -> None:
    """Stage a file with optional YAML frontmatter for batch upload.

    Parameters
    ----------
    base
        Root directory of the staging area.
    rel_path
        Relative path within the staging area.
    content
        File content (written after any frontmatter).
    metadata
        Optional metadata dict rendered as YAML frontmatter.
    """
    dest = base / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as fh:
        if metadata:
            fh.write("---\n")
            fh.write(yaml.safe_dump(metadata, sort_keys=True))
            fh.write("---\n\n")
        fh.write(content)
