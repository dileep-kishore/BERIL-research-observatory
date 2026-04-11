# OpenViking Setup

Use the full tutorial in [docs/openviking_tutorial.md](openviking_tutorial.md)
for detailed instructions.

## Quick start

```bash
uv sync --extra dev

# Generate server config from env vars or .env
uv run scripts/viking_setup.py --write-config
export OPENVIKING_CONFIG_FILE="$PWD/config/openviking/ov.conf"

# Start server (separate terminal)
uv run openviking-server --config "$OPENVIKING_CONFIG_FILE"

# Verify health
uv run scripts/viking_server_healthcheck.py

# Full ingest (first time)
uv run scripts/viking_ingest.py --no-resume --from-scratch --wait --wait-timeout 7200

# Incremental update (after editing projects)
uv run scripts/viking_ingest.py --wait --wait-timeout 7200

# Single project update
uv run scripts/viking_ingest.py --project <project_id> --wait --wait-timeout 7200
```

## Required environment variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Embeddings via OpenAI `text-embedding-3-large` |
| `CBORG_API_KEY` | Knowledge extraction via CBORG `gpt-5.4-mini` |

`viking_setup.py --write-config` reads from shell environment first,
then repo-local `.env`.

## Ingest flags

| Flag | Effect |
|------|--------|
| `--no-resume` | Re-upload all resources (ignore existing) |
| `--wait` | Block until server finishes processing (slow — see below) |
| `--wait-timeout S` | Maximum seconds to wait when `--wait` is set |
| `--project X` | Limit to specific project(s), repeatable |
| `--from-scratch` | Clear local durable ingest state and graph artifacts before running |
| `--restart-from PHASE` | Force rerun from `corpus`, `registry`, `graph`, `knowledge_graph`, `wiki`, or `log` |
| `--no-checkpoint-resume` | Do not auto-resume the latest incomplete matching run |
| `--dry-run` | Preview manifest without uploading |
| `--check` | Verify all expected resources are present |
| `--fix` | Re-ingest missing resources |
| `--model M` | Override CBORG model for extraction |

**Note on `--wait`**: The server processes uploaded resources
asynchronously, so large rebuilds can still take a while even after the
pipeline finishes staging and uploading files. Omit `--wait` for faster
runs if you do not need a blocking confirmation.

**Checkpointing**: failed runs now resume automatically from the next
incomplete phase for the same project scope. Re-run the same command to
continue, or use `--restart-from` to force a later phase to rebuild.

## Verification

```bash
uv run scripts/viking_server_healthcheck.py --watch  # monitor queue
uv run scripts/viking_ingest.py --check              # check parity
uv run scripts/viking_validate_parity.py             # full validation
```
