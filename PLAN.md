# node-health-agent — Current Plan

Last updated: 2026-03-06

## Current State

Recently completed:

1. `agent_start` emits `threshold_profile` and `thresholds_hash` in `oneshot` and `run`.
2. `run` supports `--max-iterations` with `0 = unlimited`.
3. Threshold configuration is surfaced in report metadata and documented in README.
4. Triage supports deterministic per-node summaries with rolling stats and trend labels.
5. Validation snapshot:
   - targeted tests: `26 passed`
   - full suite: `81 passed`

## Immediate Priorities

### 1) Reconcile contract and implementation drift

Goal:
Bring code, schemas, tests, and README back into exact alignment.

Scope:
- Verify `triage/render/explain.py` matches the current config-aware threshold design.
- Update `docs/contracts/event.schema.json` to reflect all emitted event fields that are part of the current contract.
- Update `docs/contracts/report.schema.json` to reflect all report fields currently emitted, including threshold metadata and any network fields if contract-relevant.
- Reconcile README examples and descriptions with actual emitted payloads and current CLI behavior.
- Add or adjust tests where current contract coverage is missing.

Done when:
- No known drift remains between runtime behavior, schemas, tests, and README.
- Current emitted fields are accurately represented in contract docs.
- Explain renderer behavior matches the documented threshold-config story.

---

### 2) Add fleet threshold mismatch detection

Goal:
Flag mixed threshold configurations across node summaries in fleet-level triage.

Scope:
- Add `--warn-mixed-thresholds` to `summarize-dir`.
- Detect multiple `thresholds_hash` values across emitted node summaries.
- Add deterministic warning output for human renderers (`text`, `pretty`, `table`, `explain`) when enabled.
- Add machine-readable mixed-threshold metadata to JSON output.
- Add tests for mixed and non-mixed fleet cases.

Done when:
- Fleet triage clearly indicates config drift when hashes differ.
- JSON output includes deterministic mixed-threshold metadata.
- Human-readable warnings appear only when appropriate and are stable.

---

### 3) Add startup-event contract validation

Goal:
Keep startup events and event schema in lockstep with stdlib-only validation tooling.

Scope:
- Extend existing validation tooling with optional event-line validation mode.
- Validate `agent_start` fields including:
  - `mode`
  - `threshold_profile`
  - `thresholds_hash`
  - optional `max_iterations`
- Add tests for valid and invalid startup event lines.

Done when:
- CI can validate both spool reports and startup events.
- Startup event validation remains stdlib-only and deterministic.

---

### 4) Tighten bounded run contract tests

Goal:
Fully lock down deterministic bounded-run behavior for automation and CI.

Scope:
- Add assertions for exact `agent_tick` counts under `--max-iterations N`.
- Add assertions for exact `agent_tick_metrics` counts under `--max-iterations N`.
- Add regression coverage confirming `max_iterations` is omitted when `0` through the real CLI path.
- Keep tests focused on contract-level behavior rather than implementation details.

Done when:
- Bounded run behavior is fully event-level contract tested.
- Unlimited mode behavior remains unchanged.

## Next Cleanup After Priorities

### 5) Reduce runtime orchestration duplication

Goal:
Improve maintainability without changing public behavior.

Scope:
- Extract shared collector/evaluation/report assembly path from `oneshot` and `run`.
- Reduce duplicated collector failure/event logic.
- Preserve current output contracts and test behavior exactly.
- Keep refactor scope narrow and non-architectural.

Done when:
- `agent/main.py` no longer contains large duplicated runtime blocks.
- Public behavior and tests remain unchanged.

## Guardrails

- Preserve deterministic outputs and stable CLI contracts unless a plan item explicitly changes them.
- Prefer minimal diffs and avoid unrelated refactors.
- Keep runtime dependencies unchanged.
- Add or update tests for every behavior change.
- Keep renderer output stable unless a plan item explicitly requires new output.