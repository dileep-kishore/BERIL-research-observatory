---
name: knowledge
description: "Search the research observatory knowledge base through OpenViking — projects, findings, figures, reusable data, entities, hypotheses, pitfalls, discoveries, research ideas, and cross-project connections. Use when the user wants to find projects by topic, search for figures, locate reusable data, explore the knowledge graph, list pitfalls or lessons learned, review discoveries, check research ideas, get a landscape overview, or asks questions like 'what do we know about X', 'what pitfalls have we seen', 'show me discoveries', 'what research ideas exist', 'have we studied Y', 'which projects involve Z', or 'show me findings on W'."
allowed-tools: Read, Bash, Grep
user-invocable: true
---

# Knowledge Query Skill

Search the observatory's knowledge via OpenViking. OpenViking must be running for all queries.

## Usage

```
/knowledge <topic>              — search projects and findings by keyword
/knowledge figures <topic>      — search figure catalog
/knowledge data <topic>         — search reusable data artifacts
/knowledge project <id>         — full summary of a specific project
/knowledge landscape            — high-level overview of all research
/knowledge entities <type>      — list entities (organism, gene, pathway, method, concept)
/knowledge connections <entity> — find all relations involving an entity
/knowledge hypotheses [status]  — list hypotheses, optionally filtered by status
/knowledge gaps                 — find unexplored entity combinations
/knowledge timeline [--project <id>] [--since <date>] — show research evolution
/knowledge related <id_or_uri>  — find related resources (1-hop graph traversal)
/knowledge grep <pattern> [--uri <scope>] [--ignore-case]  — content search
/knowledge glob <pattern>                                   — file pattern match
/knowledge browse <uri>          — browse a directory with tiered content
/knowledge traverse <entity>     — graph walk from an entity
/knowledge recall <query>        — search memories
/knowledge remember <store> <title> <body> — write a memory entry
/knowledge ingest-entity <type> <id> --profile-json <json> — create an entity
/knowledge pitfalls [topic]                  — list/search pitfalls
/knowledge discoveries [topic]               — list/search discoveries
/knowledge ideas [--status STATUS]           — list/search research ideas
```

### Optional Flags

These flags are defined on the parent parser. Place them **before** the subcommand name.

| Flag | Supported by | Description |
|------|-------------|-------------|
| `--tier L0\|L1\|L2` | `search`, `figures`, `data`, `entities`, `connections`, `browse`, `traverse` | Content detail level (default L2). L1 for overviews, L0 for one-liners. |
| `--with-memory` | `search` only | Blend memory results (journal, patterns, conversations) into search. |
| `--scope all\|resources\|memory\|graph` | `search` only | Restrict search scope. `resources` = projects + notes, `graph` = entities/hypotheses, `memory` = memories only. |

Example with flags before subcommand:
```bash
uv run scripts/query_knowledge_unified.py --tier L1 browse viking://resources/observatory/projects/
```

Subcommands not listed above (`project`, `landscape`, `gaps`, `timeline`, `hypotheses`, `related`, `grep`, `glob`, `recall`, `remember`, `ingest-entity`, `pitfalls`, `discoveries`, `ideas`) ignore these flags.

## Prerequisites

OpenViking must be running. If any query fails with a connection error, tell the user:

> "OpenViking is not reachable. See `docs/openviking_tutorial.md` for setup."

Then stop.

## Workflow

Run the unified query script for every subcommand:

```bash
uv run scripts/query_knowledge_unified.py <subcommand> ...
```

Map subcommands directly:
- `/knowledge <topic>` → `search "<topic>"`
- `/knowledge <topic> --project <id>` → `search "<topic>" --project <id>`
- `/knowledge figures <topic>` → `figures "<topic>"`
- `/knowledge data <topic>` → `data "<topic>"`
- `/knowledge project <id>` → `project <id>`
- `/knowledge landscape` → `landscape`
- `/knowledge entities <type>` → `entities <type>`
- `/knowledge connections <entity>` → `connections <entity>`
- `/knowledge hypotheses [status]` → `hypotheses [status]`
- `/knowledge gaps` → `gaps`
- `/knowledge timeline [project]` → `timeline [--project <id>] [--since <date>]`
- `/knowledge related <id>` → `related <id_or_uri>`
- `/knowledge grep <pattern>` → `grep "<pattern>"`
- `/knowledge grep <pattern> --ignore-case` → `grep "<pattern>" --ignore-case`
- `/knowledge grep <pattern> --uri <scope>` → `grep "<pattern>" --uri <scope>`
- `/knowledge glob <pattern>` → `glob "<pattern>"`
- `/knowledge browse <uri>` → `browse <uri>`
- `/knowledge traverse <entity>` → `traverse <entity_uri>`
- `/knowledge recall <query>` → `recall "<query>"`
- `/knowledge remember <store> <title> <body>` → `remember <store> <title> <body>`
- `/knowledge ingest-entity <type> <id> --profile-json <json>` → `ingest-entity <type> <id> --profile-json <json>`
- `/knowledge pitfalls` → `pitfalls`
- `/knowledge pitfalls <topic>` → `pitfalls "<topic>"`
- `/knowledge discoveries` → `discoveries`
- `/knowledge discoveries <topic>` → `discoveries "<topic>"`
- `/knowledge ideas` → `ideas`
- `/knowledge ideas --status <status>` → `ideas --status <status>`

