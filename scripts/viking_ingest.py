"""Ingest observatory resources into OpenViking via the V2 pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from observatory_context.client import OpenVikingObservatoryClient
from observatory_context.config import ObservatoryContextSettings
from observatory_context.ingest import build_resource_manifest

console = Console()
REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_progress(**kwargs) -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        **kwargs,
    )


def _wait_for_processing(
    client: OpenVikingObservatoryClient,
    timeout: float | None,
) -> None:
    wait_note = "Waiting for OpenViking processing"
    if timeout is not None:
        wait_note = f"{wait_note} (timeout {int(timeout)}s)"
    with _make_progress(transient=True) as progress:
        task = progress.add_task(wait_note, total=None)
        client.wait_until_processed(timeout=timeout)
        progress.update(task, description="OpenViking processing complete")


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest observatory resources into OpenViking.",
    )
    parser.add_argument(
        "--no-resume", action="store_true",
        help="Re-upload all resources (ignore existing)",
    )
    parser.add_argument(
        "--wait", action="store_true",
        help="Block until all processing completes",
    )
    parser.add_argument(
        "--wait-timeout", type=float, default=None,
        help="Maximum seconds to wait for OpenViking processing when --wait is set.",
    )
    parser.add_argument(
        "--project", action="append", default=None,
        help="Limit to specific project(s). Repeat for multiple.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview manifest without uploading",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit manifest items (useful with --dry-run)",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Verify all resources exist in OpenViking",
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="Re-ingest missing resources (use with --check)",
    )
    parser.add_argument(
        "--model", default=None,
        help="Override CBORG model for extraction",
    )
    parser.add_argument(
        "--from-scratch", action="store_true",
        help="Clear local ingest and graph state before starting a new run.",
    )
    parser.add_argument(
        "--restart-from",
        choices=("corpus", "registry", "graph", "knowledge_graph", "wiki", "log"),
        default=None,
        help="Force phases from this point onward to rerun for the current scope.",
    )
    parser.add_argument(
        "--no-checkpoint-resume", action="store_true",
        help="Do not auto-resume the latest incomplete matching run.",
    )
    return parser


# ------------------------------------------------------------------
# Check / fix
# ------------------------------------------------------------------


def _check_manifest(client: OpenVikingObservatoryClient, manifest: list) -> list:
    missing: list = []
    with _make_progress() as progress:
        task = progress.add_task("Checking resources", total=len(manifest))
        for item in manifest:
            if not client.resource_exists(item.uri):
                missing.append(item)
            progress.advance(task)

    if missing:
        table = Table(title=f"[red]{len(missing)} Missing Resources[/]")
        table.add_column("URI", style="red")
        table.add_column("Kind")
        for item in missing:
            table.add_row(item.uri, item.kind)
        console.print(table)
    else:
        console.print(f"[green]All {len(manifest)} resources present.[/]")

    return missing


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = ObservatoryContextSettings()

    manifest = build_resource_manifest(
        REPO_ROOT,
        project_ids=set(args.project) if args.project else None,
    )
    if args.limit is not None:
        manifest = manifest[: args.limit]

    # --- Dry run: print manifest table and exit ---
    if args.dry_run:
        table = Table(title=f"Resource Manifest ({len(manifest)} items)")
        table.add_column("URI", style="cyan", no_wrap=True)
        table.add_column("Kind")
        table.add_column("Projects")
        for item in manifest:
            table.add_row(item.uri, item.kind, ", ".join(item.project_ids))
        console.print(table)
        console.print("\n[dim]JSON output:[/]")
        print(json.dumps([item.to_dict() for item in manifest], indent=2, sort_keys=True))
        return 0

    # --- Build client and check health ---
    client = OpenVikingObservatoryClient(settings)

    if hasattr(client, "health"):
        try:
            if not client.health():
                raise RuntimeError
        except Exception:
            url = getattr(
                getattr(client, "settings", None),
                "openviking_url", "http://127.0.0.1:1933",
            )
            console.print(f"[red]OpenViking server is not reachable at {url}[/]")
            console.print("Start it with: uv run openviking-server --config config/openviking/ov.conf")
            return 1

    # --- Check mode ---
    if args.check and not args.fix:
        missing = _check_manifest(client, manifest)
        return 1 if missing else 0

    # --- Fix mode ---
    if args.fix:
        console.rule("Checking for missing resources")
        missing = _check_manifest(client, manifest)
        if not missing:
            console.print("[green]All resources present — nothing to fix.[/]")
            return 0
        console.rule(f"Re-ingesting {len(missing)} missing resources")
        from observatory_context.ingest.pipeline import IngestPipeline

        pipeline = IngestPipeline(client=client, repo_root=REPO_ROOT)
        pipeline.phase1_upload_corpus(missing, resume=False)
        if args.wait:
            with console.status("[bold]Waiting for OpenViking to process..."):
                client.wait_until_processed(timeout=args.wait_timeout)
        console.rule("Re-checking")
        still_missing = _check_manifest(client, manifest)
        return 1 if still_missing else 0

    # --- Default: run V2 pipeline ---
    from observatory_context.ingest.pipeline import IngestPipeline

    extractor = None
    cborg_api_key = getattr(settings, "cborg_api_key", None)
    if cborg_api_key:
        from observatory_context.extraction import CBORGExtractor

        extractor = CBORGExtractor(
            api_url=settings.cborg_api_url,
            model=args.model or settings.cborg_model,
            api_key=cborg_api_key,
        )

    pipeline = IngestPipeline(client=client, repo_root=REPO_ROOT)
    results = pipeline.run(
        project_ids=args.project or None,
        resume=not args.no_resume,
        extractor=extractor,
        allow_checkpoint_resume=not args.no_checkpoint_resume,
        restart_from=args.restart_from,
        from_scratch=args.from_scratch,
    )

    if args.wait:
        try:
            _wait_for_processing(client, args.wait_timeout)
            console.print("[green]All resources processed.[/]")
        except TimeoutError as exc:
            console.print(f"[yellow]Warning:[/] {exc}")

    console.print(f"\n[bold green]Done![/] {results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
