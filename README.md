# node-health-agent

**Production-ready node-local health reporting agent with deterministic triage tools for fleet-wide operational visibility.**

A lightweight, zero-dependency health monitoring solution designed for systems engineering teams who need reliable signal aggregation, predictable failure observability, and operator-friendly analysis at scale.

## Features at a Glance

- **System Collectors:** CPU load, memory availability, disk space, heartbeat, identity
- **Signal-Based Health Evaluation:** Configurable thresholds with critical/degraded escalation
- **Self-Observability Metrics:** Per-loop timing, collector diagnostics, performance tracking
- **Spool Persistence:** Append-only JSONL with retention-based rotation
- **Triage Toolkit:** 5 output formats (text/pretty/table/explain/json) + fleet summarization
- **Exit Codes for Scripting:** Health filters with 0/2/3 codes for alert integration
- **Pure Python Implementation:** No external dependencies (stdlib + typer for CLI)
- **Deterministic Outputs:** Reproducible ordering suitable for testing and automation

## Quick Start

```bash
# Install with dev tools (tests, linting)
pip install -e '.[dev]'

# Run tests
pytest -v

# Emit a single health report
node-health-agent oneshot

# Print the report JSON (useful for debugging)
node-health-agent oneshot --print-report

# Run continuous agent loop at 2-second intervals
node-health-agent run --interval 2

# Analyze local spool
node-health-triage summarize --spool spool/node_reports.jsonl --format pretty

# Fleet analysis across multiple nodes
node-health-triage summarize-dir --dir spool --format table --only-degraded
```

---

## Architecture & Design

### Core Philosophy

This project prioritizes **operational realism** over feature maximalism:

- **Predictability over cleverness:** Deterministic signal extraction and ordering
- **Explicit contracts over implicit behavior:** Versioned event types and JSON schemas
- **Failure visibility over silent degradation:** Signal omission on collector failure prevents type ambiguity
- **Graceful degradation:** Collectors degrade per-platform; partial failures don't block health assessment

### System Architecture

```
┌─────────────────────────────────────────┐
│  node-health-agent (local to each host) │
├─────────────────────────────────────────┤
│  Agent Loop                             │
│  ├─ Collectors (CPU, memory, disk)      │
│  ├─ Health Evaluation (signals)         │
│  └─ Event Emission (stdout + spool)     │
├─────────────────────────────────────────┤
│  Local Artifacts                        │
│  ├─ spool/node_reports.jsonl (reports)  │
│  └─ state/ (seq, boot_id)               │
└─────────────────────────────────────────┘
                  │
                  │ (centralized analysis)
                  ▼
┌─────────────────────────────────────────┐
│  node-health-triage (operator tools)    │
├─────────────────────────────────────────┤
│  Spool Reader                           │
│  ├─ Single-node summarize               │
│  ├─ Multi-node summarize-dir            │
│  └─ Tail reader (bounded I/O)           │
├─────────────────────────────────────────┤
│  Renderer Registry (5 formats)          │
│  ├─ text (deterministic, script-safe)   │
│  ├─ pretty (human-readable blocks)      │
│  ├─ table (columnar, fleet at-a-glance) │
│  ├─ explain (narrative with thresholds) │
│  └─ json (machine-parseable)            │
├─────────────────────────────────────────┤
│  Filters & Exit Codes                   │
│  ├─ --only-degraded (exit 2)            │
│  ├─ --only-unhealthy (exit 3)           │
│  └─ --min-degraded-count (quantile)     │
└─────────────────────────────────────────┘
```

### Collector Design

Each collector is independently responsible for signal extraction and failure handling:

