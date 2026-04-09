"""4-phase ingest pipeline orchestrator for the BERIL Research Observatory."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp

from observatory_context.client import OpenVikingObservatoryClient
from observatory_context.ingest.batch import BatchUploader
from observatory_context.ingest.manifest import ResourceManifestItem, build_resource_manifest
from observatory_context.uris import build_corpus_uri, build_wiki_log_uri


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
    ) -> dict[str, int]:
        """Execute the full 4-phase pipeline.

        Phases 2 and 3 are reserved for future implementation and return 0.

        Parameters
        ----------
        project_ids
            Projects to ingest. ``None`` discovers all projects.
        resume
            Pass to phase 1 to skip already-ingested resources.

        Returns
        -------
        dict[str, int]
            Counts per phase: ``corpus``, ``registry``, ``wiki``.
        """
        manifest = self.build_corpus_manifest(project_ids=project_ids)
        corpus_count = self.phase1_upload_corpus(manifest, resume=resume)

        # Phases 2 (registry) and 3 (wiki) will be added later
        registry_count = 0
        wiki_count = 0

        phase_results = {
            "corpus": corpus_count,
            "registry": registry_count,
            "wiki": wiki_count,
        }

        effective_project_ids = project_ids or [item.project_ids[0] for item in manifest if item.project_ids]
        unique_project_ids = list(dict.fromkeys(effective_project_ids))
        self.phase4_update_index_and_log(unique_project_ids, phase_results)

        return phase_results
