---
name: pitfall-capture
description: Detect and document pitfalls encountered during BERDL work. Invoked by other BERDL skills when errors, retries, or data surprises occur.
allowed-tools: Read, Write, Edit, Bash, AskUserQuestion
---

# Pitfall Capture Protocol

This skill is not user-invocable. It is referenced by BERDL skills (berdl, berdl-discover, hypothesis, submit) and should be followed whenever an issue is encountered during BERDL work.

## When to Trigger

Activate this protocol when any of the following occur:

1. **Query failure** — API returns an error (504, 524, 503, empty response) or SQL fails with a syntax/semantic error
2. **Incorrect results** — Data returned is wrong due to bad join key, string-vs-numeric comparison, wrong table, etc.
3. **Retry/correction cycle** — You had to substantially change your approach after an initial attempt failed
4. **Performance issue** — Query is unreasonably slow or causes OOM
5. **Data surprise** — Missing data, unexpected NULLs, coverage gaps, schema differs from documentation
6. **Environment issue** — Spark session problems, import errors, JupyterHub quirks

## Protocol Steps

### Step 1: Check for Duplicates

Search OpenViking for existing pitfalls related to this issue:

```bash
uv run scripts/query_knowledge_unified.py pitfalls "<brief description of issue>"
```

- **If already documented:** Tell the user: "This is a known pitfall." Quote or summarize the relevant guidance so the user can apply it immediately. **Stop here** — do not proceed to Step 2.
- **If not documented:** Proceed to Step 2.

### Step 2: Ask the User

Ask the user this question directly:

> "I ran into an issue: **[brief description of what went wrong]**. Do you think this could have been avoided if it were documented in the pitfalls guide? If so, I'll draft an entry for your review."

Wait for the user's response.

- **If the user says no** or indicates it's not worth documenting: Acknowledge and continue with the original task.
- **If the user says yes:** Proceed to Step 3.

### Step 3: Draft the Entry

Write a draft pitfall entry. The entry must include:

1. **A descriptive title**
2. **A category** — one of the existing categories (see below) or propose a new one
3. **A project tag** if the issue arose in a specific project context
4. **Brief explanation** of what the issue is and why it's a problem
5. **Code example** showing the wrong approach and the correct approach (SQL, Python, or shell as appropriate)
6. **Solution line** with actionable guidance

### Step 4: Determine Category

Assign one of these categories:

- **General BERDL Pitfalls** — REST API, auth, schema introspection, string-typed columns
- **Pangenome Pitfalls** — SQL syntax, ID formats, species-specific issues
- **Data Sparsity Issues** — Coverage gaps, EAV format, coordinate quality
- **Foreign Key Gotchas** — Orphan records, join key mismatches
- **Data Interpretation Issues** — Flag definitions, count relationships
- **JupyterHub Environment Issues** — Spark session, Java processes, CLI execution
- **Pandas-Specific Issues** — `.toPandas()`, NaN handling, type conversion
- **Fitness Browser Pitfalls** — String columns, case sensitivity, large tables
- **Genomes Pitfalls** — UUID identifiers, billion-row tables

If the issue doesn't fit any existing category, propose a new one.

### Step 5: Present for Review

Show the user the drafted entry (title, category, explanation, code example, solution).

Ask: "Here's the draft entry. Does this look accurate? Should I add it to the pitfalls knowledge base?"

Wait for approval. If the user wants changes, revise and re-present.

### Step 6: Write to OpenViking

On approval, create a slug from the title and add the pitfall:

```bash
uv run scripts/query_knowledge_unified.py add-pitfall "<slug>" --json '{
  "title": "<Descriptive Title>",
  "category": "<Category Name>",
  "project_ids": ["<project_id>"],
  "problem": "<Full explanation with code examples>",
  "solution": "<One-sentence actionable fix>",
  "tags": ["<relevant>", "<tags>"]
}'
```

After writing, confirm: "Pitfall added to the knowledge base."

Then **resume the original task** — pitfall capture should not derail the user's workflow.

## Important Notes

- **Don't interrupt flow unnecessarily.** If the issue is minor and you already know the fix, apply the fix first, then ask about documenting it. The user's primary task always comes first.
- **One pitfall at a time.** If multiple issues arise, handle each separately to avoid overwhelming the user.
- **Be specific.** Vague entries like "queries can be slow" are not useful. Include the exact table, the exact error, the exact fix.
- **Include the project tag** when the pitfall was discovered in the context of a specific project. This helps with traceability.
