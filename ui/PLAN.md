# Collaborative Research UI for BERDL Data Lakehouse Platform

## Vision

Build a web application that showcases the KBase BERDL data lakehouse and collaborative research findings, starting with the pangenome analysis prototype. The platform enables contributors, collaborators, and the public to discover what's been analyzed, understand the data sources, and explore shared knowledge.

---

## Architecture Overview

**Type:** Web application with FastAPI backend + Jinja2 templates + vanilla JS frontend
**Deployment:** Docker container with Nginx reverse proxy
**Data Source:** Git repository file system (read-only, no database migration)
**Update Strategy:** CI/CD pipeline rebuilds cache on git push

---

## Information Architecture

### 1. Home Page - Research Dashboard
**Purpose:** Entry point showing platform overview and latest activity

**Components:**
- **Hero stats**: Database scale (293K genomes, 27K species, 1B+ genes), 3 active projects, 12 discoveries, 25+ research ideas
- **Featured discoveries**: Latest 3 findings with project tags and statistics
- **Active projects grid**: 3 project cards with thumbnails, research questions, status
- **Quick links**: Browse Projects, Explore Data, View Knowledge Base, Research Ideas

---

### 2. Projects Section

#### 2.1 Projects List (`/projects`)
**Purpose:** Browse all analysis projects

**Components:**
- **Project cards** with:
  - Title, status badge (Completed, In Progress)
  - Research question (truncated to 150 chars)
  - Key findings preview
  - 4 visualization thumbnails
  - Metadata: # notebooks, # figures, last updated date
  - "View Project" button
- **Filters**: Status, phylum, data source

#### 2.2 Project Detail (`/projects/{project_id}`)
**Purpose:** Deep dive into specific analysis

**Sections:**
1. **Overview**
   - Research question
   - Hypothesis
   - Status and metadata (contributors, dates, data sources)

2. **Findings**
   - Key results with statistics
   - Biological interpretation
   - Links to related discoveries

3. **Methodology**
   - Approach summary
   - Data sources (BERDL tables used)
   - Notebooks list with links

4. **Visualizations**
   - Gallery view with lightbox
   - Each viz shows: title, description, file size

5. **Data Products**
   - Table of CSV/data files with:
     - Filename, description, size, download link
     - Sample rows (first 5)

6. **Related Research**
   - Cross-project dependencies
   - Research ideas that build on this work

**Example:** `/projects/cog_analysis`
- Shows: Universal functional partitioning findings
- Stats: 32 species, 9 phyla, 357,623 genes analyzed
- Visualizations: 9 PNG files (heatmaps, enrichment plots)
- Data: `cog_enrichment_summary.csv`, `sampled_species_for_cog_analysis.csv`

---

### 3. Data Catalog Section

#### 3.1 Database Overview (`/data`)
**Purpose:** Introduce the BERDL kbase_ke_pangenome data lakehouse

**Components:**
- **Database description**: What is this data? (GTDB r214, 27K species, pangenome workflow)
- **Data workflow diagram**: Genome selection → ANI → Gene clustering → Annotation
- **Scale indicators**: 293,059 genomes, 421M ANI pairs, 100M gene families
- **Access methods**: Spark SQL, REST API, JupyterHub
- **Known limitations**: Embedding coverage 28.4%, sparse env metadata, missing tables

#### 3.2 Schema Browser (`/data/schema`)
**Purpose:** Explore database tables and columns

**Layout:**
- **Left sidebar**: Searchable table list
  - Each table shows: name, row count
  - Size categories: HUGE (1B+), LARGE (100M+), Medium, Small
  - Highlighting for selected table

- **Main content**: Table detail view
  - Table name, description
  - Stats: row count, column count
  - Known limitations (warning alerts for sparsity)
  - Columns table: name, type, description, PK/FK indicators
  - Sample queries (syntax-highlighted SQL)
  - Foreign key relationships diagram

