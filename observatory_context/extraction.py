"""CBORG-based entity extraction and tier generation for observatory ingest."""

from __future__ import annotations

import json
import logging
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

_ENTITY_TYPES = Literal[
    "organism", "gene", "pathway", "condition",
    "environment", "method", "dataset", "concept",
]
_CONFIDENCE = Literal["high", "moderate", "low"]
_FINDING_TYPES = Literal["result", "negative_result", "methodological", "pattern"]
_PREDICATES = Literal[
    "enriched_in", "depleted_in", "correlated_with", "required_for",
    "produces", "degrades", "regulates", "inhibits",
    "associated_with", "studied_in", "contradicts", "supports",
]


class Entity(BaseModel):
    """A named entity extracted from a report."""

    type: _ENTITY_TYPES
    id: str
    name: str
    metadata: dict = Field(default_factory=dict)


class Relation(BaseModel):
    """A directed relationship between two entities."""

    subject: str
    predicate: _PREDICATES
    object: str
    evidence: str
    confidence: _CONFIDENCE
    conditions: list[str] = Field(default_factory=list)
    finding_type: _FINDING_TYPES = "result"
    source_span: str | None = None
    figure_refs: list[str] = Field(default_factory=list)


class HypothesisUpdate(BaseModel):
    """An update to a tracked hypothesis."""

    id: str
    status: str
    claim: str
    evidence_delta: str
    scope: str | None = None


class TimelineEvent(BaseModel):
    """A dated event in the research timeline."""

    date: str
    event: str
    type: str
    project: str | None = None


class EntityExtraction(BaseModel):
    """Container for all extracted knowledge from a single report."""

    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    hypotheses: list[HypothesisUpdate] = Field(default_factory=list)
    timeline_events: list[TimelineEvent] = Field(default_factory=list)


_EXTRACTION_SYSTEM = """\
You are extracting structured knowledge from microbiology research reports \
covering pangenome analysis, gene fitness, metabolomics, and related topics. \
Given a research report and provenance metadata, extract structured knowledge \
in JSON format matching the schema below. Return ONLY valid JSON with no \
markdown fences or commentary.

## Entity types (8)

Use these types with canonical naming:
- organism: Full species names (e.g. "Pseudomonas putida", not "P. putida")
- gene: Standard gene nomenclature (e.g. "PP_1234", "katE")
- pathway: Normalized common names (e.g. "TCA cycle", "beta-oxidation")
- condition: Experimental condition (e.g. "zinc stress", "carbon starvation")
- environment: Growth environment (e.g. "minimal media", "soil rhizosphere")
- method: Analytical method (e.g. "RB-TnSeq", "LC-MS metabolomics")
- dataset: Named dataset or database (e.g. "BERDL fitness data", "UniProt")
- concept: Abstract concept only when no other type fits

## Predicate vocabulary (constrained)

Relations MUST use one of these predicates:
enriched_in, depleted_in, correlated_with, required_for, produces, degrades, \
regulates, inhibits, associated_with, studied_in, contradicts, supports

## Confidence calibration

- high: p < 0.01 or strong quantitative evidence
- moderate: p < 0.05 or qualitative pattern
- low: suggested but not statistically tested

## Finding type classification

Each relation carries a finding_type:
- result: quantitative finding with statistical support
- negative_result: null or no-effect finding
- methodological: tool, approach, or pipeline used
- pattern: qualitative observation or trend

## Conditions and evidence

- conditions: list of experimental conditions under which the finding holds \
(e.g. ["zinc stress", "minimal media", "aerobic"])
- source_span: a brief verbatim excerpt (1-2 sentences) from the report \
supporting the claim
- figure_refs: extract figure references from ![caption](figures/filename) \
patterns in the report and link relevant ones to each relation

## Timeline events

Extract ALL dated milestones, experiments, and events. Do NOT drop these.

## Schema

{
  "entities": [
    {"type": "<entity type>", "id": "<slug>", "name": "<canonical display name>", "metadata": {}}
  ],
  "relations": [
    {
      "subject": "<entity id>",
      "predicate": "<predicate from vocabulary>",
      "object": "<entity id>",
      "evidence": "<brief description of evidence>",
      "confidence": "<high|moderate|low>",
      "conditions": ["<condition1>", "..."],
      "finding_type": "<result|negative_result|methodological|pattern>",
      "source_span": "<verbatim excerpt from report>",
      "figure_refs": ["<figures/filename.png>", "..."]
    }
  ],
  "hypotheses": [
    {
      "id": "<hypothesis id>",
      "status": "<open|supported|refuted|updated>",
      "claim": "<hypothesis statement>",
      "evidence_delta": "<what this report adds>",
      "scope": "<organism or condition scope, if applicable>"
    }
  ],
  "timeline_events": [
    {
      "date": "<YYYY-MM-DD>",
      "event": "<description>",
      "type": "<milestone|experiment|publication|meeting>",
      "project": "<project name or null>"
    }
  ]
}
"""


