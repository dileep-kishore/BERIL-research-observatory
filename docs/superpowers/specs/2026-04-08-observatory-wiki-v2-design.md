# Observatory Wiki V2: LLM-Optimized Knowledge Layer

**Date**: 2026-04-08
**Status**: Approved
**Branch**: `feature/observatory-wiki-v2`
**Base**: `feature/viking-migration`

## Summary

Redesign the observatory knowledge layer around the LLM Wiki paradigm:
pre-compiled, agent-navigable markdown wiki backed by OpenViking, with a
structured YAML registry and optional graph overlay. The primary consumer is
an AI co-scientist agent that navigates compiled synthesis pages rather than
running exhaustive searches.

## Problem

The current architecture requires the agent to:

1. Run `query_knowledge_unified.py search "topic"` to get search hits
2. Read each hit at L0/L1/L2 to piece together understanding
3. Repeat across entities, hypotheses, pitfalls, operational knowledge
4. Mentally synthesize cross-project connections from fragments
5. None of this synthesis persists — next session starts from scratch

At 100+ projects this becomes: high token cost, slow navigation, no knowledge
compounding, no gap detection, no contradiction surfacing.

## Design Principles

1. **The agent is the primary consumer.** Optimize for navigability by an LLM,
   not human browsing. The agent reads `index.md` then 2-3 topic pages, not
   15 search results.

2. **Knowledge compounds.** Good query synthesis persists as new wiki pages.
   Each session enriches the knowledge base for future sessions.

3. **Maintenance cost approaches zero.** The LLM handles all bookkeeping:
   updating cross-references, maintaining indices, flagging contradictions.
   Humans curate sources and direct analysis.

4. **Search and knowledge are different layers.** Search (OpenViking semantic
   search) is the fallback when compiled wiki pages have insufficient coverage.
   The wiki is the primary navigation surface.

5. **Reports remain authoritative.** The wiki synthesizes from immutable source
   documents. Provenance links trace every claim back to its origin.

## Three-Layer Architecture

```
Layer 1 — Raw Sources (Immutable, Git)
  projects/*/README.md, REPORT.md, notebooks, figures
  The human-authored research record. Never modified by the agent.

Layer 2 — The Observatory Wiki (LLM-Compiled, OpenViking)
  Compiled topic pages, entity profiles, cross-project syntheses,
  hypothesis trackers, gap analyses — maintained by the agent.
  The agent's primary navigation surface.

Layer 3 — The Schema + Optional Graph
  CLAUDE.md, skill definitions, entity ontology, relation types.
  Optional: Graphiti/Kuzu for multi-hop traversal (Phase 4).
```

## URI Hierarchy

```
viking://resources/observatory/
├── wiki/                           # Layer 2: Agent-compiled knowledge
│   ├── index.md                    # Master catalog (agent reads first)
│   ├── log.md                      # Append-only activity log
│   ├── topics/                     # Cross-project synthesis pages
│   │   ├── nitrogen-stress.md
│   │   ├── pangenome-fitness.md
│   │   └── dark-genes.md
│   ├── entities/                   # One page per entity
│   │   ├── organisms/
│   │   │   └── pseudomonas-putida.md
│   │   ├── genes/
│   │   ├── pathways/
│   │   ├── methods/
│   │   └── concepts/
│   ├── hypotheses/                 # Tracker pages
│   │   ├── index.md                # Status overview table
│   │   └── {hyp-id}.md
│   ├── gaps/                       # Agent-identified gaps
│   │   └── latest.md
│   └── connections/                # Cross-project link pages
│       └── {entity-A}--{entity-B}.md
├── registry/                       # Structured extracted knowledge (YAML)
│   ├── projects/{id}.yaml
│   ├── findings/{id}.yaml
│   ├── evidence/{id}.yaml
│   ├── artifacts/{id}.yaml
│   ├── figures/{id}.yaml
│   ├── pitfalls/{id}.yaml
│   └── ideas/{id}.yaml
├── corpus/                         # Indexed source documents
│   └── {project_id}/
│       ├── README.md
│       ├── REPORT.md
│       └── provenance.yaml
├── operational/                    # Pitfalls, discoveries, ideas (enriched md)
│   ├── pitfalls/
│   ├── discoveries/
│   └── research-ideas/
└── memories/                       # Session memories
    ├── journal/
    ├── patterns/
    └── conversations/
```

