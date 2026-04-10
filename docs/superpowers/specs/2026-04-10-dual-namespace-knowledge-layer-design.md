# Dual-Namespace Knowledge Layer: OpenViking Tiered + Wiki Interconnected

**Date**: 2026-04-10
**Status**: Approved
**Branch**: `feature/observatory-wiki-v2`
**Depends on**: Observatory Graph Layer (2026-04-10)

## Summary

The V2 wiki ingest broke ContextDelivery by uploading entity/hypothesis data
to `wiki/` flat files instead of the `knowledge-graph/` directory hierarchy
that OpenViking's tiered loading expects. Fix this by populating both
namespaces from the same resolved registry data: `knowledge-graph/` for
OpenViking-native tiered retrieval and `wiki/` for interconnected agent
navigation.

## Problem

ContextDelivery has 6 methods that read from `knowledge-graph/` URIs:

| Method | URI it reads | Current state |
|--------|-------------|---------------|
| `entities()` | `knowledge-graph/entities/{type}/` | **Empty** — nothing uploaded here |
| `hypotheses()` | `knowledge-graph/hypotheses/` | **Empty** |
| `traverse()` | follows relations from `knowledge-graph/entities/` | **Empty** |
| `timeline()` | `knowledge-graph/timeline/` | **Empty** |
| `search(scope=GRAPH)` | scoped to `knowledge-graph/` | **No results** |
| `_load_item(tier=L0)` | looks for `.abstract.md` in directory | **No directories exist** |

Meanwhile, `wiki/entities/{type}/{slug}.md` has the data but as flat files
without OpenViking's tiered structure. The `query_knowledge_unified.py`
subcommands `entities`, `hypotheses`, `connections`, `traverse`, `timeline`,
`landscape`, and `gaps` all return empty results.

## Design

### Dual namespace layout

After ingest, both namespaces contain the same logical entities:

```
viking://resources/observatory/
├── knowledge-graph/                    # OpenViking-native (tiered directories)
│   ├── entities/
│   │   ├── organisms/
│   │   │   ├── pseudomonas-putida/     # Directory = entity
│   │   │   │   ├── .abstract.md        # L0: "Pseudomonas putida — studied in 8 projects..."
│   │   │   │   ├── .overview.md        # L1: findings table, related entities, projects
│   │   │   │   └── profile.yaml        # L2: full structured data
│   │   │   └── escherichia-coli/
│   │   │       ├── .abstract.md
│   │   │       ├── .overview.md
│   │   │       └── profile.yaml
│   │   ├── genes/
│   │   ├── pathways/
│   │   ├── conditions/
│   │   ├── environments/
│   │   ├── methods/
│   │   ├── datasets/
│   │   └── concepts/
│   ├── hypotheses/
│   │   └── {hyp-slug}/
│   │       ├── .abstract.md
│   │       ├── .overview.md
│   │       └── hypothesis.yaml
│   └── timeline/
│       └── events.yaml
│
├── wiki/                               # Interconnected markdown (agent navigation)
│   ├── index.md
│   ├── log.md
│   ├── topics/{slug}.md                # Cross-linked project pages
│   ├── entities/{type}/{slug}.md       # Cross-linked entity pages
│   └── hypotheses/{slug}.md            # Cross-linked hypothesis pages
│
├── corpus/                             # Source documents (unchanged)
├── registry/                           # Structured YAML (unchanged)
├── memories/                           # Session memories (unchanged)
└── operational/                        # Pitfalls, discoveries, ideas (unchanged)
```

### What goes where

| Data | `knowledge-graph/` | `wiki/` |
|------|-------------------|---------|
| Entity profile | `profile.yaml` (structured) | `{slug}.md` (narrative with links) |
| Entity L0 | `.abstract.md` (1-2 sentences) | — (not needed, index has summaries) |
| Entity L1 | `.overview.md` (table + key findings) | — (wiki page IS the L1-equivalent) |
| Hypothesis | `hypothesis.yaml` + `.abstract.md` + `.overview.md` | `{slug}.md` (linked tracker) |
| Topic/project | — (not an entity type) | `topics/{slug}.md` (synthesis page) |
| Index | — | `index.md` (master catalog) |
| Timeline | `timeline/events.yaml` | — |
| Relations | OpenViking `link()` API | Markdown cross-links |

