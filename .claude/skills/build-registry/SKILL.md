---
name: build-registry
description: Re-ingest all observatory resources into OpenViking. Use when data is missing, stale, or after bulk changes to projects.
allowed-tools: Bash, Read
user-invocable: true
---

# Build Registry Skill

Re-ingest observatory resources into OpenViking so that `/knowledge` queries reflect the latest project state.

## Usage

```
/build-registry              — incremental ingest (resources + knowledge graph)
/build-registry --check      — verify ingest status without re-ingesting
/build-registry --clean      — full rebuild from local ingest state
```

## Workflow

### Incremental Ingest (default)

Run:

```bash
uv run scripts/viking_ingest.py --wait --wait-timeout 7200
```

This runs the synthesis-backed pipeline:
1. **Phase 1** — Upload project resources (README, REPORT, provenance, figures). Uses `--resume` by default to skip existing resources.
2. **Phase 2** — Extract registry entries via CBORG (gpt-5.4-mini) and persist per-project snapshots under `data/ingest/registry/projects/`.
3. **Phase 3** — Rebuild the persistent NetworkX graph from all durable registry snapshots.
4. **Phase 4** — Export the OpenViking `knowledge-graph/` namespace.
5. **Phase 5** — Compile the wiki from the same synthesis bundle.
6. **Phase 6** — Update the ingest log.

Requires `CBORG_API_KEY` env var.

### Full Rebuild from Scratch

```bash
uv run scripts/viking_ingest.py --no-resume --from-scratch --wait --wait-timeout 7200
```

- `--no-resume`: re-uploads all project resources
- `--from-scratch`: wipes local durable ingest state and graph artifacts
- All projects are re-extracted and the global knowledge layer is rebuilt

### Single Project Update

```bash
uv run scripts/viking_ingest.py --project <project_id> --wait --wait-timeout 7200
```

With `--project`, only that project's corpus and extraction are in scope, but
the graph, `knowledge-graph/`, and wiki are rebuilt from all persisted
registry snapshots to maintain a correct global knowledge layer.

### Resume a Failed Run

Re-run the same command. The latest incomplete matching run resumes
automatically from the next incomplete phase.

To force a later phase to rerun:

```bash
uv run scripts/viking_ingest.py --restart-from graph --wait --wait-timeout 7200
```

### Check Status

```bash
uv run scripts/viking_ingest.py --check
```

Verifies all expected resources are present in OpenViking. Use `--fix` to re-ingest missing ones.

### Server Health

```bash
uv run scripts/viking_server_healthcheck.py          # one-shot status
uv run scripts/viking_server_healthcheck.py --watch   # auto-refresh until queues drain
```

To use a specific CBORG model: `--model claude-haiku` or `--model gpt-5.4-mini`

## Integration

- **Called by**: `/synthesize` (Step 7.6), `/submit` (Step 2), `/berdl_start` (Phase B)
- **Generates for**: `/knowledge` (query skill), `/suggest-research` (landscape analysis)
- **Source of truth**: OpenViking (all queries go through OpenViking)
- **Local durable state**: `data/ingest/` stores per-project registry snapshots and run checkpoints

## When to Re-ingest

Run an incremental ingest (`--wait --wait-timeout 7200`) when:
- A project's REPORT.md or provenance.yaml changed
- A new project was added
- After running `/synthesize` on a project

Run a full rebuild (`--no-resume --from-scratch --wait --wait-timeout 7200`) when:
- OpenViking data store was wiped or corrupted
- After merging branches that modified many projects
- When `/knowledge` queries return unexpected results
