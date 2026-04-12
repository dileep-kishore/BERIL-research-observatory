"""Entity resolver — normalizes raw entity names to canonical forms.

Two resolution layers:
1. Rule-based: alias lookup, genus expansion, strain stripping, normalization.
2. Embedding similarity: cosine similarity against known canonical entities
   using OpenAI ``text-embedding-3-large`` (same model as OpenViking).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from observatory_context.graph.aliases import GENUS_ABBREVIATIONS, load_aliases

logger = logging.getLogger(__name__)

_ENTITY_TYPES = Literal[
    "organism",
    "gene",
    "pathway",
    "condition",
    "environment",
    "method",
    "dataset",
    "concept",
]

# Similarity thresholds per entity type
_SIMILARITY_THRESHOLDS: dict[str, float] = {
    "organism": 0.90,
    "gene": 0.85,
    "pathway": 0.85,
    "condition": 0.80,
    "environment": 0.80,
    "method": 0.85,
    "dataset": 0.85,
    "concept": 0.80,
}

# Common strain identifier patterns (trailing tokens after genus+species)
_STRAIN_PATTERN = re.compile(
    r"^(?P<species>.+?)\s+(?P<strain>[A-Z]{1,4}[\-]?\d[\w\-]*)$"
)
_EMBEDDING_BATCH_SIZE = 128
_EMBEDDING_MODEL = "text-embedding-3-large"
_EMBEDDING_DIMENSIONS = 3072


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ResolvedEntity(BaseModel):
    """Result of resolving a raw entity label."""

    canonical: str
    aliases: list[str] = Field(default_factory=list)
    entity_type: _ENTITY_TYPES
    confidence: float = 1.0
    strain: str | None = None


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class EntityResolver:
    """Normalize entity names to canonical forms.

    Parameters
    ----------
    aliases
        Canonical name -> list of known aliases.  If ``None``, the default
        alias table is loaded from disk / built-ins.
    embedding_cache
        Optional pre-populated cache mapping text -> embedding vector.
    openai_api_key
        API key for OpenAI embeddings.  Falls back to ``OPENAI_API_KEY``
        environment variable.
    """

    def __init__(
        self,
        aliases: dict[str, list[str]] | None = None,
        embedding_cache: dict[str, list[float]] | None = None,
        openai_api_key: str | None = None,
    ) -> None:
        self._aliases = aliases if aliases is not None else load_aliases()
        self._embedding_cache: dict[str, list[float]] = embedding_cache or {}
        self._api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        self._embedding_client = (
            httpx.Client(
                timeout=30.0,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            if self._api_key
            else None
        )

        # Build reverse lookup: lowercased alias -> canonical name
        self._reverse: dict[str, str] = {}
        self._rebuild_reverse()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, entity_type: str, raw_label: str) -> ResolvedEntity:
        """Resolve a single entity label to its canonical form.

        Parameters
        ----------
        entity_type
            One of ``organism``, ``gene``, ``pathway``, ``condition``,
            ``environment``, ``method``, ``dataset``, ``concept``.
        raw_label
            The raw entity name as extracted.

        Returns
        -------
        ResolvedEntity
        """
        # Layer 1 — rule-based
        result = self._resolve_rules(entity_type, raw_label)
        if result is not None:
            return result

        # Layer 2 — embedding similarity (only if API key is available)
        if self._api_key:
            canonical = self.resolve_by_embedding(
                raw_label,
                list(self._aliases.keys()),
                threshold=_SIMILARITY_THRESHOLDS.get(entity_type, 0.85),
            )
            if canonical is not None:
                return ResolvedEntity(
                    canonical=canonical,
                    aliases=[raw_label],
                    entity_type=entity_type,
                    confidence=0.85,  # below-1.0 signals embedding match
                )

        # No match — raw label becomes a new canonical entity
        return ResolvedEntity(
            canonical=raw_label.strip(),
            aliases=[],
            entity_type=entity_type,
            confidence=1.0,
        )

    def resolve_batch(
        self, entities: list[tuple[str, str]]
    ) -> dict[str, ResolvedEntity]:
        """Resolve a batch of entities, merging duplicates.

        Parameters
        ----------
        entities
            List of ``(entity_type, raw_label)`` pairs.

        Returns
        -------
        dict[str, ResolvedEntity]
            Mapping from each *raw_label* to its resolved form.
        """
        results: dict[str, ResolvedEntity] = {}
        canonical_set: dict[str, ResolvedEntity] = {}
        rule_results: dict[str, ResolvedEntity | None] = {}
        pending_labels: list[str] = []

        for entity_type, raw_label in entities:
            if raw_label in results:
                continue

            resolved = self._resolve_rules(entity_type, raw_label)
            rule_results[raw_label] = resolved
            if resolved is None:
                pending_labels.append(raw_label)

        if pending_labels and self._api_key:
            self._prefetch_embeddings([*self._aliases.keys(), *pending_labels])

        for entity_type, raw_label in entities:
            if raw_label in results:
                continue

            resolved = rule_results.get(raw_label)
            if resolved is None:
                resolved = self.resolve(entity_type, raw_label)

            # Merge with existing canonical if we've seen it
            key = resolved.canonical.lower()
            if key in canonical_set:
                existing = canonical_set[key]
                if raw_label not in existing.aliases and raw_label != existing.canonical:
                    existing.aliases.append(raw_label)
                results[raw_label] = existing
            else:
                canonical_set[key] = resolved
                results[raw_label] = resolved

        return results

    def resolve_by_embedding(
        self,
        raw_label: str,
        known_entities: list[str],
        threshold: float = 0.85,
    ) -> str | None:
        """Find the closest known entity by embedding cosine similarity.

        Parameters
        ----------
        raw_label
            The unresolved entity name.
        known_entities
            List of canonical entity names to compare against.
        threshold
            Minimum cosine similarity to accept a match.

        Returns
        -------
        str or None
            The matched canonical name, or ``None`` if no match exceeds
            the threshold.
        """
        if not known_entities:
            return None

        query_vec = self._get_embedding(raw_label)
        if query_vec is None:
            return None

        best_score = -1.0
        best_match: str | None = None

        for entity in known_entities:
            entity_vec = self._get_embedding(entity)
            if entity_vec is None:
                continue
            score = _cosine_similarity(query_vec, entity_vec)
            if score > best_score:
                best_score = score
                best_match = entity

        if best_match is not None and best_score >= threshold:
            logger.debug(
                "Embedding match: %r -> %r (%.3f)", raw_label, best_match, best_score
            )
            return best_match
        return None

    def close(self) -> None:
        """Release the shared embedding client if one was created."""
        if self._embedding_client is not None:
            self._embedding_client.close()
            self._embedding_client = None

    def update_aliases(self, canonical: str, new_alias: str) -> None:
        """Register a new alias for a canonical entity.

        Parameters
        ----------
        canonical
            The canonical entity name.
        new_alias
            A new alias to add.
        """
        if canonical not in self._aliases:
            self._aliases[canonical] = []
        if new_alias not in self._aliases[canonical]:
            self._aliases[canonical].append(new_alias)
        self._reverse[new_alias.lower().strip()] = canonical

    # ------------------------------------------------------------------
    # Layer 1: rule-based resolution
    # ------------------------------------------------------------------

    def _resolve_rules(self, entity_type: str, raw_label: str) -> ResolvedEntity | None:
        """Try rule-based resolution.  Returns ``None`` on miss."""
        normalized = self._normalize_text(raw_label)

        # For organisms, extract strain from the original label (preserving
        # case for strain identifiers like "K-12", "MR-1", "CH34").
        raw_expanded = self._expand_genus(raw_label.strip().lower())
        # Re-expand with original case for strain extraction
        raw_for_strain = raw_label.strip()
        raw_for_strain_expanded = self._expand_genus_preserve_case(raw_for_strain)
        strain: str | None = None
        species_light = raw_expanded
        if entity_type == "organism":
            _, strain = self._strip_strain(raw_for_strain_expanded)
            species_light, _ = self._strip_strain(raw_expanded)

        # 1. Genus abbreviation expansion
        expanded = self._expand_genus(normalized)
        if expanded != normalized:
            normalized = expanded

        # 2. Build candidate forms for alias lookup
        stripped = self._normalize_text(species_light) if strain else normalized
        candidates = list(dict.fromkeys([normalized, stripped]))

        # 3. Exact alias lookup
        for candidate in candidates:
            if candidate in self._reverse:
                canonical = self._reverse[candidate]
                return ResolvedEntity(
                    canonical=canonical,
                    aliases=[raw_label] if raw_label != canonical else [],
                    entity_type=entity_type,
                    confidence=1.0,
                    strain=strain,
                )

        # 4. Direct canonical match (case-insensitive) with stripped form
        canon_lower = {c.lower(): c for c in self._aliases}
        for candidate in candidates:
            if candidate in canon_lower:
                canonical = canon_lower[candidate]
                return ResolvedEntity(
                    canonical=canonical,
                    aliases=[raw_label] if raw_label != canonical else [],
                    entity_type=entity_type,
                    confidence=1.0,
                    strain=strain,
                )

        return None

    # ------------------------------------------------------------------
    # Text normalization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Lowercase, strip, and normalize separators."""
        result = text.lower().strip()
        # Normalize underscores and hyphens to spaces
        result = re.sub(r"[_\-]+", " ", result)
        # Collapse multiple spaces
        result = re.sub(r"\s+", " ", result)
        return result

    @staticmethod
    def _expand_genus(text: str) -> str:
        """Expand genus abbreviations like 'p. putida' -> 'pseudomonas putida'."""
        parts = text.split(None, 1)
        if len(parts) < 2:
            return text
        first = parts[0]
        abbrev_key = first if first.endswith(".") else None
        if abbrev_key is None:
            return text
        for abbr, genus in GENUS_ABBREVIATIONS.items():
            if abbrev_key == abbr.lower():
                return f"{genus.lower()} {parts[1]}"
        return text

    @staticmethod
    def _expand_genus_preserve_case(text: str) -> str:
        """Expand genus abbreviations, preserving case of the rest."""
        parts = text.split(None, 1)
        if len(parts) < 2:
            return text
        first = parts[0]
        abbrev_key = first.lower() if first.endswith(".") else None
        if abbrev_key is None:
            return text
        for abbr, genus in GENUS_ABBREVIATIONS.items():
            if abbrev_key == abbr.lower():
                return f"{genus} {parts[1]}"
        return text

    @staticmethod
    def _strip_strain(text: str) -> tuple[str, str | None]:
        """Split 'genus species STRAIN' into ('genus species', 'STRAIN').

        Returns the original text and ``None`` if no strain is detected.
        """
        m = _STRAIN_PATTERN.match(text)
        if m:
            return m.group("species"), m.group("strain")
        # Heuristic: if there are 3+ words and the organism looks binomial,
        # treat trailing words as strain
        parts = text.split()
        if len(parts) >= 3 and parts[0][0].isalpha() and parts[1][0].isalpha():
            species = f"{parts[0]} {parts[1]}"
            strain = " ".join(parts[2:])
            return species, strain
        return text, None

    # ------------------------------------------------------------------
    # Reverse-lookup builder
    # ------------------------------------------------------------------

    def _rebuild_reverse(self) -> None:
        """Rebuild the reverse lookup table from the current alias dict."""
        self._reverse.clear()
        for canonical, aliases in self._aliases.items():
            norm_canonical = self._normalize_text(canonical)
            self._reverse[norm_canonical] = canonical
            for alias in aliases:
                norm_alias = self._normalize_text(alias)
                self._reverse[norm_alias] = canonical

    # ------------------------------------------------------------------
    # Layer 2: embedding helpers
    # ------------------------------------------------------------------

    def _get_embedding(self, text: str) -> list[float] | None:
        """Return the embedding vector for *text*, using cache or API."""
        key = text.lower().strip()
        if key in self._embedding_cache:
            return self._embedding_cache[key]

        if not self._api_key or self._embedding_client is None:
            return None

        try:
            resp = self._embedding_client.post(
                "https://api.openai.com/v1/embeddings",
                json={
                    "model": _EMBEDDING_MODEL,
                    "input": text,
                    "dimensions": _EMBEDDING_DIMENSIONS,
                },
            )
            resp.raise_for_status()
            vec = resp.json()["data"][0]["embedding"]
            self._embedding_cache[key] = vec
            return vec
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            logger.warning("Embedding API call failed for %r: %s", text, exc)
            return None

    def _prefetch_embeddings(self, texts: list[str]) -> None:
        """Fetch uncached embeddings in batches using one shared client."""
        if not texts or not self._api_key or self._embedding_client is None:
            return

        uncached: list[str] = []
        seen: set[str] = set()
        for text in texts:
            key = text.lower().strip()
            if key in self._embedding_cache or key in seen:
                continue
            seen.add(key)
            uncached.append(text)

        for index in range(0, len(uncached), _EMBEDDING_BATCH_SIZE):
            batch = uncached[index:index + _EMBEDDING_BATCH_SIZE]
            try:
                resp = self._embedding_client.post(
                    "https://api.openai.com/v1/embeddings",
                    json={
                        "model": _EMBEDDING_MODEL,
                        "input": batch,
                        "dimensions": _EMBEDDING_DIMENSIONS,
                    },
                )
                resp.raise_for_status()
                payload = resp.json()
                for item in payload["data"]:
                    text = batch[item["index"]]
                    self._embedding_cache[text.lower().strip()] = item["embedding"]
            except (httpx.HTTPError, KeyError, IndexError) as exc:
                logger.warning("Embedding batch API call failed for %d texts: %s", len(batch), exc)


# ---------------------------------------------------------------------------
# Math utilities
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors (pure Python)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