**Example:** `/data/schema?table=gene_cluster`
- Shows: 132M rows, 11 columns
- Limitation: "Gene clusters are species-specific - cannot compare across species"
- FK: `gtdb_species_clade_id` → `gtdb_species_clade`

#### 3.3 Query Patterns (`/data/patterns`)
**Purpose:** Teach efficient querying

**Sections:**
- **Query patterns by use case**:
  - Per-species iteration (for >100 species)
  - IN clause for 10-100 species (5x faster example)
  - Chunked genome queries
  - Pagination with ORDER BY

- **Table-specific strategies**:
  - genome_ani: Always filter by species
  - gene: Never full-scan
  - eggnog_mapper_annotations: Joins to gene_cluster_id

- **Batch size recommendations table**

- **Anti-patterns to avoid**:
  - Large IN clauses (>10K items)
  - Cross-species gene JOINs
  - Collecting before filtering

---

### 4. Knowledge Base Section

#### 4.1 Discoveries Timeline (`/knowledge/discoveries`)
**Purpose:** Chronicle research findings in chronological order

**Components:**
- **Timeline view** with:
  - Date markers (2026-01, 2025-12, etc.)
  - Discovery cards showing:
    - Title (e.g., "Universal functional partitioning in bacterial pangenomes")
    - Project tag badge ([cog_analysis], [ecotype_analysis])
    - Content (markdown rendered)
    - Statistics chips (e.g., "L enrichment: +10.88%", "100% consistency")
  - Filter by project tag
  - Search discoveries

**Example discovery:**
```
[cog_analysis] Universal functional partitioning
Date: 2026-01-13
- Core genes enriched in: J (-4.65%), F (-2.09%), H (-2.06%)
- Novel genes enriched in: L (+10.88%), V (+2.83%)
- Analyzed: 32 species, 9 phyla, 357,623 genes
Interpretation: HGT is primary innovation mechanism
```

#### 4.2 Pitfalls & Gotchas (`/knowledge/pitfalls`)
**Purpose:** Document common issues to avoid

**Categories:**
- SQL Syntax Issues
- Data Sparsity Issues
- Foreign Key Gotchas
- Data Interpretation Issues
- Pandas-Specific Issues

**Each pitfall shows:**
- Problem description
- Why it happens
- Solution with code example
- Which project discovered it

#### 4.3 Performance Guide (`/knowledge/performance`)
**Purpose:** Query optimization strategies

**Sections:**
- Table size reference
- Query patterns with benchmarks
- Batch size recommendations
- Anti-patterns

#### 4.4 Research Ideas Board (`/knowledge/ideas`)
**Purpose:** Track proposed, in-progress, and completed research

**Kanban layout:**
- 3 columns: Proposed | In Progress | Completed
- Each idea card shows:
  - Title
  - Research question (truncated)
  - Priority badge (HIGH, MEDIUM, LOW)
  - Effort estimate
  - Impact estimate
  - Dependencies indicator
  - Cross-project tags

**Interactive features:**
- Filter by priority, effort, project tag
- Click card to expand details:
  - Full research question
  - Hypothesis
  - Approach
  - Dependencies list
  - Next steps

**Dependency graph visualization** (D3.js):
- Nodes: Projects (green), Research ideas (blue)
- Links: Dependencies
- Hoverable for details

---

### 5. About Section

#### 5.1 About the Project (`/about`)
**Content:**
- Project purpose: Dual goals (Science + Knowledge capture)
- Team profiles (once multiple contributors exist)
- Data workflow overview
- How to contribute
- Contact information

#### 5.2 Getting Started (`/about/getting-started`)
**Content:**
- BERDL access setup (auth token, JupyterHub)
- Repository structure tour
- Starting a new project
- Documentation workflow
- JupyterHub workflow guide

---

## Data Model

### Core Entities

