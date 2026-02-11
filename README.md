# node-health-agent

Node-local system health reporting agent with centralized triage support.

This project is designed around **operational realism** rather than ad-hoc monitoring:
- Deterministic, machine-readable outputs
- Structured logging suitable for aggregation
- Operator-friendly behavior and interfaces
- Graceful degradation across environments

The agent runs locally on each host, collects health signals, and emits standardized reports that can be triaged centrally or inspected locally.

---

## Runtime & Environment

### Supported Runtimes
- **Python**: 3.11+
- **Development**: macOS (collectors degrade gracefully where unsupported)
- **Target deployment**: Linux hosts

The agent is intentionally conservative in its runtime assumptions to support predictable behavior across heterogeneous fleets.

---

## Local Artifacts & Output

The agent produces the following local artifacts at runtime:

- **Spool (agent output)**  
  `./spool/node_reports.jsonl`  
  Append-only JSON Lines file containing emitted health reports.

- **State (agent / triage state)**  
  `./state/`  
  Local state used for agent coordination and future triage tooling.

- **Logs**  
  Structured JSON events emitted to `stdout` for easy ingestion by log collectors.

All runtime directories are expected to be ephemeral and environment-specific.

---

## Command-Line Interface

> **Note:** CLI commands below represent Phase 0 placeholders and may evolve.

### Available Commands

- **Print version and environment information**

```bash
node-health-agent version
```

**Emit a single health report and exit**

```bash
node-health-agent oneshot
```

Print the report JSON to stdout (debug only):

```bash
node-health-agent oneshot --print-report
```

* **Run the continuous agent loop**

```bash
node-health-agent run --interval 2
```

  Emits health reports at a fixed interval (in seconds).

Optional spool rotation flags:

```bash
node-health-agent run --spool-max-bytes 1048576 --spool-rotate-count 3
```

Report JSON is not printed to stdout unless you opt in with `--print-report`.

---

## Logging & Event Contract

The agent emits structured JSON log events with a minimal, stable event vocabulary.

### Required Event Types

* `agent_start`
* `agent_tick`
* `health_report_emitted`
* `collector_failed`
* `spool_write_failed`
* `spool_rotated`
* `agent_shutdown`

These events are intended to be:

* Machine-parsable
* Stable across versions
* Suitable for centralized aggregation and alerting

`agent_tick` includes per-loop timing fields:

* `interval_s`
* `tick_elapsed_ms`
* `collect_elapsed_ms`
* `build_elapsed_ms` (only when a report is emitted)
* `emit_elapsed_ms` (only when a report is emitted)
* `sleep_ms`
* `overrun`
* `reports_emitted`
* `seq` (only when a report is emitted)
* `node_id` (only when identity is available)
* `skip_emit` (only when emission is skipped)

`agent_start` includes optional spool rotation fields:

* `spool_max_bytes`
* `spool_rotate_count`

### IO Contract

* `stdout`: structured JSON events only
* `spool`: report JSONL only

To print report JSON to stdout, use `--print-report` explicitly.

---

## Health Report Format

Each emitted health report follows a deterministic JSON envelope.

### Report Characteristics

* `schema_version`: `"1"`
* UTC timestamps only
* Deterministic field ordering where applicable
* Append-only emission (no in-place mutation)

The schema is intentionally conservative to support long-term compatibility and offline analysis.

### Signals (current)

* `heartbeat_ok`
* `loadavg_1m`, `loadavg_5m`, `loadavg_15m`
* `cpu_count_logical`
* `mem_total_bytes`, `mem_available_bytes`
* `disk_total_bytes`, `disk_used_bytes`, `disk_free_bytes`

Signals from failed collectors are omitted to avoid type ambiguity.

---

## Data Handling & Security Considerations

* Runtime artifacts are written to `./spool/` and `./state/` and are intentionally **excluded from version control**.
* Health reports may include host-identifying metadata (e.g., `node_id`, timestamps).
* In real environments, treat emitted reports as **potentially sensitive operational data**.

### Node Identity

To explicitly control node identity (e.g., in simulations or testing), set:

```bash
NODE_AGENT_NODE_ID=<explicit-node-id>
```

This avoids accidental coupling to hostnames or transient identifiers.

### Test Hooks

These environment variables are test-only hooks used in CI and local validation:

```bash
NODE_AGENT_FAIL_HEARTBEAT=1
NODE_AGENT_FAIL_IDENTITY=1
NODE_AGENT_DEBUG_SLEEP_MS=1500
```

---

## Triage (local CLI)

The triage tool reads the spool and produces deterministic summaries per node:

```bash
node-health-triage tail --spool spool/node_reports.jsonl --n 50
node-health-triage summarize --spool spool/node_reports.jsonl --tail 200
```

Text output (per node) is stable and operator-friendly:

```
nodes_seen_tail: 2
nodes_emitted: 2

node_id: node-a
current_boot_id: boot-1
latest_health: OK
latest_seq: 3
latest_emitted_at: 2026-01-01T00:00:04+00:00
degraded_count_tail: 1 / 3
unhealthy_count_tail: 0 / 3
top_reasons_tail: collector_failed:cpu:1, collector_failed:memory:1
current_reasons: none

node_id: node-b
current_boot_id: boot-2
latest_health: DEGRADED
latest_seq: 2
latest_emitted_at: 2026-01-01T00:00:03+00:00
degraded_count_tail: 2 / 2
unhealthy_count_tail: 0 / 2
top_reasons_tail: collector_failed:disk:2, collector_failed:cpu:1
current_reasons: collector_failed:cpu, collector_failed:disk
```

JSON output is available for machine consumption:

```bash
node-health-triage summarize --spool spool/node_reports.jsonl --tail 200 --format json
```

Example jq usage:

```bash
# Show only degraded nodes
node-health-triage summarize --spool spool/node_reports.jsonl --tail 200 --format json \
  | jq '.nodes[] | select(.current_health == "DEGRADED")'

# Sort by degraded_count_tail
node-health-triage summarize --spool spool/node_reports.jsonl --tail 200 --format json \
  | jq '.nodes | sort_by(.degraded_count_tail)'
```

Optional filters:

```bash
node-health-triage summarize --spool spool/node_reports.jsonl --node node-a
node-health-triage summarize --spool spool/node_reports.jsonl --top-k-reasons 3
node-health-triage summarize --spool spool/node_reports.jsonl --only-degraded
node-health-triage summarize --spool spool/node_reports.jsonl --only-unhealthy
node-health-triage summarize --spool spool/node_reports.jsonl --min-degraded-count 2
```

Directory mode (multiple spools):

```bash
node-health-triage summarize-dir --dir spool --glob "*.jsonl" --tail 200
```

Exit codes when health filters are used:

* `0`: no matching nodes
* `2`: degraded nodes exist
* `3`: unhealthy nodes exist

---

## Development

Install dev tools (tests + ruff):

```bash
pip install -e '.[dev]'
```

---

## Project Philosophy

This agent favors:

* Predictability over cleverness
* Explicit contracts over implicit behavior
* Failure visibility over silent degradation

It is intended to serve as a reliable building block for higher-level triage, alerting, and fleet-health tooling.


