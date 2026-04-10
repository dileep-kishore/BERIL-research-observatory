# Observatory Graph Layer: Connected Knowledge via NetworkX

**Date**: 2026-04-10
**Status**: Approved
**Branch**: `feature/observatory-wiki-v2`

## Summary

Add a lightweight graph layer to the observatory knowledge system using
NetworkX + flat files, inspired by graphify's philosophy. Disable
OpenViking VLM (redundant — reports describe figures). Rewrite extraction
for richer, normalized output. Build cross-project entity connections,
community detection, and an MCP server for direct agent access.

## Problem

The current knowledge layer has critical deficiencies (extraction audit):

1. **No cross-project connections** — findings are scoped to single projects
2. **No entity normalization** — "P. putida" and "Pseudomonas putida" are
   separate entities; 55% of entities are catch-all "concept" type
3. **60% dead schema** — Evidence, Artifact, Figure models never populated;
   conditions, evidence_ids, figure_ids always empty
4. **VLM wastes 30+ min per ingest** — reports already describe figures
5. **Extraction prompt is underspecified** — no domain context, no
   normalization guidance, no finding type classification
6. **Timeline events silently dropped**
7. **No contradiction detection** across projects

## Design

### Architecture

```
data/graph/
├── graph.json           # NetworkX node-link format (the knowledge graph)
├── aliases.json         # canonical name → [alias1, alias2, ...] mappings
├── communities.json     # community ID → {name, members, summary}
├── GRAPH_REPORT.md      # 1-page landscape summary (agent reads first)
└── cache/               # SHA256-keyed per-project extraction cache
    └── {project_id}.json
```

### Components

#### 1. Extraction Rewrite (`observatory_context/extraction.py`)

Single CBORG call per report, but with a dramatically better prompt:

- Domain context: microbiology, genomics, pangenome analysis
- 8 entity types: organism, gene, pathway, condition, environment,
  method, dataset, concept
- Canonical name instructions: full species names, standard gene names
- Typed relations with directionality, conditions, and confidence
  calibration (p-value ranges → confidence levels)
- Finding type classification: result, negative_result, methodological,
  pattern, operational
- Provenance anchoring: section/paragraph references
- Source span extraction: exact text supporting each claim

Output schema adds: `conditions`, `finding_type`, `source_span`,
`figure_refs` (parsed from markdown `![caption](figures/...)` patterns),
`timeline_events` (no longer dropped).

#### 2. Entity Resolver (`observatory_context/graph/resolver.py`)

Two-layer resolution, zero LLM calls:

**Layer 1 — Rule-based (handles ~70%):**
- Abbreviation expansion: "P. putida" → "Pseudomonas putida"
- Strain stripping: "KT2440" preserved as attribute, not in canonical name
- Case normalization, whitespace cleanup
- Common synonym table (loaded from `aliases.json`)

**Layer 2 — Embedding similarity (handles ~25%):**
- Use existing OpenAI embeddings (text-embedding-3-large)
- Cosine similarity threshold: 0.88 for organisms, 0.85 for genes/pathways
- Cache embeddings for all known entities

Remaining ~5% ambiguous cases: flag for manual review in GRAPH_REPORT.md.

#### 3. Graph Builder (`observatory_context/graph/builder.py`)

Builds a `nx.MultiDiGraph` from resolved registry entries:

**Node types:**
- `Project` — id, title, research_question, status
- `Organism` — canonical_name, aliases, ncbi_taxonomy (if known)
- `Gene` — canonical_name, aliases
- `Pathway` — canonical_name, aliases
- `Condition` — label
- `Method` — label
- `Finding` — id, statement, confidence, finding_type, project_id
- `Hypothesis` — id, statement, status, project_ids

**Edge types:**
- `PROJECT_STUDIES → Entity` — which entities a project examines
- `FINDING_ABOUT → Entity` — which entity a finding concerns
- `FINDING_FROM → Project` — provenance
- `SUPPORTS / CONTRADICTS → Hypothesis` — evidence links
- `TESTED_IN → Project` — hypothesis testing provenance
- `RELATED_TO → Entity` — co-occurrence in findings/reports
- `SAME_AS → Entity` — resolved aliases (soft link)

**Cross-project connections** emerge naturally: when two projects study
the same organism (resolved to the same canonical node), their findings
connect through shared entity nodes.

After building: run Leiden community detection (via `graspologic` or
NetworkX Louvain fallback). Label communities by dominant entity types
and project coverage.

#### 4. Graph Report (`observatory_context/graph/report.py`)

Generates `GRAPH_REPORT.md` — a single-page landscape summary:

