"""LLM agent - handles communication with Anthropic API for diagnostics and remediation."""

import json
from typing import List, Optional

from anthropic import Anthropic

from .config import Config
from .context import OSContext
from .registry import Agent as RegistryAgent
from .schemas import DiagnosticPayload, RemediationPayload, StepResult
from .scrub import scrub

SYSTEM_PROMPT_DETECTIVE = """You are the Intelligent Inference Engine of a DevOps installation CLI wrapper.
An installation script step has just failed. You receive the failed command, its
stderr/stdout, exit code, and host OS context.

Your job: select the exact, localized terminal diagnostic commands needed to
isolate the root cause.

ANCHOR TO THE SPECIFIC ERROR:
Read the stderr/stdout carefully. If it contains a specific error code or signature,
your diagnostic commands MUST target the subsystem that produced that error. Do NOT
run network/connectivity checks against unrelated subsystems.

Examples of correct anchoring:
- stderr contains "ORA-01017" (Oracle auth failure) → diagnostics target Oracle:
  e.g. `cat config to confirm credentials present`, `nc -zv ${ORACLE_HOST} ${ORACLE_PORT}`,
  `getent hosts ${ORACLE_HOST}`. DO NOT extract the OTLP endpoint and probe IT.
- stderr contains "HTTP 401" or "PermissionDenied" from otlp.* → diagnostics target the
  OTLP exporter: `curl -v https://${OTLP_HOST}`, check NEW_RELIC_LICENSE_KEY format. DO
  NOT probe Oracle ports.
- stderr contains "name or service not known" / "no such host" → diagnostics target DNS
  for that specific hostname.

CRITICAL SAFETY: You may ONLY emit read-only diagnostic commands (e.g., ping,
nc, netstat, ss, ufw status, iptables -L, curl, systemctl status, lsof, cat, ls,
getent, dig, env, command -v).
Do NOT emit destructive or modifying commands.

You MUST respond with ONLY a valid JSON object in this exact format:
{"hypothesis": "your hypothesis", "diagnostic_commands": ["cmd1", "cmd2"]}
"""

SYSTEM_PROMPT_RESOLVER = """You are the Remediation Engine. You receive:
1. The original failed command and its error output
2. The raw terminal output from the diagnostic commands you previously requested
3. (When relevant) The list of user-supplied input variables in scope

Analyze the diagnostic output, isolate the definitive root cause, and provide:
- A precise root cause statement
- A plain-English explanation for the developer
- A single, concrete terminal command to fix the issue (or empty if a re-prompt is the right fix)
- Whether that command is destructive
- `bad_inputs`: if the root cause is a wrong user-supplied input value (credentials, hostnames,
  service names, license keys, ports, endpoints), list the EXACT names of those inputs from the
  "Available Input Variables" section, verbatim. Otherwise return an empty list.

PREFER `bad_inputs` over `remediation_command` whenever the fix is "the user typed the wrong
value". The runner can re-prompt for those inputs, regenerate any affected config files, and
retry the failed step. Editing a generated file (e.g. config.yaml) directly is fragile — the
file is regenerated on every install run, so manual edits are wiped out.

STAY ANCHORED TO THE ORIGINAL ERROR — DO NOT DRIFT ACROSS SUBSYSTEMS:
Your root_cause MUST address the SAME subsystem that produced the original error code/signature.
- Original error contains an Oracle ORA-XXXXX code → root_cause is about Oracle (creds, service,
  host, port, grants). DO NOT attribute it to OTLP/New Relic endpoint issues.
- Original error contains HTTP 4xx from an otlp.* host → root_cause is about NR ingest
  (wrong license key or wrong endpoint for the region). DO NOT attribute it to Oracle.
- Original error contains DNS/hostname resolution failure → root_cause is about that specific
  hostname only.

If the diagnostic results suggest a different subsystem than the one that produced the original
error, that is almost always misleading — trust the original error, not the secondary signal.
The diagnostic commands may have probed the wrong thing; ignore them in that case.

When the user prompt includes "context_hints" with explicit error-code → input mappings, USE
THEM. Those mappings are authoritative for this agent.

CRITICAL — DO NOT MISREAD RENDERED CONFIG FILES:
Any config file you see in diagnostic output (e.g. `cat /etc/.../config.yaml`) has ALREADY had
its `${VAR}` references substituted with the user's actual input values at install time, by
bash heredoc. If you see something like `oracle://otel:password@oracle:1521/FREEPDB1` in the
file, that means the user literally typed `password` as their password — NOT that the template
wasn't filled in. The values you see ARE the user-supplied values.

So:
- DO NOT phrase root_cause as "hardcoded credentials" or "placeholder values weren't
  substituted" or "config generator didn't substitute the variables". Substitution happened.
- DO phrase it as "the user-supplied value for X is wrong" — and put X in `bad_inputs`.
- Weak-looking values (`password`, `localhost`, `test`) are user input, not unfilled templates.

Keep explanations punchy, empathetic, and developer-centric.

You MUST respond with ONLY a valid JSON object in this exact format:
{"root_cause": "...", "human_explanation": "...", "remediation_command": "...", "is_destructive": false, "bad_inputs": []}
"""


