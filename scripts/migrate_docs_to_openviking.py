#!/usr/bin/env python3
"""Migrate docs/pitfalls.md, docs/research_ideas.md, docs/discoveries.md into OpenViking.

Parses each markdown file into structured entries and uploads them as
operational knowledge resources via ContextDelivery.

Usage:
    uv run scripts/migrate_docs_to_openviking.py [--dry-run] [--only pitfalls|ideas|discoveries]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from textwrap import dedent

from observatory_context._text import slugify

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_pitfalls(text: str) -> list[dict]:
    """Parse docs/pitfalls.md into individual pitfall entries."""
    entries: list[dict] = []
    # Split on ### headings (pitfall entries)
    parts = re.split(r"(?=^### )", text, flags=re.MULTILINE)

    # Determine current category from ## headings
    category = "General"
    for part in parts:
        # Check if this chunk starts with a ## heading (section boundary)
        cat_match = re.match(r"^## (.+)$", part, re.MULTILINE)
        if cat_match and not part.startswith("###"):
            category = cat_match.group(1).strip()
            continue

        heading_match = re.match(r"^### (.+)$", part, re.MULTILINE)
        if not heading_match:
            # Check for embedded ## category change
            embedded_cat = re.search(r"^## (.+)$", part, re.MULTILINE)
            if embedded_cat:
                category = embedded_cat.group(1).strip()
            continue

        title = heading_match.group(1).strip().strip("`")
        body = part[heading_match.end() :].strip()

        # Extract project tag if present
        project_match = re.match(r"\*\*\[(\w+)\]\*\*", body)
        project_ids = [project_match.group(1)] if project_match else []

        # Extract solution line
        solution_match = re.search(
            r"\*\*(?:Solution|Fix|Rule of thumb)\*\*:?\s*(.+?)(?:\n|$)", body
        )
        solution = solution_match.group(1).strip() if solution_match else ""

        slug = slugify(title)[:80]
        entries.append(
            {
                "id": slug,
                "title": title,
                "category": category,
                "project_ids": project_ids,
                "problem": body,
                "solution": solution,
                "tags": [],
            }
        )

    return entries


def _parse_research_ideas(text: str) -> list[dict]:
    """Parse docs/research_ideas.md into individual idea entries."""
    entries: list[dict] = []
    parts = re.split(r"(?=^### )", text, flags=re.MULTILINE)

    for part in parts:
        heading_match = re.match(r"^### (?:\[(\w+)\] )?(.+)$", part, re.MULTILINE)
        if not heading_match:
            continue

        source_project = heading_match.group(1) or ""
        title = heading_match.group(2).strip()
        body = part[heading_match.end() :].strip()

        # Extract structured fields
        status_match = re.search(r"\*\*Status\*\*:?\s*(\w+)", body)
        priority_match = re.search(r"\*\*Priority\*\*:?\s*(\w+)", body)
        effort_match = re.search(r"\*\*Effort\*\*:?\s*(.+?)(?:\n|$)", body)
        question_match = re.search(
            r"\*\*Research Question\*\*:?\s*(.+?)(?:\n\n|\n\*\*)", body, re.DOTALL
        )
        impact_match = re.search(r"\*\*Impact\*\*:?\s*(.+?)(?:\n\n|\n\*\*)", body, re.DOTALL)
        location_match = re.search(r"\*\*Location\*\*:?\s*`?([^`\n]+)`?", body)

        # Extract approach
        approach: list[str] = []
        approach_match = re.search(
            r"\*\*Approach\*\*:?\s*\n((?:- .+\n?)+)", body
        )
        if approach_match:
            approach = [
                line.strip("- ").strip()
                for line in approach_match.group(1).strip().split("\n")
                if line.strip().startswith("-")
            ]

        # Extract hypotheses
        hypotheses: dict[str, str] = {}
        hyp_matches = re.finditer(
            r"-\s+\*\*(\w+)\*\*:?\s*(.+?)(?:\n|$)", body
        )
        for m in hyp_matches:
            key = m.group(1)
            if key in ("H1", "H0", "H2", "Hypothesis"):
                hypotheses[key.lower()] = m.group(2).strip()

        # Extract dependencies
        deps: list[str] = []
        deps_match = re.search(
            r"\*\*Dependencies\*\*:?\s*\n((?:- .+\n?)+)", body
        )
        if deps_match:
            deps = [
                line.strip("- ").strip()
                for line in deps_match.group(1).strip().split("\n")
                if line.strip().startswith("-")
            ]

        # Extract progress
        progress: list[str] = []
        progress_match = re.search(
            r"\*\*Progress\*\*:?\s*\n((?:- .+\n?)+)", body
        )
        if progress_match:
            progress = [
                line.strip("- ").strip()
                for line in progress_match.group(1).strip().split("\n")
                if line.strip().startswith("-")
            ]

        status = status_match.group(1) if status_match else "PROPOSED"
        slug = slugify(title)[:80]

        entry: dict = {
            "id": slug,
            "title": title,
            "status": status.upper(),
            "priority": priority_match.group(1) if priority_match else "MEDIUM",
            "effort": effort_match.group(1).strip() if effort_match else "",
            "research_question": question_match.group(1).strip() if question_match else "",
            "approach": approach,
            "hypotheses": hypotheses,
            "impact": impact_match.group(1).strip() if impact_match else "",
            "dependencies": deps,
            "progress": progress,
            "tags": [],
        }
        if source_project:
            entry["source_project"] = source_project
        if location_match:
            entry["location"] = location_match.group(1).strip()

        entries.append(entry)

    return entries


def _parse_discoveries(text: str) -> list[dict]:
    """Parse docs/discoveries.md into individual discovery entries."""
    entries: list[dict] = []
    current_date = ""

    parts = re.split(r"(?=^### )", text, flags=re.MULTILINE)

    for part in parts:
        # Check for date section
        date_match = re.search(r"^## (\d{4}-\d{2})$", part, re.MULTILINE)
        if date_match:
            current_date = date_match.group(1)
            continue

        heading_match = re.match(
            r"^### (?:\[(\w+)\] )?(.+)$", part, re.MULTILINE
        )
        if not heading_match:
            continue

        project_id = heading_match.group(1) or ""
        title = heading_match.group(2).strip()
        body = part[heading_match.end() :].strip()

        # Remove trailing --- separators
        body = re.sub(r"\n---\s*$", "", body).strip()

        slug = slugify(title)[:80]
        entry: dict = {
            "id": slug,
            "title": title,
            "description": body,
            "date": current_date,
            "tags": [],
        }
        if project_id:
            entry["project_ids"] = [project_id]

        entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


def _upload_entries(
    delivery,
    collection: str,
    entries: list[dict],
    *,
    dry_run: bool = False,
) -> int:
    """Upload parsed entries to OpenViking."""
    count = 0
    for entry in entries:
        item_id = entry.pop("id")
        if dry_run:
            print(f"  [dry-run] {collection}/{item_id}: {entry.get('title', '')}")
            count += 1
            continue

        try:
            uri = delivery.add_operational(collection, item_id, entry, wait=False)
            print(f"  {uri}")
            count += 1
        except Exception as exc:
            print(f"  ERROR {item_id}: {exc}", file=sys.stderr)

    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate docs markdown to OpenViking")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print without uploading")
    parser.add_argument(
        "--only",
        choices=["pitfalls", "ideas", "discoveries"],
        default=None,
        help="Migrate only one collection",
    )
    args = parser.parse_args(argv)

    collections: dict[str, tuple[str, str, callable]] = {
        "pitfalls": ("pitfall", "docs/pitfalls.md", _parse_pitfalls),
        "ideas": ("research_idea", "docs/research_ideas.md", _parse_research_ideas),
        "discoveries": ("discovery", "docs/discoveries.md", _parse_discoveries),
    }

    if args.only:
        collections = {args.only: collections[args.only]}

    delivery = None
    if not args.dry_run:
        from observatory_context.runtime import build_delivery

        try:
            delivery = build_delivery(require_live=True)
        except Exception as exc:
            print(f"Error: OpenViking not reachable: {exc}", file=sys.stderr)
            return 1

    total = 0
    for name, (collection, doc_path, parser_fn) in collections.items():
        path = REPO_ROOT / doc_path
        if not path.exists():
            print(f"Skipping {name}: {path} not found")
            continue

        print(f"\n--- Migrating {name} from {doc_path} ---")
        text = path.read_text(encoding="utf-8")
        entries = parser_fn(text)
        print(f"Parsed {len(entries)} entries")

        count = _upload_entries(delivery, collection, entries, dry_run=args.dry_run)
        total += count

    if not args.dry_run and delivery:
        print("\nWaiting for OpenViking to process...")
        try:
            delivery.client.wait_until_processed(timeout=120)
        except TimeoutError:
            print("Timed out waiting — resources were queued and may still be processing.")

    print(f"\nDone. Migrated {total} entries total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