```markdown
# Observatory Knowledge Graph

**Last built**: 2026-04-10 | **Entities**: 847 | **Relations**: 4,231
**Projects**: 46 | **Communities**: 12

## Top Communities
1. **Metal Stress & Fitness** (127 entities) — metal_fitness_atlas,
   conservation_vs_fitness, bacdive_metal_validation
2. **Pangenome Structure** (98 entities) — pangenome_openness,
   costly_dispensable_genes, ...

## Cross-Project Connections
- Pseudomonas putida: studied in 8 projects (metal stress, fitness, ...)
- Core genome enrichment: finding in 3 projects (potentially contradictory)

## Research Gaps
- 14 organisms mentioned but not studied as primary subject
- 3 hypotheses proposed but never tested

## Contradictions
- core genome enrichment: metal_fitness_atlas (87.4%) vs
  conservation_vs_fitness (different methodology, different threshold)
```

#### 5. MCP Server (`observatory_context/graph/server.py`)

Lightweight MCP server (FastMCP) exposing:

| Tool | Purpose |
|------|---------|
| `search_entities` | Find entities by name (fuzzy, uses aliases + embeddings) |
| `get_neighbors` | 1-hop connections from an entity |
| `traverse` | Multi-hop BFS with depth limit and type filters |
| `get_community` | All entities + findings in a community cluster |
| `cross_project` | Entities shared between N projects |
| `find_contradictions` | Findings about same entity with conflicting claims |
| `shortest_path` | Path between two entities through the graph |
| `graph_stats` | Summary statistics (for quick orientation) |
| `add_finding` | Dynamic: agent adds a discovered connection |

Server loads `graph.json` into memory on startup. Graph reloads on
file change (watchdog or polling). The agent gets connected, contextual
results — not 15 search hits to sift through.

#### 6. Pipeline Integration

Updated 5-phase ingest:

```
Phase 1: Corpus Upload (unchanged)
  → batch upload docs to OpenViking

Phase 2: Extract & Register (improved)
  → better CBORG prompt per report
  → populate conditions, finding_type, figure_refs, timeline
  → cache extractions per-project (SHA256 of report content)

Phase 3: Resolve & Build Graph (NEW)
  → entity resolution across all projects
  → build NetworkX graph from resolved registry
  → Leiden community detection
  → serialize to data/graph/graph.json
  → generate GRAPH_REPORT.md

Phase 4: Compile Wiki (existing, improved)
  → uses resolved entity names (consistent across pages)
  → cross-references use canonical graph node IDs

Phase 5: Update Log (existing)
  → append ingest record
```

**Incremental ingest (new project added):**

1. Only extract the new/changed project(s) — cache check via SHA256
2. Load existing `graph.json`
3. Run entity resolution for new entities against existing graph
4. Merge new nodes/edges into graph
5. Re-run community detection (fast — sub-second for our scale)
6. Regenerate `GRAPH_REPORT.md`
7. Recompile affected wiki pages only

**Cost:** ~$0.02-0.05 per project (one CBORG call). Full 50-project
re-ingest: ~$1-2.50. Entity resolution: zero LLM cost (embeddings +
rules only).

### VLM Removal

Remove `vlm` section from `config/openviking/ov.conf`. When VLM is
unavailable, OpenViking:
- Skips all VLM file summary generation
- Still vectorizes/embeds all content (search works)
- Generates stub `.abstract.md`/`.overview.md` (directory listings only)

Our wiki pages and GRAPH_REPORT.md replace the VLM summaries with
richer, domain-aware content.

### Configuration

New environment variables: none.
New dependencies: `graspologic` (for Leiden), `mcp` (for server).

`ov.conf` changes: remove `vlm` section.

`.mcp.json` addition:
```json
{
  "observatory-graph": {
    "type": "stdio",
    "command": "uv",
    "args": ["run", "python", "-m", "observatory_context.graph.server"]
  }
}
```

## Files to Create

- `observatory_context/graph/__init__.py`
- `observatory_context/graph/builder.py`
- `observatory_context/graph/resolver.py`
- `observatory_context/graph/report.py`
- `observatory_context/graph/server.py`
- `observatory_context/graph/aliases.py`

## Files to Modify

- `config/openviking/ov.conf` — remove `vlm` section
- `scripts/viking_setup.py` — skip vlm config generation
- `observatory_context/extraction.py` — rewrite prompt + output schema
- `observatory_context/registry/extract.py` — populate all fields
- `observatory_context/ingest/pipeline.py` — add Phase 3 (graph building)
- `.mcp.json` — add observatory-graph server
- `pyproject.toml` — add graspologic, mcp dependencies

## Success Criteria

1. `uv run scripts/viking_ingest.py --no-resume` completes in <5 min
   (vs 30+ min with VLM)
2. `data/graph/graph.json` contains cross-project entity connections
3. Entity "Pseudomonas putida" appears once (not 5 variants)
4. `GRAPH_REPORT.md` surfaces communities, gaps, contradictions
5. MCP server responds to `search_entities("metal stress")` with
   connected context in <100ms
6. Incremental ingest of 1 new project takes <30 seconds
