"""4-phase ingest pipeline orchestrator for the BERIL Research Observatory."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import yaml

from observatory_context._text import slugify
from observatory_context.client import OpenVikingObservatoryClient
from observatory_context.ingest.batch import BatchUploader
from observatory_context.ingest.manifest import ResourceManifestItem, build_resource_manifest
from observatory_context.registry.extract import extraction_to_registry_entries
from observatory_context.registry.schema import Finding, Hypothesis
from observatory_context.uris import (
    build_corpus_uri,
    build_registry_uri,
    build_wiki_entity_uri,
    build_wiki_hypothesis_uri,
    build_wiki_index_uri,
    build_wiki_log_uri,
    build_wiki_topic_uri,
    build_wiki_uri,
)
from observatory_context.wiki.compiler import (
    compile_entity_page,
    compile_hypothesis_page,
    compile_topic_page,
)
from observatory_context.wiki.index import WikiEntry, build_index_markdown

logger = logging.getLogger(__name__)


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
        for item in manifest:
            if resume and self.client.resource_exists(item.uri):
                continue
            source = Path(item.source_path)
            if not source.exists():
                continue
            try:
                content = source.read_text(encoding="utf-8")
            except Exception:
                continue
            rel = source.name
            self.uploader.stage(corpus_staging, rel, content, metadata=item.metadata)
            staged.append(item)

        if staged:
            target_uri = build_corpus_uri("_batch")
            self.uploader.upload(
                corpus_staging,
                target_uri,
                reason="Phase 1 corpus ingest",
                wait=False,
            )

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
            return 0

        project_ids = sorted({pid for item in manifest for pid in item.project_ids})
        registry_staging = self.staging_root / "registry"
        registry_staging.mkdir(parents=True, exist_ok=True)

        all_entries: list[Finding | Hypothesis] = []

        for pid in project_ids:
            report_path = self.repo_root / "projects" / pid / "REPORT.md"
            if not report_path.exists():
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
                continue

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

        if all_entries:
            target_uri = build_registry_uri()
            self.uploader.upload(
                registry_staging,
                target_uri,
                reason="Phase 2 registry ingest",
                wait=False,
            )

        return len(all_entries)

    def phase3_compile_wiki(
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
            return 0

        wiki_staging = self.staging_root / "wiki"
        wiki_staging.mkdir(parents=True, exist_ok=True)

        wiki_entries: list[WikiEntry] = []
        page_count = 0

        # --- Entity pages ---
        # Group findings by entity ref (type, label)
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
        for entity_type, label in sorted(all_entity_keys):
            slug = slugify(label)
            e_findings = entity_findings.get((entity_type, label), [])
            e_hypotheses = entity_hypotheses.get((entity_type, label), [])
            e_projects = sorted(entity_projects.get((entity_type, label), set()))
            content = compile_entity_page(
                entity_type=entity_type,
                slug=slug,
                label=label,
                findings=e_findings,
                hypotheses=e_hypotheses,
                project_ids=e_projects,
            )
            from observatory_context.uris import _ENTITY_TYPE_PLURALS

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

        # --- Hypothesis pages ---
        for h in hypotheses:
            slug = slugify(h.hypothesis_id)
            supporting = [f for f in findings if h.hypothesis_id in (f.evidence_ids or [])]
            # Also include findings from same projects
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

        # --- Topic pages ---
        # Group findings by project_id as a simple topic proxy
        project_findings: dict[str, list[Finding]] = {}
        project_hypotheses: dict[str, list[Hypothesis]] = {}
        for f in findings:
            project_findings.setdefault(f.project_id, []).append(f)
        for h in hypotheses:
            for pid in h.project_ids:
                project_hypotheses.setdefault(pid, []).append(h)

        for pid in sorted(set(project_findings) | set(project_hypotheses)):
            slug = slugify(pid)
            t_findings = project_findings.get(pid, [])
            t_hypotheses = project_hypotheses.get(pid, [])
            content = compile_topic_page(
                slug=slug,
                title=pid,
                findings=t_findings,
                hypotheses=t_hypotheses,
                project_ids=[pid],
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

        # --- Index page ---
        index_content = build_index_markdown(wiki_entries)
        self.uploader.stage(wiki_staging, "index.md", index_content)
        page_count += 1

        # Upload wiki batch
        target_uri = build_wiki_uri()
        self.uploader.upload(
            wiki_staging,
            target_uri,
            reason="Phase 3 wiki compilation",
            wait=False,
        )

        return page_count

    def phase4_update_index_and_log(
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
        self.client.add_text_resource(
            uri=log_uri,
            content=entry,
            metadata={"kind": "log", "projects": project_ids},
            reason="Phase 4 — update wiki log",
            wait=False,
        )

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
        """Execute the full 4-phase pipeline.

        Parameters
        ----------
        project_ids
            Projects to ingest. ``None`` discovers all projects.
        resume
            Pass to phase 1 to skip already-ingested resources.
        extractor
            A ``CBORGExtractor`` for phase 2 knowledge extraction.
            If ``None``, phases 2 and 3 are skipped gracefully.

        Returns
        -------
        dict[str, int]
            Counts per phase: ``corpus``, ``registry``, ``wiki``.
        """
        manifest = self.build_corpus_manifest(project_ids=project_ids)
        corpus_count = self.phase1_upload_corpus(manifest, resume=resume)

        # Phase 2: extract knowledge and create registry entries
        registry_count = self.phase2_extract_and_register(manifest, extractor=extractor)
        if registry_count > 0:
            self.client.wait_until_processed()

        # Phase 3: compile wiki pages from registry entries
        wiki_count = self.phase3_compile_wiki(manifest)
        if wiki_count > 0:
            self.client.wait_until_processed()

        phase_results = {
            "corpus": corpus_count,
            "registry": registry_count,
            "wiki": wiki_count,
        }

        effective_project_ids = project_ids or [item.project_ids[0] for item in manifest if item.project_ids]
        unique_project_ids = list(dict.fromkeys(effective_project_ids))
        self.phase4_update_index_and_log(unique_project_ids, phase_results)

        return phase_results