## Four Operations

### 1. Ingest

Triggered when a project is added or updated.

Steps:
1. Upload source documents to `corpus/{project_id}/` via batch directory upload
2. Run CBORG extraction → structured YAML → `registry/` entries
3. Generate or update relevant wiki pages:
   - Entity profiles in `wiki/entities/` (add new findings, cross-refs)
   - Topic synthesis pages in `wiki/topics/` (if project touches that topic)
   - Hypothesis tracker entries in `wiki/hypotheses/`
4. Update `wiki/index.md` with new/changed entries
5. Append to `wiki/log.md`
6. Call `POST /api/v1/system/wait` to ensure all processing completes

Batch strategy: stage all files locally into a temp directory tree, upload
the entire tree via `client.add_resource(path=temp_dir, target=uri)` in one
call per namespace (corpus, registry, wiki). This avoids lock contention.

### 2. Query

Agent navigation flow:
1. Read `wiki/index.md` → identify 2-5 relevant topic/entity pages
2. Read topic pages (pre-compiled synthesis with coverage tags)
3. If coverage is `[low]`, drill into raw sources via OpenViking `find()`
4. If the query produces a novel synthesis, persist it as a new wiki page
   (query compounding)

### 3. Lint

Periodic health check, run as a skill (`/wiki-lint`).

Checks:
- **Contradictions**: findings from project A vs B that conflict
- **Staleness**: entity pages not updated after recent project ingests
- **Orphans**: entities referenced in findings but no profile page exists
- **Gaps**: research ideas with no project, hypotheses never tested
- **Coverage**: topics with only 1 source flagged `[coverage: low]`
- **Missing links**: entity pages that should cross-reference but don't

Output: update `wiki/gaps/latest.md` with prioritized issues.

### 4. Suggest

The co-scientist's unique capability.

Input: gap analysis + hypothesis tracker + cross-project connections
Output: novel hypotheses grounded in existing findings, prioritized by
data availability and knowledge gaps.

This operation reads the compiled wiki (not raw sources) and produces
new wiki pages in `wiki/connections/` or updates `wiki/gaps/`.

## Wiki Page Format

All wiki pages use YAML frontmatter + markdown body:

```markdown
---
title: Metal Stress Responses Across Observatory Projects
kind: topic_synthesis
sources:
  - corpus/metal-stress-ecotypes/REPORT.md
  - corpus/zinc-homeostasis-pp/REPORT.md
  - corpus/copper-response-marine/REPORT.md
  - corpus/nickel-efflux-soil/REPORT.md
coverage: high
last_compiled: 2026-04-08
related:
  - wiki/entities/pathways/czc-efflux.md
  - wiki/entities/organisms/pseudomonas-putida.md
  - wiki/hypotheses/hyp-metal-cross-resistance.md
registry_refs:
  - registry/findings/metal-stress-001.yaml
  - registry/findings/metal-stress-002.yaml
---

# Metal Stress Responses

## Summary

Four projects have investigated metal stress responses across different
organisms and metal types. The strongest findings concern zinc and copper
efflux in Pseudomonas, with preliminary evidence for cross-resistance
mechanisms. [coverage: high]

## Key Findings

1. **Czc efflux is conserved across soil Pseudomonas** — supported by
   pangenome analysis of 47 strains (metal-stress-ecotypes, Finding F-023).
   Confidence: high.

2. **Cu and Zn stress share regulatory elements** — observed in P. putida
   under dual metal exposure (zinc-homeostasis-pp, Finding F-041).
   Confidence: moderate.

## Open Questions

- No data on Mn stress in marine isolates [coverage: none]
- Cross-resistance hypothesis (HYP-007) tested in soil only — marine
  validation needed

## Related

- [[czc-efflux]] — pathway profile
- [[pseudomonas-putida]] — organism profile
- [[hyp-metal-cross-resistance]] — hypothesis tracker
```

## Registry Schema

