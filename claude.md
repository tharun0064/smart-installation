# nr-diagnose: AI-Powered Installation Diagnostics

## Project Overview

A Python CLI tool that runs agent installation scripts step-by-step. When a step fails, it uses an LLM (Claude via Anthropic API) to diagnose the failure and suggest a fix interactively.

## Architecture Flow

```
User runs: nr-diagnose run --agent otel-oracledb

        ┌─────────────────────────────────────┐
        │  1. Load Config (.env)              │
        │     - ANTHROPIC_API_KEY             │
        │     - ANTHROPIC_BASE_URL            │
        │     - LLM_MODEL_NAME                │
        └──────────────┬──────────────────────┘
                       │
        ┌──────────────▼──────────────────────┐
        │  2. Load Agent Definition           │
        │     agents/otel-oracledb/           │
        │     - manifest.yaml (metadata)      │
        │     - install.sh (steps)            │
        │     - knowledge/ (context for LLM)  │
        │     - diagnostics/hints.yaml        │
        │     - runbook/ (cached fixes)       │
        └──────────────┬──────────────────────┘
                       │
        ┌──────────────▼──────────────────────┐
        │  3. Parse install.sh → Steps        │
        │     Splits script into individual   │
        │     commands, handles continuations  │
        └──────────────┬──────────────────────┘
                       │
        ┌──────────────▼──────────────────────┐
        │  4. Execute Each Step               │
        │     bash -c "<command>"             │
        │                                     │
        │     ✓ Success → next step           │
        │     ✗ Failure → enter diagnosis     │
        └──────────────┬──────────────────────┘
                       │ (on failure)
        ┌──────────────▼──────────────────────┐
        │  5. Check Runbook First             │
        │     Pattern-match error against     │
        │     known fixes (seeded + local)    │
        │     If found → skip LLM, show fix   │
        └──────────────┬──────────────────────┘
                       │ (no match)
        ┌──────────────▼──────────────────────┐
        │  6. LLM Turn 1: Diagnose           │
        │     Send to Claude:                 │
        │       - Failed command + error      │
        │       - OS context (distro, user)   │
        │       - Agent knowledge             │
        │     Receive back:                   │
        │       - hypothesis                  │
        │       - diagnostic_commands[]       │
        └──────────────┬──────────────────────┘
                       │
        ┌──────────────▼──────────────────────┐
        │  7. Run Diagnostic Commands         │
        │     Only allowlisted safe commands  │
        │     (nc, netstat, systemctl status) │
        │     No sudo, no destructive ops     │
        └──────────────┬──────────────────────┘
                       │
        ┌──────────────▼──────────────────────┐
        │  8. LLM Turn 2: Remediate           │
        │     Send to Claude:                 │
        │       - Original error              │
        │       - Diagnostic outputs          │
        │     Receive back:                   │
        │       - root_cause                  │
        │       - human_explanation           │
        │       - remediation_command         │
        │       - is_destructive              │
        └──────────────┬──────────────────────┘
                       │
        ┌──────────────▼──────────────────────┐
        │  9. Prompt User                     │
        │     [Y]es → run fix, retry step     │
        │     [n]o  → skip step               │
        │     [q]uit → exit                   │
        │                                     │
        │     If fix works → save to runbook  │
        └─────────────────────────────────────┘
```

## Module Map

```
nr_diagnose/
├── cli.py          Entry point. Typer commands: run, list, new-agent, sync
├── config.py       Loads .env → Config dataclass
├── schemas.py      Data models (StepResult, DiagnosticPayload, RemediationPayload, etc.)
├── parser.py       Splits install.sh into executable steps
├── context.py      Collects OS info (distro, kernel, hostname, user)
├── scrub.py        Redacts API keys/passwords before sending to LLM
├── registry.py     Loads agent definitions from agents/ directory
├── diagnostics.py  Allowlisted safe command execution
├── agent.py        Anthropic SDK client - Turn 1 (diagnose) + Turn 2 (remediate)
├── runbook.py      Pattern matching cache of previously fixed issues
├── ui.py           Rich terminal output (colors, panels, prompts)
└── runner.py       Main loop: execute steps → diagnose failures → apply fixes
```

## LLM Integration (agent.py)

Uses the Anthropic Python SDK with nerd-completion proxy:

```python
from anthropic import Anthropic

client = Anthropic(
    auth_token=os.getenv("ANTHROPIC_API_KEY"),
    base_url=os.getenv("ANTHROPIC_BASE_URL"),
)

response = client.messages.create(
    model="claude-sonnet-4-5-20250514",
    max_tokens=1024,
    system="<system prompt>",
    messages=[{"role": "user", "content": "<user prompt>"}],
)
```

Two-turn conversation:
- **Turn 1 (Detective):** Receives failure context → returns diagnostic commands as JSON
- **Turn 2 (Resolver):** Receives diagnostic output → returns fix command as JSON

## Configuration (.env)

```
ANTHROPIC_API_KEY=NCUT-...        # nerd-completion token
ANTHROPIC_BASE_URL=https://nerd-completion.staging-service.nr-ops.net
LLM_MODEL_NAME=claude-sonnet-4-5-20250514
NR_DIAGNOSE_AGENTS_DIR=./agents   # optional
```

## Agent Definition Structure

```
agents/<name>/
├── manifest.yaml              # name, description, ports, services, prerequisites
├── install.sh                 # The installation script (parsed into steps)
├── knowledge/
│   ├── prerequisites.md       # What must be true before install
│   ├── common-failures.md     # Known failure modes (fed to LLM)
│   └── references.md          # Links to official docs
├── diagnostics/
│   └── hints.yaml             # priority_commands + context_hints for LLM
└── runbook/
    └── index.yaml             # Cached pattern → fix mappings
```

## Safety

- Diagnostic commands are allowlisted (diagnostics.py): ping, nc, netstat, ss, curl, etc.
- No sudo allowed in diagnostics
- `cat` restricted to /etc/ paths only
- `systemctl` restricted to `status` subcommand only
- PII scrubbed before sending to LLM (scrub.py)
- Destructive remediations flagged to user with warning

## Running

```bash
# Setup (one time)
source setup.sh

# Execute
nr-diagnose run --agent otel-oracledb
nr-diagnose run --agent otel-oracledb --dry-run
nr-diagnose list
nr-diagnose new-agent <name>
nr-diagnose sync
```

## Key Design Decisions

1. **Runbook-first:** Always checks cached fixes before calling LLM (saves time/cost)
2. **Two-turn LLM:** Separates diagnosis from remediation for better accuracy
3. **Human-in-the-loop:** Never auto-executes fixes; always prompts [Y/n/q]
4. **Learning system:** Successful LLM fixes get saved to local runbook for next time
5. **Agent-scoped knowledge:** Each agent carries its own domain context for the LLM
