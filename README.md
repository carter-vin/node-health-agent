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

* **Run the continuous agent loop**

```bash
node-health-agent run --interval 2
```

  Emits health reports at a fixed interval (in seconds).

---

## Logging & Event Contract

The agent emits structured JSON log events with a minimal, stable event vocabulary.

### Required Event Types

* `agent_start`
* `health_report_emitted`
* `collector_failed`
* `spool_write_failed`
* `agent_shutdown`

These events are intended to be:

* Machine-parsable
* Stable across versions
* Suitable for centralized aggregation and alerting

---

## Health Report Format

Each emitted health report follows a deterministic JSON envelope.

### Report Characteristics

* `schema_version`: `"1"`
* UTC timestamps only
* Deterministic field ordering where applicable
* Append-only emission (no in-place mutation)

The schema is intentionally conservative to support long-term compatibility and offline analysis.

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

---

## Project Philosophy

This agent favors:

* Predictability over cleverness
* Explicit contracts over implicit behavior
* Failure visibility over silent degradation

It is intended to serve as a reliable building block for higher-level triage, alerting, and fleet-health tooling.