### Project

```yaml
project_id: metal-stress-ecotypes
title: "Metal stress ecotype analysis in soil Pseudomonas"
status: complete
research_question: "Do metal stress response genes define ecotypes?"
organisms: [Pseudomonas putida, Pseudomonas fluorescens]
conditions: [zinc stress, copper stress]
methods: [pangenome analysis, differential expression]
datasets: [BERDL pangenome_analysis.gene_clusters]
tags: [metal-stress, pangenome, ecotype]
updated_at: 2026-03-15
```

### Finding

```yaml
finding_id: F-023
project_id: metal-stress-ecotypes
title: "Czc efflux conserved across soil Pseudomonas"
statement: >
  The czc efflux system is present in 44/47 soil Pseudomonas strains
  analyzed, with >95% sequence identity in the core operon.
confidence: high
finding_type: result
related_entities:
  - type: pathway
    label: czc efflux
  - type: organism
    label: Pseudomonas putida
conditions: [zinc stress]
source_refs:
  - corpus/metal-stress-ecotypes/REPORT.md#czc-analysis
evidence_ids: [E-023a, E-023b]
figure_ids: [FIG-metal-001]
```

### Hypothesis

```yaml
hypothesis_id: HYP-007
title: "Metal cross-resistance via shared regulatory elements"
statement: >
  Soil Pseudomonas strains with czc efflux show cross-resistance to
  copper via shared CzcRS two-component regulation.
status: tested
scope: soil Pseudomonas only
project_ids: [metal-stress-ecotypes, zinc-homeostasis-pp]
related_entities:
  - type: pathway
    label: czc efflux
  - type: pathway
    label: cop efflux
source_ref: corpus/zinc-homeostasis-pp/REPORT.md#cross-resistance
```

### Evidence

```yaml
evidence_id: E-023a
project_id: metal-stress-ecotypes
kind: statistical
summary: "44/47 strains carry czc operon (93.6% prevalence)"
source_ref: corpus/metal-stress-ecotypes/REPORT.md#prevalence
linked_figures: [FIG-metal-001]
statistical_support: "Fisher exact p < 0.001 vs random expectation"
```

### Artifact

```yaml
artifact_id: ART-metal-001
project_id: metal-stress-ecotypes
kind: dataset
path: exports/czc_prevalence_matrix.tsv
description: "Binary presence/absence matrix of czc genes across 47 strains"
upstream_notebooks: [03_pangenome_analysis.ipynb]
upstream_datasets: [BERDL pangenome_analysis.gene_clusters]
tags: [metal-stress, pangenome, reusable]
```

### Figure

```yaml
figure_id: FIG-metal-001
project_id: metal-stress-ecotypes
path: projects/metal-stress-ecotypes/figures/czc_prevalence.png
caption: "Prevalence of czc efflux genes across 47 soil Pseudomonas strains"
illustrates: [F-023]
tags: [metal-stress, pangenome, heatmap]
```

### Pitfall

```yaml
pitfall_id: PIT-spark-timeout
title: "Spark connect sessions timeout after 5 minutes idle"
description: >
  BERDL Spark sessions via spark_connect_remote disconnect after 5 minutes
  without activity. Wrap long computations in keep-alive loops.
applies_to: [berdl-query, spark-connect]
project_ids: [metal-stress-ecotypes]
source_ref: corpus/metal-stress-ecotypes/provenance.yaml
tags: [berdl, spark, timeout]
category: infrastructure
```

### ResearchIdea

```yaml
idea_id: IDEA-marine-metal
title: "Extend metal stress analysis to marine isolates"
statement: >
  The czc cross-resistance finding is established in soil only. Marine
  Pseudomonas may use different efflux systems under metal stress.
motivation: "Gap identified in metal-stress synthesis page"
related_entities:
  - type: organism
    label: Pseudomonas stutzeri
  - type: condition
    label: marine environment
priority: medium
status: proposed
project_ids: []
```

## Entity Classes

Fixed set of typed entity classes with open vocabulary values:

