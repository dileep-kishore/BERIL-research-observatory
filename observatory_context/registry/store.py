"""OpenViking-backed YAML read/write for the structured knowledge registry."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from observatory_context.registry.schema import (
    Artifact,
    Discovery,
    Evidence,
    Figure,
    Finding,
    Hypothesis,
    Pitfall,
    Project,
    ResearchIdea,
)
from observatory_context.staging import write_staged_file
from observatory_context.uris import (
    build_registry_artifact_uri,
    build_registry_discovery_uri,
    build_registry_evidence_uri,
    build_registry_figure_uri,
    build_registry_finding_uri,
    build_registry_hypothesis_uri,
    build_registry_idea_uri,
    build_registry_pitfall_uri,
    build_registry_project_uri,
    build_registry_uri,
)

if TYPE_CHECKING:
    from observatory_context.client import OpenVikingObservatoryClient


def _is_not_found(exc: Exception) -> bool:
    return any(cls.__name__ == "NotFoundError" for cls in type(exc).__mro__)


def _to_yaml(model) -> str:
    return yaml.safe_dump(model.model_dump(mode="json", exclude_none=True))


class RegistryStore:
    """Read/write registry entries in OpenViking as YAML resources."""

    def __init__(self, client: OpenVikingObservatoryClient) -> None:
        self.client = client

    # ------------------------------------------------------------------
    # Single writes
    # ------------------------------------------------------------------

    def write_finding(self, finding: Finding, wait: bool = True) -> None:
        self.client.add_text_resource(
            uri=build_registry_finding_uri(finding.finding_id),
            content=_to_yaml(finding),
            metadata={},
            reason=f"Write finding {finding.finding_id}",
            wait=wait,
        )

    def write_project(self, project: Project, wait: bool = True) -> None:
        self.client.add_text_resource(
            uri=build_registry_project_uri(project.project_id),
            content=_to_yaml(project),
            metadata={},
            reason=f"Write project {project.project_id}",
            wait=wait,
        )

    def write_hypothesis(self, hypothesis: Hypothesis, wait: bool = True) -> None:
        self.client.add_text_resource(
            uri=build_registry_hypothesis_uri(hypothesis.hypothesis_id),
            content=_to_yaml(hypothesis),
            metadata={},
            reason=f"Write hypothesis {hypothesis.hypothesis_id}",
            wait=wait,
        )

    def write_evidence(self, evidence: Evidence, wait: bool = True) -> None:
        self.client.add_text_resource(
            uri=build_registry_evidence_uri(evidence.evidence_id),
            content=_to_yaml(evidence),
            metadata={},
            reason=f"Write evidence {evidence.evidence_id}",
            wait=wait,
        )

    def write_artifact(self, artifact: Artifact, wait: bool = True) -> None:
        self.client.add_text_resource(
            uri=build_registry_artifact_uri(artifact.artifact_id),
            content=_to_yaml(artifact),
            metadata={},
            reason=f"Write artifact {artifact.artifact_id}",
            wait=wait,
        )

    def write_figure(self, figure: Figure, wait: bool = True) -> None:
        self.client.add_text_resource(
            uri=build_registry_figure_uri(figure.figure_id),
            content=_to_yaml(figure),
            metadata={},
            reason=f"Write figure {figure.figure_id}",
            wait=wait,
        )

    def write_pitfall(self, pitfall: Pitfall, wait: bool = True) -> None:
        self.client.add_text_resource(
            uri=build_registry_pitfall_uri(pitfall.pitfall_id),
            content=_to_yaml(pitfall),
            metadata={},
            reason=f"Write pitfall {pitfall.pitfall_id}",
            wait=wait,
        )

    def write_idea(self, idea: ResearchIdea, wait: bool = True) -> None:
        self.client.add_text_resource(
            uri=build_registry_idea_uri(idea.idea_id),
            content=_to_yaml(idea),
            metadata={},
            reason=f"Write idea {idea.idea_id}",
            wait=wait,
        )

    def write_discovery(self, discovery: Discovery, wait: bool = True) -> None:
        self.client.add_text_resource(
            uri=build_registry_discovery_uri(discovery.discovery_id),
            content=_to_yaml(discovery),
            metadata={},
            reason=f"Write discovery {discovery.discovery_id}",
            wait=wait,
        )

    # ------------------------------------------------------------------
    # Single reads
    # ------------------------------------------------------------------

    def read_finding(self, finding_id: str) -> Finding | None:
        try:
            content = self.client.read_resource(build_registry_finding_uri(finding_id))
        except Exception as exc:
            if _is_not_found(exc):
                return None
            raise
        return Finding.model_validate(yaml.safe_load(content))

    def read_project(self, project_id: str) -> Project | None:
        try:
            content = self.client.read_resource(build_registry_project_uri(project_id))
        except Exception as exc:
            if _is_not_found(exc):
                return None
            raise
        return Project.model_validate(yaml.safe_load(content))

    def read_hypothesis(self, hypothesis_id: str) -> Hypothesis | None:
        try:
            content = self.client.read_resource(build_registry_hypothesis_uri(hypothesis_id))
        except Exception as exc:
            if _is_not_found(exc):
                return None
            raise
        return Hypothesis.model_validate(yaml.safe_load(content))

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_findings(self, project_id: str | None = None) -> list[Finding]:
        uri = f"{build_registry_uri()}/findings"
        entries = self.client.list_resources(uri)
        findings = []
        for entry in entries:
            content = self.client.read_resource(entry["uri"])
            finding = Finding.model_validate(yaml.safe_load(content))
            if project_id is None or finding.project_id == project_id:
                findings.append(finding)
        return findings

    def list_hypotheses(self, status: str | None = None) -> list[Hypothesis]:
        uri = f"{build_registry_uri()}/hypotheses"
        entries = self.client.list_resources(uri)
        hypotheses = []
        for entry in entries:
            content = self.client.read_resource(entry["uri"])
            hyp = Hypothesis.model_validate(yaml.safe_load(content))
            if status is None or hyp.status == status:
                hypotheses.append(hyp)
        return hypotheses

    def list_projects(self) -> list[Project]:
        uri = f"{build_registry_uri()}/projects"
        entries = self.client.list_resources(uri)
        projects = []
        for entry in entries:
            content = self.client.read_resource(entry["uri"])
            projects.append(Project.model_validate(yaml.safe_load(content)))
        return projects

    # ------------------------------------------------------------------
    # Batch
    # ------------------------------------------------------------------

    def batch_write_findings(
        self, findings: list[Finding], staging_dir: Path, wait: bool = False
    ) -> None:
        """Stage finding YAML files locally then batch-upload to OpenViking."""
        for finding in findings:
            write_staged_file(
                base=staging_dir,
                rel_path=f"{finding.finding_id}.yaml",
                content=_to_yaml(finding),
            )
        self.client.batch_add(
            path=str(staging_dir),
            to=f"{build_registry_uri()}/findings",
            reason="Batch write findings",
            wait=wait,
        )
