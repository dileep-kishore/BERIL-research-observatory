---
name: suggest-research
description: "Review completed projects and their findings, then suggest a new high-impact research topic grounded in available BERDL data and scientific gaps. Use when the user wants to identify the next best research direction, asks 'what should I study next', 'where are the gaps', or 'what hasn't been explored'."
allowed-tools: Bash, Read, Write, Edit, WebSearch, AskUserQuestion
user-invocable: true
---

# Suggest Research Skill

Survey the research landscape — completed projects, their findings, proposed ideas, and available BERDL data — then synthesize a prioritized recommendation for the next research topic. The recommendation is grounded in what has been learned, what data is available, and where scientific impact is highest.

## Usage

```
/suggest-research
```

No arguments required. The skill reads the full project landscape automatically.

## Workflow

### Step 1: Read the Research Idea Backlog

Query OpenViking for existing research ideas:

```bash
uv run scripts/query_knowledge_unified.py ideas
uv run scripts/query_knowledge_unified.py ideas --status PROPOSED
uv run scripts/query_knowledge_unified.py ideas --status IN_PROGRESS
uv run scripts/query_knowledge_unified.py ideas --status COMPLETED
```

For each entry, note:
- **Status**: PROPOSED, IN_PROGRESS, or COMPLETED
- **Priority** and **Effort** tags
- **Research Question** and **Hypotheses**
- **Impact** and **Dependencies**

Build three lists:
1. `completed_ideas` — ideas with Status: COMPLETED
2. `in_progress_ideas` — ideas with Status: IN_PROGRESS
3. `proposed_ideas` — ideas with Status: PROPOSED (candidates for recommendation)

### Step 2: Read the Knowledge Graph

Run `uv run scripts/query_knowledge_unified.py browse viking://resources/observatory/knowledge-graph/entities/ --tier L1` to get entity coverage, and `uv run scripts/query_knowledge_unified.py recall "research pitfalls" --store patterns` for known pitfalls to avoid.

For each project, capture: `id`, `status`, `research_question`, `key_findings`, `tags`, `databases_used`, `depends_on`, `enables`, `references`.

Build lists: `finished_projects`, `in_progress_projects`, `proposed_projects`.

Cross-check against research ideas from Step 1.

### Step 3: Deep-Read Top-Relevant Projects

From the knowledge graph (or README scan), identify the 3-5 projects **most relevant** to emerging recommendation themes. For only those projects:

1. Read `projects/{id}/REPORT.md`
2. Extract:
   - **Key Findings** (the 2-4 headline results) — supplement the OpenViking summary with details
   - **Future Directions** section — these are investigator-suggested follow-ups
   - **Limitations** — gaps the authors identified
   - **Novel Contribution** — what made the project scientifically unique
3. Note any cross-project patterns: recurring organisms, pathways, themes, or data gaps
4. Use `references` field from OpenViking to identify literature themes cited across multiple projects

For remaining projects, the OpenViking summaries (key_findings, tags, databases_used) provide sufficient context without reading full reports.

### Step 4: Read the Discoveries Log

Query OpenViking for discoveries:

```bash
uv run scripts/query_knowledge_unified.py discoveries
```

Extract:
- Serendipitous findings not yet formalized into a project
- Patterns noted across multiple analyses
- Data anomalies flagged for follow-up

These often represent high-value starting points that are not yet in the research ideas backlog.

### Step 5: Understand Available Data

Read `docs/collections.md` to inventory the BERDL data collections. For each collection, note:
- Collection name and identifier
- What organism/scale/data type it covers
- Whether it has been heavily used (cross-reference with reports) or is underexplored

Identify **underexplored collections** — present in BERDL but rarely cited in completed project reports.

### Step 5b: Read Knowledge Graph Gaps (if available)

Run: `uv run scripts/query_knowledge_unified.py gaps`

This outputs the gap analysis covering organisms with sparse coverage,
method gaps, untested hypotheses, and unexplored entity pairs.
Use this output directly in Step 6 under "Entity gaps" and "Untested hypotheses".

Additionally, run `uv run scripts/query_knowledge_unified.py hypotheses rejected` for rejected hypotheses whose alternatives haven't been explored.

Also search for known pitfalls to avoid repeating past mistakes:

```bash
uv run scripts/query_knowledge_unified.py pitfalls
```

### Step 6: Synthesize the Landscape

Build an internal summary across Steps 1–5b:

| Dimension | Assessment |
|---|---|
| Completed topics | What themes have been thoroughly investigated? |
| Active topics | What is currently in progress (avoid duplicating)? |
| Proposed backlog | Which PROPOSED ideas have the strongest prerequisites now met? |
| Future directions | What did completed projects recommend as next steps? |
| Discovery log | What serendipitous patterns are unclaimed? |
| Underexplored data | Which BERDL collections have not been leveraged? |
| Recurring gaps | What limitation appears in multiple project reports? |
| Entity gaps | Which organisms/methods/concepts lack cross-project connections? |
| Untested hypotheses | Which proposed/testing hypotheses need validation? |