### Tier content generation

**L0 `.abstract.md`** — One-liner generated from the entity's findings:

```markdown
Pseudomonas putida — organism studied in 8 projects (metal_fitness_atlas,
conservation_vs_fitness, ...). Key finding: 87.4% of metal fitness genes
are in the core genome. Coverage: high.
```

**L1 `.overview.md`** — Structured summary with tables:

```markdown
# Pseudomonas putida

**Entity type:** organism | **Projects:** 8 | **Findings:** 12 | **Coverage:** high

## Key Findings
| ID | Title | Confidence | Project |
|----|-------|-----------|---------|
| F-metal-001 | Metal fitness genes enriched in core | high | metal_fitness_atlas |
| F-cons-003 | Core enrichment correlates with breadth | moderate | conservation_vs_fitness |

## Related Entities
| Entity | Type | Co-occurrences |
|--------|------|---------------|
| Cupriavidus metallidurans | organism | 3 |
| core genome | concept | 5 |
| czc efflux | pathway | 2 |

## Hypotheses
- HYP-007 (tested): Metal cross-resistance via shared regulation
```

**L2 `profile.yaml`** — Full structured data:

```yaml
canonical_name: Pseudomonas putida
entity_type: organism
aliases: [P. putida, Pseudomonas putida KT2440]
project_ids: [metal_fitness_atlas, conservation_vs_fitness, ...]
findings:
  - finding_id: F-metal-001
    title: Metal fitness genes enriched in core
    statement: "87.4% of metal fitness genes are in the core genome"
    confidence: high
    conditions: [zinc stress, copper stress]
    project_id: metal_fitness_atlas
related_entities:
  - canonical_name: Cupriavidus metallidurans
    entity_type: organism
    weight: 3
  - canonical_name: core genome
    entity_type: concept
    weight: 5
hypotheses:
  - hypothesis_id: HYP-007
    status: tested
community:
  id: 1
  name: Metal Stress & Fitness
```

### OpenViking relations

In addition to the directory structure, create OpenViking `link()` relations
between entities so `traverse()` works:

```python
# For each RELATED_TO edge in the NetworkX graph:
client.link_resources(
    from_uri="knowledge-graph/entities/organisms/pseudomonas-putida",
    to_uri="knowledge-graph/entities/organisms/cupriavidus-metallidurans",
    reason="co-occur in 3 findings (metal_fitness_atlas, bacdive_metal_validation, ...)"
)
```

This enables ContextDelivery's `traverse()` to walk the graph via OpenViking's
native relation system, not just the NetworkX graph file.

### Pipeline changes

Phase 3 (Build Graph) remains unchanged — it builds the NetworkX graph,
runs community detection, generates `GRAPH_REPORT.md`.

**New Phase 3.5: Populate Knowledge Graph Namespace**

After the NetworkX graph is built, generate and upload the `knowledge-graph/`
directory hierarchy:

1. For each resolved entity in the graph:
   - Generate `.abstract.md` (L0) from findings summary
   - Generate `.overview.md` (L1) with tables
   - Generate `profile.yaml` (L2) with full structured data
   - Stage into `knowledge-graph/entities/{type}/{slug}/` directory
2. For each hypothesis:
   - Generate `.abstract.md`, `.overview.md`, `hypothesis.yaml`
   - Stage into `knowledge-graph/hypotheses/{slug}/`
3. For timeline events:
   - Stage into `knowledge-graph/timeline/events.yaml`
4. Batch upload the entire `knowledge-graph/` directory
5. Create OpenViking `link()` relations for entity connections

Phase 4 (Compile Wiki) stays as-is — it generates the interconnected
markdown pages that link to each other.

**No changes needed to:**
- ContextDelivery (it already reads `knowledge-graph/` correctly)
- `query_knowledge_unified.py` (subcommands already delegate to ContextDelivery)
- Skills (they call query_knowledge_unified.py)
- The MCP graph server (it reads NetworkX, not OpenViking)

