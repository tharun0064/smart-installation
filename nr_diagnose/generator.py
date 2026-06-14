"""Auto-generates agent files (install.sh, manifest, hints) from knowledge docs using LLM."""

import json
from typing import Optional

from anthropic import Anthropic

from .config import Config
from .registry import Agent as RegistryAgent

SYSTEM_PROMPT_GENERATOR = """You are an expert DevOps engineer. The user wants to install a monitoring agent/integration.
They have provided documentation, prerequisites, and references about what they want to install.

Your job: Generate a complete, production-ready bash installation script based on the provided documentation.

Rules:
- Each step should be one atomic command (one thing that can succeed or fail)
- Add comments before each step explaining what it does (# Step N: description)
- Use standard package managers (apt, dpkg, yum, dnf) for installs
- Use heredocs (<<'EOF' ... EOF) for writing config files
- Use environment variables for secrets (e.g., ${NEW_RELIC_LICENSE_KEY}, ${DB_PASSWORD})
- Include verification steps (check connectivity, check service is running, etc.)
- Do NOT use sudo (the script runs as root in containers, or the user handles permissions)
- Keep it simple and linear — no conditionals or loops

You MUST respond with ONLY a valid JSON object in this exact format:
{
  "install_script": "#!/bin/bash\\n# Full script here...",
  "manifest": {
    "display_name": "Human-readable name",
    "description": "One-line description",
    "target_os": "linux",
    "ports": [1521],
    "services": ["otelcol-contrib"],
    "prerequisites": ["Prereq 1", "Prereq 2"]
  },
  "hints": {
    "priority_commands": ["cmd1", "cmd2"],
    "context_hints": ["hint1", "hint2"]
  },
  "common_failures": "# Common Failures\\n\\n## Failure mode 1\\n- cause\\n- cause"
}
"""


def has_real_content(text: str) -> bool:
    """Check if a knowledge file has real user-provided content (not just TODO placeholders)."""
    if not text:
        return False
    # Strip markdown headers and whitespace
    lines = [l.strip() for l in text.strip().splitlines() if l.strip() and not l.strip().startswith("#")]
    if not lines:
        return False
    # If all remaining lines are just TODO placeholders, it's not real content
    for line in lines:
        if not line.upper().startswith("TODO"):
            return True
    return False


def generate_agent_files(cfg: Config, agent: RegistryAgent) -> Optional[dict]:
    """Read knowledge files and generate install.sh + other agent files via LLM.

    Returns a dict with keys: install_script, manifest, hints, common_failures
    Or None if generation fails.
    """
    # Collect all knowledge the user has provided (skip TODO-only placeholders)
    knowledge_parts = []

    if has_real_content(agent.knowledge.references):
        knowledge_parts.append(f"## Documentation / References\n{agent.knowledge.references}")

    if has_real_content(agent.knowledge.prerequisites):
        knowledge_parts.append(f"## Prerequisites\n{agent.knowledge.prerequisites}")

    if has_real_content(agent.knowledge.common_failures):
        knowledge_parts.append(f"## Known Failure Modes\n{agent.knowledge.common_failures}")

    if not knowledge_parts:
        return None

    # Build the user prompt
    user_prompt = f"""Agent name: {agent.manifest.name}

The user has provided the following documentation and context for this integration.
Generate a complete installation script and agent configuration based on this information.

{chr(10).join(knowledge_parts)}
"""

    # Call LLM
    client = Anthropic(
        auth_token=cfg.api_key,
        base_url=cfg.base_url,
    )

    message = client.messages.create(
        model=cfg.model,
        max_tokens=4096,
        system=SYSTEM_PROMPT_GENERATOR,
        messages=[{"role": "user", "content": user_prompt}],
    )

    response_text = message.content[0].text

    # Parse JSON response
    try:
        data = json.loads(_extract_json(response_text))
        return data
    except (json.JSONDecodeError, KeyError) as e:
        return None


def is_template(install_script: str) -> bool:
    """Check if the install.sh is still the default template."""
    return "TODO: Add installation steps" in install_script


def _extract_json(s: str) -> str:
    """Extract JSON object from a response that may contain markdown code fences."""
    s = s.strip()
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()

    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        return s[start:end + 1]
    return s
