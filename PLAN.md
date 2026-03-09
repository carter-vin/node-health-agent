# node-health-agent — Refactor & Cleanup Plan

Last updated: 2026-03-06

This branch performs a focused internal cleanup of the project after the latest feature work.

Goal:
Improve code clarity, maintainability, and structure while **preserving existing behavior and contracts**.

This work intentionally **does not introduce new features**. It removes duplication, simplifies architecture, and reduces project bloat.

---

# Branch Scope

Branch name:

refactor/runtime-and-triage-cleanup

Rules:

- No new dependencies.
- No CLI behavior changes.
- No contract/schema changes unless necessary for correctness.
- Preserve deterministic output ordering.
- Preserve existing tests and public interfaces.
- Prefer minimal, targeted diffs.

---

# Phase 0 — Baseline and Guardrails

Goal:
Establish a stable baseline before any refactor work.

Tasks:

- Run full test suite.
- Ensure lint passes.
- Record baseline test count and timing.

Commands:

pytest -q
ruff check .

Done when:

- Full suite passes.
- No lint errors.
- Branch created from clean main.

---

# Phase 1 — Runtime Pipeline Extraction

Goal:
Reduce complexity and duplication in `agent/main.py`.

Current problem:

`agent/main.py` mixes:

- CLI parsing
- runtime control flow
- collector orchestration
- failure classification
- health evaluation
- report building
- spool emission
- event emission
- tick loop logic

Target design:

Move runtime logic into dedicated helpers.

New internal modules may include:

agent/runtime_collect.py  
agent/runtime_pipeline.py  
agent/runtime_emit.py  
agent/runtime_failures.py

Responsibilities:

runtime_collect
- execute collectors
- measure durations
- normalize outcomes

runtime_failures
- convert collector failures into events and reasons
- enforce identity special-case logic

runtime_pipeline
- evaluate health
- build report model
- assemble signals and meta

runtime_emit
- emit reports
- handle spool rotation
- emit report events

Done when:

- `agent/main.py` is primarily CLI wiring and loop control.
- Runtime logic exists in dedicated helpers.
- Tests pass unchanged.

---

# Phase 2 — Eliminate Oneshot/Run Duplication

Goal:
Ensure both CLI modes share the same runtime pipeline.

Current issue:

`oneshot` and `run` duplicate:

- collector invocation
- failure handling
- reason construction
- report assembly
- emission logic

Target design:

Shared runtime path:

collect signals  
→ normalize failures  
→ evaluate health  
→ build report  
→ emit report  

Mode-specific logic remains only for:

oneshot
- fatal identity failure

run
- loop timing
- bounded iteration logic
- tick events

Done when:

- Shared runtime helpers power both commands.
- Runtime code duplication removed.

---

# Phase 3 — Triage Architecture Cleanup

Goal:
Clarify boundaries between CLI, summarization, and rendering.

Problems:

- Filtering logic lives partially in CLI layer.
- Fleet metadata derived ad-hoc.
- Renderers infer too much.

Cleanup tasks:

1. Move filtering logic out of CLI into summarization helpers.

2. Introduce explicit fleet metadata builder.

Example responsibilities:

fleet_meta
- node counts
- health counts
- mixed threshold detection
- report totals
- file statistics

3. Standardize renderer input contract.

Renderers should receive:

- node summaries
- fleet metadata
- warning flags

Renderers should only format output.

Done when:

- CLI handles arguments only.
- summarization handles analysis.
- renderers handle formatting.

---

# Phase 4 — Comment and Docstring Reduction

Goal:
Reduce narrative noise and improve readability.

Guidelines:

Keep comments that explain:

- why behavior exists
- platform-specific quirks
- contract guarantees
- operational reasoning

Remove comments that explain:

- obvious control flow
- trivial assignments
- basic Python behavior

Docstrings should:

- describe intent
- remain concise

Target areas:

agent/main.py  
agent/model.py  
agent/emit.py  
triage/cli.py  
triage/summarize.py  

Done when:

- code reads cleanly without excessive commentary.

---

# Phase 5 — Helper and Module Hygiene

Goal:
Improve naming consistency and module boundaries.

Tasks:

- standardize helper naming conventions
- reduce scattered helper functions
- clarify module responsibilities

Expected structure:

agent/

main.py — CLI entrypoint  
config.py — config loading  
model.py — report structures  
logging.py — structured events  
emit.py — spool writing  
runtime_* — runtime orchestration  
collectors/ — signal gathering  

triage/

cli.py — CLI interface  
read.py — spool reading  
summarize.py — summarization logic  
render/ — output formatting  

Done when:

- each module has a clear, narrow purpose.

---

# Phase 6 — Test Suite Cleanup

Goal:
Improve test organization and maintainability.

Tasks:

- group tests logically
- reduce redundant assertions
- clarify fixture purposes

Test categories may include:

contract tests  
CLI integration tests  
unit tests  
fixture scenario tests

Bounded run tests remain but may be isolated.

Done when:

- test structure is clearer and easier to navigate.

---

# Phase 7 — Documentation Alignment

Goal:
Ensure docs reflect the refactored architecture.

Tasks:

- update README architecture description
- verify examples match runtime behavior
- remove outdated references

Done when:

- documentation accurately describes the codebase.

---

# Success Criteria

The cleanup branch succeeds if:

- external behavior is unchanged
- tests pass
- runtime duplication reduced
- `agent/main.py` significantly smaller
- renderer logic simplified
- code readability improved
- unnecessary comments removed