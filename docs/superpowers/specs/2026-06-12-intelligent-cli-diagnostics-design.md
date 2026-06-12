# Intelligent CLI Diagnostics Layer - Design Specification

**Date:** 2026-06-12
**Author:** tbalanagu
**Status:** Draft
**Project:** ai-driven-installation (Hackathon Prototype)

---

## 1. Problem Statement

Installing New Relic agents involves running multi-step shell scripts that can fail at any point due to network issues, firewall rules, missing dependencies, permission problems, or configuration errors. When a step fails, developers must manually interpret error output, search documentation, and figure out the fix. This is slow and frustrating.

## 2. Solution

A Go CLI tool that acts as an **intelligent script runner**. It:

1. Takes a shell script (e.g., New Relic agent install)
2. Parses it into individual executable steps
3. Executes steps sequentially
4. When any step fails, hands control to an AI agent that:
   - Diagnoses the issue (runs safe diagnostic commands)
   - Suggests a fix with plain-English explanation
   - Offers to execute the fix interactively (`[Y/n]`)
   - Resumes the remaining install steps on success

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────┐
│  User runs:  nr-diagnose run --agent otel-oracledb      │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Agent Loader: load agents/otel-oracledb/manifest.yaml  │
│  + knowledge/ + diagnostics/ + runbook/                 │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Script Parser: split install.sh into executable steps  │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Step Runner: execute step N                            │
│  ├── Success → move to step N+1                        │
│  └── Failure → check Runbook first                     │
└──────────────────────────┬──────────────────────────────┘
                           ▼ (on failure)
┌─────────────────────────────────────────────────────────┐
│  Runbook Lookup: match error pattern in index.yaml      │
│  ├── MATCH → show cached fix immediately (no LLM)      │
│  └── NO MATCH → proceed to AI Agent                    │
└──────────────────────────┬──────────────────────────────┘
                           ▼ (no runbook match)
┌─────────────────────────────────────────────────────────┐
│  AI Agent (Turn 1): error + OS context + knowledge/     │
│  → Returns hypothesis + diagnostic commands             │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Execute diagnostic commands locally                    │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  AI Agent (Turn 2): Receive diagnostic output           │
│  → Returns root cause + fix command + is_destructive    │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Rich UI: Show explanation + [Y/n/q] prompt             │
│  ├── Y → execute fix, re-run failed step, resume       │
│  ├── n → skip this step, continue with next step       │
│  └── q → abort entire script                           │
└──────────────────────────┬──────────────────────────────┘
                           ▼ (on successful fix)
┌─────────────────────────────────────────────────────────┐
│  Runbook Writer: save resolution to local runbook       │
│  (~/.nr-diagnose/runbook/<agent>/<entry>.md)            │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Components

| Component | Package/File | Responsibility |
|-----------|--------------|---------------|
| **CLI Entry** | `main.go` | Cobra CLI app, accepts agent name or script path, orchestrates the pipeline |
| **Agent Loader** | `internal/registry/` | Discovers and loads agent definitions from `agents/` folder |
| **Script Parser** | `internal/parser/` | Reads shell script, splits into executable steps |
| **Step Runner** | `internal/runner/` | Executes one step at a time via `os/exec`, captures stdout/stderr/exit code |
| **Context Collector** | `internal/context/` | Gathers OS info (distro, kernel, services, env) to enrich LLM context |
| **AI Diagnostic Agent** | `internal/agent/` | Two-turn LLM conversation via Nerd Completion |
| **Diagnostic Executor** | `internal/diagnostics/` | Runs LLM-suggested diagnostic commands with whitelist enforcement |
| **Runbook Manager** | `internal/runbook/` | Reads/writes/matches runbook entries; merges seeded + local |
| **Remediation UI** | `internal/ui/` | Terminal UI: colored output, panels, prompts (using lipgloss/bubbles or plain ANSI) |
| **Resume Controller** | `internal/runner/` | After fix, re-runs failed step and continues remaining steps |

---

## 5. Data Schemas

