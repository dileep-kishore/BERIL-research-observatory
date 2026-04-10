# Observatory Knowledge Layer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a shared synthesis-backed observatory knowledge layer that exports both OpenViking-native `knowledge-graph/` resources and integrated wiki pages from the same cross-project model.

**Architecture:** Keep NetworkX as the canonical internal graph artifact, add a deterministic synthesis layer on top of registry plus graph state, then export two compiled views: `knowledge-graph/` for OpenViking retrieval and `wiki/` for navigation. The unified query script stays the runtime entry point; the ingest pipeline becomes responsible for synthesis, dual export, and relation materialization.

**Tech Stack:** Python 3.12, Pydantic, PyYAML, NetworkX, OpenViking, pytest, uv

---

### Task 1: Add synthesis models and deterministic aggregation

**Files:**
- Create: `observatory_context/graph/knowledge_synthesis.py`
- Modify: `observatory_context/graph/__init__.py`
- Test: `tests/test_knowledge_synthesis.py`

**Step 1: Write the failing tests**

Add tests that build a small graph plus registry fixtures and assert that the
synthesis bundle:

- rolls up entities across projects
- computes related entities from `RELATED_TO`
- attaches hypotheses and community metadata
- creates topic and timeline outputs

**Step 2: Run test to verify it fails**

Run: `uv run --with pytest pytest tests/test_knowledge_synthesis.py -q`
Expected: FAIL because `knowledge_synthesis.py` and its models do not exist.

**Step 3: Write minimal implementation**

Implement:

- synthesis data models
- `KnowledgeSynthesizer`
- helpers to gather findings, hypotheses, projects, related entities,
  communities, topics, and timeline events
- deterministic ordering for stable exports and tests

**Step 4: Run test to verify it passes**

Run: `uv run --with pytest pytest tests/test_knowledge_synthesis.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_knowledge_synthesis.py observatory_context/graph/knowledge_synthesis.py observatory_context/graph/__init__.py
git commit -m "feat: add knowledge synthesis layer"
```

### Task 2: Export synthesized data into `knowledge-graph/`

**Files:**
- Create: `observatory_context/graph/knowledge_graph_export.py`
- Modify: `observatory_context/client.py`
- Modify: `observatory_context/uris.py`
- Test: `tests/test_knowledge_graph_export.py`

**Step 1: Write the failing tests**

Add tests that verify the exporter:

- stages `.abstract.md`, `.overview.md`, and YAML files into the expected
  `knowledge-graph/` hierarchy
- writes timeline output
- generates relation calls from graph edges

**Step 2: Run test to verify it fails**

Run: `uv run --with pytest pytest tests/test_knowledge_graph_export.py -q`
Expected: FAIL because the exporter does not exist.

**Step 3: Write minimal implementation**

Implement:

- `KnowledgeGraphExporter`
- entity, hypothesis, and timeline staging
- OpenViking relation materialization from `RELATED_TO`
- any missing URI helpers needed by the exporter

Also fix dependency loading if the main code path imports `networkx`
unconditionally.

**Step 4: Run test to verify it passes**

Run: `uv run --with pytest pytest tests/test_knowledge_graph_export.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_knowledge_graph_export.py observatory_context/graph/knowledge_graph_export.py observatory_context/client.py observatory_context/uris.py pyproject.toml
git commit -m "feat: export synthesized knowledge graph"
```

### Task 3: Refactor wiki compilation to use synthesized inputs

**Files:**
- Modify: `observatory_context/wiki/compiler.py`
- Test: `tests/test_wiki_compiler_synthesis.py`

**Step 1: Write the failing tests**

Add tests that feed synthesized entity/topic/hypothesis objects into the wiki
compiler and assert that:

- related entities are graph-derived
- topic pages reflect cross-project synthesis
- wiki output remains linked and deterministic

**Step 2: Run test to verify it fails**

Run: `uv run --with pytest pytest tests/test_wiki_compiler_synthesis.py -q`
Expected: FAIL because the compiler still expects raw findings/hypotheses only.

**Step 3: Write minimal implementation**

Add synthesis-based compiler entry points or adapt the current compiler to
accept synthesized structures without duplicating aggregation logic.

**Step 4: Run test to verify it passes**

Run: `uv run --with pytest pytest tests/test_wiki_compiler_synthesis.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_wiki_compiler_synthesis.py observatory_context/wiki/compiler.py
git commit -m "refactor: compile wiki from synthesized knowledge"
```

### Task 4: Insert synthesis and dual export into the ingest pipeline

**Files:**
- Modify: `observatory_context/ingest/pipeline.py`
- Modify: `scripts/viking_ingest.py`
- Test: `tests/test_ingest_pipeline_knowledge_layer.py`

**Step 1: Write the failing tests**

Add pipeline tests that verify:

- the pipeline builds synthesis before export
- `knowledge-graph/` export runs before wiki compilation
- phase result counts include knowledge-graph output
- incremental-friendly helpers return deterministic affected outputs

**Step 2: Run test to verify it fails**

Run: `uv run --with pytest pytest tests/test_ingest_pipeline_knowledge_layer.py -q`
Expected: FAIL because the pipeline still jumps from graph build to raw wiki
compilation.

**Step 3: Write minimal implementation**

Refactor the pipeline to:

- load staged entries once
- build the synthesis bundle
- export `knowledge-graph/`
- compile wiki from synthesized objects
- keep the existing ingest entry point working

If needed, add CLI flags for targeted export modes but avoid feature creep.

**Step 4: Run test to verify it passes**

Run: `uv run --with pytest pytest tests/test_ingest_pipeline_knowledge_layer.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_ingest_pipeline_knowledge_layer.py observatory_context/ingest/pipeline.py scripts/viking_ingest.py
git commit -m "feat: add dual knowledge-layer export pipeline"
```

### Task 5: Verify query compatibility and update docs

**Files:**
- Modify: `docs/openviking_resource_model.md`
- Modify: `docs/openviking_tutorial.md`
- Test: `tests/test_query_knowledge_layer_integration.py`

**Step 1: Write the failing tests**

Add tests for the delivery/query path that verify populated `knowledge-graph/`
resources can be browsed and traversed by the existing query service.

**Step 2: Run test to verify it fails**

Run: `uv run --with pytest pytest tests/test_query_knowledge_layer_integration.py -q`
Expected: FAIL until the exported namespace and relations match delivery
expectations.

**Step 3: Write minimal implementation**

Adjust docs and any small compatibility shims needed so the existing query
surface works against the new exported namespace.

**Step 4: Run test to verify it passes**

Run: `uv run --with pytest pytest tests/test_query_knowledge_layer_integration.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_query_knowledge_layer_integration.py docs/openviking_resource_model.md docs/openviking_tutorial.md
git commit -m "docs: describe synthesized knowledge layer"
```
