"""Synthesis-backed ingest pipeline orchestrator for the BERIL Research Observatory."""

from __future__ import annotations

import json
import logging
import shutil
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp
from typing import Any
from uuid import uuid4

import yaml
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
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

from observatory_context._text import slugify
from observatory_context.client import OpenVikingObservatoryClient
from observatory_context.graph.builder import GraphBuilder
from observatory_context.graph.knowledge_graph_export import KnowledgeGraphExporter
from observatory_context.graph.knowledge_synthesis import KnowledgeSynthesisBundle, KnowledgeSynthesizer
from observatory_context.graph.report import generate_graph_report, save_report
from observatory_context.graph.resolver import EntityResolver
from observatory_context.ingest.batch import BatchUploader
from observatory_context.ingest.manifest import ResourceManifestItem, build_resource_manifest
from observatory_context.registry.extract import extraction_to_registry_entries
from observatory_context.registry.schema import Finding, Hypothesis
from observatory_context.uris import (
    build_observatory_root_uri,
    build_projects_root_uri,
    build_registry_uri,
    build_wiki_log_uri,
    build_wiki_uri,
)
from observatory_context.wiki.compiler import (
    compile_entity_page_from_synthesis,
    compile_hypothesis_page_from_synthesis,
    compile_topic_page_from_synthesis,
)
from observatory_context.wiki.index import WikiEntry, build_index_markdown

logger = logging.getLogger(__name__)
console = Console()
_PHASE_SEQUENCE = ("corpus", "registry", "graph", "knowledge_graph", "wiki", "log")


def _make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def _format_duration(seconds: float) -> str:
    whole_seconds = max(0, int(seconds))
    minutes, seconds = divmod(whole_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def _split_markdown_frontmatter(markdown: str) -> tuple[str, str]:
    """Split YAML frontmatter from a markdown document."""
    text = markdown.strip()
    if not text.startswith("---\n"):
        return "", markdown.strip()
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return "", markdown.strip()
    return f"{parts[0]}\n---\n", parts[1].strip()


class IngestProgressTracker:
    """Render persistent run + phase status during ingest."""

    def __init__(self, console: Console, phase_order: tuple[str, ...]) -> None:
        self.console = console
        self.phase_order = phase_order
        self.run_started_at = time.monotonic()
        self.phase_started_at = self.run_started_at
        self.item_started_at: float | None = None
        self.current_phase = "Preparing run"
        self.current_item = "—"
        self.note = "Initializing"
        self.completed_phases = 0
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=30),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            TextColumn("[cyan]{task.fields[current_item]}"),
            TextColumn("[dim]{task.fields[note]}"),
            console=console,
        )
        self.run_task = self.progress.add_task(
            "Overall",
            total=len(phase_order),
            current_item="—",
            note="waiting",
        )
        self.phase_task = self.progress.add_task(
            "Current phase",
            total=1,
            current_item="—",
            note="waiting",
            visible=False,
        )
        self.live: Live | None = None

    def __enter__(self) -> IngestProgressTracker:
        self.live = Live(self._renderable(), console=self.console, refresh_per_second=4)
        self.live.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.live is not None:
            self.live.__exit__(exc_type, exc, tb)
            self.live = None

    def _renderable(self) -> Group:
        now = time.monotonic()
        item_elapsed = "—"
        if self.item_started_at is not None:
            item_elapsed = _format_duration(now - self.item_started_at)

        table = Table.grid(expand=True)
        table.add_column(style="bold")
        table.add_column()
        table.add_row("Run", f"{self.completed_phases}/{len(self.phase_order)} phases complete")
        table.add_row("Run elapsed", _format_duration(now - self.run_started_at))
        table.add_row("Phase", self.current_phase)
        table.add_row("Phase elapsed", _format_duration(now - self.phase_started_at))
        table.add_row("Current item", self.current_item)
        table.add_row("Item elapsed", item_elapsed)
        table.add_row("Status", self.note)
        return Group(
            Panel(table, title="Ingest Status", border_style="blue"),
            self.progress,
        )

    def refresh(self) -> None:
        if self.live is not None:
            self.live.update(self._renderable())

    def start_phase(self, label: str, total: int, note: str = "running") -> None:
        self.current_phase = label
        self.phase_started_at = time.monotonic()
        self.item_started_at = None
        self.current_item = "—"
        self.note = note
        self.progress.update(
            self.phase_task,
            visible=True,
            completed=0,
            total=max(total, 1),
            description=label,
            current_item=self.current_item,
            note=self.note,
        )
        self.progress.update(
            self.run_task,
            current_item=label,
            note=note,
        )
        self.refresh()

    def set_item(self, item: str, note: str = "running") -> None:
        self.current_item = item or "—"
        self.item_started_at = time.monotonic()
        self.note = note
        self.progress.update(
            self.phase_task,
            current_item=self.current_item,
            note=self.note,
        )
        self.progress.update(
            self.run_task,
            current_item=self.current_item,
            note=self.note,
        )
        self.refresh()

    def advance(self, amount: int = 1, note: str | None = None) -> None:
        if note is not None:
            self.note = note
        self.progress.update(
            self.phase_task,
            advance=amount,
            current_item=self.current_item,
            note=self.note,
        )
        self.progress.update(
            self.run_task,
            current_item=self.current_item,
            note=self.note,
        )
        self.refresh()

    def set_note(self, note: str) -> None:
        self.note = note
        self.progress.update(
            self.phase_task,
            current_item=self.current_item,
            note=self.note,
        )
        self.progress.update(
            self.run_task,
            current_item=self.current_item,
            note=self.note,
        )
        self.refresh()

    def complete_phase(self, summary: str) -> str:
        elapsed = _format_duration(time.monotonic() - self.phase_started_at)
        self.completed_phases += 1
        self.note = summary
        self.progress.update(
            self.run_task,
            advance=1,
            current_item=self.current_phase,
            note=summary,
        )
        self.progress.update(
            self.phase_task,
            visible=False,
            current_item=self.current_item,
            note=summary,
        )
        self.refresh()
        return elapsed