| Class | Examples |
|-------|---------|
| Taxon | Pseudomonas putida, Prochlorococcus marinus |
| GeneFamily | czc efflux, trpA, rpoB |
| Pathway | czc efflux, nitrogen fixation, quorum sensing |
| Condition | zinc stress, nitrogen limitation, marine |
| Environment | soil, marine, freshwater |
| Method | pangenome analysis, differential expression, fitness assay |
| Dataset | BERDL pangenome_analysis.gene_clusters |
| Concept | ecotype, dark genes, horizontal gene transfer |

Each entity reference includes: raw label, optional normalized ID, optional
namespace (NCBI, KEGG, COG, etc.).

## OpenViking API Modernization

Changes to `observatory_context/client.py`:

| Current | New |
|---------|-----|
| `add_text_resource()` writes temp file | Use `client.write(path, data)` for programmatic content |
| One-by-one resource uploads | Batch via `add_resource(path=dir, target=uri)` |
| Manual `.abstract.md`/`.overview.md` generation | Let OpenViking auto-generate L0/L1 tiers |
| No reranking | Add `rerank` section to `ov.conf` |
| `wait_until_processed()` per resource | `POST /api/v1/system/wait` after batch |
| `find()` only | Use `search()` with session for context-aware queries |
| Monolithic `ContextDelivery` (1050 lines) | Split into focused modules (see below) |

## Code Architecture

### Package restructure: `observatory_context/`

```
observatory_context/
├── __init__.py
├── config.py                    # Settings (unchanged)
├── models.py                    # Data models (extended with registry types)
├── client.py                    # OpenViking client (modernized)
├── uris.py                      # URI builders (updated for new hierarchy)
├── extraction.py                # CBORG extraction (unchanged)
├── runtime.py                   # Build helpers (updated)
│
├── wiki/                        # NEW: Wiki compilation layer
│   ├── __init__.py
│   ├── compiler.py              # Compile topic/entity/hypothesis pages
│   ├── index.py                 # Maintain wiki/index.md
│   ├── lint.py                  # Contradiction/gap/staleness detection
│   └── compound.py              # Persist query synthesis as wiki pages
│
├── registry/                    # NEW: Structured knowledge registry
│   ├── __init__.py
│   ├── schema.py                # Pydantic models for all registry types
│   ├── store.py                 # Read/write registry YAML via OpenViking
│   └── extract.py               # CBORG → registry entry pipeline
│
├── ingest/                      # REFACTORED: Simplified ingest
│   ├── __init__.py
│   ├── manifest.py              # Resource manifest (exists, updated)
│   ├── batch.py                 # NEW: Batch upload orchestration
│   └── pipeline.py              # NEW: Three-phase ingest pipeline
│
├── delivery.py                  # SIMPLIFIED: Query-focused, delegates to wiki
├── _text.py                     # Text utilities (unchanged)
├── _discovery.py                # Project discovery (unchanged)
├── _graph.py                    # Dependency graph (unchanged)
├── parsing.py                   # Report parsing (unchanged)
└── staging.py                   # File staging (updated for batch)
```

### Key module responsibilities

**`wiki/compiler.py`**: Given a project's extracted knowledge, generate or
update the relevant wiki pages. Uses CBORG for synthesis text. Tracks which
pages need updating via content hashing.

**`wiki/index.py`**: Maintain `wiki/index.md` — the master catalog. Each
entry is one line: `- [slug](path) — one-line summary (N sources, coverage: X)`.
Updated atomically after each ingest.

**`wiki/lint.py`**: Traverse all wiki pages and registry entries. Detect
contradictions (conflicting findings), staleness (pages older than latest
project ingest), orphans (referenced entities without pages), gaps (untested
hypotheses, ideas without projects). Output to `wiki/gaps/latest.md`.

**`wiki/compound.py`**: When a query produces a novel cross-project synthesis,
persist it as a new wiki page. Determine if the synthesis is novel enough to
warrant a page (not just a restatement of existing content).

**`registry/schema.py`**: Pydantic models for Project, Finding, Hypothesis,
Evidence, Artifact, Figure, Pitfall, ResearchIdea. Validates all extracted
knowledge before storage.

**`registry/store.py`**: Read/write registry YAML files via OpenViking's
write API. Batch operations for ingest. Query by type, project, entity.