class CBORGExtractor:
    """Extract entities and generate text tiers via the CBORG API.

    Parameters
    ----------
    api_url:
        Base URL for the CBORG API (e.g. ``https://api.cborg.lbl.gov/v1``).
    model:
        Model identifier to use for all completions.
    api_key:
        Bearer token for the CBORG API.
    max_input_tokens:
        Maximum input tokens the model supports. Reports exceeding this
        (estimated at ~4 chars/token) are skipped.
    max_output_tokens:
        Maximum output tokens the model supports. Used as the default
        ``max_tokens`` for extraction calls.
    """

    def __init__(
        self,
        api_url: str,
        model: str,
        api_key: str,
        max_input_tokens: int | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        self.model = model
        self._api_url = api_url.rstrip("/")
        self._max_input_tokens = max_input_tokens
        self._max_output_tokens = max_output_tokens or 16384
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=120.0,
        )

    def extract_knowledge(self, report: str, provenance: dict) -> EntityExtraction:
        """Extract entities, relations, hypotheses, and timeline events from *report*.

        Parameters
        ----------
        report:
            Raw text of the project report.
        provenance:
            Metadata about the report origin (project name, date, etc.).

        Returns
        -------
        EntityExtraction
            Parsed extraction result; empty on parse failure.

        Raises
        ------
        ValueError
            If the prompt exceeds the model's max input token estimate.
        """
        prompt = self._build_extraction_prompt(report, provenance)
        total_chars = len(_EXTRACTION_SYSTEM) + len(prompt)
        estimated_tokens = total_chars // 4  # conservative ~4 chars/token
        if self._max_input_tokens and estimated_tokens > self._max_input_tokens:
            raise ValueError(
                f"Prompt too large (~{estimated_tokens} tokens) for model limit "
                f"({self._max_input_tokens} tokens)"
            )
        raw = self._chat(
            system=_EXTRACTION_SYSTEM,
            user=prompt,
            max_tokens=self._max_output_tokens,
        )
        try:
            data = json.loads(raw)
            return EntityExtraction.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Failed to parse extraction response: %s", exc)
            return EntityExtraction()

    def generate_abstract(self, content: str, max_tokens: int = 80) -> str:
        """Generate a concise L0 abstract (one or two sentences).

        Parameters
        ----------
        content:
            Full report or document text.
        max_tokens:
            Maximum tokens for the response.

        Returns
        -------
        str
            Short abstract suitable for L0 storage.
        """
        system = (
            "You are a scientific writing assistant. "
            "Summarise the provided research content in one or two sentences, "
            "capturing the core finding or objective."
        )
        return self._chat(system=system, user=content, max_tokens=max_tokens)

    def generate_overview(self, content: str, max_tokens: int = 300) -> str:
        """Generate a structured L1 overview paragraph.

        Parameters
        ----------
        content:
            Full report or document text.
        max_tokens:
            Maximum tokens for the response.

        Returns
        -------
        str
            Medium-length overview suitable for L1 storage.
        """
        system = (
            "You are a scientific writing assistant. "
            "Write a concise overview (3-5 sentences) of the provided research content, "
            "covering background, methods, key results, and significance."
        )
        return self._chat(system=system, user=content, max_tokens=max_tokens)

    def _build_extraction_prompt(self, report: str, provenance: dict) -> str:
        """Format the user-turn extraction prompt.

        Parameters
        ----------
        report:
            Raw report text.
        provenance:
            Metadata dict to include as context.

        Returns
        -------
        str
            Formatted prompt string.
        """
        provenance_lines = "\n".join(f"  {k}: {v}" for k, v in provenance.items())
        return (
            f"Provenance:\n{provenance_lines}\n\n"
            f"Extract ALL entities, relations, hypotheses, and timeline_events "
            f"from the following report. Instructions:\n"
            f"- Use canonical full names for entities (no abbreviations)\n"
            f"- Prefer specific entity types over 'concept'\n"
            f"- Include conditions and source_span for every relation\n"
            f"- Extract figure references (![caption](figures/...)) and link "
            f"them to relevant relations\n"
            f"- Do NOT skip timeline events or dated milestones\n"
            f"- Use the constrained predicate vocabulary\n\n"
            f"Report:\n{report}"
        )

    def _chat(self, system: str, user: str, max_tokens: int) -> str:
        """Call the /chat/completions endpoint and return the response text.

        Parameters
        ----------
        system:
            System message content.
        user:
            User message content.
        max_tokens:
            Maximum tokens for the completion.

        Returns
        -------
        str
            Stripped response text from the model.
        """
        import time

        _RETRYABLE = {429, 502, 503, 504}
        for attempt in range(5):
            try:
                response = self._client.post(
                    f"{self._api_url}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "max_tokens": max_tokens,
                        "temperature": 0.0,
                    },
                )
            except httpx.TransportError as exc:
                wait = 2 ** attempt
                logger.warning("Transport error, retrying in %ds (attempt %d/5): %s", wait, attempt + 1, exc)
                time.sleep(wait)
                continue

            if response.status_code in _RETRYABLE:
                wait = float(response.headers.get("retry-after", 2 ** attempt))
                logger.warning(
                    "HTTP %d, retrying in %.1fs (attempt %d/5)",
                    response.status_code, wait, attempt + 1,
                )
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()

        response.raise_for_status()  # raise on final failure
        return ""  # unreachable

    # ------------------------------------------------------------------
    # Operational knowledge enrichment
    # ------------------------------------------------------------------

    def enrich_operational(
        self,
        collection: str,
        data: dict,
    ) -> dict:
        """Enrich a raw operational knowledge entry via LLM.

        Takes a structured dict (from a skill or migration parser) and
        returns ``{"markdown": ..., "metadata": ...}`` where *markdown*
        is a clean, natural-language document suitable for OpenViking and
        *metadata* is an enriched frontmatter dict with extracted tags,
        entities, and category.

        Parameters
        ----------
        collection:
            One of ``"pitfall"``, ``"research_idea"``, ``"discovery"``.
        data:
            Raw entry dict.  Expected keys depend on collection type.

        Returns
        -------
        dict
            ``{"markdown": str, "metadata": dict}``
        """
        system = _ENRICH_SYSTEM_PROMPTS[collection]
        user = json.dumps(data, indent=2, default=str)
        raw = self._chat(system=system, user=user, max_tokens=2048)

        # Parse the JSON response
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("LLM enrichment returned non-JSON, using raw")
            result = {}

        markdown = result.get("markdown", "")
        metadata = result.get("metadata", {})

        # Ensure required fields survive
        if not markdown:
            markdown = self._fallback_markdown(collection, data)
        for key in ("title", "kind"):
            if key not in metadata:
                metadata[key] = data.get(key, data.get("title", ""))
        metadata.setdefault("kind", collection)

        return {"markdown": markdown, "metadata": metadata}

    def generate_collection_overview(
        self,
        collection: str,
        summaries: list[str],
    ) -> str:
        """Generate a collection-level overview from item summaries.

        Parameters
        ----------
        collection:
            Collection type name.
        summaries:
            List of one-line summaries of each item in the collection.

        Returns
        -------
        str
            Markdown overview suitable as ``_overview.md``.
        """
        system = (
            f"You are a scientific knowledge organizer. Given a list of {collection} "
            f"summaries from a microbial genomics research observatory, write a "
            f"structured overview that groups them by theme/category, highlights "
            f"the most important ones, and identifies patterns. "
            f"Output clean markdown with headings and bullet points."
        )
        user = "\n".join(f"- {s}" for s in summaries)
        return self._chat(system=system, user=user, max_tokens=2048)

    def _fallback_markdown(self, collection: str, data: dict) -> str:
        """Generate minimal markdown when LLM enrichment fails."""
        title = data.get("title", "Untitled")
        if collection == "pitfall":
            problem = data.get("problem", "")
            solution = data.get("solution", "")
            return f"# {title}\n\n{problem}\n\n**Solution**: {solution}\n"
        elif collection == "research_idea":
            question = data.get("research_question", "")
            return f"# {title}\n\n**Research Question**: {question}\n"
        else:
            desc = data.get("description", "")
            return f"# {title}\n\n{desc}\n"


