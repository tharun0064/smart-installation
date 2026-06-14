# nr-diagnose — Project Overview

An AI-powered installer that doesn't just run a script. It watches every step, diagnoses failures with an LLM, and proposes a concrete fix the user can approve in-line.

---

## 1. The Problem

Installing observability agents (OTel collectors, APM agents, infra agents) looks simple in the docs but fails constantly in practice. The same install script breaks differently on every host:

- The Oracle listener is on a non-standard port.
- The license key is for the EU region but the script points at the US OTLP endpoint.
- A firewall silently drops outbound 4317.
- The user pasted `password` as the password.
- A YAML indent error keeps the collector from booting.

What happens today:

1. The script fails with a stderr line like `ORA-01017: invalid username/password`.
2. The user copies the error into Slack, a search bar, or an LLM chat window.
3. They paste it into ten config files, restart, paste again, restart again.
4. Half the time the fix the script "found" lives in someone's head and never makes it back into the docs.

The cost: every install is a from-scratch debugging session, the same five errors get re-debugged forever, and the install experience for our agents looks fragile to customers.

---

## 2. The Solution

`nr-diagnose` wraps the install script in an agentic loop. Each step is a checkpoint. On failure, it runs a tight two-turn conversation with Claude (via New Relic's Nerd Completion gateway) to localize the root cause, then proposes a fix the user can approve.

**The loop:**

```
parse install.sh  →  run step
       │
       ├── ✓ pass → next step
       │
       └── ✗ fail
              │
              ├── 1. Check runbook (cached fixes from prior runs)
              │      hit  → show fix, prompt [Y/n/q]
              │      miss → call LLM
              │
              ├── 2. LLM Turn 1 (Detective)
              │      input:  failed cmd + stderr + OS + agent knowledge
              │      output: hypothesis + safe diagnostic commands
              │
              ├── 3. Run diagnostics (allowlisted, read-only, no sudo)
              │
              ├── 4. LLM Turn 2 (Resolver)
              │      input:  diagnostic outputs + original error
              │      output: root_cause, explanation, fix_command,
              │              is_destructive, bad_inputs[]
              │
              └── 5. Prompt user
                     [Y] run fix → retry step → save to runbook
                     [u] update inputs → re-render configs → retry
                     [n] skip
                     [q] quit
```

**Three things this gets right:**

| | |
|---|---|
| **Domain-aware** | Each agent (`otel-oracledbreceiver`, `otel-mysql`, …) ships its own `knowledge/`, `diagnostics/hints.yaml`, and seeded `runbook/`. The LLM sees the right context for the subsystem at hand instead of generic shell advice. |
| **Anchored** | The Detective and Resolver prompts explicitly forbid drift across subsystems. ORA codes get Oracle diagnostics; HTTP 401 from `otlp.*` gets New Relic diagnostics. The model can't quietly pivot to "have you checked DNS?" when the original error was an Oracle auth failure. |
| **Self-improving** | Every successful LLM fix is written to a local runbook keyed by error pattern. The next user with the same error skips the LLM entirely. `nr-diagnose sync` promotes local fixes to the shared agent repo. |

---

## 3. Architecture at a Glance

### 3.1 Module map

```
nr_diagnose/
├── cli.py          Typer entry: run, list, new-agent, sync
├── config.py       .env → Config (api_key, base_url, model, agents_dir)
├── registry.py     Loads agents/<name>/ into Agent objects
├── parser.py       Splits install.sh into Step objects (handles heredocs)
├── inputs.py       Collects required_inputs from manifest, prompts user,
│                   persists to .config.env per agent
├── generator.py    Auto-generates install.sh from knowledge/references.md
│                   when scaffold is still a template
├── runner.py       Main loop. Step approval, execution, failure handling,
│                   input re-prompting, config re-rendering, validation
├── agent.py        Anthropic SDK client. Detective + Resolver prompts
├── diagnostics.py  Allowlisted command executor (ping, nc, ss, curl, …)
├── runbook.py      Pattern → fix cache (seeded + local)
├── context.py      Host facts (distro, kernel, user) for the LLM
├── scrub.py        Redacts secrets before any prompt leaves the box
├── schemas.py      StepResult, DiagnosticPayload, RemediationPayload, …
└── ui.py           Rich-based terminal output and prompts
```

### 3.2 Agent definition

An agent is a directory of declarative facts about one integration:

```
agents/otel-oracledbreceiver/
├── manifest.yaml           name, display_name, ports, services,
│                           prerequisites, required_inputs (with secret flags)
├── install.sh              the actual install steps
├── knowledge/
│   ├── prerequisites.md    what must be true before install
│   ├── common-failures.md  known failure modes (fed to the Detective)
│   └── references.md       links to upstream docs
├── diagnostics/
│   └── hints.yaml          priority_commands + context_hints
│                           (e.g. "ORA-01017 → ORACLE_USERNAME/ORACLE_PASSWORD")
└── runbook/
    └── index.yaml          seeded pattern → fix mappings
```

Authoring a new agent means filling in those files and pointing the framework at them. `nr-diagnose new-agent <name>` scaffolds the structure.

### 3.3 LLM integration

```python
from anthropic import Anthropic

client = Anthropic(
    auth_token=cfg.api_key,             # NCUT-… token from Nerd Completion
    base_url=cfg.base_url,              # https://nerd-completion.staging-service.nr-ops.net
)
client.messages.create(
    model=cfg.model,                    # claude-sonnet-4-5-20250514
    max_tokens=1024,
    system=SYSTEM_PROMPT_DETECTIVE | SYSTEM_PROMPT_RESOLVER,
    messages=[{"role": "user", "content": user_prompt}],
)
```

Both prompts force a strict JSON shape so the runner can act deterministically:

- **Detective →** `{"hypothesis": str, "diagnostic_commands": [str]}`
- **Resolver →** `{"root_cause": str, "human_explanation": str, "remediation_command": str, "is_destructive": bool, "bad_inputs": [str]}`

Routing through Nerd Completion (instead of calling Anthropic directly) is what makes this approved for internal use — security, compliance, governance, and cost visibility all live there.

### 3.4 Safety boundaries

| Layer | Rule |
|---|---|
| Diagnostics | Allowlist-only: `ping`, `nc`, `netstat`, `ss`, `curl`, `systemctl status`, `cat /etc/…`, `lsof`, `getent`, `dig`, `command -v`. No `sudo`. No writes. |
| Install steps | Pattern-classified: install/write/service-modify steps require user approval; `echo`, `sleep`, `mkdir -p`, status checks auto-run. |
| Remediations | Every fix is human-in-the-loop. Destructive fixes are flagged with a warning before the prompt. |
| Data egress | `scrub.py` redacts API keys, passwords, and license keys from every prompt before it leaves the host. |
| Config drift | When the LLM blames a user input (`bad_inputs`), the runner re-prompts the user and re-renders any earlier install steps that referenced the changed input — so manual edits to generated config files don't get clobbered next run. |

---

## 4. nr-diagnose vs. a Traditional CLI Installer

The same install, two worlds:

| | Traditional install CLI | nr-diagnose |
|---|---|---|
| **What it does on success** | Runs the script. | Runs the script. |
| **What it does on failure** | Prints the stderr. Exits non-zero. | Diagnoses, proposes a fix, prompts the user, retries. |
| **Where the troubleshooting knowledge lives** | In docs, Slack, and people's heads. | In each agent's `knowledge/` and `runbook/`, version-controlled. |
| **Cost of seeing the same error twice** | Same as the first time. | Free — runbook hit, no LLM call. |
| **Handling of bad user input** | Script fails on step N; user re-runs from step 1. | LLM flags `bad_inputs`, runner re-prompts and regenerates downstream config in place. |
| **Domain awareness** | None. The script is generic bash. | Per-agent priority diagnostics and error-code → input mappings. |
| **Safety on automated fixes** | N/A. | Allowlisted diagnostics, scrubbed prompts, every remediation human-approved. |
| **Improvement loop** | Manual doc updates, if anyone remembers. | Every fix is captured automatically; `nr-diagnose sync` promotes it to the team. |

### Why not just use Claude Code?

Claude Code is a generic agent — it gathers context, edits files, runs tools. It's great when the task is open-ended ("debug this repo"). nr-diagnose is the opposite: a narrow, deterministic harness with a fixed lifecycle (parse → execute → on failure: diagnose → remediate → retry). The LLM isn't driving — it's a constrained reasoner inside a controlled loop, with a strict JSON contract and an allowlisted action surface. That's what makes it safe to point at a real install with real credentials on a real host.

---

## 5. Running It

```bash
# one-time setup
source setup.sh

# list available agents
nr-diagnose list

# scaffold a new agent
nr-diagnose new-agent otel-postgres

# preview the parsed steps without executing
nr-diagnose run --agent otel-oracledbreceiver --dry-run

# run for real (with AI fallback on failures)
nr-diagnose run --agent otel-oracledbreceiver

# share locally-learned fixes back to the team
nr-diagnose sync
```

Configuration lives in `.env`:

```
ANTHROPIC_API_KEY=NCUT-...
ANTHROPIC_BASE_URL=https://nerd-completion.staging-service.nr-ops.net
LLM_MODEL_NAME=claude-sonnet-4-5-20250514
NR_DIAGNOSE_AGENTS_DIR=./agents
```

---

## 6. Key Design Decisions

1. **Runbook before LLM.** Cached fixes are checked first. The LLM is the fallback, not the front door.
2. **Two-turn LLM.** Diagnosis and remediation are separate roles with separate prompts. Mixing them produces worse fixes.
3. **Anchored prompts.** Both system prompts forbid drifting across subsystems — Oracle errors stay in Oracle-land.
4. **Human-in-the-loop, always.** No auto-execution of fixes. `[Y/n/u/q]`.
5. **Inputs are first-class.** When the root cause is "user typed the wrong value," the fix is to re-prompt and re-render — not to hand-edit a generated file that gets overwritten next run.
6. **Knowledge ships with the agent.** Each integration carries its own context, diagnostics hints, and seeded runbook. The framework stays generic; the agents stay domain-rich.
