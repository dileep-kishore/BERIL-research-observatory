# OpenViking API Modernization

**Date:** 2026-04-01
**Branch:** feature/viking-migration
**Scope:** observatory_context package + query_knowledge_unified.py + ingest scripts

## Summary

Modernize the observatory's OpenViking integration to use the full Python SDK
capabilities: rich search results with scores/match reasons, proper session
lifecycle management, progressive tier loading, relation management, and
consolidated ingest utilities.

## Goals

1. Surface OpenViking's rich `MatchedContext` data (scores, match reasons,
   relations, categories) through the full stack
2. Add proper session lifecycle (create/resume/commit with auto-memory extraction)
3. Expose progressive L0->L1->L2 drill-down via CLI
4. Add `link`/`unlink`/`stat` commands for relation and resource management
5. Consolidate ingest script utilities and expose missing client methods

## Non-Goals

- Changing the OpenViking server configuration or data schema
- Re-ingesting existing data (all changes are read-side or new operations)
- Rewriting the ingest pipeline logic (only consolidating shared utilities)

---

## Design

### 1. Model Enrichment (`observatory_context/models.py`)

Add optional fields to `ContextItem` for rich search metadata:

```python
class RelatedItem(BaseModel):
    """Inline relation returned by OpenViking search."""
    uri: str
    reason: str

class ContextItem(BaseModel):
    # ... existing fields unchanged ...
    score: float | None = None
    match_reason: str | None = None
    is_leaf: bool | None = None
    category: str | None = None
    related: list[RelatedItem] = Field(default_factory=list)
```

Add `session_id` to `SearchResults`:

```python
class SearchResults(BaseModel):
    # ... existing fields ...
    session_id: str | None = None
```

All new fields have defaults — zero breaking changes for existing consumers.

### 2. Client Enrichment (`observatory_context/client.py`)

Expose missing OpenViking SDK methods on `OpenVikingObservatoryClient`:

```python
# New methods
def rm(self, uri: str, recursive: bool = False) -> None
def unlink(self, from_uri: str, to_uri: str) -> None
def stat(self, uri: str) -> dict[str, Any]  # already exists but verify return shape
def batch_add(self, path: str, to: str, reason: str, wait: bool = False) -> dict[str, Any]

# Session management
def create_session(self) -> str  # returns session_id
def get_session(self, session_id: str) -> dict[str, Any]
def add_session_message(self, session_id: str, role: str, parts: list) -> None
def commit_session(self, session_id: str) -> dict[str, Any]
```

The `search()` method signature changes to accept a `session` object (from
`client.session()`) instead of just a session_id string, for full SDK usage.

### 3. Delivery Layer Updates (`observatory_context/delivery.py`)

**Search methods** — populate new `ContextItem` fields from `MatchedContext`:

```python
def search(self, query, ...) -> SearchResults:
    # Map MatchedContext fields -> ContextItem fields:
    #   ctx.score -> item.score
    #   ctx.match_reason -> item.match_reason
    #   ctx.is_leaf -> item.is_leaf
    #   ctx.category -> item.category
    #   ctx.relations -> item.related (as RelatedItem list)
```

**Session management** — new methods:

```python
def start_session(self) -> str
    """Create a new OpenViking session, persist ID to .beril-session file."""

def resume_session(self) -> str | None
    """Read session ID from .beril-session if it exists."""

def commit_session(self, session_id: str) -> dict[str, Any]
    """Commit session, triggering memory extraction."""

def session_status(self, session_id: str) -> dict[str, Any]
    """Get session metadata and status."""
```

**Relation management** — new methods:

```python
def link(self, from_uri: str, to_uris: list[str], reason: str) -> None
def unlink(self, from_uri: str, to_uri: str) -> None
```

### 4. Query Script Updates (`scripts/query_knowledge_unified.py`)

**Enriched output** — `_print_context_item()` gains:
```
- score: 0.92
- match_reason: Semantic match on microbiome diversity
- related: viking://resources/..., viking://resources/...
```

**New subcommands:**