class IngestPipeline:
    """Orchestrate the 4-phase corpus ingest into OpenViking.

    Parameters
    ----------
    client
        OpenVikingObservatoryClient (or compatible mock).
    repo_root
        Root of the BERIL observatory repository.
    staging_root
        Local directory used for staging files before upload.
        Created as a temp directory if not provided.
    """

    def __init__(
        self,
        client: OpenVikingObservatoryClient,
        repo_root: Path,
        staging_root: Path | None = None,
    ) -> None:
        self.client = client
        self.repo_root = repo_root
        self.staging_root = staging_root or Path(mkdtemp(prefix="observatory-ingest-"))
        self.uploader = BatchUploader(client)
        self._tracker: IngestProgressTracker | None = None
        self.state_root = self.repo_root / "data" / "ingest"
        self.registry_state_root = self.state_root / "registry" / "projects"
        self.runs_root = self.state_root / "runs"
        self._ensure_state_dirs()

    # ------------------------------------------------------------------
    # Phase helpers
    # ------------------------------------------------------------------

    def _ensure_state_dirs(self) -> None:
        self.registry_state_root.mkdir(parents=True, exist_ok=True)
        self.runs_root.mkdir(parents=True, exist_ok=True)

    def clear_local_state(self) -> None:
        """Remove local durable ingest state and graph artifacts."""
        shutil.rmtree(self.state_root, ignore_errors=True)
        shutil.rmtree(self.repo_root / "data" / "graph", ignore_errors=True)
        self._ensure_state_dirs()

    def _phase_summary(
        self,
        label: str,
        count: int,
        elapsed: str | None = None,
        unit: str = "items",
    ) -> str:
        summary = f"{count} {unit}"
        if elapsed is not None:
            summary = f"{summary} in {elapsed}"
        return f"  [green]✓[/] {label}: {summary}"

    def _scope_key(self, project_ids: list[str] | None) -> str:
        return "__all__" if not project_ids else ",".join(sorted(project_ids))

    def _new_run_id(self) -> str:
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{timestamp}-{uuid4().hex[:8]}"

    def _checkpoint_path(self, run_id: str) -> Path:
        return self.runs_root / run_id / "checkpoint.json"

    def _create_checkpoint(
        self,
        run_id: str,
        project_ids: list[str] | None,
        resume_phase1: bool,
    ) -> dict[str, Any]:
        now = datetime.now(tz=timezone.utc).isoformat()
        checkpoint = {
            "run_id": run_id,
            "scope_key": self._scope_key(project_ids),
            "project_ids": sorted(project_ids) if project_ids else None,
            "resume_phase1": resume_phase1,
            "status": "running",
            "created_at": now,
            "updated_at": now,
            "phases": {
                phase: {"status": "pending", "count": 0}
                for phase in _PHASE_SEQUENCE
            },
        }
        self._save_checkpoint(checkpoint)
        return checkpoint

    def _save_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        path = self._checkpoint_path(checkpoint["run_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
        path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True), encoding="utf-8")

    def _load_checkpoint(self, run_id: str) -> dict[str, Any]:
        return json.loads(self._checkpoint_path(run_id).read_text(encoding="utf-8"))

    def _find_latest_incomplete_checkpoint(
        self,
        project_ids: list[str] | None,
    ) -> dict[str, Any] | None:
        scope_key = self._scope_key(project_ids)
        candidates = sorted(self.runs_root.glob("*/checkpoint.json"), reverse=True)
        for candidate in candidates:
            checkpoint = json.loads(candidate.read_text(encoding="utf-8"))
            if checkpoint.get("scope_key") != scope_key:
                continue
            if checkpoint.get("status") in {"running", "failed"}:
                return checkpoint
        return None

    def _phase_is_complete(self, checkpoint: dict[str, Any], phase: str) -> bool:
        return checkpoint["phases"][phase]["status"] == "completed"

    def _mark_phase_completed(
        self,
        checkpoint: dict[str, Any],
        phase: str,
        count: int,
    ) -> dict[str, Any]:
        checkpoint["phases"][phase] = {
            "status": "completed",
            "count": count,
            "completed_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        self._save_checkpoint(checkpoint)
        return checkpoint

    def _mark_run_failed(
        self,
        checkpoint: dict[str, Any],
        phase: str,
        exc: Exception,
    ) -> None:
        checkpoint["status"] = "failed"
        checkpoint["phases"][phase] = {
            "status": "failed",
            "count": checkpoint["phases"][phase].get("count", 0),
            "error": str(exc),
            "failed_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        self._save_checkpoint(checkpoint)

    def _reset_from_phase(self, checkpoint: dict[str, Any], phase: str) -> dict[str, Any]:
        start = _PHASE_SEQUENCE.index(phase)
        for phase_name in _PHASE_SEQUENCE[start:]:
            checkpoint["phases"][phase_name] = {"status": "pending", "count": 0}
        checkpoint["status"] = "running"
        self._save_checkpoint(checkpoint)
        return checkpoint

    def _prepare_run(
        self,
        project_ids: list[str] | None,
        resume_phase1: bool,
        allow_checkpoint_resume: bool,
        restart_from: str | None,
        from_scratch: bool,
    ) -> dict[str, Any]:
        if from_scratch:
            self.clear_local_state()
        if restart_from is not None and not allow_checkpoint_resume:
            raise ValueError("--restart-from requires checkpoint resume to be enabled")
        checkpoint = None
        if allow_checkpoint_resume and not from_scratch:
            checkpoint = self._find_latest_incomplete_checkpoint(project_ids)
        if checkpoint is None:
            checkpoint = self._create_checkpoint(
                run_id=self._new_run_id(),
                project_ids=project_ids,
                resume_phase1=resume_phase1,
            )
        elif restart_from is not None:
            checkpoint = self._reset_from_phase(checkpoint, restart_from)
        return checkpoint

    def _persist_project_entries(
        self,
        project_id: str,
        entries: list[Finding | Hypothesis],
    ) -> None:
        project_root = self.registry_state_root / project_id
        shutil.rmtree(project_root, ignore_errors=True)
        (project_root / "findings").mkdir(parents=True, exist_ok=True)
        (project_root / "hypotheses").mkdir(parents=True, exist_ok=True)

        for entry in entries:
            if isinstance(entry, Finding):
                rel_path = project_root / "findings" / f"{entry.finding_id}.yaml"
            elif isinstance(entry, Hypothesis):
                rel_path = project_root / "hypotheses" / f"{entry.hypothesis_id}.yaml"
            else:
                continue
            rel_path.write_text(
                yaml.dump(entry.model_dump(exclude_none=True), default_flow_style=False, sort_keys=True),
                encoding="utf-8",
            )

    def _load_persisted_entries(self) -> tuple[list[Finding], list[Hypothesis]]:
        findings: list[Finding] = []
        hypotheses: list[Hypothesis] = []
        if not self.registry_state_root.exists():
            return findings, hypotheses
        for project_dir in sorted(self.registry_state_root.iterdir()):
            findings_dir = project_dir / "findings"
            hypotheses_dir = project_dir / "hypotheses"
            if findings_dir.exists():
                for path in sorted(findings_dir.glob("*.yaml")):
                    data = yaml.safe_load(path.read_text(encoding="utf-8"))
                    if data:
                        findings.append(Finding.model_validate(data))
            if hypotheses_dir.exists():
                for path in sorted(hypotheses_dir.glob("*.yaml")):
                    data = yaml.safe_load(path.read_text(encoding="utf-8"))
                    if data:
                        hypotheses.append(Hypothesis.model_validate(data))
        return findings, hypotheses

    def _stage_registry_snapshot(self, registry_staging: Path) -> int:
        """Materialize the durable registry store into a flat staging tree."""
        registry_staging.mkdir(parents=True, exist_ok=True)
        findings, hypotheses = self._load_persisted_entries()
        for finding in findings:
            self.uploader.stage(
                registry_staging,
                f"findings/{finding.finding_id}.yaml",
                yaml.dump(
                    finding.model_dump(exclude_none=True),
                    default_flow_style=False,
                    sort_keys=True,
                ),
            )
        for hypothesis in hypotheses:
            self.uploader.stage(
                registry_staging,
                f"hypotheses/{hypothesis.hypothesis_id}.yaml",
                yaml.dump(
                    hypothesis.model_dump(exclude_none=True),
                    default_flow_style=False,
                    sort_keys=True,
                ),
            )
        return len(findings) + len(hypotheses)

    def build_corpus_manifest(
        self, project_ids: list[str] | None = None
    ) -> list[ResourceManifestItem]:
        """Build the resource manifest from the repository.

        Parameters
        ----------
        project_ids
            Limit to these project IDs. ``None`` discovers all projects.

        Returns
        -------
        list[ResourceManifestItem]
            Ordered list of resources ready for ingest.
        """
        return build_resource_manifest(self.repo_root, project_ids=project_ids)

    def phase1_upload_corpus(
        self, manifest: list[ResourceManifestItem], resume: bool = True
    ) -> int:
        """Stage all source files and upload as a batch to the corpus namespace.

        Parameters
        ----------
        manifest
            Items to upload.
        resume
            Skip items whose URI already exists in OpenViking when ``True``.

        Returns
        -------
        int
            Number of items staged (and queued for upload).
        """
        corpus_staging = self.staging_root / "corpus"
        shutil.rmtree(corpus_staging, ignore_errors=True)
        corpus_staging.mkdir(parents=True, exist_ok=True)

        staged: list[ResourceManifestItem] = []
        tracker = self._tracker
        if tracker is not None:
            tracker.start_phase("Phase 1: Uploading corpus", len(manifest), note="Scanning source files")
            for item in manifest:
                source_name = Path(item.source_path).name
                tracker.set_item(source_name, note="Checking remote state")
                if resume and self.client.resource_exists(item.uri):
                    tracker.advance(note="Already present, skipped")
                    continue
                source = Path(item.source_path)
                if not source.exists():
                    tracker.advance(note="Missing local file, skipped")
                    continue
                try:
                    content = source.read_text(encoding="utf-8")
                except Exception:
                    tracker.advance(note="Unreadable file, skipped")
                    continue
                rel = item.uri.removeprefix(f"{build_projects_root_uri()}/")
                self.uploader.stage(corpus_staging, rel, content, metadata=item.metadata)
                staged.append(item)
                tracker.advance(note="Staged for upload")
        else:
            with _make_progress() as progress:
                task = progress.add_task("Phase 1: Uploading corpus", total=len(manifest))
                for item in manifest:
                    progress.update(task, description=f"Phase 1: {Path(item.source_path).name}")
                    if resume and self.client.resource_exists(item.uri):
                        progress.advance(task)
                        continue
                    source = Path(item.source_path)
                    if not source.exists():
                        progress.advance(task)
                        continue
                    try:
                        content = source.read_text(encoding="utf-8")
                    except Exception:
                        progress.advance(task)
                        continue
                    rel = item.uri.removeprefix(f"{build_projects_root_uri()}/")
                    self.uploader.stage(corpus_staging, rel, content, metadata=item.metadata)
                    staged.append(item)
                    progress.advance(task)

        if staged:
            target_uri = build_projects_root_uri()
            if tracker is not None:
                tracker.set_note(f"Uploading {len(staged)} staged resources")
            self.uploader.upload(
                corpus_staging,
                target_uri,
                reason="Phase 1 corpus ingest",
                wait=False,
                preserve_structure=True,
            )
        elapsed = tracker.complete_phase(f"{len(staged)} resources uploaded") if tracker is not None else None
        console.print(self._phase_summary("Phase 1", len(staged), elapsed, unit="resources uploaded"))
        return len(staged)

    def phase2_extract_and_register(
        self,
        manifest: list[ResourceManifestItem],
        extractor: Any | None = None,
    ) -> int:
        """Extract knowledge from project reports and upload registry entries.

        Parameters
        ----------
        manifest
            Resource manifest from phase 1 (used to discover project IDs).
        extractor
            A ``CBORGExtractor`` instance. If ``None``, phase 2 is skipped
            (graceful degradation).

        Returns
        -------
        int
            Number of registry entries created.
        """
        if extractor is None:
            if self._tracker is not None:
                self._tracker.start_phase("Phase 2: Extracting knowledge", 1, note="Skipped (no extractor)")
                self._tracker.complete_phase("Skipped (no extractor)")
            console.print("  [dim]Phase 2: skipped (no extractor)[/]")
            return 0

        project_ids = sorted({pid for item in manifest for pid in item.project_ids})
        registry_staging = self.staging_root / "registry"
        shutil.rmtree(registry_staging, ignore_errors=True)
        registry_staging.mkdir(parents=True, exist_ok=True)

        all_entries: list[Finding | Hypothesis] = []
        tracker = self._tracker
        if tracker is not None:
            tracker.start_phase("Phase 2: Extracting knowledge", len(project_ids), note="Loading project reports")
            for pid in project_ids:
                tracker.set_item(pid, note="Reading report")
                report_path = self.repo_root / "projects" / pid / "REPORT.md"
                if not report_path.exists():
                    self._persist_project_entries(pid, [])
                    tracker.advance(note="No REPORT.md, skipped")
                    continue

                report_text = report_path.read_text(encoding="utf-8")
                prov_path = self.repo_root / "projects" / pid / "provenance.yaml"
                provenance: dict = {}
                if prov_path.exists():
                    provenance = yaml.safe_load(prov_path.read_text(encoding="utf-8")) or {}
                try:
                    tracker.set_note("Calling CBORG extractor")
                    extraction = extractor.extract_knowledge(report_text, provenance)
                except (ValueError, Exception) as exc:
                    logger.warning("Extraction failed for %s: %s", pid, exc)
                    self._persist_project_entries(pid, [])
                    tracker.advance(note=f"Skipped after extraction error: {exc}")
                    continue

                entries = extraction_to_registry_entries(extraction, pid)
                self._persist_project_entries(pid, entries)
                all_entries.extend(entries)
                tracker.advance(note=f"Persisted {len(entries)} registry entries")
        else:
            with _make_progress() as progress:
                task = progress.add_task("Phase 2: Extracting knowledge", total=len(project_ids))
                for pid in project_ids:
                    progress.update(task, description=f"Phase 2: {pid}")
                    report_path = self.repo_root / "projects" / pid / "REPORT.md"
                    if not report_path.exists():
                        self._persist_project_entries(pid, [])
                        progress.advance(task)
                        continue

                    report_text = report_path.read_text(encoding="utf-8")
                    prov_path = self.repo_root / "projects" / pid / "provenance.yaml"
                    provenance: dict = {}
                    if prov_path.exists():
                        provenance = yaml.safe_load(prov_path.read_text(encoding="utf-8")) or {}
                    try:
                        extraction = extractor.extract_knowledge(report_text, provenance)
                    except (ValueError, Exception) as exc:
                        logger.warning("Extraction failed for %s: %s", pid, exc)
                        self._persist_project_entries(pid, [])
                        progress.advance(task)
                        continue

                    entries = extraction_to_registry_entries(extraction, pid)
                    self._persist_project_entries(pid, entries)
                    all_entries.extend(entries)
                    progress.advance(task)

        staged_count = self._stage_registry_snapshot(registry_staging)
        if staged_count:
            target_uri = build_registry_uri()
            if tracker is not None:
                tracker.set_note(f"Uploading {staged_count} registry files")
            self.uploader.upload(
                registry_staging,
                target_uri,
                reason="Phase 2 registry ingest",
                wait=False,
                preserve_structure=True,
            )

        elapsed = tracker.complete_phase(f"{len(all_entries)} registry entries created") if tracker is not None else None
        console.print(self._phase_summary("Phase 2", len(all_entries), elapsed, unit="registry entries created"))
        return len(all_entries)

    def phase3_build_graph(
        self,
        manifest: list[ResourceManifestItem],
        findings: list[Finding] | None = None,
        hypotheses: list[Hypothesis] | None = None,
    ) -> int:
        """Resolve entities and build the knowledge graph.

        Parameters
        ----------
        manifest
            Resource manifest (used to discover project metadata).
        findings
            Pre-collected findings. If ``None``, reads staged YAML.
        hypotheses
            Pre-collected hypotheses. If ``None``, reads staged YAML.

        Returns
        -------
        int
            Number of graph nodes created.
        """
        # Collect entries from staged registry files if not provided
        if findings is None or hypotheses is None:
            findings, hypotheses = self._load_persisted_entries()

        if not findings and not hypotheses:
            if self._tracker is not None:
                self._tracker.start_phase("Phase 3: Building graph", 1, note="Skipped (no registry entries)")
                self._tracker.complete_phase("Skipped (no registry entries)")
            console.print("  [dim]Phase 3: skipped (no registry entries)[/]")
            return 0

        graph_dir = self.repo_root / "data" / "graph"
        graph_dir.mkdir(parents=True, exist_ok=True)
        graph_path = graph_dir / "graph.json"
        builder = GraphBuilder()

        # Initialize entity resolver
        aliases_path = graph_dir / "aliases.json"
        resolver = EntityResolver(
            aliases=None,  # loads defaults + aliases_path if exists
        )

        # Collect all entity references for batch resolution
        entity_refs: list[tuple[str, str]] = []
        for f in findings:
            for ref in f.related_entities:
                entity_refs.append((ref.type, ref.label))
        for h in hypotheses:
            for ref in h.related_entities:
                entity_refs.append((ref.type, ref.label))

        try:
            tracker = self._tracker
            if tracker is not None:
                tracker.start_phase("Phase 3: Building graph", 3, note="Resolving entity aliases")
                tracker.set_item("entity-resolution", note=f"Resolving {len(entity_refs)} entity references")
                resolved = resolver.resolve_batch(entity_refs)
                tracker.advance(note=f"Resolved {len(resolved)} canonical entities")

                tracker.set_item("graph-build", note="Adding project, entity, finding, and hypothesis nodes")
                project_ids = sorted(
                    {finding.project_id for finding in findings}
                    | {project_id for hypothesis in hypotheses for project_id in hypothesis.project_ids}
                )
                for pid in project_ids:
                    readme_path = self.repo_root / "projects" / pid / "README.md"
                    title = pid
                    if readme_path.exists():
                        first_line = readme_path.read_text(encoding="utf-8").split("\n")[0]
                        if first_line.startswith("# "):
                            title = first_line[2:].strip()
                    builder.add_project(pid, title)

                for raw_label, resolved_entity in resolved.items():
                    builder.add_entity(
                        canonical_name=resolved_entity.canonical,
                        entity_type=resolved_entity.entity_type,
                        aliases=resolved_entity.aliases,
                    )

                for f in findings:
                    entity_map = {}
                    for ref in f.related_entities:
                        if ref.label in resolved:
                            r = resolved[ref.label]
                            from observatory_context.graph.builder import _entity_node_id
                            entity_map[ref.label] = _entity_node_id(r.entity_type, r.canonical)
                    builder.add_finding(f, entity_map)

                for h in hypotheses:
                    entity_map = {}
                    for ref in h.related_entities:
                        if ref.label in resolved:
                            r = resolved[ref.label]
                            from observatory_context.graph.builder import _entity_node_id
                            entity_map[ref.label] = _entity_node_id(r.entity_type, r.canonical)
                    builder.add_hypothesis(h, entity_map)
                tracker.advance(note="Graph nodes and edges built")

                tracker.set_item("communities", note="Running community detection and writing graph artifacts")
                communities = builder.build_communities()
                builder.serialize(graph_path)

                from observatory_context.graph.aliases import save_aliases
                save_aliases(resolver._aliases, aliases_path)

                import json
                communities_path = graph_dir / "communities.json"
                communities_path.write_text(
                    json.dumps(communities, indent=2, default=str),
                    encoding="utf-8",
                )

                report_content = generate_graph_report(builder)
                report_path = graph_dir / "GRAPH_REPORT.md"
                save_report(report_content, report_path)
                tracker.advance(note="Graph artifacts written")
            else:
                with _make_progress() as progress:
                    task = progress.add_task(
                        "Phase 3: Resolving entities", total=3,
                    )

                    resolved = resolver.resolve_batch(entity_refs)
                    progress.advance(task)

                    # Add project nodes
                    progress.update(task, description="Phase 3: Building graph")
                    project_ids = sorted(
                        {finding.project_id for finding in findings}
                        | {project_id for hypothesis in hypotheses for project_id in hypothesis.project_ids}
                    )
                    for pid in project_ids:
                        readme_path = self.repo_root / "projects" / pid / "README.md"
                        title = pid
                        if readme_path.exists():
                            first_line = readme_path.read_text(encoding="utf-8").split("\n")[0]
                            if first_line.startswith("# "):
                                title = first_line[2:].strip()
                        builder.add_project(pid, title)

                    # Add resolved entities
                    for raw_label, resolved_entity in resolved.items():
                        builder.add_entity(
                            canonical_name=resolved_entity.canonical,
                            entity_type=resolved_entity.entity_type,
                            aliases=resolved_entity.aliases,
                        )

                    # Add findings with resolved entity links
                    for f in findings:
                        entity_map = {}
                        for ref in f.related_entities:
                            if ref.label in resolved:
                                r = resolved[ref.label]
                                from observatory_context.graph.builder import _entity_node_id
                                entity_map[ref.label] = _entity_node_id(r.entity_type, r.canonical)
                        builder.add_finding(f, entity_map)

                    # Add hypotheses with resolved entity links
                    for h in hypotheses:
                        entity_map = {}
                        for ref in h.related_entities:
                            if ref.label in resolved:
                                r = resolved[ref.label]
                                from observatory_context.graph.builder import _entity_node_id
                                entity_map[ref.label] = _entity_node_id(r.entity_type, r.canonical)
                        builder.add_hypothesis(h, entity_map)
                    progress.advance(task)

                    # Community detection + report
                    progress.update(task, description="Phase 3: Communities + report")
                    communities = builder.build_communities()
                    builder.serialize(graph_path)

                    # Save updated aliases
                    from observatory_context.graph.aliases import save_aliases
                    save_aliases(resolver._aliases, aliases_path)

                    # Save communities
                    import json
                    communities_path = graph_dir / "communities.json"
                    communities_path.write_text(
                        json.dumps(communities, indent=2, default=str),
                        encoding="utf-8",
                    )

                    # Generate GRAPH_REPORT.md
                    report_content = generate_graph_report(builder)
                    report_path = graph_dir / "GRAPH_REPORT.md"
                    save_report(report_content, report_path)
                    progress.advance(task)
        finally:
            resolver.close()

        node_count = builder.G.number_of_nodes()
        elapsed = tracker.complete_phase(
            f"{node_count} nodes, {builder.G.number_of_edges()} edges, {len(communities)} communities"
        ) if tracker is not None else None
        summary = (
            f"  [green]✓[/] Phase 3: {node_count} nodes, "
            f"{builder.G.number_of_edges()} edges, "
            f"{len(communities)} communities"
        )
        if elapsed is not None:
            summary = f"{summary} in {elapsed}"
        console.print(summary)
        return node_count

    def _load_staged_entries(self) -> tuple[list[Finding], list[Hypothesis]]:
        """Load findings and hypotheses from staged registry YAML."""
        staged_findings: list[Finding] = []
        staged_hypotheses: list[Hypothesis] = []
        registry_staging = self.staging_root / "registry"
        if registry_staging.exists():
            findings_dir = registry_staging / "findings"
            if findings_dir.exists():
                for f in sorted(findings_dir.glob("*.yaml")):
                    data = yaml.safe_load(f.read_text(encoding="utf-8"))
                    if data:
                        staged_findings.append(Finding.model_validate(data))
            hyp_dir = registry_staging / "hypotheses"
            if hyp_dir.exists():
                for f in sorted(hyp_dir.glob("*.yaml")):
                    data = yaml.safe_load(f.read_text(encoding="utf-8"))
                    if data:
                        staged_hypotheses.append(Hypothesis.model_validate(data))
        return staged_findings, staged_hypotheses

    def _load_graph_artifacts(self) -> tuple[Any | None, dict[str, dict] | None]:
        """Load persisted graph and community artifacts from disk."""
        graph_path = self.repo_root / "data" / "graph" / "graph.json"
        communities_path = self.repo_root / "data" / "graph" / "communities.json"
        graph = None
        communities = None
        if graph_path.exists():
            graph = GraphBuilder.load(graph_path).G
        if communities_path.exists():
            import json

            communities = json.loads(communities_path.read_text(encoding="utf-8"))
        return graph, communities

    def _build_project_metadata(
        self,
        manifest: list[ResourceManifestItem],
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Build project titles and optional dates from repository files."""
        project_titles: dict[str, str] = {}
        project_dates: dict[str, str] = {}
        project_ids = sorted({pid for item in manifest for pid in item.project_ids})
        for project_id in project_ids:
            readme_path = self.repo_root / "projects" / project_id / "README.md"
            if readme_path.exists():
                first_line = readme_path.read_text(encoding="utf-8").splitlines()[0]
                if first_line.startswith("# "):
                    project_titles[project_id] = first_line[2:].strip()
            prov_path = self.repo_root / "projects" / project_id / "provenance.yaml"
            if prov_path.exists():
                provenance = yaml.safe_load(prov_path.read_text(encoding="utf-8")) or {}
                for key in ("updated_at", "created_at", "date_completed"):
                    if provenance.get(key):
                        project_dates[project_id] = str(provenance[key])
                        break
        return project_titles, project_dates

    def _maybe_generate_rich_wiki_page(
        self,
        *,
        extractor: Any | None,
        page_kind: str,
        page_label: str,
        synthesis_payload: dict[str, Any],
        fallback_content: str,
        tracker: IngestProgressTracker | None = None,
    ) -> str:
        """Optionally rewrite one wiki page with the LLM, falling back on failure."""
        if (
            extractor is None
            or getattr(extractor, "supports_wiki_generation", False) is not True
            or not hasattr(extractor, "generate_wiki_page_from_synthesis")
        ):
            return fallback_content
        try:
            if tracker is not None:
                tracker.set_note(f"Generating rich {page_kind} page")
            rewritten_body = extractor.generate_wiki_page_from_synthesis(page_kind, synthesis_payload)
            frontmatter, _ = _split_markdown_frontmatter(fallback_content)
            if frontmatter:
                return f"{frontmatter}\n{rewritten_body.strip()}\n"
            return rewritten_body
        except Exception as exc:
            logger.warning("Wiki page generation failed for %s: %s", page_label, exc)
            if tracker is not None:
                tracker.set_note(f"Falling back to deterministic {page_kind} page")
            return fallback_content

    def build_synthesis_bundle(
        self,
        manifest: list[ResourceManifestItem],
        findings: list[Finding] | None = None,
        hypotheses: list[Hypothesis] | None = None,
    ) -> tuple[KnowledgeSynthesisBundle, Any | None]:
        """Build the shared synthesis bundle from staged registry and graph artifacts."""
        if findings is None or hypotheses is None:
            findings, hypotheses = self._load_persisted_entries()
        if not findings and not hypotheses:
            return KnowledgeSynthesisBundle(), None
        graph, communities = self._load_graph_artifacts()
        project_ids = sorted(
            {finding.project_id for finding in findings}
            | {project_id for hypothesis in hypotheses for project_id in hypothesis.project_ids}
        )
        synthesizer = KnowledgeSynthesizer()
        return synthesizer.synthesize(
            findings=findings,
            hypotheses=hypotheses,
            project_ids=project_ids,
            graph=graph,
            communities=communities,
        ), graph

    def phase4_export_knowledge_graph(
        self,
        bundle: KnowledgeSynthesisBundle,
        graph: Any | None = None,
    ) -> int:
        """Export synthesized knowledge into the OpenViking `knowledge-graph/` namespace."""
        if not bundle.entities and not bundle.hypotheses and not bundle.timeline_events:
            if self._tracker is not None:
                self._tracker.start_phase("Phase 4: Exporting knowledge graph", 1, note="Skipped (empty synthesis bundle)")
                self._tracker.complete_phase("Skipped (empty synthesis bundle)")
            console.print("  [dim]Phase 4: skipped (empty synthesis bundle)[/]")
            return 0
        export_staging = self.staging_root / "knowledge-layer"
        shutil.rmtree(export_staging, ignore_errors=True)
        export_staging.mkdir(parents=True, exist_ok=True)
        exporter = KnowledgeGraphExporter(bundle=bundle, graph=graph)
        tracker = self._tracker
        if tracker is not None:
            tracker.start_phase("Phase 4: Exporting knowledge graph", 3, note="Rendering knowledge-layer files")
        file_count = exporter.export_all(export_staging)
        if tracker is not None:
            tracker.set_item("knowledge-layer", note=f"Uploading {file_count} knowledge-graph files")
        self.uploader.upload(
            export_staging,
            build_observatory_root_uri(),
            reason="Phase 4 knowledge-graph export",
            wait=True,
            preserve_structure=True,
        )
        if tracker is not None:
            tracker.advance(note="Files uploaded and processed")
            tracker.set_item("relations", note="Creating knowledge-graph relations")
        relation_count = exporter.create_relations(self.client)
        if tracker is not None:
            tracker.advance(note="Graph relations created")
        elapsed = tracker.complete_phase(
            f"{file_count} files and {relation_count} relations exported"
        ) if tracker is not None else None
        summary = (
            f"  [green]✓[/] Phase 4: {file_count} knowledge-graph files and "
            f"{relation_count} relations exported"
        )
        if elapsed is not None:
            summary = f"{summary} in {elapsed}"
        console.print(summary)
        return file_count

    def phase5_compile_wiki(
        self,
        manifest: list[ResourceManifestItem],
        bundle: KnowledgeSynthesisBundle,
        findings: list[Finding] | None = None,
        hypotheses: list[Hypothesis] | None = None,
        extractor: Any | None = None,
    ) -> int:
        """Compile wiki pages from registry entries and upload them.

        Parameters
        ----------
        manifest
            Resource manifest (used to discover project IDs).
        findings
            Pre-collected findings. If ``None``, reads staged YAML from the
            registry staging directory.
        hypotheses
            Pre-collected hypotheses. If ``None``, reads staged YAML from the
            registry staging directory.

        Returns
        -------
        int
            Number of wiki pages compiled.
        """
        if findings is None or hypotheses is None:
            findings, hypotheses = self._load_persisted_entries()

        if not bundle.entities and not bundle.hypotheses and not bundle.topics:
            if self._tracker is not None:
                self._tracker.start_phase("Phase 5: Compiling wiki", 1, note="Skipped (empty synthesis bundle)")
                self._tracker.complete_phase("Skipped (empty synthesis bundle)")
            console.print("  [dim]Phase 5: skipped (empty synthesis bundle)[/]")
            return 0

        wiki_staging = self.staging_root / "wiki"
        shutil.rmtree(wiki_staging, ignore_errors=True)
        wiki_staging.mkdir(parents=True, exist_ok=True)

        wiki_entries: list[WikiEntry] = []
        page_count = 0
        findings_by_id = {finding.finding_id: finding for finding in findings}
        hypotheses_by_id = {hypothesis.hypothesis_id: hypothesis for hypothesis in hypotheses}
        total_pages = len(bundle.entities) + len(bundle.hypotheses) + len(bundle.topics) + 1
        tracker = self._tracker
        if tracker is not None:
            tracker.start_phase("Phase 5: Compiling wiki", total_pages, note="Rendering wiki pages")
            from observatory_context.uris import _ENTITY_TYPE_PLURALS

            for entity in bundle.entities:
                page_label = f"entity/{entity.slug}"
                tracker.set_item(page_label, note="Compiling entity page")
                content = compile_entity_page_from_synthesis(
                    entity,
                    findings_by_id=findings_by_id,
                    hypotheses_by_id=hypotheses_by_id,
                )
                content = self._maybe_generate_rich_wiki_page(
                    extractor=extractor,
                    page_kind="entity",
                    page_label=page_label,
                    synthesis_payload=entity.model_dump(mode="json", exclude_none=True),
                    fallback_content=content,
                    tracker=tracker,
                )
                plural = _ENTITY_TYPE_PLURALS.get(entity.entity_type, f"{entity.entity_type}s")
                rel_path = f"entities/{plural}/{entity.slug}.md"
                self.uploader.stage(wiki_staging, rel_path, content)
                wiki_entries.append(
                    WikiEntry(
                        slug=entity.slug,
                        section=f"entities/{plural}",
                        summary=entity.canonical_name,
                        source_count=len(entity.finding_ids),
                        coverage=entity.coverage,
                    )
                )
                page_count += 1
                tracker.advance(note="Entity page staged")

            for hypothesis in bundle.hypotheses:
                page_label = f"hypothesis/{hypothesis.slug}"
                tracker.set_item(page_label, note="Compiling hypothesis page")
                content = compile_hypothesis_page_from_synthesis(
                    hypothesis,
                    findings_by_id=findings_by_id,
                    hypotheses_by_id=hypotheses_by_id,
                )
                content = self._maybe_generate_rich_wiki_page(
                    extractor=extractor,
                    page_kind="hypothesis",
                    page_label=page_label,
                    synthesis_payload=hypothesis.model_dump(mode="json", exclude_none=True),
                    fallback_content=content,
                    tracker=tracker,
                )
                rel_path = f"hypotheses/{hypothesis.slug}.md"
                self.uploader.stage(wiki_staging, rel_path, content)
                wiki_entries.append(
                    WikiEntry(
                        slug=hypothesis.slug,
                        section="hypotheses",
                        summary=hypothesis.statement[:80],
                        source_count=len(hypothesis.supporting_findings),
                        coverage=hypothesis.coverage,
                    )
                )
                page_count += 1
                tracker.advance(note="Hypothesis page staged")

            for topic in bundle.topics:
                page_label = f"topic/{topic.slug}"
                tracker.set_item(page_label, note="Compiling topic page")
                content = compile_topic_page_from_synthesis(
                    topic,
                    findings_by_id=findings_by_id,
                    hypotheses_by_id=hypotheses_by_id,
                )
                content = self._maybe_generate_rich_wiki_page(
                    extractor=extractor,
                    page_kind="topic",
                    page_label=page_label,
                    synthesis_payload=topic.model_dump(mode="json", exclude_none=True),
                    fallback_content=content,
                    tracker=tracker,
                )
                rel_path = f"topics/{topic.slug}.md"
                self.uploader.stage(wiki_staging, rel_path, content)
                wiki_entries.append(
                    WikiEntry(
                        slug=topic.slug,
                        section="topics",
                        summary=topic.title,
                        source_count=len(topic.finding_ids),
                        coverage="high" if len(topic.finding_ids) >= 5 else "medium" if len(topic.finding_ids) >= 2 else "low",
                    )
                )
                page_count += 1
                tracker.advance(note="Topic page staged")

            tracker.set_item("index", note="Compiling index page")
            index_content = build_index_markdown(wiki_entries)
            self.uploader.stage(wiki_staging, "index.md", index_content)
            page_count += 1
            tracker.advance(note="Index page staged")
        else:
            with _make_progress() as progress:
                task = progress.add_task("Phase 5: Compiling wiki", total=total_pages)

                from observatory_context.uris import _ENTITY_TYPE_PLURALS

                for entity in bundle.entities:
                    progress.update(task, description=f"Phase 5: entity/{entity.slug}")
                    content = compile_entity_page_from_synthesis(
                        entity,
                        findings_by_id=findings_by_id,
                        hypotheses_by_id=hypotheses_by_id,
                    )
                    content = self._maybe_generate_rich_wiki_page(
                        extractor=extractor,
                        page_kind="entity",
                        page_label=f"entity/{entity.slug}",
                        synthesis_payload=entity.model_dump(mode="json", exclude_none=True),
                        fallback_content=content,
                    )
                    plural = _ENTITY_TYPE_PLURALS.get(entity.entity_type, f"{entity.entity_type}s")
                    rel_path = f"entities/{plural}/{entity.slug}.md"
                    self.uploader.stage(wiki_staging, rel_path, content)
                    wiki_entries.append(
                        WikiEntry(
                            slug=entity.slug,
                            section=f"entities/{plural}",
                            summary=entity.canonical_name,
                            source_count=len(entity.finding_ids),
                            coverage=entity.coverage,
                        )
                    )
                    page_count += 1
                    progress.advance(task)

                for hypothesis in bundle.hypotheses:
                    progress.update(task, description=f"Phase 5: hypothesis/{hypothesis.slug}")
                    content = compile_hypothesis_page_from_synthesis(
                        hypothesis,
                        findings_by_id=findings_by_id,
                        hypotheses_by_id=hypotheses_by_id,
                    )
                    content = self._maybe_generate_rich_wiki_page(
                        extractor=extractor,
                        page_kind="hypothesis",
                        page_label=f"hypothesis/{hypothesis.slug}",
                        synthesis_payload=hypothesis.model_dump(mode="json", exclude_none=True),
                        fallback_content=content,
                    )
                    rel_path = f"hypotheses/{hypothesis.slug}.md"
                    self.uploader.stage(wiki_staging, rel_path, content)
                    wiki_entries.append(
                        WikiEntry(
                            slug=hypothesis.slug,
                            section="hypotheses",
                            summary=hypothesis.statement[:80],
                            source_count=len(hypothesis.supporting_findings),
                            coverage=hypothesis.coverage,
                        )
                    )
                    page_count += 1
                    progress.advance(task)

                for topic in bundle.topics:
                    progress.update(task, description=f"Phase 5: topic/{topic.slug}")
                    content = compile_topic_page_from_synthesis(
                        topic,
                        findings_by_id=findings_by_id,
                        hypotheses_by_id=hypotheses_by_id,
                    )
                    content = self._maybe_generate_rich_wiki_page(
                        extractor=extractor,
                        page_kind="topic",
                        page_label=f"topic/{topic.slug}",
                        synthesis_payload=topic.model_dump(mode="json", exclude_none=True),
                        fallback_content=content,
                    )
                    rel_path = f"topics/{topic.slug}.md"
                    self.uploader.stage(wiki_staging, rel_path, content)
                    wiki_entries.append(
                        WikiEntry(
                            slug=topic.slug,
                            section="topics",
                            summary=topic.title,
                            source_count=len(topic.finding_ids),
                            coverage="high" if len(topic.finding_ids) >= 5 else "medium" if len(topic.finding_ids) >= 2 else "low",
                        )
                    )
                    page_count += 1
                    progress.advance(task)

                progress.update(task, description="Phase 5: index")
                index_content = build_index_markdown(wiki_entries)
                self.uploader.stage(wiki_staging, "index.md", index_content)
                page_count += 1
                progress.advance(task)

        # Upload wiki batch
        target_uri = build_wiki_uri()
        if tracker is not None:
            tracker.set_note(f"Uploading {page_count} wiki pages")
        self.uploader.upload(
            wiki_staging,
            target_uri,
            reason="Phase 5 wiki compilation",
            wait=True,
            preserve_structure=True,
        )

        elapsed = tracker.complete_phase(f"{page_count} wiki pages compiled") if tracker is not None else None
        console.print(self._phase_summary("Phase 5", page_count, elapsed, unit="wiki pages compiled"))
        return page_count

    def phase3_compile_wiki(
        self,
        manifest: list[ResourceManifestItem],
        findings: list[Finding] | None = None,
        hypotheses: list[Hypothesis] | None = None,
        extractor: Any | None = None,
    ) -> int:
        """Compatibility wrapper for older tests and call sites."""
        bundle, _graph = self.build_synthesis_bundle(manifest, findings=findings, hypotheses=hypotheses)
        return self.phase5_compile_wiki(
            manifest,
            bundle,
            findings=findings,
            hypotheses=hypotheses,
            extractor=extractor,
        )

    def phase5_update_index_and_log(
        self, project_ids: list[str], phase_results: dict[str, int]
    ) -> None:
        """Write a run log entry under the ingest log collection.

        Parameters
        ----------
        project_ids
            Projects included in this ingest run.
        phase_results
            Counts returned by each phase.
        """
        entry = self.build_log_entry("ingest", project_ids, phase_results)
        log_staging = self.staging_root / "log"
        shutil.rmtree(log_staging, ignore_errors=True)
        log_staging.mkdir(parents=True, exist_ok=True)
        log_name = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ-ingest.md")
        self.uploader.stage(log_staging, log_name, entry, metadata={"kind": "log", "projects": project_ids})
        log_uri = build_wiki_log_uri()
        tracker = self._tracker
        if tracker is not None:
            tracker.start_phase("Phase 6: Writing ingest log", 1, note="Uploading run log entry")
            tracker.set_item(log_name, note="Uploading run log entry")
        for attempt in range(60):
            try:
                self.uploader.upload(
                    log_staging,
                    log_uri,
                    reason="Phase 6 — update wiki log",
                    wait=True,
                )
                break
            except Exception as exc:
                if "lock" in str(exc).lower() and attempt < 59:
                    delay = min(2 ** attempt, 30)
                    if tracker is not None:
                        tracker.set_note(
                            f"Waiting on wiki lock ({attempt + 1}/60), retry in {delay}s"
                        )
                    logger.warning(
                        "Phase 6 lock contention, retrying in %ds (attempt %d/60)...",
                        delay,
                        attempt + 1,
                    )
                    time.sleep(delay)
                else:
                    raise RuntimeError(f"Phase 6 log entry failed: {exc}") from exc
        if tracker is not None:
            elapsed = tracker.complete_phase("Ingest log entry uploaded")
            console.print(self._phase_summary("Phase 6", 1, elapsed, unit="log entry written"))

    def phase4_update_index_and_log(
        self, project_ids: list[str], phase_results: dict[str, int]
    ) -> None:
        """Compatibility wrapper for older tests and call sites."""
        self.phase5_update_index_and_log(project_ids, phase_results)

    def build_log_entry(
        self,
        action: str,
        project_ids: list[str],
        phase_results: dict[str, int],
    ) -> str:
        """Format a markdown log entry.

        Parameters
        ----------
        action
            Label for the action (e.g. ``"ingest"``).
        project_ids
            Projects covered.
        phase_results
            Mapping of phase name to item count.

        Returns
        -------
        str
            Markdown-formatted log entry.
        """
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        projects_str = ", ".join(project_ids)
        results_str = "\n".join(f"- {k}: {v}" for k, v in phase_results.items())
        return (
            f"## {timestamp} — {action}\n\n"
            f"Projects: {projects_str}\n\n"
            f"Results:\n{results_str}\n"
        )

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def run(
        self,
        project_ids: list[str] | None = None,
        resume: bool = True,
        extractor: Any | None = None,
        allow_checkpoint_resume: bool = True,
        restart_from: str | None = None,
        from_scratch: bool = False,
    ) -> dict[str, int]:
        """Execute the full synthesis-backed pipeline.

        Parameters
        ----------
        project_ids
            Projects to ingest. ``None`` discovers all projects.
        resume
            Pass to phase 1 to skip already-ingested resources.
        extractor
            A ``CBORGExtractor`` for phase 2 knowledge extraction.
            If ``None``, phases 2-5 are skipped gracefully.
        allow_checkpoint_resume
            Automatically resume the latest incomplete compatible run.
        restart_from
            Force phases from this point onward to rerun.
        from_scratch
            Clear local durable ingest and graph state before starting.

        Returns
        -------
        dict[str, int]
            Counts per phase: ``corpus``, ``registry``, ``graph``,
            ``knowledge_graph``, ``wiki``.
        """
        console.print("\n[bold]Observatory Wiki V2 Ingest[/]")
        console.print(f"Projects: {', '.join(project_ids) if project_ids else 'all'}\n")

        if restart_from is not None and restart_from not in _PHASE_SEQUENCE:
            raise ValueError(f"restart_from must be one of {_PHASE_SEQUENCE!r}")

        checkpoint = self._prepare_run(
            project_ids=project_ids,
            resume_phase1=resume,
            allow_checkpoint_resume=allow_checkpoint_resume,
            restart_from=restart_from,
            from_scratch=from_scratch,
        )
        if checkpoint["status"] in {"running", "failed"} and any(
            phase_data["status"] == "completed" for phase_data in checkpoint["phases"].values()
        ):
            next_pending = next(
                (
                    phase
                    for phase in _PHASE_SEQUENCE
                    if checkpoint["phases"][phase]["status"] != "completed"
                ),
                "done",
            )
            console.print(f"[dim]Resuming run {checkpoint['run_id']} from {next_pending}[/]")

        manifest = self.build_corpus_manifest(project_ids=project_ids)
        phase_results = {
            phase: int(checkpoint["phases"][phase].get("count", 0))
            for phase in ("corpus", "registry", "graph", "knowledge_graph", "wiki")
        }

        bundle: KnowledgeSynthesisBundle | None = None
        graph: Any | None = None
        current_phase = "corpus"
        tracker_cm = IngestProgressTracker(console, _PHASE_SEQUENCE) if console.is_terminal else nullcontext(None)
        try:
            with tracker_cm as tracker:
                self._tracker = tracker
                if tracker is not None:
                    completed_phases = sum(
                        1 for phase in _PHASE_SEQUENCE if checkpoint["phases"][phase]["status"] == "completed"
                    )
                    tracker.completed_phases = completed_phases
                    tracker.progress.update(
                        tracker.run_task,
                        completed=completed_phases,
                        current_item="resume" if completed_phases else "starting",
                        note="Resuming checkpoint" if completed_phases else "Starting new run",
                    )
                    tracker.refresh()
                if not self._phase_is_complete(checkpoint, "corpus"):
                    phase_results["corpus"] = self.phase1_upload_corpus(manifest, resume=resume)
                    checkpoint = self._mark_phase_completed(checkpoint, "corpus", phase_results["corpus"])
                else:
                    phase_results["corpus"] = int(checkpoint["phases"]["corpus"].get("count", 0))

                current_phase = "registry"
                if not self._phase_is_complete(checkpoint, "registry"):
                    phase_results["registry"] = self.phase2_extract_and_register(manifest, extractor=extractor)
                    checkpoint = self._mark_phase_completed(checkpoint, "registry", phase_results["registry"])
                else:
                    phase_results["registry"] = int(checkpoint["phases"]["registry"].get("count", 0))

                current_phase = "graph"
                if not self._phase_is_complete(checkpoint, "graph"):
                    phase_results["graph"] = self.phase3_build_graph(manifest)
                    checkpoint = self._mark_phase_completed(checkpoint, "graph", phase_results["graph"])
                else:
                    phase_results["graph"] = int(checkpoint["phases"]["graph"].get("count", 0))

                if (
                    not self._phase_is_complete(checkpoint, "knowledge_graph")
                    or not self._phase_is_complete(checkpoint, "wiki")
                ):
                    if tracker is not None:
                        tracker.set_note("Building synthesis bundle")
                    bundle, graph = self.build_synthesis_bundle(manifest)

                current_phase = "knowledge_graph"
                if not self._phase_is_complete(checkpoint, "knowledge_graph"):
                    assert bundle is not None
                    phase_results["knowledge_graph"] = self.phase4_export_knowledge_graph(bundle, graph=graph)
                    checkpoint = self._mark_phase_completed(
                        checkpoint,
                        "knowledge_graph",
                        phase_results["knowledge_graph"],
                    )
                else:
                    phase_results["knowledge_graph"] = int(
                        checkpoint["phases"]["knowledge_graph"].get("count", 0)
                    )

                current_phase = "wiki"
                if not self._phase_is_complete(checkpoint, "wiki"):
                    assert bundle is not None
                    phase_results["wiki"] = self.phase5_compile_wiki(
                        manifest,
                        bundle,
                        extractor=extractor,
                    )
                    checkpoint = self._mark_phase_completed(checkpoint, "wiki", phase_results["wiki"])
                else:
                    phase_results["wiki"] = int(checkpoint["phases"]["wiki"].get("count", 0))

                current_phase = "log"
                effective_project_ids = project_ids or [item.project_ids[0] for item in manifest if item.project_ids]
                unique_project_ids = list(dict.fromkeys(effective_project_ids))
                if not self._phase_is_complete(checkpoint, "log"):
                    self.phase5_update_index_and_log(unique_project_ids, phase_results)
                    checkpoint = self._mark_phase_completed(checkpoint, "log", 1)

                checkpoint["status"] = "completed"
                self._save_checkpoint(checkpoint)
                if tracker is not None:
                    tracker.set_note("Run completed")
                return phase_results
        except Exception as exc:
            self._mark_run_failed(checkpoint, current_phase, exc)
            raise
        finally:
            self._tracker = None