```go
// internal/schemas/schemas.go

// AgentManifest defines a monitoring agent's metadata and context.
type AgentManifest struct {
    Name          string   `yaml:"name"`
    DisplayName   string   `yaml:"display_name"`
    Description   string   `yaml:"description"`
    TargetOS      string   `yaml:"target_os"`
    Ports         []int    `yaml:"ports"`
    Services      []string `yaml:"services"`
    Prerequisites []string `yaml:"prerequisites"`
}

// DiagnosticPayload is Turn 1 output: LLM tells us what diagnostic commands to run.
type DiagnosticPayload struct {
    Hypothesis         string   `json:"hypothesis"`
    DiagnosticCommands []string `json:"diagnostic_commands"`
}

// RemediationPayload is Turn 2 output: LLM provides the fix after seeing diagnostic results.
type RemediationPayload struct {
    RootCause          string `json:"root_cause"`
    HumanExplanation   string `json:"human_explanation"`
    RemediationCommand string `json:"remediation_command"`
    IsDestructive      bool   `json:"is_destructive"`
}

// StepResult captures the result of executing a single script step.
type StepResult struct {
    StepNumber int    `json:"step_number"`
    Command    string `json:"command"`
    ExitCode   int    `json:"exit_code"`
    Stdout     string `json:"stdout"`
    Stderr     string `json:"stderr"`
    Success    bool   `json:"success"`
}

// RunbookEntry represents a single resolved issue in the runbook.
type RunbookEntry struct {
    ID            string `yaml:"id"`
    ErrorPattern  string `yaml:"error_pattern"`
    StepFailed    string `yaml:"step_failed"`
    RootCause     string `yaml:"root_cause"`
    FixCommand    string `yaml:"fix_command"`
    ResolvedCount int    `yaml:"resolved_count"`
    FirstSeen     string `yaml:"first_seen"`
    LastSeen      string `yaml:"last_seen"`
}

// RunbookIndex is the lookup table mapping error patterns to entry files.
type RunbookIndex struct {
    Entries []RunbookIndexEntry `yaml:"entries"`
}

type RunbookIndexEntry struct {
    Pattern  string `yaml:"pattern"`   // regex or substring match
    EntryFile string `yaml:"entry_file"` // relative path to .md file
}
```

---

## 6. LLM Integration

### Provider
- **Gateway:** Nerd Completion (NR internal LLM gateway)
- **Route:** Nerd Completion → AWS Bedrock → Claude
- **Base URL:** `https://nerd-completion.staging-service.nr-ops.net`
- **Auth:** API key from `~/.claude/nerd-completion.json` or `ANTHROPIC_API_KEY` env var
- **SDK:** Direct HTTP calls to OpenAI-compatible Chat Completions API (no external SDK needed)
- **Model:** `claude-sonnet-4-6` (configurable via env var `LLM_MODEL_NAME`)
- **Structured output:** JSON mode enforced via system prompt + response parsing into Go structs

### System Prompts

**Turn 1 — The Detective:**
```
You are the Intelligent Inference Engine of a DevOps installation CLI wrapper.
An installation script step has just failed. You receive the failed command, its
stderr/stdout, exit code, and host OS context.

Your job: select the exact, localized terminal diagnostic commands needed to
isolate the root cause.

CRITICAL SAFETY: You may ONLY emit read-only diagnostic commands (e.g., ping,
nc, netstat, ss, ufw status, iptables -L, curl, systemctl status, lsof).
Do NOT emit destructive or modifying commands.
```

**Turn 2 — The Resolver:**
```
You are the Remediation Engine. You receive:
1. The original failed command and its error output
2. The raw terminal output from the diagnostic commands you previously requested

Analyze the diagnostic output, isolate the definitive root cause, and provide:
- A precise root cause statement
- A plain-English explanation for the developer
- A single, concrete terminal command to fix the issue
- Whether that command is destructive

Keep explanations punchy, empathetic, and developer-centric.
```

---

## 7. Script Parsing Rules

The parser handles real shell scripts by:

1. **Skipping:** empty lines, comment-only lines (`#`), shebangs (`#!/bin/bash`), `set` directives
2. **Treating each logical command as one step:** split on newlines
3. **Handling continuations:** lines ending with `\` are joined with the next line
4. **Preserving chains:** `&&` chains are kept as a single step (logically one operation)
5. **Handling pipes:** piped commands (`|`) are kept as a single step
6. **Block handling:** `if/then/fi`, `for/do/done` blocks are treated as single steps

---

## 8. Safety & Security

### Diagnostic Command Whitelist
Only these commands (and their flags) may be executed during diagnosis:
- `ping`, `nc`, `netstat`, `ss`
- `curl`, `wget` (GET only)
- `traceroute`, `nslookup`, `dig`
- `ufw status`, `iptables -L` (list only)
- `systemctl status <service>`
- `ps`, `lsof`, `df`, `free`
- `cat` (for config files in `/etc/` only)
- `dpkg -l`, `apt list`, `rpm -q` (package queries)

Any command not on this whitelist is rejected and not executed.

### Credential Scrubbing
Before sending context to the LLM:
- Strip `license_key`, `api_key`, `password`, `secret`, `token` values
- Replace with `<REDACTED>`
- Pattern match: any string matching common key formats (40-char hex, base64 blocks)

### Destructive Command Warning
If `is_destructive=True` in the remediation response:
- Show a prominent warning panel (red border)
- Require explicit `Y` (not just Enter) to proceed

---

## 9. Agent Registry (Extensible Plugin System)

### Concept

Each monitoring agent (OTel OracleDB, MSSQL, Infra, Java APM, etc.) lives in its own subfolder under `agents/`. Adding a new agent = adding a new folder. No code changes required.

### Folder Structure

```
agents/
├── otel-oracledb/
│   ├── manifest.yaml              # Agent metadata (name, ports, services, prerequisites)
│   ├── install.sh                 # The install script to run step-by-step
│   ├── knowledge/
│   │   ├── prerequisites.md       # What must be true before install starts
│   │   ├── common-failures.md     # Known failure modes + fixes (seeded LLM context)
│   │   └── references.md          # Links to official docs, troubleshooting guides
│   ├── diagnostics/
│   │   └── hints.yaml             # Agent-specific diagnostic commands to prioritize
│   └── runbook/
│       ├── index.yaml             # Lookup: error pattern → entry file
│       └── *.md                   # Seeded runbook entries (shipped with the tool)
│
├── otel-mssql/                    # Added later — same structure
│   ├── manifest.yaml
│   ├── install.sh
│   ├── knowledge/
│   ├── diagnostics/
│   └── runbook/
│
└── _template/                     # Skeleton for scaffolding new agents
    ├── manifest.yaml
    ├── install.sh
    ├── knowledge/
    │   ├── prerequisites.md
    │   ├── common-failures.md
    │   └── references.md
    ├── diagnostics/
    │   └── hints.yaml
    └── runbook/
        └── index.yaml
```

### manifest.yaml Example

```yaml
name: otel-oracledb
display_name: "OpenTelemetry OracleDB Receiver"
description: "Installs and configures OTel Collector with OracleDB receiver"
target_os: linux
ports: [1521]
services: [otelcol-contrib]
prerequisites:
  - "Oracle Instant Client installed"
  - "TNS_ADMIN environment variable configured"
  - "DB user with SELECT_CATALOG_ROLE grant"
```

### diagnostics/hints.yaml Example

```yaml
# Agent-specific commands the LLM should prioritize for this agent type
priority_commands:
  - "tnsping ORCL"
  - "nc -zv localhost 1521"
  - "echo $TNS_ADMIN"
  - "ls $ORACLE_HOME/network/admin/tnsnames.ora"
  - "systemctl status otelcol-contrib"

# Context the LLM should always consider for this agent
context_hints:
  - "OracleDB receiver requires Oracle Instant Client libs in LD_LIBRARY_PATH"
  - "TNS resolution failures are the #1 cause of connection issues"
  - "Check listener.ora and tnsnames.ora for mismatched SERVICE_NAME"
