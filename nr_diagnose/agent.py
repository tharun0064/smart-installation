"""LLM agent - handles communication with Anthropic API for diagnostics and remediation."""

import json
from typing import Optional

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

CRITICAL SAFETY: You may ONLY emit read-only diagnostic commands (e.g., ping,
nc, netstat, ss, ufw status, iptables -L, curl, systemctl status, lsof).
Do NOT emit destructive or modifying commands.

You MUST respond with ONLY a valid JSON object in this exact format:
{"hypothesis": "your hypothesis", "diagnostic_commands": ["cmd1", "cmd2"]}
"""

SYSTEM_PROMPT_RESOLVER = """You are the Remediation Engine. You receive:
1. The original failed command and its error output
2. The raw terminal output from the diagnostic commands you previously requested

Analyze the diagnostic output, isolate the definitive root cause, and provide:
- A precise root cause statement
- A plain-English explanation for the developer
- A single, concrete terminal command to fix the issue
- Whether that command is destructive

Keep explanations punchy, empathetic, and developer-centric.

You MUST respond with ONLY a valid JSON object in this exact format:
{"root_cause": "...", "human_explanation": "...", "remediation_command": "...", "is_destructive": false}
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

    def remediate(self, step: StepResult, diagnostic_results: dict, agent_info: Optional[RegistryAgent]) -> RemediationPayload:
        """Turn 2: Send diagnostic results to LLM, get fix back."""
        user_prompt = _build_remediation_prompt(step, diagnostic_results, agent_info)
        user_prompt = scrub(user_prompt)

        response = self._chat(SYSTEM_PROMPT_RESOLVER, user_prompt)

        data = json.loads(_extract_json(response))
        return RemediationPayload(
            root_cause=data.get("root_cause", ""),
            human_explanation=data.get("human_explanation", ""),
            remediation_command=data.get("remediation_command", ""),
            is_destructive=data.get("is_destructive", False),
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


def _build_remediation_prompt(step: StepResult, diagnostic_results: dict, agent_info: Optional[RegistryAgent]) -> str:
    """Build the user prompt for Turn 2 (remediation)."""
    parts = []
    parts.append(f"## Original Failed Command\n```\n{step.command}\n```\n")

    if step.stderr:
        parts.append(f"## Original Error\n```\n{step.stderr}\n```\n")

    parts.append("## Diagnostic Results\n")
    for cmd, output in diagnostic_results.items():
        parts.append(f"### `{cmd}`\n```\n{output}\n```\n")

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