class LLMAgent:
    """Handles LLM communication for diagnostics and remediation."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = Anthropic(
            auth_token=cfg.api_key,
            base_url=cfg.base_url,
        )

    def diagnose(self, step: StepResult, os_ctx: OSContext, agent_info: Optional[RegistryAgent]) -> DiagnosticPayload:
        """Turn 1: Send failure context to LLM, get diagnostic commands back."""
        user_prompt = _build_diagnostic_prompt(step, os_ctx, agent_info)
        user_prompt = scrub(user_prompt)

        response = self._chat(SYSTEM_PROMPT_DETECTIVE, user_prompt)

        data = json.loads(_extract_json(response))
        return DiagnosticPayload(
            hypothesis=data.get("hypothesis", ""),
            diagnostic_commands=data.get("diagnostic_commands", []),
        )

    def remediate(
        self,
        step: StepResult,
        diagnostic_results: dict,
        agent_info: Optional[RegistryAgent],
        available_inputs: Optional[List[str]] = None,
    ) -> RemediationPayload:
        """Turn 2: Send diagnostic results to LLM, get fix back."""
        user_prompt = _build_remediation_prompt(step, diagnostic_results, agent_info, available_inputs)
        user_prompt = scrub(user_prompt)

        response = self._chat(SYSTEM_PROMPT_RESOLVER, user_prompt)

        data = json.loads(_extract_json(response))
        return RemediationPayload(
            root_cause=data.get("root_cause", ""),
            human_explanation=data.get("human_explanation", ""),
            remediation_command=data.get("remediation_command", ""),
            is_destructive=data.get("is_destructive", False),
            bad_inputs=data.get("bad_inputs", []) or [],
        )

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a message to the Anthropic API and return the response text."""
        message = self.client.messages.create(
            model=self.cfg.model,
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ],
        )
        return message.content[0].text


def _build_diagnostic_prompt(step: StepResult, os_ctx: OSContext, agent_info: Optional[RegistryAgent]) -> str:
    """Build the user prompt for Turn 1 (diagnostic)."""
    parts = []
    parts.append(f"## Failed Command\n```\n{step.command}\n```\n")
    parts.append(f"## Exit Code: {step.exit_code}\n")

    if step.stdout:
        parts.append(f"## Stdout\n```\n{step.stdout}\n```\n")
    if step.stderr:
        parts.append(f"## Stderr\n```\n{step.stderr}\n```\n")

    parts.append(f"## OS Context\n{os_ctx.to_string()}\n")

    if agent_info:
        if agent_info.knowledge.common_failures:
            parts.append(f"## Known Failure Modes for {agent_info.manifest.display_name}\n{agent_info.knowledge.common_failures}\n")
        if agent_info.knowledge.prerequisites:
            parts.append(f"## Prerequisites\n{agent_info.knowledge.prerequisites}\n")
        if agent_info.hints.priority_commands:
            parts.append("## Suggested Diagnostic Commands (prioritize these)\n")
            for cmd in agent_info.hints.priority_commands:
                parts.append(f"- {cmd}")
            parts.append("")
        if agent_info.hints.context_hints:
            parts.append("## Domain Context\n")
            for hint in agent_info.hints.context_hints:
                parts.append(f"- {hint}")
            parts.append("")

    return "\n".join(parts)


def _build_remediation_prompt(
    step: StepResult,
    diagnostic_results: dict,
    agent_info: Optional[RegistryAgent],
    available_inputs: Optional[List[str]] = None,
) -> str:
    """Build the user prompt for Turn 2 (remediation)."""
    parts = []
    parts.append(f"## Original Failed Command\n```\n{step.command}\n```\n")

    if step.stderr:
        parts.append(f"## Original Error\n```\n{step.stderr}\n```\n")

    parts.append("## Diagnostic Results\n")
    for cmd, output in diagnostic_results.items():
        parts.append(f"### `{cmd}`\n```\n{output}\n```\n")

    # Authoritative error-code → input mappings from the agent. Resolver must use these.
    if agent_info and agent_info.hints.context_hints:
        parts.append("## Domain Context (authoritative — apply these to populate `bad_inputs`)\n")
        for hint in agent_info.hints.context_hints:
            parts.append(f"- {hint}")
        parts.append("")

    if available_inputs:
        parts.append("## Available Input Variables (use these names verbatim in `bad_inputs`)\n")
        for name in available_inputs:
            parts.append(f"- {name}")
        parts.append("")

    return "\n".join(parts)


def _extract_json(s: str) -> str:
    """Extract JSON object from a response that may contain markdown code fences."""
    s = s.strip()

    # Remove code fences
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()

    # Find the JSON object
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        return s[start:end + 1]
    return s
