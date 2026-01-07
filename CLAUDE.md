# Pangenome Science Project

## Purpose

Use the `kbase_ke_pangenome` database to pursue scientific questions in microbial genomics and ecology, while building shared documentation that accelerates future work.

## Dual Goals

1. **Science**: Answer research questions in `projects/` subdirectories
2. **Knowledge**: Capture learnings in `docs/` to reduce re-discovery overhead

## Documentation Workflow

When working on any science project, update `docs/` when you discover:

| Discovery Type | Add To |
|----------------|--------|
| Query pitfall or gotcha | `docs/pitfalls.md` |
| Performance issue or strategy | `docs/performance.md` |
| Data limitation or coverage gap | `docs/pitfalls.md` |
| Useful insight about data structure | `docs/schema.md` |
| Any other learning worth sharing | `docs/discoveries.md` |

**Tag each addition** with the project that uncovered it:
```markdown
### [ecotype_analysis] AlphaEarth coverage is only 28%
Discovered that only 83K/293K genomes have embeddings...
```

## Documentation Files

| File | Purpose |
|------|---------|
| `docs/overview.md` | Project goals, data workflow, scientific context |
| `docs/schema.md` | Table schemas, columns, relationships, row counts |
| `docs/pitfalls.md` | SQL gotchas, data sparsity, common errors |
| `docs/performance.md` | Query strategies for large tables |
| `docs/discoveries.md` | Running log of insights (low-friction capture) |

## Project Structure

Each science project in `projects/` should have:
- `README.md`: Question being addressed, approach, key findings
- `notebooks/`: Analysis notebooks
- `data/`: Extracted/processed data (gitignore large files)

Current projects:
- `projects/ecotype_analysis/` - Environment vs phylogeny effects on gene content
- `projects/pangenome_openness/` - Open vs closed pangenome patterns

## Database Access

- **Database**: `kbase_ke_pangenome` on BERDL Delta Lakehouse
- **Auth**: Token in `.env` file (KB_AUTH_TOKEN)
- **API**: `https://hub.berdl.kbase.us/apis/mcp/`
- **Direct Spark**: Use JupyterHub for complex queries

Use `/berdl` skill for BERDL queries. Read `docs/pitfalls.md` before your first query.

## Key Reminders

1. Species IDs contain `--` which breaks SQL. Use `LIKE 'prefix%'` patterns.
2. Large tables (gene, genome_ani) need filters. Never full-scan.
3. AlphaEarth embeddings only cover 28% of genomes.
4. Gene clusters are species-specific. Can't compare across species.
5. Update docs when you learn something worth sharing!