A bare argument (no subcommand) is treated as `search` for backward compatibility:
```bash
uv run scripts/query_knowledge_unified.py "some topic"
# equivalent to: search "some topic"
```

### Subcommand: `/knowledge <topic>`

**Search projects and findings by keyword.**
Run: `uv run scripts/query_knowledge_unified.py search "<topic>"`

Scoped to a project: `uv run scripts/query_knowledge_unified.py search "<topic>" --project <project_id>`

Supports `--tier`, `--with-memory`, `--scope`, `--kind <resource_kind>`, `--limit N` (default 10).

Output format:
```markdown
### Results for "{topic}"

**1. {project_id}** ({status})
- **Q**: {research_question}
- **Findings**: {top 2-3 key findings}
- **Tags**: {tags}
- **Data**: {databases_used}
- [README](projects/{id}/README.md) | [REPORT](projects/{id}/REPORT.md)
```

### Subcommand: `/knowledge figures <topic>`

**Search the figure catalog.**
Run: `uv run scripts/query_knowledge_unified.py figures "<topic>"`

Supports `--tier`. Output: table of matching figures with project, file, and caption. Cap at 20.

### Subcommand: `/knowledge data <topic>`

**Search reusable data artifacts.**
Run: `uv run scripts/query_knowledge_unified.py data "<topic>"`

Supports `--tier`. Output: table of matching artifacts with project, file, description, and reusable flag.

### Subcommand: `/knowledge project <id>`

**Full summary of a specific project.**
Run: `uv run scripts/query_knowledge_unified.py project <id>`

Always fetches at L2 (ignores `--tier`). Output: title, status, research question, key findings, tags, data sources, artifacts, dependencies, provenance status.

### Subcommand: `/knowledge landscape`

**High-level overview of all research.**
Run: `uv run scripts/query_knowledge_unified.py landscape`

Always fetches at L1 (ignores `--tier`). Output: status counts, top tags, BERDL collections, dependency graph, coverage gaps.

### Subcommand: `/knowledge entities <type>`

**List entities of a given type from the knowledge graph.**
Run: `uv run scripts/query_knowledge_unified.py entities <type>`

Valid types: `organism`, `gene`, `pathway`, `method`, `concept`

Supports `--tier`. Output: table with ID, name, project count, description.

### Subcommand: `/knowledge connections <entity_uri>`

**Find all relations involving a specific entity.**
Run: `uv run scripts/query_knowledge_unified.py connections <entity_uri>`

Supports `--tier`. Output: outgoing and incoming relation tables with predicate, target/source, evidence project, confidence.

### Subcommand: `/knowledge hypotheses [status]`

**List hypotheses, optionally filtered by lifecycle status.**
Run: `uv run scripts/query_knowledge_unified.py hypotheses [status]`

Valid statuses: `proposed`, `refined`, `testing`, `validated`, `rejected`, `merged`, `superseded`

Output: table with ID, status, statement, origin project, evidence counts.

### Subcommand: `/knowledge gaps`

**Find unexplored entity combinations and research opportunities.**
Run: `uv run scripts/query_knowledge_unified.py gaps`

Output: organisms needing analysis, method coverage gaps, untested hypotheses, unexplored entity pairs.

### Subcommand: `/knowledge timeline [--project <id>] [--since <date>]`

**Show research evolution chronologically.**
Run: `uv run scripts/query_knowledge_unified.py timeline [--project <id>] [--since <date>]`

With no arguments, shows all timeline events across all projects. Output: table with date, type, project, summary.

### Subcommand: `/knowledge related <id_or_uri>`

**Find related resources via 1-hop graph traversal.**
Run: `uv run scripts/query_knowledge_unified.py related <id_or_uri>`

Output: root entity, connected entities, and relation edges.

### Subcommand: `/knowledge browse <uri>`

**Browse a directory in the knowledge graph with tiered content.**
Run: `uv run scripts/query_knowledge_unified.py --tier L1 browse <uri>`

Supports `--tier` (default L2, but L1 recommended for browsing). Examples:
- `--tier L1 browse viking://resources/observatory/knowledge-graph/entities/` — list all entity types
- `--tier L0 browse viking://resources/observatory/knowledge-graph/entities/organisms/` — compact organism list
- `browse viking://resources/observatory/projects/` — list all projects at L2

