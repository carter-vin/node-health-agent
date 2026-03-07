# node-health-agent — Development Plan

Last updated: 2026-03-06

## Current Status

Recently completed:

- threshold_profile and thresholds_hash emitted in agent_start
- bounded run mode via --max-iterations
- mixed-threshold detection in summarize-dir
- startup-event validation tooling
- network signal fields added to report schema
- deterministic contract test coverage expanded

Test status:
87 passed, 0 failed

---

# Immediate Next Work

## 1. Operator-Focused Triage Improvements

Goal:
Improve usability and clarity of fleet triage output.

Scope:

- Fleet health summary header
- Better explain renderer config awareness
- Optional change detection mode
- Improved watch-mode output

Done when:

- summarize-dir shows fleet summary
- explain output correctly reflects threshold config context
- change detection highlights health transitions
- watch mode displays fleet health summary

---

## 2. Demo Fixtures

Goal:
Improve project demonstration and testing coverage.

Scope:

Add deterministic fleet scenarios:

- healthy fleet
- degraded nodes
- mixed thresholds
- reboot scenario

Done when:

Fixtures support triage tests and README examples.

---

# Next Major Work (After Next Branch)

## Runtime Orchestration Cleanup

Goal:
Reduce duplication and simplify runtime control flow.

Scope:

- Extract shared runtime pipeline
- Reduce oneshot/run duplication
- Isolate collector execution and health evaluation
- Keep CLI behavior unchanged

Done when:

agent/main.py becomes a thin orchestration layer.

---

## Renderer / Summary Architecture Cleanup

Goal:
Simplify renderer and metadata handling.

Scope:

- tighten NodeSummary structure
- centralize warning/header logic
- simplify renderer interfaces

Done when:

renderers consume consistent summary metadata.

---

## Codebase Simplification

Goal:
Improve clarity and maintainability.

Scope:

- remove redundant comments
- tighten docstrings
- reduce helper duplication
- improve module boundaries

Done when:

code reads clearly with minimal narrative comments.

---

# Guardrails

- Preserve deterministic output ordering.
- Maintain CLI contracts unless explicitly planned.
- Avoid new dependencies.
- Prefer minimal, targeted diffs.