| Command | Description |
|---------|-------------|
| `session start` | Create session, save ID to `.beril-session` |
| `session status` | Show current session info |
| `session commit` | Commit session, trigger memory extraction |
| `session clear` | Remove `.beril-session` file |
| `link <from_uri> <to_uri> [--reason]` | Create explicit relation |
| `unlink <from_uri> <to_uri>` | Remove relation |
| `stat <uri>` | Show resource metadata |
| `drill <query>` | Progressive L0->L1->L2 interactive drill-down |

**Session integration** — `search` auto-resumes session from `.beril-session`
when `--session` is passed without a value:
```bash
# Start a session
uv run scripts/query_knowledge_unified.py session start

# Searches auto-use session context
uv run scripts/query_knowledge_unified.py --session search "microbiome"

# Commit when done
uv run scripts/query_knowledge_unified.py session commit
```

**`drill` subcommand** — progressive loading workflow:
```bash
uv run scripts/query_knowledge_unified.py drill "pangenome analysis"
# Shows L0 abstracts for top matches
# User picks a result number
# Shows L1 overview
# User confirms for L2
# Shows full content
```

Since the CLI is non-interactive (invoked by skills), `drill` takes optional
`--pick N` and `--depth L0|L1|L2` flags for scripted use:
```bash
# Get L1 overview of first match
uv run scripts/query_knowledge_unified.py drill "pangenome" --pick 1 --depth L1
```

### 5. Client Wrapper Consolidation (`observatory_context/client.py`)

Methods currently accessed via `client.client.xyz()` (bypassing the wrapper)
get proper wrapper methods:

- `rm()` — used by `viking_ingest.py` for graph cleanup
- `batch_add()` — wraps `add_resource(path=dir, to=uri)` pattern used by both
  ingest scripts
- `unlink()` — new, for relation removal

### 6. Ingest Script Improvements

**Shared staging utility** — extract `_write_file()` to
`observatory_context/staging.py`:

```python
def write_staged_file(
    base: Path,
    rel_path: str,
    content: str,
    metadata: dict | None = None,
) -> None:
    """Stage a file with optional YAML frontmatter for batch upload."""
```

Both `viking_ingest.py` and `migrate_docs_to_openviking.py` import from here
instead of duplicating.

**viking_ingest.py changes:**
- Replace `client.client.add_resource(...)` with `client.batch_add(...)`
- Replace `client.client.rm(...)` with `client.rm(...)`
- Add optional `--link-relations` flag: after ingest, call `client.link()` to
  create explicit OpenViking relations between entities (currently they're only
  stored as YAML files, not as OpenViking graph edges)

**migrate_docs_to_openviking.py changes:**
- Replace `delivery.client.client.add_resource(...)` with
  `delivery.client.batch_add(...)`
- Import `write_staged_file` from shared utility

### 7. Output Format

The `--json` flag is not in scope (per user preference for option C — "just
change it"). The text output format gains new fields inline:

```
## 1. Microbiome diversity analysis
- uri: viking://resources/observatory/projects/pangenome-01/...
- kind: project_document
- tier: L2
- score: 0.92
- match_reason: Semantic match on microbiome diversity patterns
- projects: pangenome-01
- related: viking://resources/.../related-doc (Related documentation)

<content>
```

Fields only appear when present (score/match_reason only from search results,
not from `browse` or `get`).

---

## File Change Summary

| File | Change Type |
|------|-------------|
| `observatory_context/models.py` | Add `RelatedItem`, extend `ContextItem`, `SearchResults` |
| `observatory_context/client.py` | Add `rm`, `unlink`, `batch_add`, session methods |
| `observatory_context/delivery.py` | Map `MatchedContext` fields, add session/link methods |
| `observatory_context/staging.py` | **New** — shared `write_staged_file` utility |
| `scripts/query_knowledge_unified.py` | Enrich output, add 8 new subcommands |
| `scripts/viking_ingest.py` | Use wrapper methods, import shared staging |
| `scripts/migrate_docs_to_openviking.py` | Use wrapper methods, import shared staging |

## Testing

- Existing `query_knowledge_unified.py` subcommands continue to work with
  richer output
- New subcommands (`session`, `link`, `unlink`, `stat`, `drill`) tested
  manually against running OpenViking
- Ingest scripts tested with `--dry-run` to verify staging changes
- No re-ingest of existing data required