### New module

`observatory_context/graph/knowledge_graph_export.py`:

```python
class KnowledgeGraphExporter:
    """Generate the knowledge-graph/ directory hierarchy from resolved graph data."""

    def __init__(self, builder: GraphBuilder, resolver: EntityResolver):
        self.builder = builder
        self.resolver = resolver

    def generate_entity_l0(self, entity_type: str, canonical: str,
                           findings: list[Finding], project_ids: list[str]) -> str:
        """One-liner abstract for .abstract.md."""

    def generate_entity_l1(self, entity_type: str, canonical: str,
                           findings: list[Finding], hypotheses: list[Hypothesis],
                           related: list[dict], project_ids: list[str]) -> str:
        """Structured overview for .overview.md."""

    def generate_entity_l2(self, entity_type: str, canonical: str,
                           findings: list[Finding], hypotheses: list[Hypothesis],
                           related: list[dict], project_ids: list[str],
                           community: dict | None) -> str:
        """Full profile.yaml content."""

    def generate_hypothesis_l0(self, hypothesis: Hypothesis) -> str:
    def generate_hypothesis_l1(self, hypothesis: Hypothesis,
                               supporting: list[Finding]) -> str:
    def generate_hypothesis_l2(self, hypothesis: Hypothesis,
                               supporting: list[Finding]) -> str:

    def export_all(self, staging_dir: Path) -> int:
        """Generate all files into staging_dir, return file count."""

    def create_relations(self, client: OpenVikingObservatoryClient) -> int:
        """Create OpenViking link() relations from graph edges. Return count."""
```

### Query flow after implementation

```
Agent: "What organisms are in the knowledge graph?"
  → /knowledge skill calls: query_knowledge_unified.py entities organism
  → ContextDelivery.entities("organism")
  → browses knowledge-graph/entities/organisms/ (directory listing)
  → returns L1 overviews (tables with findings, projects, coverage)

Agent: "Tell me about Pseudomonas putida"
  → query_knowledge_unified.py search "Pseudomonas putida" --scope graph
  → ContextDelivery.search(scope=GRAPH)
  → OpenViking finds knowledge-graph/entities/organisms/pseudomonas-putida/
  → at L2: returns profile.yaml (full structured data)
  → at L1: returns .overview.md (table summary)

Agent: "What's connected to Pseudomonas putida?"
  → query_knowledge_unified.py traverse <entity_uri> --hops 2
  → ContextDelivery.traverse()
  → follows OpenViking link() relations
  → returns connected entities at requested tier

Agent: "Show me the wiki page for Pseudomonas putida"
  → query_knowledge_unified.py wiki-topic pseudomonas-putida
  → reads wiki/entities/organisms/pseudomonas-putida.md
  → interconnected page with links to related entities, projects, hypotheses
```

### Cost

Zero additional LLM calls. L0/L1/L2 content is generated deterministically
from the registry data and graph structure — no CBORG summarization needed.
The only API calls are OpenViking `link()` for creating relations (~5000
calls for our graph, fast HTTP, no rate limit).

### Migration

No migration needed — the `knowledge-graph/` namespace is currently empty.
The new phase simply populates it for the first time.

## Files to Create

- `observatory_context/graph/knowledge_graph_export.py`

## Files to Modify

- `observatory_context/ingest/pipeline.py` — add Phase 3.5 after graph build
- `observatory_context/uris.py` — ensure all `knowledge-graph/` builders work with new entity types

## Success Criteria

1. `query_knowledge_unified.py entities` returns all resolved entities with L1 overviews
2. `query_knowledge_unified.py hypotheses` returns hypothesis list with status
3. `query_knowledge_unified.py traverse <entity>` walks graph via OpenViking relations
4. `query_knowledge_unified.py search "topic" --scope graph` returns graph hits
5. Wiki pages still work with full interconnection
6. Tier loading works: `--tier L0` returns abstracts, `--tier L1` returns overviews