| Collector | Signals | Linux | macOS | Failure Behavior |
|-----------|---------|-------|-------|------------------|
| `heartbeat` | `heartbeat_ok` | ✅ | ✅ | Signal omitted |
| `identity` | `node_id`, `boot_id` | ✅ | ✅ | Random IDs generated |
| `cpu` | `loadavg_1m/5m/15m`, `cpu_count_logical` | ✅ | ✅ | Signal omitted |
| `memory` | `mem_total_bytes`, `mem_available_bytes` | ✅ | ✅ (degraded) | Signal omitted |
| `disk` | `disk_total/used/free_bytes` | ✅ | ✅ (degraded) | Signal omitted |

Failed collectors emit `collector_failed:<name>` reason tags but don't block report emission.

---

## Runtime & Environment

### Supported Runtimes

- **Python:** 3.11+
- **Development/Testing:** macOS (collectors degrade gracefully)
- **Production Target:** Linux hosts

### Installation

```bash
# Development (with pytest, ruff)
pip install -e '.[dev]'

# Production (minimal, no dev dependencies)
pip install -e .
```

The project has **zero external runtime dependencies** beyond Python standard library and Typer (CLI framework).

---

## Local Artifacts

The agent creates and manages the following local directories:

- **`./spool/`**: Append-only JSONL spool containing health reports  
  - Primary file: `node_reports.jsonl`
  - Rotation files: `node_reports.jsonl.0`, `.1`, `.2` (with `--spool-rotate-count`)
  - Used by triage CLI for analysis

- **`./state/`**: Agent coordination state  
  - `seq.json`: Report sequence number for idempotency
  - `boot_id`: System boot identifier for restart detection

Both directories are **excluded from version control** and should be treated as ephemeral runtime artifacts.

---

## Agent Command Reference

### `node-health-agent version`

Print version and runtime environment:

```bash
$ node-health-agent version
node-health-agent v0.1.0
python=3.14.2
os=Linux 5.15.0
machine=arm64
utc_now=2026-02-11T18:00:00.000000+00:00
```

### `node-health-agent oneshot`

Emit a single health report and exit. Events are written to stdout, report is written to spool.

```bash
# Basic usage
node-health-agent oneshot

# Print report JSON to stdout (useful for debugging)
node-health-agent oneshot --print-report

# Custom spool location
node-health-agent oneshot --spool-path /var/tmp/custom.jsonl
```

### `node-health-agent run`

Run the agent continuously in a loop, emitting reports at regular intervals:

```bash
# Default: 10-second interval, unlimited duration
node-health-agent run

# 2-second interval
node-health-agent run --interval 2

# Stop after N iterations
node-health-agent run --max-iterations 100

# Enable spool rotation
node-health-agent run \
  --spool-max-bytes 1048576 \
  --spool-rotate-count 5

# Custom spool path
node-health-agent run --spool-path /var/opt/agent/reports.jsonl
```

**Environment Variables:**

- `NODE_AGENT_NODE_ID`: Override node identity (useful for testing)
- `NODE_AGENT_FAIL_HEARTBEAT=1`: Force heartbeat failure (test hook)
- `NODE_AGENT_FAIL_IDENTITY=1`: Force identity failure (test hook)
- `NODE_AGENT_DEBUG_SLEEP_MS`: Inject custom sleep duration (test hook)

---

## Event & Logging Contract

The agent emits structured JSON events to `stdout` with a versioned, stable event vocabulary. All output is newline-delimited JSON suitable for log aggregation pipelines.

### Required Event Types

| Event | Frequency | Purpose |
|-------|-----------|---------|
| `agent_start` | Once, at startup | Agent initialization metadata |
| `agent_tick` | Every loop iteration | Per-tick timing and status |
| `agent_tick_metrics` | Every loop iteration | Collector performance diagnostics |
| `health_report_emitted` | When report emitted | Spool write confirmation |
| `collector_failed` | On collector error | Signal omission notification |
| `spool_write_failed` | On write error | Persistence failure alert |
| `spool_rotated` | On rotation | Old spool archival notification |
| `agent_shutdown` | At exit | Agent termination metadata |

### Event Examples