```python
# app/models.py

@dataclass
class Project:
    id: str                          # e.g., "cog_analysis"
    title: str
    research_question: str
    hypothesis: Optional[str]
    approach: str
    status: str                      # "Completed", "In Progress", "Proposed"
    findings: str
    notebooks: List[Notebook]
    visualizations: List[Visualization]
    data_files: List[DataFile]
    created_date: datetime
    updated_date: datetime
    contributors: List[str]
    related_discoveries: List[str]   # Discovery IDs
    related_ideas: List[str]         # Research idea IDs

@dataclass
class Discovery:
    id: str
    title: str
    content: str                     # Markdown
    project_tag: str                 # e.g., "[cog_analysis]"
    date: datetime
    statistics: Dict[str, Any]       # Parsed from content
    related_projects: List[str]

@dataclass
class Table:
    name: str
    description: str
    row_count: int
    columns: List[Column]
    known_limitations: List[str]
    sample_queries: List[str]
    foreign_keys: List[ForeignKey]

@dataclass
class ResearchIdea:
    id: str
    title: str
    research_question: str
    status: str                      # "PROPOSED", "IN_PROGRESS", "COMPLETED"
    priority: str                    # "HIGH", "MEDIUM", "LOW"
    effort: str                      # e.g., "Low (1 week)"
    impact: str                      # e.g., "High"
    dependencies: List[str]          # Project/idea IDs
    next_steps: List[str]
    cross_project_tags: List[str]
```

---

## Backend Architecture

### FastAPI Application Structure

**Location:** `ui/` subdirectory within the research repository

```
ke-pangenome-science/              # Existing research repo (root)
├── projects/                      # Research projects (existing)
├── docs/                          # Knowledge docs (existing)
├── data/                          # Shared data (existing)
├── exploratory/                   # Exploratory work (existing)
├── PROJECT.md                     # Main docs (existing)
├── .gitignore                     # Existing
└── ui/                            # NEW: Web UI application
    ├── app/
    │   ├── __init__.py
    │   ├── main.py                # FastAPI app entry point
    │   ├── config.py              # Configuration (repo path = "../")
    │   ├── models.py              # Data models
    │   ├── parser.py              # Repository parser (reads from ../)
    │   ├── search.py              # Whoosh search service
    │   ├── cache.py               # Caching layer
    │   ├── routes/
    │   │   ├── __init__.py
    │   │   ├── home.py           # Home page
    │   │   ├── projects.py       # Projects routes
    │   │   ├── data.py           # Data catalog routes
    │   │   ├── knowledge.py      # Knowledge base routes
    │   │   └── about.py          # About/docs routes
    │   ├── templates/
    │   │   ├── base.html         # Base template with nav
    │   │   ├── home.html
    │   │   ├── projects/
    │   │   │   ├── list.html
    │   │   │   └── detail.html
    │   │   ├── data/
    │   │   │   ├── overview.html
    │   │   │   ├── schema.html
    │   │   │   └── patterns.html
    │   │   ├── knowledge/
    │   │   │   ├── discoveries.html
    │   │   │   ├── pitfalls.html
    │   │   │   ├── performance.html
    │   │   │   └── ideas.html
    │   │   └── about/
    │   │       ├── about.html
    │   │       └── getting-started.html
    │   └── static/
    │       ├── css/
    │       │   ├── main.css      # Core styles
    │       │   ├── components.css # Reusable components
    │       │   └── pages.css     # Page-specific styles
    │       ├── js/
    │       │   ├── search.js
    │       │   ├── dependency-graph.js  # D3.js visualization
    │       │   └── lightbox.js   # PhotoSwipe integration
    │       └── images/
    │           └── logo.svg
    ├── data/                      # UI-specific data (cache, search index)
    │   ├── cache.json            # Parsed repository cache
    │   └── indexdir/             # Whoosh search index
    ├── requirements.txt
    ├── Dockerfile
    ├── docker-compose.yml
    └── README.md                  # UI setup and deployment guide
```

**Key Points:**
- UI code lives in `ui/` subdirectory of research repo
- Parser reads content from parent directory: `../projects/`, `../docs/`, `../data/`
- Static assets (visualizations) served directly from `../projects/*/data/`
- UI-specific data (cache, search index) stays in `ui/data/`

