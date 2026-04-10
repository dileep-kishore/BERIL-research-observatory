# OpenViking Resource Model

OpenViking is the single source of truth for all observatory knowledge data.

## URI hierarchy

The observatory uses five top-level namespaces under
`viking://resources/observatory/`:

```text
viking://resources/observatory/
├── wiki/                           # Compiled knowledge (agent's primary surface)
│   ├── index.md                    # Master catalog — read this first
│   ├── log.md                      # Append-only ingest activity log
│   ├── topics/{slug}.md            # Cross-project synthesis pages
│   ├── entities/{type}/{slug}.md   # Entity profiles (organism, gene, pathway, …)
│   └── hypotheses/{hyp-id}.md      # Hypothesis tracker pages
├── registry/                       # Structured extracted knowledge (YAML)
│   ├── projects/{id}.yaml
│   ├── findings/{id}.yaml
│   ├── hypotheses/{id}.yaml
│   ├── evidence/{id}.yaml
│   ├── artifacts/{id}.yaml
│   ├── figures/{id}.yaml
│   ├── pitfalls/{id}.yaml
│   ├── ideas/{id}.yaml
│   └── discoveries/{id}.yaml
├── corpus/                         # Indexed source documents (immutable)
│   └── {project_id}/
│       ├── README.md
│       ├── REPORT.md
│       ├── provenance.yaml
│       └── figures/
├── operational/                    # Enriched pitfalls, discoveries, ideas
│   ├── pitfalls/
│   ├── discoveries/
│   └── research-ideas/
└── memories/                       # Session memories
    ├── journal/
    ├── patterns/
    └── conversations/
```

## Resource kinds

| Kind | Description | Example URI |
|------|-------------|-------------|
| `project` | Project README entry point | `corpus/{id}/README.md` |
| `project_document` | REPORT.md and provenance.yaml | `corpus/{id}/REPORT.md` |
| `figure` | Project figure files | `corpus/{id}/figures/{name}` |
| `finding` | Extracted finding (YAML) | `registry/findings/{id}.yaml` |
| `hypothesis` | Extracted hypothesis (YAML) | `registry/hypotheses/{id}.yaml` |
| `entity_profile` | Compiled entity wiki page | `wiki/entities/{type}/{slug}.md` |
| `topic_synthesis` | Cross-project synthesis | `wiki/topics/{slug}.md` |
| `hypothesis_tracker` | Hypothesis status page | `wiki/hypotheses/{id}.md` |
| `log` | Ingest activity log | `wiki/log.md` |

## Wiki page format

All wiki pages use YAML frontmatter + markdown:

```markdown
---
title: Metal Stress Responses
kind: topic_synthesis
sources:
  - corpus/metal-stress-ecotypes/REPORT.md
  - corpus/zinc-homeostasis-pp/REPORT.md
coverage: high
last_compiled: 2026-04-08
---

# Metal Stress Responses

## Key Findings
…
```

Kinds: `entity_profile`, `topic_synthesis`, `hypothesis_tracker`.

## Registry schema

Structured YAML entries extracted by CBORG from project reports:

- **Finding** — statement, confidence, related entities, source refs
- **Hypothesis** — statement, status (proposed/tested/supported/mixed/not_supported), project refs
- **Project** — research question, organisms, methods, dependencies
- **Evidence** — statistical support linked to findings
- **Artifact** — reusable datasets with provenance
- **Figure** — captioned figures linked to findings
- **Pitfall** — documented gotchas and workarounds
- **ResearchIdea** — proposed future directions

## Entity classes

| Class | Examples |
|-------|---------|
| Taxon | Pseudomonas putida, Prochlorococcus marinus |
| GeneFamily | czc efflux, trpA, rpoB |
| Pathway | nitrogen fixation, quorum sensing |
| Condition | zinc stress, nitrogen limitation |
| Environment | soil, marine, freshwater |
| Method | pangenome analysis, fitness assay |
| Dataset | BERDL pangenome_analysis.gene_clusters |
| Concept | ecotype, dark genes, horizontal gene transfer |

## Deterministic metadata

Every manifest item carries stable fields: `id`, `kind`, `title`,
`project_ids`, `source_refs`, `tags`.

## Idempotency rule

Resources are identified by their deterministic URI. Re-ingest reuses the
same URI for the same source artifact so parity checks detect duplicates
by URI alone.
