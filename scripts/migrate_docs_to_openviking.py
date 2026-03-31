#!/usr/bin/env python3
"""Migrate docs/pitfalls.md, docs/research_ideas.md, docs/discoveries.md into OpenViking.

Parses each markdown file into structured entries, enriches them via the
CBORG LLM (gpt-5.4-mini), and uploads as clean markdown resources with
proper frontmatter.  Also generates collection-level overviews.

Usage:
    uv run scripts/migrate_docs_to_openviking.py [--dry-run] [--no-enrich] [--only pitfalls|ideas|discoveries]

Requires CBORG_API_KEY for LLM enrichment (skipped with --no-enrich).
Source markdown files are read from git history if they no longer exist on disk.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from observatory_context._text import slugify

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Source file resolution (read from git if deleted)
# ---------------------------------------------------------------------------


def _read_source(rel_path: str) -> str | None:
    """Read a source file from disk or git history."""
    path = REPO_ROOT / rel_path
    if path.exists():
        return path.read_text(encoding="utf-8")
    # Try git history — find the last commit where the file existed
    try:
        result = subprocess.run(
            ["git", "log", "--all", "--diff-filter=d", "--format=%H", "-1", "--", rel_path],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        commit = result.stdout.strip()
        if not commit:
            # Fallback: get the commit that deleted it, then use its parent
            result = subprocess.run(
                ["git", "log", "--all", "--diff-filter=D", "--format=%H", "-1", "--", rel_path],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            commit = result.stdout.strip()
            if commit:
                commit = f"{commit}^"
        if commit:
            result = subprocess.run(
                ["git", "show", f"{commit}:{rel_path}"],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            if result.returncode == 0:
                return result.stdout
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_pitfalls(text: str) -> list[dict]:
    """Parse docs/pitfalls.md into individual pitfall entries."""
    entries: list[dict] = []
    parts = re.split(r"(?=^### )", text, flags=re.MULTILINE)
    category = "General"

    for part in parts:
        cat_match = re.match(r"^## (.+)$", part, re.MULTILINE)
        if cat_match and not part.startswith("###"):
            category = cat_match.group(1).strip()
            continue

        heading_match = re.match(r"^### (.+)$", part, re.MULTILINE)
        if not heading_match:
            embedded_cat = re.search(r"^## (.+)$", part, re.MULTILINE)
            if embedded_cat:
                category = embedded_cat.group(1).strip()
            continue

        title = heading_match.group(1).strip().strip("`")
        body = part[heading_match.end() :].strip()

        project_match = re.match(r"\*\*\[(\w+)\]\*\*", body)
        project_ids = [project_match.group(1)] if project_match else []

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

        status_match = re.search(r"\*\*Status\*\*:?\s*(\w+)", body)
        priority_match = re.search(r"\*\*Priority\*\*:?\s*(\w+)", body)
        effort_match = re.search(r"\*\*Effort\*\*:?\s*(.+?)(?:\n|$)", body)
        question_match = re.search(
            r"\*\*Research Question\*\*:?\s*(.+?)(?:\n\n|\n\*\*)", body, re.DOTALL
        )
        impact_match = re.search(r"\*\*Impact\*\*:?\s*(.+?)(?:\n\n|\n\*\*)", body, re.DOTALL)
        location_match = re.search(r"\*\*Location\*\*:?\s*`?([^`\n]+)`?", body)

        approach: list[str] = []
        approach_match = re.search(r"\*\*Approach\*\*:?\s*\n((?:- .+\n?)+)", body)
        if approach_match:
            approach = [
                line.strip("- ").strip()
                for line in approach_match.group(1).strip().split("\n")
                if line.strip().startswith("-")
            ]

        hypotheses: dict[str, str] = {}
        hyp_matches = re.finditer(r"-\s+\*\*(\w+)\*\*:?\s*(.+?)(?:\n|$)", body)
        for m in hyp_matches:
            key = m.group(1)
            if key in ("H1", "H0", "H2", "Hypothesis"):
                hypotheses[key.lower()] = m.group(2).strip()

        deps: list[str] = []
        deps_match = re.search(r"\*\*Dependencies\*\*:?\s*\n((?:- .+\n?)+)", body)
        if deps_match:
            deps = [
                line.strip("- ").strip()
                for line in deps_match.group(1).strip().split("\n")
                if line.strip().startswith("-")
            ]

        progress: list[str] = []
        progress_match = re.search(r"\*\*Progress\*\*:?\s*\n((?:- .+\n?)+)", body)
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
            entry["project_ids"] = [source_project]
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
        date_match = re.search(r"^## (\d{4}-\d{2})$", part, re.MULTILINE)
        if date_match:
            current_date = date_match.group(1)
            continue

        heading_match = re.match(r"^### (?:\[(\w+)\] )?(.+)$", part, re.MULTILINE)
        if not heading_match:
            continue

        project_id = heading_match.group(1) or ""
        title = heading_match.group(2).strip()
        body = part[heading_match.end() :].strip()
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
    enrich: bool = True,
) -> int:
    """Upload parsed entries to OpenViking via ContextDelivery."""
    count = 0
    total = len(entries)
    for i, entry in enumerate(entries, 1):
        item_id = entry.pop("id")
        title = entry.get("title", item_id)
        if dry_run:
            print(f"  [{i}/{total}] [dry-run] {collection}/{item_id}: {title}")
            count += 1
            continue

        try:
            uri = delivery.add_operational(
                collection, item_id, entry, enrich=enrich, wait=False,
            )
            print(f"  [{i}/{total}] {uri}")
            count += 1
        except Exception as exc:
            print(f"  [{i}/{total}] ERROR {item_id}: {exc}", file=sys.stderr)
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate docs markdown to OpenViking")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print without uploading")
    parser.add_argument("--no-enrich", action="store_true", help="Skip LLM enrichment")
    parser.add_argument(
        "--only",
        choices=["pitfalls", "ideas", "discoveries"],
        default=None,
        help="Migrate only one collection",
    )
    parser.add_argument(
        "--overviews", action="store_true",
        help="Generate collection-level overviews after migration",
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
            delivery = build_delivery(require_live=True, with_extractor=not args.no_enrich)
        except Exception as exc:
            print(f"Error: OpenViking not reachable: {exc}", file=sys.stderr)
            return 1

        if not args.no_enrich and not delivery.extractor:
            print(
                "Warning: No CBORG extractor configured. "
                "Set CBORG_API_KEY for LLM enrichment, or use --no-enrich.",
                file=sys.stderr,
            )

    enrich = not args.no_enrich
    total = 0

    for name, (collection, doc_path, parser_fn) in collections.items():
        text = _read_source(doc_path)
        if text is None:
            print(f"Skipping {name}: {doc_path} not found (on disk or in git history)")
            continue

        print(f"\n--- Migrating {name} from {doc_path} ---")
        entries = parser_fn(text)
        print(f"Parsed {len(entries)} entries")

        count = _upload_entries(
            delivery, collection, entries,
            dry_run=args.dry_run, enrich=enrich,
        )
        total += count

    if not args.dry_run and delivery:
        print("\nWaiting for OpenViking to process...")
        try:
            delivery.client.wait_until_processed(timeout=300)
            print("Processing complete.")
        except TimeoutError:
            print("Timed out waiting — resources were queued and may still be processing.")

        # Generate collection overviews
        if args.overviews:
            print("\n--- Generating collection overviews ---")
            for name, (collection, _, _) in collections.items():
                try:
                    uri = delivery.add_collection_overview(collection)
                    if uri:
                        print(f"  {name} overview: {uri}")
                    else:
                        print(f"  {name} overview: skipped (no extractor or no items)")
                except Exception as exc:
                    print(f"  {name} overview ERROR: {exc}", file=sys.stderr)

    print(f"\nDone. Migrated {total} entries total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