### Repository Parser (`app/parser.py`)

```python
class RepositoryParser:
    """Parse git repository file system into structured data"""

    def __init__(self, repo_path: str = ".."):
        """
        Initialize parser.

        Args:
            repo_path: Path to repository root. Default "../" since UI code
                      lives in ui/ subdirectory of the research repo.
        """
        self.repo_path = Path(repo_path).resolve()

    def parse_all(self) -> Dict[str, Any]:
        """Parse entire repository"""
        return {
            'projects': self.parse_projects(),
            'discoveries': self.parse_discoveries(),
            'tables': self.parse_schema(),
            'pitfalls': self.parse_pitfalls(),
            'performance_tips': self.parse_performance(),
            'research_ideas': self.parse_ideas(),
            'stats': self.calculate_stats()
        }

    def parse_projects(self) -> List[Project]:
        """Parse all projects from projects/ directory"""
        projects = []
        projects_dir = self.repo_path / 'projects'

        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue

            project = self._parse_project_dir(project_dir)
            projects.append(project)

        return projects

    def _parse_project_dir(self, project_dir: Path) -> Project:
        """Parse single project directory"""
        readme_path = project_dir / 'README.md'
        readme_content = readme_path.read_text()

        # Extract sections using regex or markdown parser
        research_question = self._extract_section(readme_content, 'Research Question')
        hypothesis = self._extract_section(readme_content, 'Hypothesis')
        findings = self._extract_section(readme_content, 'Key Findings')

        # Parse notebooks
        notebooks = self._parse_notebooks(project_dir / 'notebooks')

        # Parse visualizations
        visualizations = self._parse_visualizations(project_dir / 'data')

        # Get git metadata
        created_date = self._get_first_commit_date(project_dir)
        updated_date = self._get_last_commit_date(project_dir)

        return Project(
            id=project_dir.name,
            title=self._extract_title(readme_content),
            research_question=research_question,
            hypothesis=hypothesis,
            findings=findings,
            notebooks=notebooks,
            visualizations=visualizations,
            created_date=created_date,
            updated_date=updated_date,
            # ... other fields
        )

    def parse_discoveries(self) -> List[Discovery]:
        """Parse discoveries from docs/discoveries.md"""
        discoveries_path = self.repo_path / 'docs' / 'discoveries.md'
        content = discoveries_path.read_text()

        # Split by ### headers
        sections = re.split(r'\n### ', content)
        discoveries = []

        for section in sections[1:]:  # Skip intro
            # Extract title, project tag, date, content
            lines = section.split('\n')
            title_line = lines[0]

            # Parse [project_tag] from title
            match = re.match(r'\[(\w+)\] (.+)', title_line)
            if match:
                project_tag = match.group(1)
                title = match.group(2)

                discovery = Discovery(
                    id=self._generate_id(title),
                    title=title,
                    project_tag=project_tag,
                    content='\n'.join(lines[1:]),
                    # ... parse statistics from content
                )
                discoveries.append(discovery)

        return discoveries

    def parse_schema(self) -> List[Table]:
        """Parse tables from docs/schema.md"""
        schema_path = self.repo_path / 'docs' / 'schema.md'
        content = schema_path.read_text()

        # Parse markdown tables and sections
        # Extract table names, row counts, column definitions
        # Build Table objects with Column children

        return tables

    def parse_ideas(self) -> List[ResearchIdea]:
        """Parse research ideas from docs/research_ideas.md"""
        ideas_path = self.repo_path / 'docs' / 'research_ideas.md'
        content = ideas_path.read_text()

        # Parse markdown headers and extract:
        # - Status from section (High Priority / Medium Priority / etc.)
        # - Title, research question, hypothesis
        # - Dependencies, next steps

        return ideas
```

### Caching Strategy

