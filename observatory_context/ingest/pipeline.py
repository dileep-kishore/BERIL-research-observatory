"""Synthesis-backed ingest pipeline orchestrator for the BERIL Research Observatory."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

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

    # ------------------------------------------------------------------
    # Phase helpers
    # ------------------------------------------------------------------

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
        registry_staging.mkdir(parents=True, exist_ok=True)

        all_entries: list[Finding | Hypothesis] = []

        with _make_progress() as progress:
            task = progress.add_task("Phase 2: Extracting knowledge", total=len(project_ids))
            for pid in project_ids:
                progress.update(task, description=f"Phase 2: {pid}")
                report_path = self.repo_root / "projects" / pid / "REPORT.md"
                if not report_path.exists():
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
                    progress.advance(task)
                    continue

                # Throttle to stay under CBORG rate limits (~20 req/min)
                time.sleep(3)

                entries = extraction_to_registry_entries(extraction, pid)
                all_entries.extend(entries)

                for entry in entries:
                    if isinstance(entry, Finding):
                        rel_path = f"findings/{entry.finding_id}.yaml"
                    elif isinstance(entry, Hypothesis):
                        rel_path = f"hypotheses/{entry.hypothesis_id}.yaml"
                    else:
                        continue
                    content = yaml.dump(
                        entry.model_dump(exclude_none=True),
                        default_flow_style=False,
                        sort_keys=True,
                    )
                    self.uploader.stage(registry_staging, rel_path, content)
                progress.advance(task)

        if all_entries:
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
            findings, hypotheses = self._load_staged_entries()

        if not findings and not hypotheses:
            console.print("  [dim]Phase 3: skipped (no registry entries)[/]")
            return 0

        graph_dir = self.repo_root / "data" / "graph"
        graph_dir.mkdir(parents=True, exist_ok=True)

        # Load existing graph for incremental builds
        graph_path = graph_dir / "graph.json"
        if graph_path.exists():
            builder = GraphBuilder.load(graph_path)
        else:
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
            project_ids = sorted({pid for item in manifest for pid in item.project_ids})
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
            findings, hypotheses = self._load_staged_entries()
        if not findings and not hypotheses:
            return KnowledgeSynthesisBundle(), None
        graph, communities = self._load_graph_artifacts()
        project_ids = sorted({pid for item in manifest for pid in item.project_ids})
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
            findings, hypotheses = self._load_staged_entries()

        if not bundle.entities and not bundle.hypotheses and not bundle.topics:
            console.print("  [dim]Phase 5: skipped (empty synthesis bundle)[/]")
            return 0

        wiki_staging = self.staging_root / "wiki"
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
                    logger.warning("Phase 6 log entry failed (non-critical): %s", exc)
                    break

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

        Returns
        -------
        dict[str, int]
            Counts per phase: ``corpus``, ``registry``, ``graph``,
            ``knowledge_graph``, ``wiki``.
        """
        console.print("\n[bold]Observatory Wiki V2 Ingest[/]")
        console.print(f"Projects: {', '.join(project_ids) if project_ids else 'all'}\n")

        manifest = self.build_corpus_manifest(project_ids=project_ids)
        corpus_count = self.phase1_upload_corpus(manifest, resume=resume)

        # Phase 2: extract knowledge and create registry entries
        registry_count = self.phase2_extract_and_register(manifest, extractor=extractor)

        # Phase 3: resolve entities and build knowledge graph
        graph_count = self.phase3_build_graph(manifest)

        bundle, graph = self.build_synthesis_bundle(manifest)

        knowledge_graph_count = self.phase4_export_knowledge_graph(bundle, graph=graph)

        wiki_count = self.phase5_compile_wiki(manifest, bundle)

        phase_results = {
            "corpus": corpus_count,
            "registry": registry_count,
            "graph": graph_count,
            "knowledge_graph": knowledge_graph_count,
            "wiki": wiki_count,
        }

        effective_project_ids = project_ids or [item.project_ids[0] for item in manifest if item.project_ids]
        unique_project_ids = list(dict.fromkeys(effective_project_ids))
        self.phase5_update_index_and_log(unique_project_ids, phase_results)

        return phase_results
