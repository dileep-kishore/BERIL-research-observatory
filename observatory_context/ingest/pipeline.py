"""4-phase ingest pipeline orchestrator for the BERIL Research Observatory."""

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
from observatory_context.graph.report import generate_graph_report, save_report
from observatory_context.graph.resolver import EntityResolver
from observatory_context.ingest.batch import BatchUploader
from observatory_context.ingest.manifest import ResourceManifestItem, build_resource_manifest
from observatory_context.registry.extract import extraction_to_registry_entries
from observatory_context.registry.schema import Finding, Hypothesis
from observatory_context.uris import (
    build_corpus_uri,
    build_registry_uri,
    build_wiki_log_uri,
    build_wiki_uri,
)
from observatory_context.wiki.compiler import (
    compile_entity_page,
    compile_hypothesis_page,
    compile_topic_page,
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

    def phase4_compile_wiki(
        self,
        manifest: list[ResourceManifestItem],
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
        # Collect entries from staged registry files if not provided
        if findings is None or hypotheses is None:
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
            if findings is None:
                findings = staged_findings
            if hypotheses is None:
                hypotheses = staged_hypotheses

        if not findings and not hypotheses:
            console.print("  [dim]Phase 4: skipped (no registry entries)[/]")
            return 0

        wiki_staging = self.staging_root / "wiki"
        wiki_staging.mkdir(parents=True, exist_ok=True)

        # Load graph for cross-linking (built in Phase 3)
        import networkx as nx
        graph_path = self.repo_root / "data" / "graph" / "graph.json"
        graph: nx.MultiDiGraph | None = None
        communities: dict[str, dict] | None = None
        if graph_path.exists():
            import json as _json
            graph = nx.node_link_graph(_json.loads(graph_path.read_text(encoding="utf-8")))
            comm_path = self.repo_root / "data" / "graph" / "communities.json"
            if comm_path.exists():
                communities = _json.loads(comm_path.read_text(encoding="utf-8"))

        wiki_entries: list[WikiEntry] = []
        page_count = 0

        # --- Entity pages ---
        entity_findings: dict[tuple[str, str], list[Finding]] = {}
        entity_hypotheses: dict[tuple[str, str], list[Hypothesis]] = {}
        entity_projects: dict[tuple[str, str], set[str]] = {}

        for f in findings:
            for ref in f.related_entities:
                key = (ref.type, ref.label)
                entity_findings.setdefault(key, []).append(f)
                entity_projects.setdefault(key, set()).add(f.project_id)

        for h in hypotheses:
            for ref in h.related_entities:
                key = (ref.type, ref.label)
                entity_hypotheses.setdefault(key, []).append(h)
                for pid in h.project_ids:
                    entity_projects.setdefault(key, set()).add(pid)

        all_entity_keys = set(entity_findings) | set(entity_hypotheses)
        project_findings: dict[str, list[Finding]] = {}
        project_hypotheses: dict[str, list[Hypothesis]] = {}
        project_entities: dict[str, list[dict]] = {}
        for f in findings:
            project_findings.setdefault(f.project_id, []).append(f)
            for ref in f.related_entities:
                project_entities.setdefault(f.project_id, []).append(
                    {"type": ref.type, "label": ref.label}
                )
        for h in hypotheses:
            for pid in h.project_ids:
                project_hypotheses.setdefault(pid, []).append(h)
        topic_ids = sorted(set(project_findings) | set(project_hypotheses))

        # Deduplicate project_entities
        for pid in project_entities:
            seen = set()
            deduped = []
            for ent in project_entities[pid]:
                key = (ent["type"], ent["label"])
                if key not in seen:
                    seen.add(key)
                    deduped.append(ent)
            project_entities[pid] = deduped

        total_pages = len(all_entity_keys) + len(hypotheses) + len(topic_ids) + 1

        with _make_progress() as progress:
            task = progress.add_task("Phase 4: Compiling wiki", total=total_pages)

            from observatory_context.uris import _ENTITY_TYPE_PLURALS
            from observatory_context.graph.builder import _entity_node_id

            for entity_type, label in sorted(all_entity_keys):
                slug = slugify(label)
                progress.update(task, description=f"Phase 4: entity/{slug}")
                e_findings = entity_findings.get((entity_type, label), [])
                e_hypotheses = entity_hypotheses.get((entity_type, label), [])
                e_projects = sorted(entity_projects.get((entity_type, label), set()))

                # Get related entities from graph
                related_entities: list[dict] = []
                community_info: dict | None = None
                if graph is not None:
                    nid = _entity_node_id(entity_type, label)
                    if nid in graph:
                        # Find RELATED_TO neighbors
                        for _, neighbor, data in graph.edges(nid, data=True):
                            if data.get("relation") == "RELATED_TO" and neighbor in graph.nodes:
                                ndata = graph.nodes[neighbor]
                                if ndata.get("kind") == "entity":
                                    related_entities.append({
                                        "type": ndata.get("entity_type", "concept"),
                                        "label": ndata.get("canonical_name", neighbor),
                                        "weight": data.get("weight", 1),
                                    })
                        # Get community info
                        if communities:
                            comm_id = str(graph.nodes[nid].get("community", ""))
                            if comm_id in communities:
                                c = communities[comm_id]
                                community_info = {
                                    "name": c.get("name", f"Community {comm_id}"),
                                    "size": len(c.get("members", [])),
                                }

                content = compile_entity_page(
                    entity_type=entity_type,
                    slug=slug,
                    label=label,
                    findings=e_findings,
                    hypotheses=e_hypotheses,
                    project_ids=e_projects,
                    related_entities=related_entities,
                    community=community_info,
                )
                plural = _ENTITY_TYPE_PLURALS.get(entity_type, f"{entity_type}s")
                rel_path = f"entities/{plural}/{slug}.md"
                self.uploader.stage(wiki_staging, rel_path, content)
                wiki_entries.append(
                    WikiEntry(
                        slug=slug,
                        section=f"entities/{plural}",
                        summary=label,
                        source_count=len(e_findings),
                        coverage="high" if len(e_findings) >= 5 else "medium" if len(e_findings) >= 2 else "low",
                    )
                )
                page_count += 1
                progress.advance(task)

            # --- Hypothesis pages ---
            for h in hypotheses:
                slug = slugify(h.hypothesis_id)
                progress.update(task, description=f"Phase 4: hypothesis/{slug}")
                supporting = [f for f in findings if h.hypothesis_id in (f.evidence_ids or [])]
                if not supporting:
                    supporting = [f for f in findings if f.project_id in h.project_ids]
                content = compile_hypothesis_page(
                    hypothesis=h,
                    supporting_findings=supporting,
                )
                rel_path = f"hypotheses/{slug}.md"
                self.uploader.stage(wiki_staging, rel_path, content)
                wiki_entries.append(
                    WikiEntry(
                        slug=slug,
                        section="hypotheses",
                        summary=h.statement[:80],
                        source_count=len(supporting),
                        coverage="high" if len(supporting) >= 5 else "medium" if len(supporting) >= 2 else "low",
                    )
                )
                page_count += 1
                progress.advance(task)

            # --- Topic pages ---
            for pid in topic_ids:
                slug = slugify(pid)
                progress.update(task, description=f"Phase 4: topic/{slug}")
                t_findings = project_findings.get(pid, [])
                t_hypotheses = project_hypotheses.get(pid, [])
                t_entities = project_entities.get(pid, [])
                content = compile_topic_page(
                    slug=slug,
                    title=pid,
                    findings=t_findings,
                    hypotheses=t_hypotheses,
                    project_ids=[pid],
                    entities_studied=t_entities,
                )
                rel_path = f"topics/{slug}.md"
                self.uploader.stage(wiki_staging, rel_path, content)
                wiki_entries.append(
                    WikiEntry(
                        slug=slug,
                        section="topics",
                        summary=f"Findings from {pid}",
                        source_count=len(t_findings),
                        coverage="high" if len(t_findings) >= 5 else "medium" if len(t_findings) >= 2 else "low",
                    )
                )
                page_count += 1
                progress.advance(task)

            # --- Index page ---
            progress.update(task, description="Phase 4: index")
            index_content = build_index_markdown(wiki_entries)
            self.uploader.stage(wiki_staging, "index.md", index_content)
            page_count += 1
            progress.advance(task)

        # Upload wiki batch
        target_uri = build_wiki_uri()
        self.uploader.upload(
            wiki_staging,
            target_uri,
            reason="Phase 4 wiki compilation",
            wait=False,
        )

        console.print(f"  [green]✓[/] Phase 4: {page_count} wiki pages compiled")
        return page_count

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
                    reason="Phase 4 — update wiki log",
                    wait=False,
                )
                break
            except Exception as exc:
                if "lock" in str(exc).lower() and attempt < 7:
                    delay = min(2 ** attempt, 30)
                    logger.warning("Phase 4 lock contention, retrying in %ds (attempt %d/8)...", delay, attempt + 1)
                    time.sleep(delay)
                else:
                    logger.warning("Phase 4 log entry failed (non-critical): %s", exc)
                    break

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
        """Execute the full 5-phase pipeline.

        Parameters
        ----------
        project_ids
            Projects to ingest. ``None`` discovers all projects.
        resume
            Pass to phase 1 to skip already-ingested resources.
        extractor
            A ``CBORGExtractor`` for phase 2 knowledge extraction.
            If ``None``, phases 2-4 are skipped gracefully.

        Returns
        -------
        dict[str, int]
            Counts per phase: ``corpus``, ``registry``, ``graph``, ``wiki``.
        """
        console.print("\n[bold]Observatory Wiki V2 Ingest[/]")
        console.print(f"Projects: {', '.join(project_ids) if project_ids else 'all'}\n")

        manifest = self.build_corpus_manifest(project_ids=project_ids)
        corpus_count = self.phase1_upload_corpus(manifest, resume=resume)

        # Phase 2: extract knowledge and create registry entries
        registry_count = self.phase2_extract_and_register(manifest, extractor=extractor)

        # Phase 3: resolve entities and build knowledge graph
        graph_count = self.phase3_build_graph(manifest)

        # Phase 4: compile wiki pages from registry entries
        wiki_count = self.phase4_compile_wiki(manifest)

        phase_results = {
            "corpus": corpus_count,
            "registry": registry_count,
            "graph": graph_count,
            "wiki": wiki_count,
        }

        effective_project_ids = project_ids or [item.project_ids[0] for item in manifest if item.project_ids]
        unique_project_ids = list(dict.fromkeys(effective_project_ids))
        self.phase5_update_index_and_log(unique_project_ids, phase_results)

        return phase_results