```

### How Knowledge Files Feed the LLM

When a step fails and the LLM is invoked, the system prompt includes:
1. The error output + OS context (always)
2. Contents of `knowledge/common-failures.md` (agent-specific known issues)
3. Contents of `diagnostics/hints.yaml` (priority commands + context hints)
4. Contents of `knowledge/prerequisites.md` (what should have been true)

This gives the LLM targeted domain knowledge without needing fine-tuning.

### Adding a New Agent

```bash
# Scaffold a new agent from template
nr-diagnose new-agent otel-mssql

# Creates agents/otel-mssql/ with all skeleton files
# Developer fills in manifest.yaml, writes install.sh, seeds knowledge/
```

---

## 10. Self-Learning Runbook

### Concept

Every time the AI agent successfully resolves an issue, the resolution is saved as a runbook entry. Next time any user hits the same error pattern, the fix is served instantly from the runbook — no LLM call needed.

### Storage Layers

| Layer | Location | Purpose |
|-------|----------|---------|
| **Seeded** | `agents/<name>/runbook/` (in repo) | Known issues shipped with the tool |
| **Local** | `~/.nr-diagnose/runbook/<name>/` | Learned from this user's resolutions |
| **Merged at runtime** | Both paths checked | Seeded checked first, then local |

### Runtime Flow

```
Step fails
  → Extract error string from stderr/stdout
  → Check seeded runbook (agents/<name>/runbook/index.yaml)
  → Check local runbook (~/.nr-diagnose/runbook/<name>/index.yaml)
  ├── MATCH FOUND:
  │   → Display cached resolution (no LLM call)
  │   → Show [Y/n/q] prompt
  │   → If Y and fix succeeds: increment resolved_count, update last_seen
  └── NO MATCH:
      → Normal 2-turn LLM flow
      → If fix succeeds: write new runbook entry to local storage
```

### Runbook Entry Format

```markdown
# runbook/003-firewall-block-1521.md
---
id: "003"
error_pattern: "ORA-12541: TNS:no listener"
step_failed: "Step 5: Verify Oracle connectivity"
root_cause: "Oracle listener port 1521 blocked by firewall"
fix_command: "sudo ufw allow 1521/tcp"
resolved_count: 1
first_seen: "2026-06-12T14:30:00Z"
last_seen: "2026-06-12T14:30:00Z"
---

## Symptoms
Connection to Oracle DB on port 1521 times out during OTel receiver setup.

## Diagnosis
- `nc -zv localhost 1521` → Connection refused
- `ufw status` → 1521 not in allow list

## Resolution
`sudo ufw allow 1521/tcp`
```

### Pattern Matching

The `index.yaml` uses substring matching (not full regex) for simplicity:

```yaml
entries:
  - pattern: "ORA-12541"
    entry_file: "003-firewall-block-1521.md"
  - pattern: "TNS:no listener"
    entry_file: "003-firewall-block-1521.md"
  - pattern: "connection refused.*1521"
    entry_file: "003-firewall-block-1521.md"
```

Multiple patterns can point to the same entry. Matching is case-insensitive.

### Sync Command

```bash
# Push local runbook entries to the shared repo
nr-diagnose sync

# What it does:
# 1. Copies new entries from ~/.nr-diagnose/runbook/<agent>/ → agents/<agent>/runbook/
# 2. Merges index.yaml (deduplicates patterns)
# 3. Stages files with git add
# 4. Commits with message: "runbook: add <N> entries for <agent>"
# 5. User handles git push
```

### Runbook UI Indicator

When a fix comes from the runbook vs. LLM, the UI shows it:

```
╭─── Root Cause (from runbook) ─────────────────────────╮
│ Oracle listener port 1521 blocked by firewall          │
│ (resolved 3 times previously)                          │
╰────────────────────────────────────────────────────────╯
```

---

## 11. CLI Interface

```bash
# Run an agent install with AI diagnostics
nr-diagnose run --agent otel-oracledb