**agent_start**
```json
{
  "agent_version": "0.1.0",
  "event_type": "agent_start",
  "mode": "oneshot",
  "spool_path": "spool/node_reports.jsonl",
  "spool_max_bytes": null,
  "spool_rotate_count": 3,
  "utc_now": "2026-02-11T18:00:00.000000+00:00"
}
```

**agent_tick**
```json
{
  "agent_version": "0.1.0",
  "event_type": "agent_tick",
  "interval_s": 10,
  "tick_elapsed_ms": 45,
  "collect_elapsed_ms": 8,
  "build_elapsed_ms": 12,
  "emit_elapsed_ms": 15,
  "sleep_ms": 9955,
  "overrun": false,
  "reports_emitted": 1,
  "seq": 42,
  "node_id": "prod-web-01",
  "utc_now": "2026-02-11T18:00:15.000000+00:00"
}
```

**agent_tick_metrics** (self-observability)
```json
{
  "agent_version": "0.1.0",
  "event_type": "agent_tick_metrics",
  "tick_duration_ms": 32,
  "sleep_drift_ms": 3,
  "overrun": false,
  "collector_total_ms": 8,
  "slowest_collector_name": "disk",
  "slowest_collector_ms": 3,
  "utc_now": "2026-02-11T18:00:15.000000+00:00"
}
```

**health_report_emitted**
```json
{
  "agent_version": "0.1.0",
  "event_type": "health_report_emitted",
  "bytes": 487,
  "seq": 42,
  "spool_path": "spool/node_reports.jsonl",
  "mode": "oneshot",
  "utc_now": "2026-02-11T18:00:15.000000+00:00"
}
```

**agent_shutdown**
```json
{
  "agent_version": "0.1.0",
  "event_type": "agent_shutdown",
  "mode": "oneshot",
  "utc_now": "2026-02-11T18:00:16.000000+00:00"
}
```

### IO Contract

- **stdout:** Structured JSON events (one per line)
- **spool:** Health reports only (JSONL format)
- **stderr:** Warnings and errors (human-readable, for operators)

To inspect events in real-time:

```bash
node-health-agent run | jq -c 'select(.event_type == "agent_tick_metrics")'
```

---

## Health Report Schema

Each health report is a JSON object included in the spool JSONL file. Reports are append-only and immutable.

### Schema v1 Structure

```json
{
  "assessment": {
    "health": "OK|DEGRADED|UNHEALTHY",
    "reasons": ["string..."]
  },
  "identity": {
    "node_id": "string",
    "boot_id": "string"
  },
  "signals": {
    "heartbeat_ok": true,
    "loadavg_1m": 1.2,
    "loadavg_5m": 1.5,
    "loadavg_15m": 1.8,
    "cpu_count_logical": 8,
    "mem_total_bytes": 16777216,
    "mem_available_bytes": 8388608,
    "disk_total_bytes": 1099511627776,
    "disk_used_bytes": 549755813888,
    "disk_free_bytes": 549755813888
  },
  "meta": {
    "schema_version": "1",
    "agent_version": "0.1.0"
  },
  "timing": {
    "seq": 42,
    "emitted_at": "2026-02-11T18:00:15.000000+00:00"
  }
}
```

### Report Characteristics

- **schema_version:** `"1"` (stable, backward-compatible)
- **Field Ordering:** Deterministic for reproducibility and testing
- **Timestamps:** UTC only, RFC3339 format
- **Signal Omission:** Signals from failed collectors are omitted (type safety)
- **Immutability:** Reports are append-only; never modified in place

### Health Status Determination

Health is derived from signal thresholds and collector failures:

#### OK (all systems nominal)
- No collector failures
- No signal thresholds exceeded
- `heartbeat_ok == true`

#### DEGRADED (operational but degraded)
- Any `collector_failed:*` reason present, OR
- Non-critical signal thresholds exceeded (`signal:*_low` reasons)

#### UNHEALTHY (immediate action required)
- Critical signal thresholds exceeded (`signal:*_critical` reasons)

