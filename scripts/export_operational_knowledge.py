#!/usr/bin/env python3
"""Export operational knowledge (pitfalls, research ideas, discoveries) from OpenViking to YAML.

Recreates local YAML files from OpenViking as the source of truth.

Usage:
    uv run scripts/export_operational_knowledge.py [--output-dir DIR] [--only pitfalls|ideas|discoveries]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from observatory_context.models import Tier


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export operational knowledge from OpenViking to YAML"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/operational-knowledge-export"),
        help="Output directory (default: data/operational-knowledge-export)",
    )
    parser.add_argument(
        "--only",
        choices=["pitfalls", "ideas", "discoveries"],
        default=None,
        help="Export only one collection",
    )
    args = parser.parse_args(argv)

    from observatory_context.runtime import build_delivery

    try:
        delivery = build_delivery(require_live=True)
    except Exception as exc:
        print(f"Error: OpenViking not reachable: {exc}", file=sys.stderr)
        return 1

    collections = {
        "pitfalls": "pitfall",
        "ideas": "research_idea",
        "discoveries": "discovery",
    }

    if args.only:
        collections = {args.only: collections[args.only]}

    output_dir: Path = args.output_dir
    total = 0

    for name, collection in collections.items():
        print(f"\n--- Exporting {name} ---")
        items = delivery.list_operational(collection, tier=Tier.L2)

        if not items:
            print(f"  No {name} found in OpenViking.")
            continue

        coll_dir = output_dir / name
        coll_dir.mkdir(parents=True, exist_ok=True)

        for item in items:
            # Parse YAML body from content
            content = item.content
            try:
                data = yaml.safe_load(content)
            except yaml.YAMLError:
                data = {"title": item.title, "content": content}

            if not isinstance(data, dict):
                data = {"title": item.title, "content": str(data)}

            # Derive filename from URI
            slug = item.uri.rstrip("/").rsplit("/", 2)[-2]  # parent dir is the slug
            out_path = coll_dir / f"{slug}.yaml"

            out_path.write_text(
                yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            print(f"  {out_path}")
            total += 1

    print(f"\nExported {total} entries to {output_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