_ENRICH_SYSTEM_PROMPTS = {
    "pitfall": """\
You are a technical writing assistant for a microbial genomics research observatory.
Given a raw pitfall entry (JSON), produce a JSON response with two keys:

"markdown": A clean, well-structured markdown document describing this pitfall.
  - Start with a heading (# Title)
  - Explain the problem clearly in natural language
  - Include code examples (use fenced code blocks with language tags)
  - End with a clear "**Solution**:" line
  - Write for a data scientist who queries BERDL databases

"metadata": A dict with these fields:
  - "title": string
  - "kind": "pitfall"
  - "category": one of: "BERDL Query", "Data Sparsity", "Join & Foreign Key",
    "Data Interpretation", "JupyterHub Environment", "Pandas & Type Conversion",
    "Fitness Browser", "Genomes", "Pangenome", "Performance", "Spark", "Other"
  - "tags": list of 2-5 lowercase keyword tags
  - "project_ids": list of project IDs mentioned (empty list if none)
  - "entities": list of related entity references like "organisms/ecoli" or "methods/spark-sql"

Return ONLY valid JSON with no markdown fences or commentary.""",

    "research_idea": """\
You are a scientific writing assistant for a microbial genomics research observatory.
Given a raw research idea entry (JSON), produce a JSON response with two keys:

"markdown": A clean, well-structured markdown document describing this research idea.
  - Start with a heading (# Title)
  - Include sections: Research Question, Hypotheses, Approach, Expected Impact
  - If status/priority/effort are provided, include them as a metadata block at the top
  - Write clearly for a computational biologist

"metadata": A dict with these fields:
  - "title": string
  - "kind": "research_idea"
  - "status": "PROPOSED" | "IN_PROGRESS" | "COMPLETED" (preserve from input)
  - "priority": "HIGH" | "MEDIUM" | "LOW" (preserve from input)
  - "effort": string estimate (preserve from input)
  - "tags": list of 2-5 lowercase keyword tags
  - "project_ids": list of related project IDs
  - "entities": list of related entity references

Return ONLY valid JSON with no markdown fences or commentary.""",

    "discovery": """\
You are a scientific writing assistant for a microbial genomics research observatory.
Given a raw discovery entry (JSON), produce a JSON response with two keys:

"markdown": A clean, well-structured markdown document describing this discovery.
  - Start with a heading (# Title)
  - Present the finding clearly with specific numbers and statistics
  - Explain the biological significance
  - Note any implications or follow-up questions
  - Write for a microbiologist or computational biologist

"metadata": A dict with these fields:
  - "title": string
  - "kind": "discovery"
  - "tags": list of 2-5 lowercase keyword tags
  - "project_ids": list of project IDs this discovery came from
  - "entities": list of related entity references like "organisms/ecoli"
  - "date": date string (preserve from input)

Return ONLY valid JSON with no markdown fences or commentary.""",
}