### Signal Thresholds & Reasons

| Signal | Threshold | Reason | Health |
|--------|-----------|--------|--------|
| **CPU load** | > cpu_count × 0.85 | `signal:cpu_high` | DEGRADED |
| **CPU load** | > cpu_count × 1.25 | `signal:cpu_critical` | UNHEALTHY |
| **Memory avail** | < 15% | `signal:mem_available_low` | DEGRADED |
| **Memory avail** | < 8% | `signal:mem_available_critical` | UNHEALTHY |
| **Disk free** | < 10% | `signal:disk_free_low` | DEGRADED |
| **Disk free** | < 5% | `signal:disk_free_critical` | UNHEALTHY |
| **Any collector** | Error | `collector_failed:<name>` | DEGRADED |

Thresholds are defined in `agent/evaluate.py` and can be tuned per-deployment.

### Example Reports

**Healthy System (OK)**
```json
{
  "assessment": {
    "health": "OK",
    "reasons": []
  },
  "signals": {
    "heartbeat_ok": true,
    "loadavg_1m": 0.8,
    "cpu_count_logical": 8,
    "mem_available_bytes": 12884901888,
    "mem_total_bytes": 16777216,
    "disk_free_bytes": 549755813888,
    "disk_total_bytes": 1099511627776
  }
}
```

**Degraded System (DEGRADED)**
```json
{
  "assessment": {
    "health": "DEGRADED",
    "reasons": ["collector_failed:heartbeat", "signal:mem_available_low"]
  },
  "signals": {
    "heartbeat_ok": null,
    "loadavg_1m": 1.2,
    "cpu_count_logical": 8,
    "mem_available_bytes": 2147483648,
    "mem_total_bytes": 16777216,
    "disk_free_bytes": 549755813888,
    "disk_total_bytes": 1099511627776
  }
}
```

**Critical System (UNHEALTHY)**
```json
{
  "assessment": {
    "health": "UNHEALTHY",
    "reasons": ["signal:cpu_critical", "signal:disk_free_critical"]
  },
  "signals": {
    "heartbeat_ok": true,
    "loadavg_1m": 10.5,
    "cpu_count_logical": 8,
    "mem_available_bytes": 4294967296,
    "mem_total_bytes": 16777216,
    "disk_free_bytes": 54975581388,
    "disk_total_bytes": 1099511627776
  }
}
```

---

## Data Handling & Security

### Privacy & Sensitivity

- Health reports include operational metadata (node_id, boot_id, timestamps) suitable for fleet analysis
- In production, treat emitted reports as **operationally sensitive data**
- Spool files should be protected with appropriate file permissions (e.g., `chmod 600`)
- Consider encrypting spools in transit to centralized aggregation systems

### Node Identity Control

By default, the agent uses system hostname. Override with environment variable:

```bash
# Explicit node identity (useful for testing or multi-node containers)
NODE_AGENT_NODE_ID=prod-web-01 node-health-agent oneshot

# Generate stable IDs in CI/testing
export NODE_AGENT_NODE_ID="test-node-$(date +%s)"
node-health-agent oneshot
```

### Boot ID Tracking

The agent tracks system boot ID to detect restarts. This allows operators to correlate health degradation with infrastructure events:

- Boot ID reset → Signal discontinuity
- Same Boot ID across reports → Continuous operation
- Boot ID mismatch → Possible clock skew or node replacement

---

## Development & Testing

### Setup

```bash
# Clone and install with dev dependencies
git clone <repo>
cd node-health-agent
pip install -e '.[dev]'
```

### Running Tests

```bash
# Run all tests with verbose output
pytest -v

# Run specific test file
pytest tests/test_evaluate_health.py -v

# Run tests matching pattern
pytest -k "degraded" -v

# Run with coverage (if coverage.py installed)
pytest --cov=agent --cov=triage
```

