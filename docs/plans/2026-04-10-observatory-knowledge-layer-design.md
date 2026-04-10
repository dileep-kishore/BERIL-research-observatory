# Observatory Knowledge Layer Design

**Date:** 2026-04-10
**Status:** Approved
**Branch:** `feature/observatory-knowledge-layer`

## Goal

Build a real observatory knowledge layer that combines the OpenViking tiered
resource system with the wiki, while keeping both backed by the same
cross-project synthesized model. The resulting layer must support full rebuilds
from source data, incremental updates as new projects arrive, and efficient
OpenViking-backed querying through the existing unified query script.

## Constraints

- No VLM components in the knowledge-layer pipeline.
- The wiki is a compiled view, not an input to future synthesis.
- NetworkX remains the canonical internal graph artifact.
- OpenViking remains the canonical retrieval surface for agents.
- The pipeline must support both rebuild-from-scratch and incremental updates.

## Recommended Architecture

The canonical source of truth is:

1. project corpus
2. extracted structured registry entries
3. persistent graph artifacts
4. alias and clustering metadata

The wiki and `knowledge-graph/` namespaces are compiled outputs from that shared
state, not parallel sources of truth.

The ingest flow becomes:

```text
corpus -> registry -> graph -> synthesis -> {knowledge-graph, wiki}
```

This introduces a new synthesis layer between graph construction and export.

## Canonical Internal Model

The system should introduce a structured synthesis layer that aggregates
cross-project knowledge from registry entries plus NetworkX graph structure.

Recommended synthesized objects:

- `SynthesizedEntity`
- `SynthesizedHypothesis`
- `SynthesizedTopic`
- `SynthesizedCommunity`
- `SynthesizedTimelineEvent`
- `KnowledgeSynthesisBundle`

These objects should capture:

- canonical identity
- project coverage
- finding and hypothesis provenance
- related entities and edge weights
- cluster/community membership
- aggregate confidence and evidence summaries
- deterministic text for L0/L1 exports
- YAML-serializable structured content for L2 exports

## Role of NetworkX

NetworkX is the build-time synthesis engine. It is not the runtime query
surface.

It is responsible for:

- entity and project connectivity
- co-occurrence-derived `RELATED_TO` structure
- hypothesis-to-entity and finding-to-entity relationships
- cross-project aggregation support
- community detection and cluster membership
- identifying related neighbors and neighborhood strength

The compiled outputs use this graph-derived structure:

- `knowledge-graph/` gets tiered files and OpenViking relations
- `wiki/` gets narrative pages and cross-links

## Namespace Model

### `knowledge-graph/`

The OpenViking-native retrieval namespace contains tiered directories and
structured files.

Example layout:

```text
knowledge-graph/
├── entities/{plural}/{slug}/
│   ├── .abstract.md
│   ├── .overview.md
│   └── profile.yaml
├── hypotheses/{slug}/
│   ├── .abstract.md
│   ├── .overview.md
│   └── hypothesis.yaml
└── timeline/
    └── events.yaml
```

It also receives explicit OpenViking relations generated from NetworkX edges so
`ContextDelivery.traverse()` works through OpenViking.

### `wiki/`

The wiki becomes the linked narrative surface generated from the same
synthesized objects.

It should contain:

- `index.md`
- `topics/{slug}.md`
- `entities/{plural}/{slug}.md`
- `hypotheses/{slug}.md`
- `log.md`

Topic pages should reflect synthesized cross-project themes rather than only
per-project summaries.

## Ingest and Update Semantics

### Full rebuild

A full rebuild regenerates:

- graph artifacts under `data/graph/`
- synthesis artifacts or manifests
- all `knowledge-graph/` resources
- all `wiki/` resources
- OpenViking relations for graph traversal

### Incremental update

An incremental ingest:

- ingests changed or new projects
- extracts changed registry entries
- merges them into the persistent graph
- recomputes only affected synthesized entities, hypotheses, topics,
  communities, and timeline items
- upserts only affected `knowledge-graph/` and `wiki/` resources
- reconciles affected OpenViking relations

No generated markdown is read back as source input.

## Module Boundaries

### `observatory_context/graph/knowledge_synthesis.py`

Pure aggregation layer that reads registry data and graph state and produces a
`KnowledgeSynthesisBundle`. No OpenViking I/O. No markdown file writing.

### `observatory_context/graph/knowledge_graph_export.py`

Renders synthesized objects into staged `knowledge-graph/` files and creates
OpenViking relations from graph edges.

### `observatory_context/wiki/compiler.py`

Should accept synthesized inputs so wiki rendering and `knowledge-graph/`
rendering stay aligned.

### `observatory_context/ingest/pipeline.py`

Should add:

- synthesis phase
- knowledge-graph export phase
- wiki compilation from synthesized objects

### `scripts/viking_ingest.py`

Remains the operational entry point. It should grow flags for targeted rebuilds
and incremental runs if needed, but the core behavior continues to drive the
pipeline.

### `scripts/query_knowledge_unified.py`

Remains the query entry point. Existing graph-oriented commands should begin
working once `knowledge-graph/` is populated correctly.

## Non-Goals

- No direct NetworkX query path for agents.
- No wiki-as-source-of-truth loop.
- No VLM or vision-based synthesis.
- No Neo4j or external graph runtime.

## Practical Outcome

After implementation:

- `query_knowledge_unified.py entities ...` returns real entity rollups
- `hypotheses`, `connections`, `traverse`, `timeline`, and `landscape` return
  synthesized OpenViking-backed results
- wiki pages and OpenViking tiered resources stay aligned because they are
  compiled from the same synthesis bundle
- the system supports rebuilds and incremental additions without relying on
  generated markdown as input