```python
# app/cache.py

class RepositoryCache:
    """Cache parsed repository data with invalidation"""

    def __init__(self, repo_path: str, cache_path: str):
        self.repo_path = Path(repo_path)
        self.cache_path = Path(cache_path)
        self.parser = RepositoryParser(repo_path)
        self._cache = None
        self._last_modified = None

    def get_data(self) -> Dict[str, Any]:
        """Get cached data or rebuild if stale"""
        current_modified = self._get_repo_last_modified()

        if self._cache is None or current_modified > self._last_modified:
            # Cache miss or stale - rebuild
            self._cache = self.parser.parse_all()
            self._last_modified = current_modified
            self._save_cache()

        return self._cache

    def _get_repo_last_modified(self) -> datetime:
        """Get latest modification time from git"""
        # Use GitPython to get last commit timestamp
        repo = git.Repo(self.repo_path)
        return datetime.fromtimestamp(repo.head.commit.committed_date)

    def _save_cache(self):
        """Persist cache to disk"""
        with open(self.cache_path, 'w') as f:
            json.dump(self._cache, f, default=str)

    def invalidate(self):
        """Force cache rebuild on next request"""
        self._cache = None
        if self.cache_path.exists():
            self.cache_path.unlink()
```

### Search Service

```python
# app/search.py

from whoosh.index import create_in, open_dir
from whoosh.fields import Schema, TEXT, ID, KEYWORD
from whoosh.qparser import MultifieldParser

class SearchService:
    """Full-text search using Whoosh"""

    schema = Schema(
        id=ID(stored=True),
        type=ID(stored=True),          # "project", "discovery", "idea", "pitfall"
        title=TEXT(stored=True),
        content=TEXT(stored=True),
        project_tag=KEYWORD(stored=True),
        url=ID(stored=True)
    )

    def __init__(self, index_dir: str, cache: RepositoryCache):
        self.index_dir = Path(index_dir)
        self.cache = cache
        self.index = None

    def build_index(self):
        """Build search index from cached data"""
        if not self.index_dir.exists():
            self.index_dir.mkdir(parents=True)

        # Create or open index
        self.index = create_in(self.index_dir, self.schema)

        writer = self.index.writer()
        data = self.cache.get_data()

        # Index projects
        for project in data['projects']:
            writer.add_document(
                id=project.id,
                type='project',
                title=project.title,
                content=f"{project.research_question} {project.findings}",
                url=f"/projects/{project.id}"
            )

        # Index discoveries
        for discovery in data['discoveries']:
            writer.add_document(
                id=discovery.id,
                type='discovery',
                title=discovery.title,
                content=discovery.content,
                project_tag=discovery.project_tag,
                url=f"/knowledge/discoveries#{discovery.id}"
            )

        # Index research ideas
        for idea in data['research_ideas']:
            writer.add_document(
                id=idea.id,
                type='idea',
                title=idea.title,
                content=idea.research_question,
                url=f"/knowledge/ideas#{idea.id}"
            )

        writer.commit()

    def search(self, query_str: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search across all indexed content"""
        if not self.index:
            self.index = open_dir(self.index_dir)

        parser = MultifieldParser(['title', 'content'], schema=self.schema)
        query = parser.parse(query_str)

        with self.index.searcher() as searcher:
            results = searcher.search(query, limit=limit)

            return [
                {
                    'id': hit['id'],
                    'type': hit['type'],
                    'title': hit['title'],
                    'snippet': hit.highlights('content', top=1),
                    'project_tag': hit.get('project_tag'),
                    'url': hit['url']
                }
                for hit in results
            ]
```

---

## Frontend Design

### Academic Theme Styling

