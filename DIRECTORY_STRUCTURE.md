# Pangenome Science Project - Directory Structure

```
ke-pangenome-science/
│
├── PROJECT.md                          # Main project documentation
├── .env                                # Authentication token (KB_AUTH_TOKEN)
│
├── docs/                               # Shared knowledge base
│   ├── overview.md                     # Project goals & data workflow
│   ├── schema.md                       # Database table schemas
│   ├── pitfalls.md                     # SQL gotchas & common errors
│   ├── performance.md                  # Query optimization strategies
│   ├── discoveries.md                  # Running log of insights
│   └── research_ideas.md               # Future research directions & project ideas
│
├── data/                               # Shared data across projects
│   ├── pangenome_summary.csv           # Stats for all 27K species
│   ├── core_ogs_parts/                 # Core orthologous groups (100 parts)
│   ├── ecotypes/                       # Ecotype clustering data
│   │   ├── alphaearth_embeddings.csv
│   │   ├── genome_clusters_cog/        # COG annotations (20 parts)
│   │   └── within_species_ani/         # ANI matrices (10 parts)
│   └── ecotypes_expanded/              # Extended ecotype analysis
│       ├── target_genomes_expanded.csv
│       ├── embeddings_expanded.csv
│       ├── species_ecological_categories.csv
│       ├── gene_clusters_expanded/     # Gene cluster data (11 parts)
│       └── ani_expanded/               # ANI matrices (2 parts)
│
├── projects/                           # Individual science projects
│   │
│   ├── cog_analysis/                   # COG functional categories analysis
│   │   ├── README.md                   # Research question & approach
│   │   ├── notebooks/
│   │   │   ├── cog_analysis.ipynb                    # Main analysis (N. gonorrhoeae)
│   │   │   └── species_selection_exploration.ipynb   # Multi-species planning
│   │   └── data/
│   │       ├── cog_distributions.csv                 # Results from analysis
│   │       ├── cog_heatmap.png                       # Visualization
│   │       └── cog_enrichment.png                    # Enrichment plots
│   │
│   ├── ecotype_analysis/               # Environment vs phylogeny effects
│   │   ├── docs/
│   │   ├── notebooks/
│   │   │   ├── 01_data_extraction.ipynb
│   │   │   └── 02_ecotype_correlation_analysis.ipynb
│   │   ├── figures/
│   │   │   ├── ecotype_correlation_summary.png
│   │   │   ├── embedding_diversity_distribution.png
│   │   │   └── environmental_vs_host_comparison.png
│   │   └── scripts/
│   │
│   └── pangenome_openness/             # Open vs closed pangenome patterns
│       ├── docs/
│       ├── notebooks/
│       │   └── 01_explore_gene_data.ipynb
│       ├── data/
│       │   ├── pangenome_stats.csv
│       │   ├── pangenome_ecotype_merged.csv
│       │   └── species_selection_stats.csv
│       └── figures/
│           └── pangenome_vs_effects.png
│
├── exploratory/                        # Scratch work & exploratory analysis
│   ├── berdl_pangenome_exploration.ipynb
│   ├── gene_content_phylogeny_analysis.ipynb
│   ├── pangenome_scaling_laws_analysis.ipynb
│   ├── ecotype_expansion_analysis.ipynb
│   ├── data/                           # Exploratory data files
│   │   ├── phylo_distance_matrix*.npy
│   │   ├── jaccard_matrix*.npy
│   │   └── species_og_profiles.pkl
│   └── figure*.png/pdf                 # Exploratory figures
│
└── .claude/                            # Claude Code configuration
    ├── settings.local.json
    └── skills/
        └── berdl/
            └── SKILL.md                # BERDL query skill documentation
```

## Key Directory Purposes

### Root Level
- **PROJECT.md**: Main documentation explaining project structure and workflows
- **.env**: Authentication token for BERDL database access

### docs/
Shared knowledge base that grows with discoveries:
- Document SQL pitfalls, performance strategies, schema details
- Capture research ideas and future directions as they emerge
- Tag each entry with the project that discovered it (e.g., `[cog_analysis]`)

### data/
Shared extracts reusable across projects:
- Large datasets partitioned into chunks (e.g., `part_000.csv`, `part_001.csv`)
- If another project might need it, put it here
- Include genome metadata, species lists, pangenome stats

### projects/
Each subdirectory is a complete research project with:
- **README.md**: Research question, approach, findings
- **notebooks/**: Jupyter notebooks for analysis
- **data/**: Project-specific processed data
- **figures/**: Visualizations and plots
- Standard structure: docs/, notebooks/, data/, figures/, scripts/

### exploratory/
Scratch space for ad-hoc analysis:
- Experiments that haven't been formalized into projects
- Quick explorations and prototypes
- Gets messy, that's OK!

## Current Projects

| Project | Status | Description |
|---------|--------|-------------|
| **cog_analysis** | Active | COG functional category distributions across core/auxiliary/novel genes |
| **ecotype_analysis** | Active | Environment vs phylogeny effects on gene content |
| **pangenome_openness** | Active | Open vs closed pangenome patterns |

## Database Access

**Database**: `kbase_ke_pangenome` on BERDL Delta Lakehouse
- 293,059 genomes across 27,690 species
- Access via Spark SQL on JupyterHub
- Tables: genome, pangenome, gene_cluster, eggnog_mapper_annotations, etc.

## Workflow

1. **Start a new project**: Create `projects/new_project/` with README, notebooks/, data/
2. **Query database**: Use Spark SQL on JupyterHub (see PROJECT.md for examples)
3. **Document learnings**: Update `docs/` when you discover pitfalls or insights
4. **Save shared data**: If data is reusable, put in top-level `data/`
5. **Keep project data local**: Project-specific outputs go in `projects/*/data/`
