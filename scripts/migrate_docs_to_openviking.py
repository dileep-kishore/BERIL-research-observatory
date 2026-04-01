#!/usr/bin/env python3
"""Migrate docs/pitfalls.md, docs/research_ideas.md, docs/discoveries.md into OpenViking.

Parses each markdown file into structured entries, enriches them via the
CBORG LLM (gpt-5.4-mini), stages everything locally, and uploads as a
single batch — matching the project ingest pattern.

Also generates collection-level overviews and cross-links to projects.

Usage:
    uv run scripts/migrate_docs_to_openviking.py [--dry-run] [--no-enrich] [--only pitfalls|ideas|discoveries]

Requires CBORG_API_KEY for LLM enrichment (skipped with --no-enrich).
Source markdown files are read from docs/ or from git history if deleted.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from observatory_context._text import slugify
from observatory_context.staging import write_staged_file
from observatory_context.uris import _OPERATIONAL_COLLECTIONS, _ROOT

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Staging helpers (same pattern as viking_ingest.py)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Source file resolution (read from disk or git history)
# ---------------------------------------------------------------------------


def _read_source(rel_path: str) -> str | None:
    """Read a source file from disk or git history."""
    path = REPO_ROOT / rel_path
    if path.exists():
        return path.read_text(encoding="utf-8")
    try:
        result = subprocess.run(
            ["git", "log", "--all", "--diff-filter=d", "--format=%H", "-1", "--", rel_path],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        commit = result.stdout.strip()
        if not commit:
            result = subprocess.run(
                ["git", "log", "--all", "--diff-filter=D", "--format=%H", "-1", "--", rel_path],
                capture_output=True, text=True, cwd=REPO_ROOT,
            )
            commit = result.stdout.strip()
            if commit:
                commit = f"{commit}^"
        if commit:
            result = subprocess.run(
                ["git", "show", f"{commit}:{rel_path}"],
                capture_output=True, text=True, cwd=REPO_ROOT,
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
        entries.append({
            "id": slug, "title": title, "category": category,
            "project_ids": project_ids, "problem": body,
            "solution": solution, "tags": [],
        })
    return entries


def _parse_research_ideas(text: str) -> list[dict]:
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

        approach: list[str] = []
        approach_match = re.search(r"\*\*Approach\*\*:?\s*\n((?:- .+\n?)+)", body)
        if approach_match:
            approach = [
                line.strip("- ").strip()
                for line in approach_match.group(1).strip().split("\n")
                if line.strip().startswith("-")
            ]

        hypotheses: dict[str, str] = {}
        for m in re.finditer(r"-\s+\*\*(\w+)\*\*:?\s*(.+?)(?:\n|$)", body):
            if m.group(1) in ("H1", "H0", "H2", "Hypothesis"):
                hypotheses[m.group(1).lower()] = m.group(2).strip()

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
            "id": slug, "title": title, "status": status.upper(),
            "priority": priority_match.group(1) if priority_match else "MEDIUM",
            "effort": effort_match.group(1).strip() if effort_match else "",
            "research_question": question_match.group(1).strip() if question_match else "",
            "approach": approach, "hypotheses": hypotheses,
            "impact": impact_match.group(1).strip() if impact_match else "",
            "dependencies": deps, "progress": progress, "tags": [],
        }
        if source_project:
            entry["source_project"] = source_project
            entry["project_ids"] = [source_project]
        entries.append(entry)
    return entries


def _parse_discoveries(text: str) -> list[dict]:
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
            "id": slug, "title": title, "description": body,
            "date": current_date, "tags": [],
        }
        if project_id:
            entry["project_ids"] = [project_id]
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Staging (enrich + write to local tree)
# ---------------------------------------------------------------------------


def _stage_entries(
    staging_dir: Path,
    collection: str,
    entries: list[dict],
    extractor=None,
    *,
    enrich: bool = True,
) -> int:
    """Enrich entries via LLM and stage as markdown files in a local tree."""
    from observatory_context.delivery import ContextDelivery

    dir_name = _OPERATIONAL_COLLECTIONS[collection]
    count = 0
    total = len(entries)

    for i, entry in enumerate(entries, 1):
        item_id = entry.pop("id")
        title = entry.get("title", item_id)
        rel_path = f"{dir_name}/{item_id}.md"

        # LLM enrichment
        if enrich and extractor:
            try:
                result = extractor.enrich_operational(collection, entry)
                markdown = result["markdown"]
                metadata = result["metadata"]
            except Exception as exc:
                print(f"  [{i}/{total}] LLM failed for {item_id}: {exc}", file=sys.stderr, flush=True)
                markdown = ContextDelivery._fallback_markdown(collection, entry)
                metadata = ContextDelivery._basic_metadata(collection, entry)
        else:
            markdown = ContextDelivery._fallback_markdown(collection, entry)
            metadata = ContextDelivery._basic_metadata(collection, entry)

        # Ensure core metadata
        metadata.setdefault("title", title)
        metadata.setdefault("kind", collection)

        write_staged_file(staging_dir, rel_path, markdown, metadata=metadata)
        print(f"  [{i}/{total}] {rel_path}", flush=True)
        count += 1

    return count


def _stage_overview(
    staging_dir: Path,
    collection: str,
    entries: list[dict],
    extractor,
) -> bool:
    """Generate and stage a collection-level overview."""
    dir_name = _OPERATIONAL_COLLECTIONS[collection]
    summaries = [f"{e.get('title', '')}: {str(e.get('description', e.get('problem', e.get('research_question', ''))))[:150]}" for e in entries]

    try:
        overview_md = extractor.generate_collection_overview(collection, summaries)
        meta = {"title": f"{collection.replace('_', ' ').title()} Overview", "kind": "overview"}
        write_staged_file(staging_dir, f"{dir_name}/_overview.md", overview_md, metadata=meta)
        return True
    except Exception as exc:
        print(f"  Overview generation failed: {exc}", file=sys.stderr, flush=True)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate docs markdown to OpenViking")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print without uploading")
    parser.add_argument("--no-enrich", action="store_true", help="Skip LLM enrichment")
    parser.add_argument(
        "--only", choices=["pitfalls", "ideas", "discoveries"],
        default=None, help="Migrate only one collection",
    )
    parser.add_argument("--no-overviews", action="store_true", help="Skip collection overview generation")
    args = parser.parse_args(argv)

    collections: dict[str, tuple[str, str, callable]] = {
        "pitfalls": ("pitfall", "docs/pitfalls.md", _parse_pitfalls),
        "ideas": ("research_idea", "docs/research_ideas.md", _parse_research_ideas),
        "discoveries": ("discovery", "docs/discoveries.md", _parse_discoveries),
    }

    if args.only:
        collections = {args.only: collections[args.only]}

    # Parse all sources first
    all_parsed: dict[str, tuple[str, list[dict]]] = {}
    for name, (collection, doc_path, parser_fn) in collections.items():
        text = _read_source(doc_path)
        if text is None:
            print(f"Skipping {name}: {doc_path} not found (on disk or in git history)")
            continue
        entries = parser_fn(text)
        print(f"Parsed {len(entries)} {name} from {doc_path}")
        all_parsed[name] = (collection, entries)

    if not all_parsed:
        print("Nothing to migrate.")
        return 0

    if args.dry_run:
        total = sum(len(entries) for _, entries in all_parsed.values())
        for name, (collection, entries) in all_parsed.items():
            for entry in entries:
                print(f"  [dry-run] {collection}/{entry.get('id', '?')}: {entry.get('title', '?')}")
        print(f"\nDone. Would migrate {total} entries total.")
        return 0

    # Build delivery with extractor
    from observatory_context.runtime import build_delivery

    enrich = not args.no_enrich
    try:
        delivery = build_delivery(require_live=True, with_extractor=enrich)
    except Exception as exc:
        print(f"Error: OpenViking not reachable: {exc}", file=sys.stderr)
        return 1

    extractor = delivery.extractor
    if enrich and not extractor:
        print(
            "Warning: No CBORG extractor configured. "
            "Set CBORG_API_KEY for LLM enrichment, or use --no-enrich.",
            file=sys.stderr,
        )

    # Stage everything locally first (batch pattern)
    staging_dir = Path(tempfile.mkdtemp(prefix="ov_operational_"))
    total = 0

    try:
        for name, (collection, entries) in all_parsed.items():
            print(f"\n--- Staging {name} ({len(entries)} entries) ---", flush=True)
            # Make a copy since _stage_entries pops 'id'
            entries_copy = [dict(e) for e in entries]
            count = _stage_entries(
                staging_dir, collection, entries_copy,
                extractor=extractor, enrich=enrich,
            )
            total += count

            # Generate collection overview
            if not args.no_overviews and extractor:
                print(f"\n  Generating {name} overview...", flush=True)
                if _stage_overview(staging_dir, collection, entries, extractor):
                    print(f"  Overview staged.", flush=True)

        # Count staged files
        file_count = sum(1 for f in staging_dir.rglob("*") if f.is_file())
        print(f"\nStaged {file_count} files in local tree")

        # Batch upload to OpenViking
        print("Uploading batch to OpenViking...", flush=True)
        delivery.client.batch_add(
            path=str(staging_dir),
            to=_ROOT,
            reason="Batch ingest operational knowledge (pitfalls, ideas, discoveries)",
            wait=False,
        )

        print("Waiting for OpenViking to process...", flush=True)
        try:
            delivery.client.wait_until_processed(timeout=300)
            print("Processing complete.")
        except TimeoutError:
            print("Timed out waiting — resources were queued and may still be processing.")

    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)

    print(f"\nDone. Migrated {total} entries total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