# Run a raw script (without agent context)
nr-diagnose run ./custom-install.sh

# Run with verbose output (show all step stdout)
nr-diagnose run --agent otel-oracledb --verbose

# Dry-run: parse and show steps without executing
nr-diagnose run --agent otel-oracledb --dry-run

# Specify a custom model
nr-diagnose run --agent otel-oracledb --model claude-sonnet-4-6

# List available agents
nr-diagnose list

# Scaffold a new agent
nr-diagnose new-agent otel-mssql

# Sync local runbook entries to shared repo
nr-diagnose sync
```

---

## 12. UI/UX Design (Terminal)

Uses `github.com/charmbracelet/lipgloss` for styled output and `github.com/charmbracelet/bubbles` for spinners/progress (or plain ANSI escape codes for minimal dependencies).

### During Normal Execution
- Step progress indicator: `[3/7] Running: apt-get update`
- Green checkmarks for successful steps
- Spinner animation during execution

### On Failure
- Red X with failed step highlighted
- Spinner: "AI Agent diagnosing failure..."
- Spinner: "Running diagnostic commands..."

### Remediation Display
```
╭─── Root Cause ────────────────────────────────────────╮
│ PostgreSQL port 5432 is blocked by UFW firewall       │
╰───────────────────────────────────────────────────────╯

💡 Explanation:
  The agent install requires connectivity to the local
  PostgreSQL instance on port 5432, but your firewall
  (UFW) is actively blocking inbound TCP on that port.

🔧 Suggested Fix:
  sudo ufw allow 5432/tcp

⚠️  This command modifies your firewall rules.

Execute this fix? [Y]es / [n]o (skip step) / [q]uit:
```

### After Fix Applied
- Re-run the failed step
- If it passes: green checkmark, resume remaining steps
- If it still fails: offer to retry diagnosis or abort

---

## 13. Sample Install Script (Demo/Prototype)

```bash
#!/bin/bash
# install-nr-agent.sh — New Relic Infrastructure Agent Install

# Step 1: Add New Relic GPG key
curl -s https://download.newrelic.com/infrastructure_agent/gpg/newrelic-infra.gpg | sudo apt-key add -

# Step 2: Add New Relic APT repository
echo "deb https://download.newrelic.com/infrastructure_agent/linux/apt focal main" | sudo tee /etc/apt/sources.list.d/newrelic-infra.list

# Step 3: Update package index
sudo apt-get update

# Step 4: Install the agent
sudo apt-get install -y newrelic-infra

# Step 5: Configure license key
echo "license_key: YOUR_NR_LICENSE_KEY" | sudo tee /etc/newrelic-infra.yml

# Step 6: Start the agent service
sudo systemctl start newrelic-infra

# Step 7: Verify agent connectivity
curl -sf https://infra-api.newrelic.com/healthcheck || exit 1
```

---

## 14. Test Scenarios

### Scenario A: Firewall Block (UFW)
- **Fails at:** Step 7 (connectivity check)
- **Error:** `curl: (7) Failed to connect to infra-api.newrelic.com port 443: Connection refused`
- **Diagnostic commands returned:** `ufw status`, `nc -zv infra-api.newrelic.com 443`, `iptables -L`
- **Root cause:** UFW blocking outbound 443
- **Fix:** `sudo ufw allow out 443/tcp`

### Scenario B: Missing Dependency
- **Fails at:** Step 4 (apt install)
- **Error:** `E: Unable to locate package newrelic-infra`
- **Diagnostic commands returned:** `apt-cache policy newrelic-infra`, `cat /etc/apt/sources.list.d/newrelic-infra.list`, `apt-get update 2>&1 | tail -20`
- **Root cause:** Repository not properly added (wrong distro codename)
- **Fix:** `echo "deb https://download.newrelic.com/infrastructure_agent/linux/apt $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/newrelic-infra.list && sudo apt-get update`

