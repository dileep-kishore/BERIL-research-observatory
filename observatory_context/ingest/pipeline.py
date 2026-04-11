"""Synthesis-backed ingest pipeline orchestrator for the BERIL Research Observatory."""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp
from typing import Any
from uuid import uuid4

import yaml
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

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
    build_corpus_uri,
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
        console=console,
    )


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
                rel = source.name
                self.uploader.stage(corpus_staging, rel, content, metadata=item.metadata)
                staged.append(item)
                progress.advance(task)

        if staged:
            target_uri = build_corpus_uri("_batch")
            self.uploader.upload(
                corpus_staging,
                target_uri,
                reason="Phase 1 corpus ingest",
                wait=False,
            )

        console.print(f"  [green]✓[/] Phase 1: {len(staged)} resources uploaded")
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
            console.print("  [dim]Phase 2: skipped (no extractor)[/]")
            return 0

        project_ids = sorted({pid for item in manifest for pid in item.project_ids})
        registry_staging = self.staging_root / "registry"
        shutil.rmtree(registry_staging, ignore_errors=True)
        registry_staging.mkdir(parents=True, exist_ok=True)

        all_entries: list[Finding | Hypothesis] = []

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

                # Throttle to stay under CBORG rate limits (~20 req/min)
                time.sleep(3)

                entries = extraction_to_registry_entries(extraction, pid)
                self._persist_project_entries(pid, entries)
                all_entries.extend(entries)
                progress.advance(task)

        staged_count = self._stage_registry_snapshot(registry_staging)
        if staged_count:
            target_uri = build_registry_uri()
            self.uploader.upload(
                registry_staging,
                target_uri,
                reason="Phase 2 registry ingest",
                wait=False,
            )

        console.print(f"  [green]✓[/] Phase 2: {len(all_entries)} registry entries created")
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

        # Resolve all entities
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

        node_count = builder.G.number_of_nodes()
        console.print(
            f"  [green]✓[/] Phase 3: {node_count} nodes, "
            f"{builder.G.number_of_edges()} edges, "
            f"{len(communities)} communities"
        )
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
            console.print("  [dim]Phase 4: skipped (empty synthesis bundle)[/]")
            return 0
        export_staging = self.staging_root / "knowledge-layer"
        shutil.rmtree(export_staging, ignore_errors=True)
        export_staging.mkdir(parents=True, exist_ok=True)
        exporter = KnowledgeGraphExporter(bundle=bundle, graph=graph)
        file_count = exporter.export_all(export_staging)
        self.uploader.upload(
            export_staging,
            build_observatory_root_uri(),
            reason="Phase 4 knowledge-graph export",
            wait=False,
        )
        relation_count = exporter.create_relations(self.client)
        console.print(
            f"  [green]✓[/] Phase 4: {file_count} knowledge-graph files and "
            f"{relation_count} relations exported"
        )
        return file_count

    def phase5_compile_wiki(
        self,
        manifest: list[ResourceManifestItem],
        bundle: KnowledgeSynthesisBundle,
        findings: list[Finding] | None = None,
        hypotheses: list[Hypothesis] | None = None,
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
        self.uploader.upload(
            wiki_staging,
            target_uri,
            reason="Phase 5 wiki compilation",
            wait=False,
        )

        console.print(f"  [green]✓[/] Phase 5: {page_count} wiki pages compiled")
        return page_count

    def phase3_compile_wiki(
        self,
        manifest: list[ResourceManifestItem],
        findings: list[Finding] | None = None,
        hypotheses: list[Hypothesis] | None = None,
    ) -> int:
        """Compatibility wrapper for older tests and call sites."""
        bundle, _graph = self.build_synthesis_bundle(manifest, findings=findings, hypotheses=hypotheses)
        return self.phase5_compile_wiki(manifest, bundle, findings=findings, hypotheses=hypotheses)

    def phase5_update_index_and_log(
        self, project_ids: list[str], phase_results: dict[str, int]
    ) -> None:
        """Append a log entry to wiki/log.md.

        Parameters
        ----------
        project_ids
            Projects included in this ingest run.
        phase_results
            Counts returned by each phase.
        """
        entry = self.build_log_entry("ingest", project_ids, phase_results)
        log_uri = build_wiki_log_uri()
        for attempt in range(8):
            try:
                self.client.add_text_resource(
                    uri=log_uri,
                    content=entry,
                    metadata={"kind": "log", "projects": project_ids},
                    reason="Phase 6 — update wiki log",
                    wait=False,
                )
                break
            except Exception as exc:
                if "lock" in str(exc).lower() and attempt < 7:
                    delay = min(2 ** attempt, 30)
                    logger.warning("Phase 6 lock contention, retrying in %ds (attempt %d/8)...", delay, attempt + 1)
                    time.sleep(delay)
                else:
                    raise RuntimeError(f"Phase 6 log entry failed: {exc}") from exc

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
        try:
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
                phase_results["wiki"] = self.phase5_compile_wiki(manifest, bundle)
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
            return phase_results
        except Exception as exc:
            self._mark_run_failed(checkpoint, current_phase, exc)
            raise