### Step 7: Ask the User for Priorities (Optional)

If the user did not specify a focus, ask:

> "I've reviewed the project landscape. To tailor my recommendation, a few quick questions:
> 1. Any preferred scientific theme? (e.g., evolution, metabolism, ecology, gene function)
> 2. Effort preference? (Low: 1–2 weeks / Medium: 1 month / High: multi-month)
> 3. Should the new topic extend an existing project or open a new direction entirely?"

If the user says "just suggest something," skip to Step 8 with no constraints.

### Step 8: Identify Top Candidates

From the synthesized landscape, identify 2–3 candidate topics. For each candidate, score it against:

| Criterion | Weight | Question |
|---|---|---|
| Scientific novelty | High | Is this genuinely new relative to completed work? |
| Data readiness | High | Is required BERDL data available and well-characterized? |
| Impact | High | Does it extend or challenge a significant existing finding? |
| Feasibility | Medium | Are dependencies met? Does similar methodology already exist in the repo? |
| Backlog alignment | Medium | Does it address a PROPOSED idea or Future Direction from a report? |
| Effort fit | Low | Is the scope appropriate for a focused project? |

Select the **top candidate** with the strongest combined score. Retain the runner-up as an alternative.

### Step 9: Search Literature for the Top Candidate

Invoke `/literature-review` (or search directly via `paper-search-mcp` tools) to answer:

1. Has this specific question been studied before? In which organisms/scales?
2. What methods were used and what were the results?
3. What remains unstudied or contested?
4. Are there contradictory findings that BERDL's scale could resolve?

Use this to sharpen the hypothesis and confirm novelty.

### Step 10: Present the Recommendation

Present a structured recommendation to the user:

```markdown
## Recommended Research Topic: {Title}

### Why Now?
{1–2 sentences: what completed work enables this, and why this is the right next step}

### Research Question
{The specific scientific question, one sentence}

### Hypotheses
- **H1**: {Primary hypothesis with direction}
- **H0**: {Null hypothesis}
- **H2** (optional): {Secondary exploratory hypothesis}

### Grounding in Completed Work
- Extends **{project_id}** (Finding: {key result from its REPORT.md})
- Addresses the limitation noted in **{project_id}**: "{limitation quote}"
- Uses methodology established in **{project_id}** (reuse notebooks/src/)

### Required BERDL Data
| Collection | Tables | What it provides |
|---|---|---|
| `{collection_id}` | `{table}` | {description} |

### Approach
1. {Step 1: data extraction query approach}
2. {Step 2: analysis method}
3. {Step 3: statistical test or model}
4. {Step 4: validation or comparison}

### Expected Impact
- {Scientific contribution 1}
- {Scientific contribution 2}
- {Connection to the broader BERIL mission}

### Literature Context
- Aligns with: {Author et al. Year} — {key point}
- Extends beyond: {Author et al. Year} — {what BERDL adds}
- Open question: {what the literature has not settled}

### Effort Estimate
**{Low / Medium / High}** — {brief rationale}

### Dependencies
- {Any prerequisite data, analysis, or completed project required}

---

### Alternative Topic: {Alt Title}
{2–3 sentence summary of the alternative and why it was ranked second}
```

### Step 11: Offer to Register and Start the Idea

After presenting the recommendation, ask:

> "Would you like me to register this as a research idea and start it as a new project?"

If yes:

1. **Add to OpenViking**: Create the research idea in the knowledge base:

```bash
uv run scripts/query_knowledge_unified.py add-idea "<slug>" --json '{
  "title": "<Title>",
  "status": "PROPOSED",
  "priority": "<HIGH/MEDIUM/LOW>",
  "effort": "<effort estimate>",
  "research_question": "<question>",
  "approach": ["Step 1", "Step 2", "Step 3"],
  "hypotheses": {"h1": "<hypothesis>", "h0": "<null hypothesis>"},
  "impact": "<impact statement>",
  "dependencies": ["<dep1>", "<dep2>"],
  "tags": ["<tag1>", "<tag2>"]
}'
```

2. **Start the project**: Invoke `/berdl_start` to scaffold and begin the new project, using the confirmed research idea (title, research question, hypotheses, approach, and data sources from Step 10) as the starting context for ideation.

If no, leave no changes.

## Integration

- **Reads from**: OpenViking (via `scripts/query_knowledge_unified.py`) — research ideas, discoveries, pitfalls, knowledge graph, projects; `docs/collections.md`; `projects/*/REPORT.md` (top 3-5 only)
- **Calls**: `/literature-review` (Step 9, for novelty check on top candidate); `/berdl_start` (Step 11, if user confirms the idea)
- **Optionally writes**: OpenViking research idea (via `add-idea` subcommand)
- **Consumed by**: `/literature-review`, `/synthesize`

## Pitfall Detection

When you encounter errors, unexpected results, retry cycles, performance issues, or data surprises during this task, follow the pitfall-capture protocol in `.claude/skills/pitfall-capture/SKILL.md`.
