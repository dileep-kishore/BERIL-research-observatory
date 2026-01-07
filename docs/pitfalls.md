# BERDL Database: Common Pitfalls & Gotchas

**Database**: `kbase_ke_pangenome`
**Purpose**: Quick reference for avoiding common issues when querying the pangenome database.

---

## SQL Syntax Issues

### The `--` Problem in Species IDs

Species clade IDs contain `--` which SQL interprets as a comment delimiter.

```sql
-- BAD: Everything after '--' is treated as a comment
SELECT * FROM kbase_ke_pangenome.genome
WHERE gtdb_species_clade_id = 's__Escherichia_coli--RS_GCF_000005845.2'

-- GOOD: Use LIKE pattern to avoid the issue
SELECT * FROM kbase_ke_pangenome.genome
WHERE gtdb_species_clade_id LIKE 's__Escherichia_coli%'

-- GOOD: Or escape in Python before building query
species_prefix = species_id.split('--')[0]
query = f"WHERE gtdb_species_clade_id LIKE '{species_prefix}%'"
```

### ID Format Reference

| ID Type | Format | Example |
|---------|--------|---------|
| `genome_id` | `RS_GCF_XXXXXXXXX.X` or `GB_GCA_XXXXXXXXX.X` | `RS_GCF_000005845.2` |
| `gtdb_species_clade_id` | `s__Genus_species--{representative_genome_id}` | `s__Escherichia_coli--RS_GCF_000005845.2` |
| `gene_cluster_id` | `{contig}_{number}` or `{prefix}_mmseqsCluster_{number}` | `NZ_CP095497.1_1766` |

---

## Data Sparsity Issues

### AlphaEarth Embeddings (28.4% coverage)

Only 83,227 of 293,059 genomes have environmental embeddings.

```sql
-- Check if a species has embeddings before relying on them
SELECT COUNT(DISTINCT ae.genome_id) as n_with_embeddings,
       COUNT(DISTINCT g.genome_id) as n_total
FROM kbase_ke_pangenome.genome g
LEFT JOIN kbase_ke_pangenome.alphaearth_embeddings_all_years ae
    ON g.genome_id = ae.genome_id
WHERE g.gtdb_species_clade_id LIKE 's__Klebsiella_pneumoniae%'
```

**Why sparse?**: Embeddings require valid lat/lon coordinates, which are often missing in NCBI metadata, especially for clinical isolates.

### NCBI Environment Metadata (EAV format)

The `ncbi_env` table uses Entity-Attribute-Value format - multiple rows per sample.

```sql
-- Get isolation source for a genome
SELECT content
FROM kbase_ke_pangenome.ncbi_env
WHERE accession = 'SAMN12345678'
  AND harmonized_name = 'isolation_source'

-- Pivot to get multiple attributes
SELECT accession,
       MAX(CASE WHEN harmonized_name = 'isolation_source' THEN content END) as isolation_source,
       MAX(CASE WHEN harmonized_name = 'geo_loc_name' THEN content END) as location
FROM kbase_ke_pangenome.ncbi_env
WHERE accession IN ('SAMN12345678', 'SAMN87654321')
GROUP BY accession
```

### Geographic Coordinates

`ncbi_lat_lon` in `gtdb_metadata` is often:
- NULL (most common)
- Malformed strings ("missing", "not collected")
- Low precision ("37.0 N 122.0 W")

---

## Foreign Key Gotchas

### Orphan Pangenomes (12 species)

12 pangenome records reference species clades not in `gtdb_species_clade`:

```
s__Portiera_aleyrodidarum--RS_GCF_000300075.1
s__Profftella_armatura--RS_GCF_000441555.1
s__Nanosynbacter_sp022828325--RS_GCF_022828325.1
... (mostly symbionts and single-genome species)
```

These are valid pangenomes but filtered from species metadata. Handle with LEFT JOIN.

### Annotation Table Join Key

`eggnog_mapper_annotations.query_name` joins to `gene_cluster.gene_cluster_id`, NOT to `gene.gene_id`:

```sql
-- CORRECT: Join on gene_cluster_id
SELECT gc.gene_cluster_id, e.COG_category, e.Description
FROM kbase_ke_pangenome.gene_cluster gc
LEFT JOIN kbase_ke_pangenome.eggnog_mapper_annotations e
    ON gc.gene_cluster_id = e.query_name
WHERE gc.gtdb_species_clade_id LIKE 's__Mycobacterium%'

-- WRONG: gene_id won't match
SELECT * FROM kbase_ke_pangenome.eggnog_mapper_annotations
WHERE query_name = 'some_gene_id'  -- This won't find anything
```

### Gene Clusters are Species-Specific

Gene cluster IDs are only meaningful within a species. You cannot compare cluster IDs across species:

```sql
-- This comparison is MEANINGLESS:
-- Cluster "X_123" in E. coli is unrelated to "X_123" in Salmonella

-- To compare gene content across species, use:
-- 1. COG categories from eggnog_mapper_annotations
-- 2. KEGG orthologs (KEGG_ko column)
-- 3. PFAM domains
```

---

## Data Interpretation Issues

### Core/Auxiliary/Singleton Definitions

In `gene_cluster` table:
- `is_core` = 1: Present in ≥95% of genomes
- `is_auxiliary` = 1: Present in <95% and >1 genome
- `is_singleton` = 1: Present in exactly 1 genome

**These are mutually exclusive** (only one flag is 1 per row).

**Important**: These are stored as integers (0/1), not booleans:
```sql
-- CORRECT
WHERE is_core = 1

-- May fail depending on SQL dialect
WHERE is_core = true
```

### Pangenome Table Count Interpretation

In `pangenome` table:
- `no_core` + `no_aux_genome` = `no_gene_clusters` (total clusters)
- `no_singleton_gene_clusters` ⊂ `no_aux_genome` (singletons are a subset of auxiliary)

```sql
-- Verify: core + aux = total
SELECT
    no_core + no_aux_genome as computed_total,
    no_gene_clusters as reported_total,
    no_singleton_gene_clusters as singletons,
    no_aux_genome as auxiliary
FROM kbase_ke_pangenome.pangenome
LIMIT 5
```

---

## Missing Tables

These tables are mentioned in project documentation but **do not exist** in the database:

| Table | Mentioned Purpose | Status |
|-------|-------------------|--------|
| `phylogenetic_tree` | Species trees from core genes | NOT FOUND |
| `phylogentic_tree_distance_pairs` | Pairwise phylo distances | NOT FOUND |
| `pangenome_build_protocol` | Build parameters | NOT FOUND (but `protocol_id` column exists) |
| `genomad_mobile_elements` | Plasmid/virus annotations | NOT FOUND |
| `IMG_env` | IMG environment metadata | NOT FOUND |

---

## API vs Direct Spark

### REST API Issues

The REST API at `https://hub.berdl.kbase.us/apis/mcp/` can fail with:

| Error | Meaning | Solution |
|-------|---------|----------|
| 504 Gateway Timeout | Query took too long | Simplify query, add filters |
| 503 "cannot schedule new futures after shutdown" | Spark executor restarting | Wait 30s, retry |
| Empty response | Query failed silently | Check query syntax |

### When to Use Direct Spark

Use direct `spark.sql()` on the cluster when:
- Query involves >1M rows
- JOINs across large tables
- Aggregations on billion-row tables
- REST API keeps timing out

```python
# On BERDL JupyterHub
result = spark.sql("""
    SELECT genome_id, COUNT(*) as n_genes
    FROM kbase_ke_pangenome.gene
    WHERE genome_id IN (...)
    GROUP BY genome_id
""").toPandas()
```

---

## Quick Checklist

Before running a query, verify:

- [ ] Species IDs don't contain raw `--` in WHERE clauses
- [ ] Large tables have appropriate filters (genome_id, species_id)
- [ ] JOIN keys are correct (gene_cluster_id for annotations)
- [ ] You're not comparing gene clusters across species
- [ ] Expected tables actually exist (check schema doc)
- [ ] Data coverage is sufficient for your analysis (especially embeddings)