**`registry/extract.py`**: Pipeline from CBORG EntityExtraction → registry
entries. Maps extracted entities, relations, hypotheses to registry schema.

**`ingest/batch.py`**: Orchestrate batch uploads. Stage files locally into
a temp directory tree, upload per namespace (corpus, registry, wiki) via
single `add_resource()` calls. Use `system/wait` after all uploads.

**`ingest/pipeline.py`**: The main ingest pipeline. Four phases:
1. Corpus upload (batch)
2. CBORG extraction → registry entries (batch)
3. Wiki compilation (update affected pages)
4. Index + log update

## Ingest Pipeline Detail

```
Input: project_id or --all

Phase 1: Corpus Upload
  - build_resource_manifest() → list of source files
  - Stage to temp dir maintaining URI structure
  - client.add_resource(path=temp_dir, target="viking://resources/observatory/corpus/")
  - client.wait_processed()

Phase 2: Registry Extraction
  - For each project with REPORT.md:
    - Check extraction cache (.kg_cache/)
    - If stale: run CBORG extraction → EntityExtraction
    - Map to registry schema → YAML files
  - Stage all registry YAML to temp dir
  - client.add_resource(path=temp_dir, target="viking://resources/observatory/registry/")
  - client.wait_processed()

Phase 3: Wiki Compilation
  - For each affected project:
    - Identify which wiki pages need updating (entity profiles, topic pages, hypothesis trackers)
    - Compile updated pages via CBORG synthesis
  - Stage all wiki pages to temp dir
  - client.add_resource(path=temp_dir, target="viking://resources/observatory/wiki/")
  - client.wait_processed()

Phase 4: Index + Log
  - Regenerate wiki/index.md from all wiki pages
  - Append ingest record to wiki/log.md
  - Upload both via client.write()
```

## Delivery Simplification

The current `ContextDelivery` (1050 lines) is split:

| Current method | New location |
|---------------|-------------|
| `search()`, `get()`, `browse()` | `delivery.py` (simplified) |
| `traverse()`, `entities()`, `hypotheses()`, `timeline()` | `delivery.py` (delegates to registry) |
| `remember()`, `recall()` | `delivery.py` (unchanged) |
| `start_session()`, `commit_session()` | `delivery.py` (unchanged) |
| `add_operational()`, `list_operational()`, `update_operational()` | `registry/store.py` |
| `ingest_entity()`, `ingest_resource()` | `ingest/pipeline.py` |
| `link()`, `unlink()` | `delivery.py` (unchanged) |
| `add_collection_overview()` | `wiki/compiler.py` |

## Skills Updates

| Skill | Change |
|-------|--------|
| `/knowledge` | Read `wiki/index.md` first, then navigate wiki pages. Fall back to search only when coverage is low. |
| `/build-registry` | Updated to run new 4-phase ingest pipeline |
| `/wiki-lint` | NEW: Run lint checks, output gap analysis |
| `/suggest-research` | Updated to read wiki gap analysis + compiled syntheses |
| `/synthesize` | Updated to persist good synthesis as wiki pages (compound) |
| `/discovery-capture` | Write to both `operational/discoveries/` and update relevant wiki pages |
| `/pitfall-capture` | Write to both `operational/pitfalls/` and update relevant wiki pages |

## Configuration Changes

### ov.conf additions

```json
{
  "rerank": {
    "provider": "openai",
    "api_key": "<OPENAI_API_KEY>",
    "model": "gpt-4o-mini"
  }
}
```

### New environment variables

None required. Existing `OPENAI_API_KEY`, `CBORG_API_KEY`, and
`BERIL_OPENVIKING_URL` are sufficient.

## Migration Plan

### From current state

1. Create new URI namespaces (`wiki/`, `registry/`, `corpus/`)
2. Move existing `projects/` content to `corpus/`
3. Move existing `knowledge-graph/` entity data to `registry/` YAML
4. Run initial wiki compilation from existing registry data
5. Generate `wiki/index.md` from compiled pages
6. Update all skills to use new navigation pattern
7. Deprecate old `knowledge-graph/` URI namespace
8. Update CLAUDE.md with new navigation instructions