### Scenario C: Permission Denied
- **Fails at:** Step 6 (systemctl start)
- **Error:** `Failed to start newrelic-infra.service: Access denied`
- **Diagnostic commands returned:** `whoami`, `groups`, `sudo -l`
- **Root cause:** Script not run with sudo / user not in sudoers
- **Fix:** `sudo systemctl start newrelic-infra`

---

## 15. Dependencies

```
go >= 1.22
github.com/spf13/cobra           # CLI framework
github.com/charmbracelet/lipgloss # Terminal styling
github.com/charmbracelet/bubbles  # Spinners, progress bars
github.com/fatih/color            # Simple colored output (alternative to lipgloss)
gopkg.in/yaml.v3                  # YAML parsing for manifests, hints, runbook index
```

No external LLM SDK required — Nerd Completion exposes an OpenAI-compatible REST API; we use `net/http` + `encoding/json` directly.

---

## 16. File Structure

```
ai-driven-installation/
├── main.go                          # CLI entry point (Cobra app)
├── go.mod
├── go.sum
├── cmd/
│   ├── run.go                       # "run" subcommand
│   ├── list.go                      # "list" subcommand (show available agents)
│   ├── new_agent.go                 # "new-agent" subcommand (scaffold)
│   └── sync.go                      # "sync" subcommand (push runbook upstream)
├── internal/
│   ├── registry/
│   │   ├── registry.go             # Agent discovery + manifest loading
│   │   └── registry_test.go
│   ├── parser/
│   │   ├── parser.go               # Shell script parser
│   │   └── parser_test.go
│   ├── runner/
│   │   ├── runner.go               # Step executor + resume controller
│   │   └── runner_test.go
│   ├── context/
│   │   └── context.go              # OS context collector
│   ├── agent/
│   │   ├── agent.go                # LLM integration (Nerd Completion HTTP client)
│   │   └── agent_test.go
│   ├── diagnostics/
│   │   ├── diagnostics.go          # Diagnostic command executor + whitelist
│   │   └── diagnostics_test.go
│   ├── runbook/
│   │   ├── runbook.go              # Runbook read/write/match/merge logic
│   │   └── runbook_test.go
│   ├── ui/
│   │   └── ui.go                   # Terminal UI (lipgloss/bubbles)
│   ├── schemas/
│   │   └── schemas.go              # Go structs for all data types
│   └── config/
│       └── config.go               # Configuration (env vars, model settings)
├── agents/
│   ├── _template/                   # Skeleton for new agents
│   │   ├── manifest.yaml
│   │   ├── install.sh
│   │   ├── knowledge/
│   │   │   ├── prerequisites.md
│   │   │   ├── common-failures.md
│   │   │   └── references.md
│   │   ├── diagnostics/
│   │   │   └── hints.yaml
│   │   └── runbook/
│   │       └── index.yaml
│   └── otel-oracledb/              # First agent (hackathon demo)
│       ├── manifest.yaml
│       ├── install.sh
│       ├── knowledge/
│       │   ├── prerequisites.md
│       │   ├── common-failures.md
│       │   └── references.md
│       ├── diagnostics/
│       │   └── hints.yaml
│       └── runbook/
│           └── index.yaml
├── CLAUDE.md
├── solutions.md
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-06-12-intelligent-cli-diagnostics-design.md
```

---

## 17. Build & Run

```bash
# Build
go build -o nr-diagnose .

# Run with an agent
./nr-diagnose run --agent otel-oracledb

# Run a raw script (no agent context)
./nr-diagnose run ./some-script.sh

# List available agents
./nr-diagnose list

# Scaffold new agent
./nr-diagnose new-agent otel-mssql

# Sync local runbook to repo
./nr-diagnose sync

# Run tests
go test ./...
```

---

## 18. Out of Scope (for prototype)

- Windows/macOS support (Linux/Ubuntu only)
- Multiple concurrent script execution
- Custom plugin system for adding new diagnostic tools beyond the agent folder structure
- Multi-language install scripts (only bash)
- Automatic rollback of partially-completed installs
- Remote runbook storage (cloud/API-based) — only git-based sync for now
- Runbook conflict resolution (last-write-wins on sync)
