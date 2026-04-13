# Phase 5 Wiki Resume Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Phase 5 resume from partially staged wiki pages without regenerating already completed pages, including avoiding repeat LLM calls when cached page content exists.

**Architecture:** Persist each generated wiki page into a run-local cache under `data/ingest/runs/<run_id>/`. Store per-page completion state in the checkpoint so Phase 5 can rebuild the staging directory from cached pages and generate only missing pages on resume. Keep the existing phase-level checkpoint model intact and only extend the wiki phase payload.

**Tech Stack:** Python, pytest, rich progress, existing ingest checkpoint JSON.

---

### Task 1: Add wiki page cache helpers

**Files:**
- Modify: `observatory_context/ingest/pipeline.py`

**Step 1: Write the failing test**

Add a regression test that pre-populates a cached wiki page and a partial wiki checkpoint, then verifies a resumed Phase 5 run restores the cached page and does not call the LLM for it.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ingest_pipeline.py -k wiki_resume -v`
Expected: fail because Phase 5 does not yet use cached pages.

**Step 3: Write minimal implementation**

Add small helpers for:
- run directory resolution
- wiki cache path resolution
- restoring a cached page into the staging tree
- recording page completion in the checkpoint

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ingest_pipeline.py -k wiki_resume -v`
Expected: pass.

### Task 2: Wire Phase 5 resume into the pipeline

**Files:**
- Modify: `observatory_context/ingest/pipeline.py`

**Step 1: Write the failing test**

Extend the Phase 5 regression test to verify that a fully resumed run still uploads the rebuilt wiki batch and completes the phase count.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ingest_pipeline.py -k run_resumes -v`
Expected: fail until `run()` passes the checkpoint into Phase 5.

**Step 3: Write minimal implementation**

Update `run()` to pass the active checkpoint into `phase5_compile_wiki()`. Make `_mark_phase_completed()` and `_mark_run_failed()` preserve any nested wiki page state.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ingest_pipeline.py -k run_resumes -v`
Expected: pass.

### Task 3: Verify the full ingest path

**Files:**
- Modify: `tests/test_ingest_pipeline.py`

**Step 1: Write the failing test**

Add a focused test for a resumed Phase 5 run that skips one cached page and regenerates the rest.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ingest_pipeline.py -k phase5_resume -v`
Expected: fail before the cache-aware code is in place.

**Step 3: Write minimal implementation**

Confirm the test passes without changing the remaining ingest phases.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ingest_pipeline.py -k phase5_resume -v`
Expected: pass.

