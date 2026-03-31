---
name: discovery-capture
description: "Record a serendipitous finding or unexpected pattern as a discovery in the knowledge base. Use when analysis reveals something surprising, when a cross-project pattern emerges, or when the user says 'that's interesting', 'record this finding', or 'add this as a discovery'."
allowed-tools: Read, Write, Edit, Bash, AskUserQuestion
---

# Discovery Capture Protocol

This skill is not user-invocable. It is referenced by other skills (synthesize, interpret, compare) and should be followed whenever a noteworthy finding is encountered during analysis work.

## When to Trigger

Activate this protocol when any of the following occur:

1. **Unexpected data pattern** — analysis reveals a trend, outlier, or correlation not predicted by the hypothesis
2. **Cross-project insight** — a finding in one project connects to or contradicts findings from another
3. **Method finding** — a technique, parameter choice, or workflow step produces unexpectedly good (or bad) results
4. **Biological surprise** — organism behavior, gene function, or pathway activity differs from literature expectations
5. **Tool/infrastructure finding** — a BERDL quirk, performance characteristic, or data quality insight worth preserving

## Protocol Steps

### Step 1: Check for Duplicates

Search OpenViking for existing discoveries related to this finding:

```bash
uv run scripts/query_knowledge_unified.py discoveries "<brief description of finding>"
```

- **If already documented:** Tell the user: "This is a known discovery." Quote or summarize the existing entry. **Stop here.**
- **If not documented:** Proceed to Step 2.

### Step 2: Ask the User

Ask the user directly:

> "I noticed something interesting: **[brief description of what was found]**. Should I record this as a discovery in the knowledge base?"

Wait for the user's response.

- **If the user says no:** Acknowledge and continue with the original task.
- **If the user says yes:** Proceed to Step 3.

### Step 3: Draft the Entry

Write a draft discovery entry. The entry must include:

1. **A descriptive title**
2. **A category** — one of: Data Pattern, Cross-Project Insight, Method Finding, Biological Surprise, Tool/Infrastructure (or propose a new category)
3. **Project tag(s)** if discovered in a specific project context
4. **Brief explanation** of what was found and why it matters
5. **Evidence** — data reference, figure, notebook output, or specific numbers
6. **Implications** for future work or follow-up analysis

### Step 4: Present for Review

Show the user the drafted entry (title, category, explanation, evidence, implications).

Ask: "Here's the draft discovery. Does this look accurate? Should I add it to the knowledge base?"

Wait for approval. If the user wants changes, revise and re-present.

### Step 5: Write to OpenViking

On approval, create a slug from the title and add the discovery:

```bash
uv run scripts/query_knowledge_unified.py add-discovery "<slug>" --json '{
  "title": "<Descriptive Title>",
  "category": "<Category Name>",
  "project_ids": ["<project_id>"],
  "description": "<What was found and why it matters>",
  "evidence": "<Data reference or figure>",
  "implications": "<What this means for future work>",
  "tags": ["<relevant>", "<tags>"]
}'
```

The system will:
1. Rewrite the entry as clean, searchable markdown via the CBORG LLM
2. Auto-extract tags, related entities, and refine the category
3. Upload as a single markdown resource with proper frontmatter
4. Cross-link to related projects in the knowledge graph

After writing, confirm: "Discovery added to the knowledge base."

Then **resume the original task** — discovery capture should not derail the user's workflow.

## Important Notes

- **Don't interrupt flow unnecessarily.** If the finding is minor and tangential, note it mentally and ask about recording it at a natural pause point. The user's primary task always comes first.
- **One discovery at a time.** If multiple findings emerge, handle each separately.
- **Be specific.** Vague entries like "interesting pattern observed" are not useful. Include the exact finding, the exact data, the exact implication.
- **Include the project tag** when the discovery was made in a specific project context.
- **LLM enrichment is automatic.** Provide the raw facts — the enrichment pipeline formats them properly.

## Integration

- **Query backend**: `scripts/query_knowledge_unified.py` (requires OpenViking)
- **Write command**: `add-discovery` subcommand
- **Read command**: `discoveries` subcommand (also available via `/knowledge discoveries`)
- **Triggered by**: `/synthesize`, `/interpret`, `/compare`, or conversational context
- **Related skills**: `/pitfall-capture` (similar protocol for pitfalls), `/knowledge` (reading discoveries)
