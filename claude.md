To prime Claude (or any LLM) to baseline and write code for this project, you need to provide it with a structured, developer-focused technical brief. Models perform best when they are given explicit architectural boundaries, schema structures, and data flows rather than just high-level product goals.

The comprehensive technical dataset below gives Claude everything it needs to begin generating actual implementation code, including the specific **architectural options** available for the project.

---

## 📋 Project Context & Grounding

* **Project Name:** Intelligent CLI Diagnostics Layer (Hackathon Prototype)
* **Core Objective:** Intercept terminal installation failures, pass the state to an LLM, dynamically execute specific local diagnostic tools based on LLM intuition, and return an interactive, actionable remediation command.
* **Target Scope for Prototype:** Focus entirely on a **Linux/Ubuntu environment** diagnosing a blocked database port connection failure (e.g., PostgreSQL on `5432` or MySQL on `3306`).

---

## 🛠️ Implementation Options (The Tech Stack Matrix)

Provide Claude with these exact options to decide how the prototype will be built. For a hackathon, **Option 1** is highly recommended for speed and reliability.

| Layer | Option 1: Lightweight & Fast (Recommended) | Option 2: Full Enterprise Agent |
| --- | --- | --- |
| **CLI Runtime** | **Python 3.11+ (Typer + Rich)**<br>

<br>• Fast setup, native OS execution, incredible UI visuals via Rich. | **Node.js (Commander + Chalk + Ora)**<br>

<br>• Great if the team consists entirely of frontend/JS developers. |
| **AI Integration** | **Instructor Library (Pydantic)**<br>

<br>• Directly forces OpenAI/Anthropic to output strict Python objects. No syntax parsing errors. | **LangChain / LangGraph**<br>

<br>• Powerful state machines, but can add unnecessary complexity for a 48-hour build. |
| **LLM Provider** | **OpenAI (`gpt-4o-mini`)** or **Anthropic (`claude-3-5-haiku`)**<br>

<br>• Ultra-cheap, milliseconds-fast latency, native structured outputs. | **Ollama (Local `Llama-3`)**<br>

<br>• Completely free/local, but slower on hackathon laptops and harder to enforce strict JSON schemas reliably. |

---

## 🔄 System Flow & State Machine

```
[Phase 1: Interception] ──> Run Installer ──> Catch Error Trace & Local OS Context
                                                     │
                                                     ▼
[Phase 2: Hypothesis]   ──> Send to LLM ──> Receive Local Terminal Commands To Run
                                                     │
                                                     ▼
[Phase 3: Execution]    ──> Run Diagnostics (e.g., netstat, nc) ──> Pipe Output to LLM
                                                     │
                                                     ▼
[Phase 4: Remediation]  ──> LLM Gen Final Fix ──> Render UI ──> Interactive [Y/n] Exec

```

---

## 🗂️ Data Schemas (JSON/Pydantic)

To avoid LLM hallucination or broken outputs, Claude must force the AI to communicate using strict, predictable data schemas.

### 1. The Diagnostic Collection Schema (Turn 1 Output)

When the installation first fails, the LLM must look at the error and output *only* this structure to tell the CLI what diagnostic commands to run:

```python
from pydantic import BaseModel, Field
from typing import List

class DiagnosticPayload(BaseModel):
    hypothesis: str = Field(description="The AI's initial guess of what is wrong based on the installation error.")
    diagnostic_commands: List[str] = Field(description="List of safe, local bash commands to execute to test the hypothesis (e.g., ['nc -zv localhost 5432', 'ufw status']).")

```

### 2. The Remediation Schema (Turn 2 Output)

After the CLI runs those commands and returns the raw terminal text, the LLM processes it and returns the final resolution schema:

```python
class RemediationPayload(BaseModel):
    root_cause: str = Field(description="The precise, isolated reason for the network block.")
    human_explanation: str = Field(description="A plain-English explanation summarizing what is wrong for the developer.")
    remediation_command: str = Field(description="The exact terminal command needed to resolve the issue (e.g., 'sudo ufw allow 5432/tcp').")
    is_destructive: bool = Field(description="Flag true if the remediation command could alter critical system data.")

```

---

## 🎭 Prompt Engineering Blueprints

### System Prompt 1: The Detective (Turn 1)

```text
You are the Intelligent Inference Engine of a DevOps installation CLI wrapper. 
An installation script has just failed. Your job is to select the exact, localized terminal diagnostic utilities needed to isolate the network topology bottleneck.

CRITICAL SAFETY: You may only emit read-only diagnostic commands (e.g., ping, nc, netstat, ufw status, iptables -L, curl). Do NOT emit destructive or modifying commands.

```

### System Prompt 2: The Resolver (Turn 2)

```text
You are the Remediation Engine. You will receive the raw terminal logs generated by the diagnostic commands you previously requested. 
Analyze the logs, isolate the definitive root cause, and synthesize a single, clean, concrete terminal command that the user can execute to permanently fix their local environment mismatch. 
Keep explanations highly punchy, empathetic, and developer-centric.

```

---

## 🧪 Mock Data for Testing & Validation

Provide these mock scenarios so Claude can write unit tests or dry-run simulations without hitting live infrastructure:

### Scenario A: Closed Local Firewall (UFW)

* **Agent Type:** PostgreSQL Monitoring Agent
* **Initial Error Caught:** `dial tcp 127.0.0.1:5432: connect: connection refused`
* **Expected Diagnostic Output:** `nc: connect to localhost (127.0.0.1) port 5432 (tcp) failed: Connection refused`
* **Expected Final Remediation:** `sudo ufw allow 5432/tcp`

### Scenario B: Cloud Security Group/Timeout Block

* **Agent Type:** Cloud Metrics Forwarder
* **Initial Error Caught:** `Error: Connect timed out to telemetry.api.provider.com:443 after 15000ms`
* **Expected Diagnostic Output:** `traceroute to telemetry.api.provider.com... drops off entirely at router hop #4.`
* **Expected Final Remediation:** *"Your corporate outbound proxy or AWS Security Group is dropping packets to our endpoint. Please whitelist outbound TCP traffic to port 443 for telemetry.api.provider.com."*

---

## 🎯 Copy-Paste Prompt to Initialize Claude

Once you choose your path, paste this exact block directly into Claude to generate your codebase boilerplate:

```text
"We are building the Intelligent CLI Diagnostics Layer hackathon project based on the provided technical brief. 

We choose OPTION 1: Python (Typer + Rich) with OpenAI (gpt-4o-mini) using the Instructor library for strict Pydantic parsing.

Please generate a single, fully functional python script (`diagnose_cli.py`) that:
1. Implements a mock 'failed installation' command simulating a blocked port 5432.
2. Implements the Instructor/OpenAI client configuration.
3. Implements the two-turn diagnostic and remediation state machine loop using the exact Pydantic schemas specified.
4. Uses Python's `subprocess` module safely to run the LLM-requested diagnostic checks.
5. Uses the Rich library to print beautiful spinners, layout boxes, and interactive [y/N] prompts for the user to auto-execute the remediation command."

```