**Test Coverage:**
- Health evaluation thresholds and escalation logic
- Event contract payloads and fields
- Spool rotation behavior and file management
- Triage filtering and exit codes
- Multi-node aggregation
- Collector failure handling

### Code Quality

```bash
# Run linter
ruff check .

# Auto-fix lint issues
ruff check --fix .

# Format code
ruff format .
```

### Manual Testing

```bash
# Clean slate
rm -rf spool state

# Single report with output
node-health-agent oneshot --print-report | jq .

# Generate multiple reports
for i in {1..5}; do
  node-health-agent oneshot > /dev/null 2>&1
  sleep 0.5
done

# Analyze with different formats
node-health-triage summarize --spool spool/node_reports.jsonl --format pretty
node-health-triage summarize --spool spool/node_reports.jsonl --format table
node-health-triage summarize --spool spool/node_reports.jsonl --format json | jq .

# Test failure scenarios
NODE_AGENT_FAIL_HEARTBEAT=1 node-health-agent oneshot --print-report | jq '.assessment'

# Fleet simulation
mkdir fleet_spools
for node in web-01 web-02 db-01; do
  NODE_AGENT_NODE_ID=$node node-health-agent oneshot --spool-path fleet_spools/$node.jsonl
done

node-health-triage summarize-dir --dir fleet_spools --format table
node-health-triage summarize-dir --dir fleet_spools --only-degraded
```

### Project Structure

```
node-health-agent/
├── agent/                    # Agent core
│   ├── collectors/          # System signal collection
│   ├── emit.py              # Spool & event emission
│   ├── evaluate.py          # Health evaluation logic
│   ├── logging.py           # Event contract
│   ├── main.py              # Agent loop & CLI
│   ├── model.py             # Data models
│   └── state.py             # State coordination
│
├── triage/                  # Operator tooling
│   ├── cli.py               # Triage CLI commands
│   ├── read.py              # Spool file reader
│   ├── summarize.py         # Per-node aggregation
│   └── render/              # Output format renderers
│       ├── base.py          # Renderer base class
│       ├── json.py          # JSON renderer
│       ├── text.py          # Text renderer
│       ├── pretty.py        # Pretty block renderer
│       ├── table.py         # Table renderer
│       ├── explain.py       # Narrative renderer
│       └── utils.py         # Formatting utilities
│
├── tests/                   # Test suite
│   ├── test_*.py            # Unit & integration tests
│   └── fixtures/            # Test data
│
├── pyproject.toml           # Dependencies & metadata
└── README.md                # This file
```

---

## Triage CLI (`node-health-triage`)

The triage tool reads spool files and produces deterministic summaries for operator workflows. It supports local analysis of a single-node spool or fleet-wide analysis across multiple spools.

### Triage Commands

#### `tail` - Quick Spool Inspection

Read the last N reports and print statistics:

```bash
node-health-triage tail --spool spool/node_reports.jsonl --n 50
```

Output:
```
reports_parsed: 50
last_seq: 42
```

This command is useful for validating spool file integrity without full parsing overhead.

#### `summarize` - Single-Node Analysis

Aggregate reports from a single spool file per node:

```bash
# Default: text format, last 200 reports
node-health-triage summarize --spool spool/node_reports.jsonl

# Custom tail size
node-health-triage summarize --spool spool/node_reports.jsonl --tail 100
```

**Output (text format):**
```
nodes_seen_tail: 1
nodes_emitted: 1

node_id: prod-web-01
current_boot_id: 8cd1e68f-8f75-436e-853f-ad9cfd241327
latest_health: OK
latest_seq: 42
latest_emitted_at: 2026-02-11T18:00:15.000000+00:00
degraded_count_tail: 0 / 200
unhealthy_count_tail: 0 / 200
top_reasons_tail: none
current_reasons: none
```

#### `summarize-dir` - Multi-Node Fleet View

Aggregate reports from multiple spool files (one node per file):

