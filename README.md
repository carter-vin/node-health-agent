# node-health-agent

> Node-local health reporting agent with centralized triage tooling

This project focuses on operationally realistic system monitoring: deterministic outputs, structured logging, and opperator-friendly design/interfaces.

## Runtime

### Supported Runtime
- Python 3.11+
- Development: macOS supported (collectors degrade gracefully)
- Target deployment: Linux hosts

### Local Artifacts
- Spool (agent output): ./spool/node_reports.jsonl
- State (agent/triage state): ./state/
- Logs: structured JSON to stdout

### CLI Commands (Phase 0 placeholders)
- Print version and environment:
  - `node-health-agent version`
- Emit one report and exit:
  - `node-health-agent oneshot`
- Run continuous agent loop:
  - `node-health-agent run --interval 2`

### Log Event Contract (minimum)
- agent_start
- health_report_emitted
- collector_failed
- spool_write_failed
- agent_shutdown

### Report Schema
- schema_version: "1"
- UTC timestamps
- Deterministic JSON envelope

## Data Handling / Security Notes

- The agent writes runtime artifacts to `./spool/` and `./state/`. These directories are intentionally excluded from git.
- Reports may include host-identifying metadata (node_id, timestamps). Treat emitted reports as potentially sensitive in real environments.
- For simulations or deployments, set `NODE_AGENT_NODE_ID` to control node identity explicitly.