```css
/* static/css/main.css */

:root {
  /* Typography */
  --font-serif: 'IBM Plex Serif', Georgia, serif;
  --font-sans: 'IBM Plex Sans', -apple-system, system-ui, sans-serif;
  --font-mono: 'IBM Plex Mono', 'Courier New', monospace;

  /* Colors - Academic palette */
  --gray-50: #fafafa;
  --gray-100: #f5f5f5;
  --gray-200: #eeeeee;
  --gray-300: #e0e0e0;
  --gray-700: #616161;
  --gray-900: #212121;

  --primary: #00897b;     /* Teal - scientific, trustworthy */
  --secondary: #5e35b1;   /* Deep purple - academic */
  --accent: #ff6f00;      /* Orange - highlights */

  /* Status colors */
  --status-completed: #388e3c;
  --status-in-progress: #1976d2;
  --status-proposed: #757575;

  /* Priority colors */
  --priority-high: #d32f2f;
  --priority-medium: #f57c00;
  --priority-low: #388e3c;

  /* Spacing */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;
  --space-16: 64px;
}

body {
  font-family: var(--font-serif);
  font-size: 18px;
  line-height: 1.7;
  color: var(--gray-900);
  background: var(--gray-50);
  margin: 0;
  padding: 0;
}

h1, h2, h3, h4, h5, h6 {
  font-family: var(--font-sans);
  font-weight: 600;
  line-height: 1.3;
  margin-top: var(--space-8);
  margin-bottom: var(--space-4);
}

h1 { font-size: 2.5rem; }
h2 { font-size: 2rem; }
h3 { font-size: 1.5rem; }

code {
  font-family: var(--font-mono);
  font-size: 0.9em;
  background: var(--gray-100);
  padding: 2px 6px;
  border-radius: 3px;
}

pre code {
  display: block;
  padding: var(--space-4);
  background: var(--gray-900);
  color: #f8f8f2;
  overflow-x: auto;
}
```

---

## Implementation Roadmap

### Phase 1: MVP (2-3 weeks)

**Week 1:**
- Set up FastAPI project structure
- Implement RepositoryParser for projects, discoveries, schema
- Build basic caching mechanism
- Create base template with navigation

**Week 2:**
- Build routes for Home, Projects List, Project Detail
- Implement Data Catalog overview and schema browser
- Add markdown rendering with syntax highlighting
- Create project card and discovery timeline components

**Week 3:**
- Complete Knowledge Base pages (discoveries, pitfalls, performance)
- Add search functionality (Whoosh integration)
- Responsive CSS styling (mobile-first)
- Static asset serving for visualizations

**Deliverable:** Functional read-only platform with all content browsable

### Phase 2: Enhanced Discovery (1-2 weeks)

**Week 4:**
- Research ideas Kanban board
- Dependency graph visualization (D3.js)
- Image lightbox for visualizations
- Advanced search with filters

**Week 5:**
- Cross-reference links between content
- Project timeline view
- Contributor attribution
- Print-friendly layouts

**Deliverable:** Rich discovery experience with interconnected content

### Phase 3: Production Deployment (1 week)

**Week 6:**
- Docker containerization
- Nginx reverse proxy configuration
- CI/CD pipeline setup
- SSL/HTTPS configuration
- Performance optimization (thumbnails, lazy loading, compression)

**Deliverable:** Production-ready deployment with automatic updates

---

## Success Metrics

**Technical:**
- All 3 projects browsable with complete metadata
- 12 discoveries displayed in timeline
- 14 database tables with schemas accessible
- Search returns results in <500ms
- Pages load in <2 seconds
- Mobile responsive (works on tablets/phones)

**User Experience:**
- New visitors can understand "what's been analyzed" in <1 minute
- Contributors can find their discoveries easily
- Data engineers can access schema and query patterns
- Research ideas are discoverable and filterable

**Extensibility:**
- Adding new project requires only README + notebook files (no code changes)
- Adding new BERDL data store requires only config change
- Cache invalidation works automatically on git push

---

## Technology Stack

**Backend:**
- FastAPI 0.109.0 (web framework)
- Uvicorn (ASGI server)
- Jinja2 (templates)
- python-markdown (markdown → HTML)
- Whoosh 2.7.4 (search)
- GitPython 3.1.40 (git metadata)
- Pillow 10.2.0 (thumbnails)

**Frontend:**
- Vanilla JavaScript (no framework)
- D3.js v7 (dependency graphs)
- PhotoSwipe 5 (image lightbox)
- Prism.js (code highlighting)
- Feather Icons (SVG icons)
- IBM Plex fonts (Serif, Sans, Mono)