```bash
# Analyze all .jsonl files in directory
node-health-triage summarize-dir --dir spool --glob "*.jsonl"

# With custom tail size
node-health-triage summarize-dir --dir fleet_spools --glob "node-*.jsonl" --tail 500

# Fleet-wide health check (table format)
node-health-triage summarize-dir --dir fleet_spools --format table
```

**Constraint:** Each spool file **must** contain reports for exactly one node_id. Multi-node spools are rejected with an error.

### Output Formats

All triage commands support multiple output formats via `--format`:

| Format | Use Case | Example Output |
|--------|----------|----------------|
| **text** (default) | Script parsing, logs | Deterministic key=value format |
| **pretty** | Operator dashboards | Readable blocks with units |
| **table** | Fleet at-a-glance | Columnar: NODE, HEALTH, CPU, DISK, etc. |
| **explain** | Escalation tools | Hierarchical narrative with thresholds |
| **json** | Integration APIs | Machine-parseable with complete data |

**Pretty Format Example:**
```
NODE prod-web-01
-----------------
Health: OK
Seq: 42   Boot: 8cd1e68f-...
Emitted: 2026-02-11T18:00:15.000000+00:00

CPU load (1m/5m/15m): 0.8 / 1.2 / 1.5
Disk free: 500 GB
Memory available: 12 GB

Degraded (tail): 0 / 200
Unhealthy (tail): 0 / 200
Top reasons: none
```

**Table Format Example:**
```
NODE           HEALTH    CPU1  MEM_FREE  DISK_FREE  DEG  UNH
prod-web-01    OK        0.8   12G       500G       0    0
prod-db-01     DEGRADED  2.1   4G        50G        15   0
prod-cache-01  UNHEALTHY 8.5   1G        10G        0    2
```

**JSON Format Example:**
```bash
node-health-triage summarize --spool spool/node_reports.jsonl --format json | jq .
```

Output:
```json
{
  "meta": {
    "computed_at": "2026-02-11T18:00:20.000000+00:00",
    "nodes_emitted": 1,
    "nodes_seen_tail": 1,
    "reports_invalid": 0,
    "reports_parsed": 200,
    "schema_version": "1",
    "spool_path": "spool/node_reports.jsonl",
    "tail_n": 200
  },
  "nodes": [
    {
      "current_boot_id": "8cd1e68f-...",
      "current_health": "OK",
      "current_reasons": [],
      "degraded_count_tail": 0,
      "latest_emitted_at": "2026-02-11T18:00:15.000000+00:00",
      "latest_seq": 42,
      "node_id": "prod-web-01",
      "reports_seen_tail": 200,
      "top_reasons_tail": [],
      "unhealthy_count_tail": 0
    }
  ]
}
```

### Filtering & Exit Codes

Triage supports operational filters that return meaningful exit codes for scripting:

```bash
# Filter to degraded nodes (exit 2 if found, 0 if none)
node-health-triage summarize --spool spool/node_reports.jsonl --only-degraded

# Filter to unhealthy nodes (exit 3 if found, 0 if none)
node-health-triage summarize --spool spool/node_reports.jsonl --only-unhealthy

# Advanced: nodes with at least 5 degraded reports in tail
node-health-triage summarize --spool spool/node_reports.jsonl --min-degraded-count 5

# Combine filters (AND logic)
node-health-triage summarize-dir --dir fleet --format table --only-degraded --min-degraded-count 3
```

**Exit Codes:**

| Code | Meaning |
|------|---------|
| 0 | No matching nodes found |
| 2 | Degraded nodes exist |
| 3 | Unhealthy nodes exist |

**Example - Alert Integration:**
```bash
#!/bin/bash
node-health-triage summarize-dir --dir fleet --only-unhealthy
case $? in
  0) echo "Fleet healthy" ;;
  2) echo "WARNING: Degraded nodes found" | mail ops@corp.com ;;
  3) echo "CRITICAL: Unhealthy nodes found" | mail ops@corp.com ; exit 1 ;;
esac
```