### Backwards compatibility

During migration, both old and new URIs will work. The old `delivery.py`
methods that reference `knowledge-graph/` URIs will be updated to delegate
to `registry/` lookups. After migration is verified, old namespaces are
removed.

## Build Phases

### Phase 1: OpenViking Modernization

Modernize `client.py` and `ingest/` to use OpenViking's full API:
- `client.write()` for programmatic content
- Batch directory upload
- `system/wait` for batch completion
- Reranking configuration
- Let OpenViking auto-generate tiers

### Phase 2: Wiki Compilation Layer

Build `wiki/` subpackage:
- `compiler.py`: generate topic/entity/hypothesis pages from registry
- `index.py`: maintain `wiki/index.md`
- `lint.py`: contradiction/gap/staleness detection
- `compound.py`: persist query synthesis

### Phase 3: Structured Registry

Build `registry/` subpackage:
- `schema.py`: Pydantic models for all registry types
- `store.py`: OpenViking-backed YAML store
- `extract.py`: CBORG → registry pipeline

Refactor `ingest/pipeline.py` to use new 4-phase pipeline.

### Phase 4: Graph Layer (Future, Optional)

Add Graphiti with Kuzu (embedded) for multi-hop queries:
- Feed registry entities/relations via `add_triplet()`
- Community detection for automatic topic clustering
- Graph-enhanced gap detection

Not in scope for this implementation.

## Success Criteria

The knowledge layer is successful if:

1. **Token efficiency**: Agent navigates to relevant knowledge in 2-3 reads
   (index + topic pages) instead of 10-15 searches
2. **Knowledge compounds**: Each research session enriches the wiki for
   future sessions
3. **Gap detection works**: `/wiki-lint` surfaces real contradictions and
   missing coverage
4. **Zero maintenance**: Adding a project automatically updates all affected
   wiki pages, index, and cross-references
5. **Provenance is traceable**: Every wiki claim links back to a registry
   finding which links back to a source report

## Tool Decisions

| Tool | Decision | Reason |
|------|----------|--------|
| OpenViking | Keep + modernize | Already running, good embedding search, tiered loading, Python API, batch support |
| QMD | Not used | No Python API, OpenViking search + wiki index is sufficient |
| Graphiti | Deferred to Phase 4 | High value for graph queries, but wiki + registry covers 80% of needs |
| LLM Wiki | Design philosophy | Implemented via OpenViking storage + wiki/ compilation layer |
| CBORG | Keep | Powers extraction and wiki page synthesis |

## Files to Create

- `observatory_context/wiki/__init__.py`
- `observatory_context/wiki/compiler.py`
- `observatory_context/wiki/index.py`
- `observatory_context/wiki/lint.py`
- `observatory_context/wiki/compound.py`
- `observatory_context/registry/__init__.py`
- `observatory_context/registry/schema.py`
- `observatory_context/registry/store.py`
- `observatory_context/registry/extract.py`
- `observatory_context/ingest/batch.py`
- `observatory_context/ingest/pipeline.py`

## Files to Modify

- `observatory_context/client.py` — modernize API usage
- `observatory_context/uris.py` — add new URI builders
- `observatory_context/models.py` — extend with registry types
- `observatory_context/delivery.py` — simplify, delegate to wiki/registry
- `observatory_context/config.py` — add rerank config
- `observatory_context/runtime.py` — update builders
- `scripts/viking_ingest.py` — delegate to `ingest/pipeline.py`
- `scripts/query_knowledge_unified.py` — wiki-first navigation
- `scripts/viking_setup.py` — add rerank to config generation
- `config/openviking/ov.conf` — add rerank section

## Files to Delete (after migration)

- `observatory_context/service/` — replaced by wiki + registry
- `observatory_context/retrieval/` — replaced by OpenViking search + wiki
- `observatory_context/overlays/` — unused
- `observatory_context/materialize/` — unused
- `observatory_context/baseline.py` — unused
- `observatory_context/parity.py` — unused
- `observatory_context/render.py` — replaced by wiki pages
- `observatory_context/notes/` — absorbed into wiki
