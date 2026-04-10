# OpenViking Tutorial

OpenViking is the single source of truth for all observatory knowledge data.
This tutorial walks through setup, ingest, and querying.

## Prerequisites

- `uv`
- Python 3.11+
- `openviking-server` available in the project environment

Install the project environment:

```bash
uv sync --extra dev
```

## 1. Create the repo-local server config

```bash
export OPENAI_API_KEY="your-openai-api-key"
uv run scripts/viking_setup.py --write-config
export OPENVIKING_CONFIG_FILE="$PWD/config/openviking/ov.conf"
```

The setup script resolves settings from shell environment first, then
repo-local `.env`. It generates `config/openviking/ov.conf` with concrete
values for:

| Variable | Default |
|----------|---------|
| `OPENAI_API_KEY` | (required) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` |
| `OPENVIKING_EMBEDDING_MODEL` | `text-embedding-3-large` |
| `OPENVIKING_EMBEDDING_DIMENSION` | `3072` |

The config also includes VLM and rerank sections that use CBORG:

```json
{
  "vlm": {
    "api_base": "https://api.cborg.lbl.gov/v1",
    "model": "gpt-5.4-mini"
  },
  "rerank": {
    "api_base": "https://api.cborg.lbl.gov/v1",
    "model": "gpt-5.4-mini"
  }
}
```

## 2. Start the local server

```bash
uv run openviking-server --config "$OPENVIKING_CONFIG_FILE"
```

If you add `server.root_api_key` to the config, also export:

```bash
export BERIL_OPENVIKING_API_KEY="your-api-key"
```

## 3. Check server health

```bash
uv run scripts/viking_server_healthcheck.py
```

Expected: a Rich dashboard showing HEALTHY status, processing queue
progress, vector store stats, and component badges. Use `--watch` to
auto-refresh:

```bash
uv run scripts/viking_server_healthcheck.py --watch --interval 10
```

## 4. Ingest observatory resources

Preview the manifest first:

```bash
uv run scripts/viking_ingest.py --dry-run --limit 5
```

Full ingest (recommended for first run):

```bash
uv run scripts/viking_ingest.py --no-resume
```

This runs a four-phase pipeline:

### Phase 1 — Corpus Upload

Scans `projects/*/`, discovers README.md, REPORT.md, provenance.yaml,
and figures. Batch uploads to `viking://resources/observatory/corpus/`.
Supports resume mode (skips already-ingested URIs by default).

### Phase 2 — Registry Extraction

For each project with a REPORT.md, runs CBORG extraction (default model:
`gpt-5.4-mini`). Requires `CBORG_API_KEY`. Extracts entities, relations,
hypotheses, and timeline events into structured YAML registry entries.
Uploads to `viking://resources/observatory/registry/`.

### Phase 3 — Wiki Compilation

Compiles wiki pages from registry entries:
- **Entity profiles** in `wiki/entities/{type}/{slug}.md`
- **Topic synthesis** pages in `wiki/topics/{slug}.md`
- **Hypothesis trackers** in `wiki/hypotheses/{id}.md`
- **Master index** at `wiki/index.md`

Uploads to `viking://resources/observatory/wiki/`.

### Phase 4 — Log Update

Appends a timestamped ingest record to `wiki/log.md`. Retries with
exponential backoff if the server holds a lock from Phase 3 processing.

### Server-side processing

After upload, OpenViking processes each resource asynchronously:
embeddings (OpenAI) and VLM file summaries (CBORG). With CBORG's
~20 req/min rate limit, processing 1000+ resources takes 30+ minutes.

Use `--wait` to block until processing completes, or omit it — data is
queryable immediately, summaries populate in the background.

### Common ingest commands

```bash
# Full ingest from scratch
uv run scripts/viking_ingest.py --no-resume

# Incremental update (only new/changed resources)
uv run scripts/viking_ingest.py

# Single project
uv run scripts/viking_ingest.py --project rbtnseq_pooled_fitness

# Verify all resources exist
uv run scripts/viking_ingest.py --check

# Re-ingest missing resources
uv run scripts/viking_ingest.py --fix
```

## 5. Query the knowledge base

All knowledge access goes through `scripts/query_knowledge_unified.py`,
which delegates to the `ContextDelivery` service layer. Skills call it
via CLI subcommands rather than talking to OpenViking directly.

### Search and navigation

```bash
# Semantic search across all resources
uv run scripts/query_knowledge_unified.py search "fitness genes"

# Project summary
uv run scripts/query_knowledge_unified.py project rbtnseq_pooled_fitness

# Browse figures and reusable data
uv run scripts/query_knowledge_unified.py figures
uv run scripts/query_knowledge_unified.py data

# Content search (grep/glob across resources)
uv run scripts/query_knowledge_unified.py grep "RB-TnSeq"
uv run scripts/query_knowledge_unified.py glob "*.png"
```

### Knowledge graph

```bash
# List entities by type
uv run scripts/query_knowledge_unified.py entities

# Show relations for an entity
uv run scripts/query_knowledge_unified.py connections "Pseudomonas"

# Graph overview
uv run scripts/query_knowledge_unified.py landscape

# Graph traversal
uv run scripts/query_knowledge_unified.py traverse \
  viking://resources/observatory/wiki/entities/organisms/pseudomonas-putida
```

### Research metadata

```bash
# Hypotheses and their status
uv run scripts/query_knowledge_unified.py hypotheses

# Research gaps (proposed/testing hypotheses)
uv run scripts/query_knowledge_unified.py gaps

# Pitfalls, discoveries, research ideas
uv run scripts/query_knowledge_unified.py pitfalls
uv run scripts/query_knowledge_unified.py discoveries
uv run scripts/query_knowledge_unified.py ideas
```

### Wiki operations

```bash
# Master index (agent reads this first)
uv run scripts/query_knowledge_unified.py wiki-index

# Topic synthesis page
uv run scripts/query_knowledge_unified.py wiki-topic "cofitness"

# Lint — contradiction, staleness, gap detection
uv run scripts/query_knowledge_unified.py wiki-lint
```

### Memory and sessions

```bash
# Recall memories
uv run scripts/query_knowledge_unified.py recall "normalization"

# Write a memory
uv run scripts/query_knowledge_unified.py remember "finding about X"

# Session management
uv run scripts/query_knowledge_unified.py session start
uv run scripts/query_knowledge_unified.py session status
```

### Progressive drill-down

```bash
# L0 → L1 → L2 progressive refinement
uv run scripts/query_knowledge_unified.py drill "metabolite biosynthesis"
```

### Relations

```bash
# Link/unlink resources
uv run scripts/query_knowledge_unified.py link <uri-a> <uri-b> --predicate "relates-to"
uv run scripts/query_knowledge_unified.py unlink <uri-a> <uri-b>
```

### Global options

| Flag | Effect |
|------|--------|
| `--tier L0\|L1\|L2` | Detail level (default: L2) |
| `--with-memory` | Blend memory results into search |
| `--scope all\|resources\|memory\|graph` | Limit search scope |
| `--session ID` | Context-aware search (uses OpenViking `search()`) |

### Tier system

| Tier | Size | Content |
|------|------|---------|
| L0 | ~80 tokens | One-line abstract |
| L1 | ~300 tokens | Overview / summary table |
| L2 | Full | Complete content |

Pass `--tier L0` or `--tier L1` to reduce token usage when scanning many
results.

## 6. Code architecture

```
observatory_context/
├── client.py               # OpenViking HTTP client wrapper
├── config.py               # Settings (Pydantic, BERIL_* env vars)
├── delivery.py             # ContextDelivery — unified query facade
├── extraction.py           # CBORG knowledge extraction
├── uris.py                 # Deterministic URI builders
├── models.py               # Data models
│
├── wiki/                   # Wiki compilation layer
│   ├── compiler.py         # Compile entity/topic/hypothesis pages
│   ├── index.py            # Maintain wiki/index.md
│   └── lint.py             # Contradiction/gap/staleness detection
│
├── registry/               # Structured knowledge registry
│   ├── schema.py           # Pydantic models (Finding, Hypothesis, …)
│   ├── store.py            # YAML read/write via OpenViking
│   └── extract.py          # CBORG extraction → registry entries
│
└── ingest/                 # 4-phase ingest pipeline
    ├── manifest.py         # Resource manifest builder
    ├── batch.py            # Batch upload orchestration
    └── pipeline.py         # Phase 1–4 pipeline orchestrator
```

## 7. Run repository verification

```bash
uv run --with pytest pytest scripts/tests -q
uv run scripts/validate_provenance.py
uv run scripts/viking_ingest.py --check
uv run scripts/viking_validate_parity.py
```

## Troubleshooting

- **`FAIL: OpenViking server is not reachable`**:
  Start the server first or verify `BERIL_OPENVIKING_URL`.
- **`FAIL: config not found .../ov.conf`**:
  Run `uv run scripts/viking_setup.py --write-config`.
- **`Missing OPENAI_API_KEY`**:
  Export it in your shell or add to `.env`, then rerun setup.
- **`--check` reports missing resources**:
  Run `uv run scripts/viking_ingest.py --fix`.
- **`Failed to acquire point lock`**:
  Server is still processing previous uploads. Wait or omit `--wait`.
- **CBORG 429 rate limits**:
  Normal during large ingests (~20 req/min limit). The server retries
  automatically with backoff.
- **CBORG 401 Unauthorized**:
  Check that `CBORG_API_KEY` is valid and not expired.