### Advanced Usage

**Interactive Multi-Line Analysis:**
```bash
node-health-triage summarize --spool spool/node_reports.jsonl \
  --format json \
  | jq '.nodes[] | select(.current_health == "DEGRADED")'
```

**Fleet-wide Health Summary:**
```bash
node-health-triage summarize-dir --dir fleet_spools \
  --format table \
  --only-degraded \
  | head -20
```

**Top K Reasons Across Fleet:**
```bash
node-health-triage summarize-dir --dir fleet_spools \
  --format json \
  --top-k-reasons 5 \
  | jq '.nodes[].top_reasons_tail'
```

**Specific Node Analysis:**
```bash
node-health-triage summarize \
  --spool spool/node_reports.jsonl \
  --node prod-web-01 \
  --format explain
```

---

## Operations & Deployment

### Production Checklist

Before deploying to production, ensure:

- [ ] Python 3.11+ available on all target hosts
- [ ] Disk space allocated for spool (recommend: `--spool-max-bytes 50MB`, rotation enabled)
- [ ] Log aggregation pipeline reads stdout (receives structured JSON events)
- [ ] Monitoring/alerting configured for exit codes (triage filters)
- [ ] Threshold tuning validated for your environment (CPU, memory, disk)
- [ ] Permissions: spool/state directories writable, readable by monitoring system
- [ ] Clock synchronization: Ensure NTP enabled for accurate UTC timestamps

### Deployment Patterns

**Systemd Service (Linux)**
```ini
[Unit]
Description=Node Health Agent
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -m agent.main run --interval 10
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
WorkingDirectory=/var/opt/node-health-agent

[Install]
WantedBy=multi-user.target
```

**Docker**
```dockerfile
FROM python:3.11-alpine
WORKDIR /app
COPY . .
RUN pip install -e .
ENTRYPOINT ["node-health-agent", "run", "--interval", "10"]
```

**Kubernetes DaemonSet**
```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-health-agent
spec:
  template:
    spec:
      containers:
      - name: agent
        image: node-health-agent:latest
        env:
        - name: NODE_AGENT_NODE_ID
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        volumeMounts:
        - name: spool
          mountPath: /spool
      volumes:
      - name: spool
        hostPath:
          path: /var/lib/node-health-agent/spool
```

### Log Aggregation Integration

**ELK Stack (Elasticsearch)**
```json
{
  "hosts": ["log-collector:9200"],
  "pipeline": "drop-fields",
  "outputs": {
    "elasticsearch": {
      "hosts": ["log-collector:9200"],
      "index": "node-health-%{+YYYY.MM.dd}"
    }
  }
}
```

**Datadog**
```yaml
logs:
  - type: file
    path: /var/log/node-health-agent.log
    service: node-health-agent
    source: python
    tags:
      - env:production
```

### Monitoring & Alerting

**Prometheus Metrics (sample exporter)**
```python
# Parse agent_tick_metrics events and expose as Prometheus metrics
health_agent_tick_duration.observe(tick_duration_ms / 1000.0)
health_agent_collector_slowest.observe(slowest_collector_ms / 1000.0)
health_report_health_status.labels(node_id=node_id, health=health).set(health_code)
```

**Alert Rules (example)**
```yaml
- alert: NodeHealthCritical
  expr: health_report_health_status == 3  # UNHEALTHY
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Node {{ $labels.node_id }} is unhealthy"

- alert: NodeHealthDegraded
  expr: health_report_health_status == 2  # DEGRADED
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Node {{ $labels.node_id }} is degraded"
```

---

## Extensibility & Tuning

### Custom Thresholds

Health evaluation thresholds are defined in `agent/evaluate.py`:

```python
CPU_DEGRADED_FACTOR = 0.85   # loadavg > cpu_count * 0.85
CPU_UNHEALTHY_FACTOR = 1.25  # loadavg > cpu_count * 1.25

MEM_DEGRADED_PCT = 15.0      # < 15% available
MEM_UNHEALTHY_PCT = 8.0      # < 8% available

DISK_DEGRADED_PCT = 10.0     # < 10% free
DISK_UNHEALTHY_PCT = 5.0     # < 5% free
```

To customize, modify these constants and rebuild/redeploy:

```bash
# Edit thresholds
vim agent/evaluate.py

# Reinstall
pip install -e .

# Test new thresholds
pytest tests/test_evaluate_health.py -v
```

### Adding Custom Collectors

Collectors extend `agent.collectors.base.Collector`:

```python
from agent.collectors.base import Collector, CollectorResult

class CustomCollector(Collector):
    name = "custom"
    
    def collect(self) -> CollectorResult:
        try:
            # Your signal extraction logic
            return CollectorResult(signals={"my_custom_signal": value})
        except Exception as e:
            return CollectorResult(failed=True, error=str(e))
```

Register in `agent/collectors/__init__.py` and invoke in `agent/main.py`.

### Extending Renderers

Create a new renderer by extending `triage.render.base.Renderer`:

```python
from triage.render.base import Renderer

class CustomRenderer(Renderer):
    name = "custom"
    
    def render(self, summaries, *, meta: dict) -> str:
        # Your custom formatting logic
        return formatted_output
```

Register in `triage/render/__init__.py`:

```python
from triage.render.custom import CustomRenderer

RENDERERS = {..., CustomRenderer()}
```

---

## Troubleshooting

### Agent produces no output

**Problem:** `node-health-agent oneshot` produces no events  
**Solution:**
1. Check Python version: `python3 --version` (must be 3.11+)
2. Verify installation: `pip show node-health-agent`
3. Check disk space: `df -h ./spool`
4. Enable verbose output: `node-health-agent oneshot --print-report`

### Spool file grows unbounded

**Problem:** `spool/node_reports.jsonl` consuming disk space  
**Solution:**
```bash
# Enable rotation
node-health-agent run --spool-max-bytes 52428800 --spool-rotate-count 3

# OR manually clean old spools
find spool -name "*.jsonl.*" -mtime +7 -delete
```

### Health always DEGRADED

**Problem:** Health consistently reports DEGRADED despite good signals  
**Solution:**
1. Check `current_reasons`: `node-health-triage summarize --format explain`
2. If `collector_failed:*` present, check individual collector output
3. Validate thresholds: `python3 -c "from agent.evaluate import *; print(CPU_DEGRADED_FACTOR)"`

### Triage exits with code 0 when expecting 2/3

**Problem:** Filters not working correctly  
**Solution:**
```bash
# Debug triage filters
node-health-triage summarize --spool spool/node_reports.jsonl --format json | jq '.nodes[].current_health'

# Manually check exit code
node-health-triage summarize --only-unhealthy
echo $?  # Should be 0, 2, or 3
```

---

## Contributing

Contributions are welcome. Please ensure:

1. All tests pass: `pytest -v`
2. Code is linted: `ruff check . && ruff format .`
3. New features include tests
4. Documentation is updated
5. Commit messages are clear and descriptive

### Development Workflow

```bash
# Create feature branch
git checkout -b feature/my-feature

# Make changes and test locally
pytest -v
ruff check . --fix

# Commit and push
git push origin feature/my-feature

# Open pull request with description of changes
```

---

## Project Philosophy

This agent is built on essential principles for production systems:

- **Predictability:** Deterministic outputs, stable contracts, version-aware events
- **Visibility:** Explicit failure modes, signal omission on error, detailed metrics
- **Simplicity:** Pure Python, minimal dependencies, easy to extend and debug
- **Reliability:** Comprehensive testing, graceful degradation, no silent failures

It is designed as a **foundational building block** for operators and engineers who need robust node-level health visibility without operational overhead.

---

## License

This project is licensed under the MIT License. See `LICENSE` file for details.