**Infrastructure:**
- Docker + Docker Compose
- Nginx (reverse proxy, static files)
- GitHub Actions or GitLab CI (CI/CD)

---

## Critical Implementation Files

**To Read:**
- `/Users/paramvirdehal/KBase/ke-pangenome-science/docs/schema.md` - Database schema source
- `/Users/paramvirdehal/KBase/ke-pangenome-science/docs/discoveries.md` - Discoveries timeline content
- `/Users/paramvirdehal/KBase/ke-pangenome-science/docs/research_ideas.md` - Research ideas board content
- `/Users/paramvirdehal/KBase/ke-pangenome-science/projects/cog_analysis/README.md` - Project structure template
- `/Users/paramvirdehal/KBase/ke-pangenome-science/DIRECTORY_STRUCTURE.md` - Repository organization guide

**To Create:**
- `ui/app/main.py` - FastAPI application entry
- `ui/app/parser.py` - Repository file system parser (reads from `../`)
- `ui/app/cache.py` - Caching layer
- `ui/app/search.py` - Whoosh search service
- `ui/app/routes/` - Route handlers (projects, data, knowledge, about)
- `ui/app/templates/` - Jinja2 HTML templates
- `ui/app/static/` - CSS, JavaScript, images
- `ui/Dockerfile` - Container definition
- `ui/docker-compose.yml` - Service orchestration
- `ui/README.md` - UI setup and deployment instructions

**To Update:**
- `.gitignore` - Add `ui/data/cache.json`, `ui/data/indexdir/` to ignore generated UI data

---

## Verification Plan

**End-to-End Testing:**

1. **Browse Projects:**
   - Navigate to /projects
   - See 3 project cards (cog_analysis, ecotype_analysis, pangenome_openness)
   - Click "View Project" on cog_analysis
   - Verify research question, findings, 9 visualizations displayed
   - Click visualization thumbnail → lightbox opens full-size image

2. **Explore Data Catalog:**
   - Navigate to /data
   - See database overview with 293,059 genomes stat
   - Click "Browse Schema"
   - Search for "gene_cluster" table
   - Verify 132M rows shown, columns table populated
   - See known limitation warning about species-specific clusters

3. **Search Functionality:**
   - Enter "mobile elements" in search box
   - See COG analysis project and L enrichment discovery
   - Click discovery result → jump to discoveries timeline

4. **Knowledge Base:**
   - Navigate to /knowledge/discoveries
   - See timeline with 12 discoveries
   - Filter by "[cog_analysis]" tag → see 2 discoveries
   - Navigate to /knowledge/ideas
   - See Kanban board with 25+ ideas across columns
   - Click HIGH priority idea → expand details

5. **Mobile Responsive:**
   - Open site on 375px width device
   - Verify navigation collapses to hamburger menu
   - Verify project cards stack vertically
   - Verify schema browser sidebar converts to accordion

**Performance Testing:**
- Home page loads in <2s (check network waterfall)
- Search responds in <500ms (measure via browser DevTools)
- Visualization gallery loads progressively (lazy loading works)
- Cache invalidation works (modify discoveries.md, rebuild, see update)

---

## Future Enhancements (Post-MVP)

**Phase 4: Query Builder** (if demand exists)
- Simple SQL query constructor
- Preview first 100 rows
- Download results as CSV
- Query history

**Phase 5: User Authentication** (for contributors)
- Login via GitHub OAuth
- Track individual contributions
- Notification when others cite your work
- Personal dashboard

**Phase 6: Computational Notebooks** (integration)
- Render Jupyter notebooks inline (nbconvert)
- Link to JupyterHub "Run This Notebook"
- Version comparison for notebook diffs

**Phase 7: Multi-Store Federation**
- Add metagenome data store
- Add metabolomics data store
- Unified search across stores
- Cross-store research ideas

---

## Questions for User Before Implementation

None - ready to proceed with implementation based on current requirements.
