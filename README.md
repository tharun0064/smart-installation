# nr-diagnose

AI-powered CLI that runs agent installation scripts step-by-step. When a step fails, it uses an LLM (Claude) to diagnose the failure and suggest a fix interactively.

## Architecture

```mermaid
graph TB
    subgraph CLI["CLI Layer (cli.py)"]
        RUN["nr-diagnose run"]
        LIST["nr-diagnose list"]
        NEW["nr-diagnose new-agent"]
        SYNC["nr-diagnose sync"]
    end

    subgraph Execution["Execution Layer"]
        CONFIG["Config (.env)"]
        REGISTRY["Registry"]
        PARSER["Parser"]
        INPUTS["Input Collector"]
        RUNNER["Runner (main loop)"]
        CONTEXT["OS Context"]
    end

    subgraph Intelligence["Intelligence Layer"]
        LLM["LLM Agent (Anthropic SDK)"]
        RUNBOOK["Runbook Manager"]
        DIAG["Diagnostics (allowlisted)"]
        SCRUB["PII Scrubber"]
    end

    subgraph AgentDefs["Agent Definitions (agents/)"]
        MANIFEST["manifest.yaml"]
        INSTALL["install.sh"]
        KNOWLEDGE["knowledge/"]
        HINTS["diagnostics/hints.yaml"]
        RB_ENTRIES["runbook/index.yaml"]
    end

    subgraph External["External"]
        ANTHROPIC["Anthropic API\n(nerd-completion)"]
        SHELL["bash -c (step exec)"]
    end

    %% CLI to Execution
    RUN --> CONFIG
    RUN --> REGISTRY
    RUN --> PARSER
    RUN --> INPUTS
    RUN --> RUNNER

    %% Execution internals
    REGISTRY --> AgentDefs
    PARSER --> INSTALL
    INPUTS --> MANIFEST
    RUNNER --> CONTEXT
    RUNNER --> SHELL

    %% Execution to Intelligence
    RUNNER --> RUNBOOK
    RUNNER --> LLM
    RUNNER --> DIAG
    LLM --> SCRUB
    LLM --> ANTHROPIC
    LLM --> KNOWLEDGE
    LLM --> HINTS
    RUNBOOK --> RB_ENTRIES

    %% Styling
    classDef cliStyle fill:#4A90D9,color:#fff
    classDef execStyle fill:#7B68EE,color:#fff
    classDef intellStyle fill:#E85D75,color:#fff
    classDef agentStyle fill:#50C878,color:#fff
    classDef extStyle fill:#FF8C00,color:#fff

    class RUN,LIST,NEW,SYNC cliStyle
    class CONFIG,REGISTRY,PARSER,INPUTS,RUNNER,CONTEXT execStyle
    class LLM,RUNBOOK,DIAG,SCRUB intellStyle
    class MANIFEST,INSTALL,KNOWLEDGE,HINTS,RB_ENTRIES agentStyle
    class ANTHROPIC,SHELL extStyle
```

### How It Works

```mermaid
sequenceDiagram
    participant U as User
    participant R as Runner
    participant S as Shell
    participant RB as Runbook
    participant AI as LLM Agent
    participant API as Anthropic API

    U->>R: nr-diagnose run --agent <name>
    R->>R: Parse install.sh into steps

    loop For each step
        R->>U: Show step, ask approval [Y/s/q]
        U->>R: Y (approve)
        R->>S: bash -c "command"
        S-->>R: exit code + output

        alt Step succeeds
            R->>U: [checkmark] Step passed
        else Step fails
            R->>RB: Check runbook for cached fix
            alt Runbook match found
                RB-->>R: Known fix
                R->>U: Show cached remediation
            else No match
                R->>AI: Turn 1: Diagnose (error + context)
                AI->>API: Send prompt
                API-->>AI: hypothesis + diagnostic_commands
                AI-->>R: Diagnosis
                R->>S: Run safe diagnostic commands
                S-->>R: Diagnostic output
                R->>AI: Turn 2: Remediate (diagnostics)
                AI->>API: Send prompt
                API-->>AI: root_cause + fix_command
                AI-->>R: Remediation
            end
            R->>U: Show fix, ask [Y/r/n/q]
            U->>R: Y (apply fix)
            R->>S: Execute fix
            R->>RB: Save fix to runbook (learn)
        end
    end

    R->>U: Summary (passed/failed/skipped)
```

## Quick Start

```bash
# 1. Clone and setup
git clone <repo-url>
cd ai-driven-installation
source setup.sh

# 2. Configure API key
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY

# 3. Run
nr-diagnose run --agent otel-oracledbreceiver
nr-diagnose run --agent otel-oracledbreceiver --dry-run  # preview only
```

## Commands

| Command | Description |
|---------|-------------|
| `nr-diagnose run --agent <name>` | Run installation with AI diagnostics |
| `nr-diagnose run --agent <name> --dry-run` | Preview parsed steps without executing |
| `nr-diagnose list` | List available agents |
| `nr-diagnose new-agent <name>` | Scaffold a new agent definition |
| `nr-diagnose sync` | Share learned fixes back to the repo |

## Docker (with Oracle test environment)

```bash
docker compose -f docker-compose.test.yml build nr-diagnose
docker compose -f docker-compose.test.yml up -d oracle
docker compose -f docker-compose.test.yml run --rm nr-diagnose run --agent otel-oracledbreceiver
```

## Agent Structure

```
agents/<name>/
├── manifest.yaml              # Metadata (name, ports, services, inputs)
├── install.sh                 # Installation script (parsed into steps)
├── knowledge/
│   ├── prerequisites.md       # Preconditions for AI context
│   ├── common-failures.md     # Known failure modes (AI cheat sheet)
│   └── references.md          # Official docs and guides
├── diagnostics/
│   └── hints.yaml             # Priority diagnostic commands
└── runbook/
    └── index.yaml             # Cached pattern -> fix mappings
```

## Safety

- Diagnostic commands are allowlisted (no sudo, no destructive ops)
- PII/secrets scrubbed before sending to LLM
- Destructive remediations flagged with warning
- Human-in-the-loop: never auto-executes fixes
