"""Render and persist a verification report for an OpenViking ingest run."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from observatory_context.client import OpenVikingObservatoryClient
from observatory_context.config import ObservatoryContextSettings
from observatory_context.ingest import build_resource_manifest
from observatory_context.ingest.manifest import ResourceManifestItem
from observatory_context.uris import build_observatory_root_uri, build_wiki_log_uri

console = Console()
REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = REPO_ROOT / "data" / "ingest" / "runs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a verification report for an ingest run.")
    parser.add_argument("--run-id", default=None, help="Specific run ID under data/ingest/runs/")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional report path. Defaults to data/ingest/runs/<run-id>/verification_report.md",
    )
    return parser


def _latest_run_dir() -> Path:
    runs = sorted((path for path in RUNS_ROOT.iterdir() if path.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        raise FileNotFoundError(f"No ingest runs found under {RUNS_ROOT}")
    return runs[0]


def _load_checkpoint(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))


def _namespace_status(client: OpenVikingObservatoryClient, uri: str) -> tuple[bool, int | None, str | None]:
    try:
        items = client.list_resources(uri, recursive=False)
        return True, len(items), None
    except Exception as exc:
        return False, None, f"{type(exc).__name__}: {exc}"


def _load_descendants(
    client: OpenVikingObservatoryClient,
    cache: dict[str, list[dict[str, Any]]],
    parent_uri: str,
) -> list[dict[str, Any]]:
    if parent_uri not in cache:
        try:
            cache[parent_uri] = client.list_resources(parent_uri, recursive=True)
        except Exception:
            cache[parent_uri] = []
    return cache[parent_uri]


def _verify_manifest_item(
    client: OpenVikingObservatoryClient,
    item: ResourceManifestItem,
    descendant_cache: dict[str, list[dict[str, Any]]],
) -> bool:
    source_name = Path(item.source_path).name
    if source_name == "README.md":
        parent_uri = item.uri.rsplit("/", 1)[0]
        return any(entry.get("name") == "README.md" for entry in _load_descendants(client, descendant_cache, parent_uri))
    if source_name == "REPORT.md":
        parent_uri = item.uri.rsplit("/", 1)[0]
        descendants = _load_descendants(client, descendant_cache, parent_uri)
        return any(
            entry.get("name") == "REPORT.md"
            or str(entry.get("name", "")).startswith("Report_")
            or "Report_" in str(entry.get("rel_path", ""))
            for entry in descendants
        )
    try:
        return client.resource_exists(item.uri)
    except Exception:
        return False


def _verify_manifest(client: OpenVikingObservatoryClient, manifest: list[ResourceManifestItem]) -> tuple[Counter[str], list[ResourceManifestItem]]:
    descendant_cache: dict[str, list[dict[str, Any]]] = {}
    counts: Counter[str] = Counter()
    missing: list[ResourceManifestItem] = []
    for item in manifest:
        bucket = item.kind
        if _verify_manifest_item(client, item, descendant_cache):
            counts[f"{bucket}_present"] += 1
        else:
            counts[f"{bucket}_missing"] += 1
            missing.append(item)
    return counts, missing


def _render_phase_table(checkpoint: dict[str, Any]) -> Table:
    table = Table(title="Run Phases")
    table.add_column("Phase")
    table.add_column("Status")
    table.add_column("Count", justify="right")
    for phase, payload in checkpoint["phases"].items():
        table.add_row(phase, str(payload.get("status", "unknown")), str(payload.get("count", 0)))
    return table


def _render_namespace_table(client: OpenVikingObservatoryClient) -> Table:
    table = Table(title="Namespace Status")
    table.add_column("URI")
    table.add_column("Present")
    table.add_column("Children", justify="right")
    table.add_column("Error")
    for uri in (
        build_observatory_root_uri(),
        f"{build_observatory_root_uri()}/projects",
        f"{build_observatory_root_uri()}/registry",
        f"{build_observatory_root_uri()}/knowledge-graph",
        f"{build_observatory_root_uri()}/wiki",
        build_wiki_log_uri(),
    ):
        present, child_count, error = _namespace_status(client, uri)
        table.add_row(uri, "yes" if present else "no", "-" if child_count is None else str(child_count), error or "")
    return table


def _render_manifest_table(counts: Counter[str], missing: list[ResourceManifestItem]) -> Table:
    table = Table(title="Manifest Verification")
    table.add_column("Kind")
    table.add_column("Present", justify="right")
    table.add_column("Missing", justify="right")
    kinds = sorted({key.rsplit("_", 1)[0] for key in counts})
    for kind in kinds:
        table.add_row(kind, str(counts.get(f"{kind}_present", 0)), str(counts.get(f"{kind}_missing", 0)))
    if missing:
        table.caption = f"First missing URI: {missing[0].uri}"
    return table


def _build_markdown_report(
    run_id: str,
    checkpoint: dict[str, Any],
    namespaces: list[tuple[str, bool, int | None, str | None]],
    counts: Counter[str],
    missing: list[ResourceManifestItem],
) -> str:
    lines = [f"# OpenViking Ingest Report: {run_id}", ""]
    lines.append(f"Status: **{checkpoint.get('status', 'unknown')}**")
    lines.append("")
    lines.append("## Phases")
    lines.append("")
    for phase, payload in checkpoint["phases"].items():
        lines.append(f"- {phase}: {payload.get('status')} ({payload.get('count', 0)})")
    lines.append("")
    lines.append("## Namespaces")
    lines.append("")
    for uri, present, child_count, error in namespaces:
        suffix = f"{child_count} children" if child_count is not None else (error or "error")
        lines.append(f"- {uri}: {'present' if present else 'missing'} ({suffix})")
    lines.append("")
    lines.append("## Manifest Verification")
    lines.append("")
    for kind in sorted({key.rsplit('_', 1)[0] for key in counts}):
        lines.append(
            f"- {kind}: {counts.get(f'{kind}_present', 0)} present, {counts.get(f'{kind}_missing', 0)} missing"
        )
    if missing:
        lines.append("")
        lines.append("## Missing Examples")
        lines.append("")
        for item in missing[:10]:
            lines.append(f"- {item.kind}: {item.uri}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = RUNS_ROOT / args.run_id if args.run_id else _latest_run_dir()
    checkpoint = _load_checkpoint(run_dir)
    manifest = build_resource_manifest(REPO_ROOT)
    client = OpenVikingObservatoryClient(ObservatoryContextSettings())

    console.print(Panel.fit(f"Run ID: {checkpoint['run_id']}\nStatus: {checkpoint.get('status', 'unknown')}"))
    console.print(_render_phase_table(checkpoint))

    namespace_rows = [
        (uri, *_namespace_status(client, uri))
        for uri in (
            build_observatory_root_uri(),
            f"{build_observatory_root_uri()}/projects",
            f"{build_observatory_root_uri()}/registry",
            f"{build_observatory_root_uri()}/knowledge-graph",
            f"{build_observatory_root_uri()}/wiki",
            build_wiki_log_uri(),
        )
    ]
    console.print(_render_namespace_table(client))

    counts, missing = _verify_manifest(client, manifest)
    console.print(_render_manifest_table(counts, missing))

    report_path = Path(args.output) if args.output else run_dir / "verification_report.md"
    report_path.write_text(
        _build_markdown_report(checkpoint["run_id"], checkpoint, namespace_rows, counts, missing),
        encoding="utf-8",
    )
    console.print(f"\nReport written to {report_path}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
