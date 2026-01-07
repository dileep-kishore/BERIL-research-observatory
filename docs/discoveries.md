# Discoveries Log

Running log of insights discovered during science projects. Tag each with `[project_name]`.

Periodically refactor stable insights into the appropriate structured doc (schema.md, pitfalls.md, performance.md).

---

## 2026-01

### [ecotype_analysis] Environment vs Phylogeny: Phylogeny usually dominates

Analysis of 172 species with sufficient data showed:
- Median partial correlation for environment effect: 0.0025
- Median partial correlation for phylogeny effect: 0.0143
- Phylogeny dominates in 60.5% of species
- Environment dominates in 39.5% of species

No significant difference between "environmental" bacteria (where lat/lon is meaningful) and host-associated bacteria (p=0.66).

### [ecotype_analysis] ANI extraction requires per-species iteration

Attempting to query ANI for all 13K+ genomes in a single IN clause fails/times out. Must iterate over species and query ANI for each species separately. See `docs/performance.md` for pattern.

### [pangenome_openness] Pangenome table has pre-computed stats

The `pangenome` table already contains `no_core`, `no_aux_genome`, `no_singleton_gene_clusters`, `no_gene_clusters` - no need to compute from gene_cluster table.

### [pangenome_openness] No correlation between openness and env/phylo effects

Tested whether open pangenomes (low core fraction) show different patterns. Results:
- rho=-0.05, p=0.54 for environment effect
- rho=0.03, p=0.73 for phylogeny effect
- No significant relationship found

### [integrity_checks] 12 orphan pangenomes are symbionts

The 12 pangenomes without matching species clades are mostly obligate symbionts:
- Portiera aleyrodidarum (whitefly symbiont)
- Profftella armatura (psyllid symbiont)
- Various uncultivated lineages (UBA, TMED, SCGC prefixes)

These are valid pangenomes but filtered from species metadata due to single-genome status.

---

## Template

```markdown
### [project_name] Brief title

Description of what was discovered, why it matters, and any implications
for future analyses.
```