### Subcommand: `/knowledge traverse <entity_uri>`

**Graph walk from an entity through its relations.**
Run: `uv run scripts/query_knowledge_unified.py traverse <entity_uri> [--hops N] [--relation-filter PRED]`

Supports `--tier`. `--hops` defaults to 1. Examples:
- `traverse viking://resources/observatory/knowledge-graph/entities/organisms/escherichia-coli --hops 2` — E. coli and 2-hop neighbors
- `traverse viking://resources/observatory/knowledge-graph/entities/organisms/ecoli --relation-filter studied-in` — only "studied-in" relations

### Subcommand: `/knowledge recall <query>`

**Search the memory system for past insights, patterns, and decisions.**
Run: `uv run scripts/query_knowledge_unified.py recall "<query>" [--store journal|patterns|conversations] [--limit N]`

`--limit` defaults to 5.

Memory stores:
- `journal` — research decisions, hypothesis refinements, analysis pivots
- `patterns` — cross-project heuristics and learned lessons
- `conversations` — data surprises, debugging insights, BERDL quirks

### Subcommand: `/knowledge remember <store> <title> <body>`

**Write a memory entry to the knowledge base.**
Run: `uv run scripts/query_knowledge_unified.py remember <store> <title> <body> [--entities e1,e2] [--projects p1,p2] [--tags t1,t2]`

Positional arguments:
- `store` — one of `journal`, `patterns`, `conversations`
- `title` — short title for the memory
- `body` — memory content

Optional flags:
- `--entities` — comma-separated entity references
- `--projects` — comma-separated project IDs
- `--tags` — comma-separated tags

Output: URI of the created memory entry.

### Subcommand: `/knowledge ingest-entity <type> <id>`

**Create a new entity with a profile in the knowledge graph.**
Run: `uv run scripts/query_knowledge_unified.py ingest-entity <type> <id> --profile-json '<json>' [--relations-json '<json>']`

Positional arguments:
- `type` — one of `organism`, `gene`, `pathway`, `method`, `concept`
- `id` — entity identifier slug (e.g., `escherichia-coli`)

Required flag:
- `--profile-json` — JSON string with entity profile data

Optional flag:
- `--relations-json` — JSON array of relations

Output: URI of the created entity.

### Subcommand: `/knowledge grep <pattern>`

**Search inside resource content for a text pattern (requires OpenViking).**
Run: `uv run scripts/query_knowledge_unified.py grep "<pattern>" [--uri <scope>] [--ignore-case]`

Requires a live OpenViking server. If the server is not running, tell the user:

> "grep requires a live OpenViking server. See `docs/openviking_tutorial.md` for setup."

Output: matches grouped by resource URI with line numbers.

### Subcommand: `/knowledge glob <pattern>`

**Find resources by file pattern (requires OpenViking).**
Run: `uv run scripts/query_knowledge_unified.py glob "<pattern>"`

Requires a live OpenViking server. If the server is not running, tell the user:

> "glob requires a live OpenViking server. See `docs/openviking_tutorial.md` for setup."

Output: list of matching resource URIs with total count.

### Subcommand: `/knowledge pitfalls [topic]`

**List or search pitfalls in the knowledge base.**
Run: `uv run scripts/query_knowledge_unified.py pitfalls [topic]`

Optional positional argument filters by keyword. Supports `--category` to filter by pitfall category.

Output: numbered list of pitfalls with title, category, problem description, and solution.

### Subcommand: `/knowledge discoveries [topic]`

**List or search discoveries in the knowledge base.**
Run: `uv run scripts/query_knowledge_unified.py discoveries [topic]`

Optional positional argument filters by keyword.

Output: numbered list of discoveries with title, category, description, and evidence.

### Subcommand: `/knowledge ideas [--status STATUS]`

**List or search research ideas in the knowledge base.**
Run: `uv run scripts/query_knowledge_unified.py ideas [--status STATUS]`

Optional `--status` filter: `PROPOSED`, `IN_PROGRESS`, `COMPLETED`.

Output: numbered list of research ideas with title, status, priority, and research question.

## Integration

- **Query backend**: `scripts/query_knowledge_unified.py` (requires OpenViking)
- **Data source**: OpenViking (single source of truth for all observatory knowledge)
- **Re-ingested by**: `/build-registry` (re-ingests all resources into OpenViking)
- **Consumed by**: agents and users exploring the research landscape
- **Related skills**: `/suggest-research` (landscape analysis + idea writing), `/build-registry` (re-ingest), `/synthesize` (updates knowledge after project completion), `/pitfall-capture` (pitfall writing), discovery-capture (discovery writing)
