"""Interactive collection of user inputs (credentials, hostnames) referenced by install steps."""

import getpass
import os
import re
import shlex
from pathlib import Path
from typing import Dict, List, Optional

from .parser import Step
from .registry import Agent as RegistryAgent
from .schemas import RequiredInput
from . import ui


# ${VAR}, ${VAR:-default}, ${VAR:default}, ${VAR-default}
ENV_VAR_REF = re.compile(r"\$\{(\w+)(?::?[-=]?([^}]*))?\}")

# Heuristic — names that look like secrets even if not declared in manifest
SECRET_HINTS = ("PASSWORD", "PASSWD", "SECRET", "TOKEN", "KEY", "API_KEY", "LICENSE")


def scan_required_vars(steps: List[Step]) -> Dict[str, str]:
    """Find every ${VAR} referenced across all steps. Returns {name: default_or_empty}."""
    found: Dict[str, str] = {}
    for step in steps:
        for match in ENV_VAR_REF.finditer(step.command):
            name = match.group(1)
            default = match.group(2) or ""
            # Don't overwrite a real default with an empty one if the var appears twice
            if name not in found or (not found[name] and default):
                found[name] = default
    return found


def load_saved_config(agent_dir: str) -> Dict[str, str]:
    """Load previously-saved input values from <agent_dir>/.config.env, if any."""
    path = Path(agent_dir) / ".config.env"
    if not path.exists():
        return {}
    values: Dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        try:
            tokens = shlex.split(v, posix=True)
            values[k.strip()] = tokens[0] if tokens else ""
        except ValueError:
            values[k.strip()] = v
    return values


def save_config(agent_dir: str, values: Dict[str, str]) -> str:
    """Write values to <agent_dir>/.config.env. Returns the path."""
    path = Path(agent_dir) / ".config.env"
    lines = ["# nr-diagnose: saved inputs (do not commit)"]
    for k, v in values.items():
        lines.append(f"{k}={shlex.quote(v)}")
    path.write_text("\n".join(lines) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return str(path)


def _is_secret(name: str, declared: Optional[RequiredInput]) -> bool:
    if declared is not None:
        return declared.secret
    upper = name.upper()
    return any(h in upper for h in SECRET_HINTS)


def collect(steps: List[Step], agent_info: Optional[RegistryAgent]) -> Dict[str, str]:
    """Prompt the user for every ${VAR} referenced in steps, with manifest-driven labels.

    Reads any previously-saved values from <agent_dir>/.config.env and offers to reuse them.
    Returns a {name: value} dict the runner can merge into subprocess env.
    """
    required = scan_required_vars(steps)
    if not required:
        return {}

    declared_by_name: Dict[str, RequiredInput] = {}
    if agent_info:
        declared_by_name = {ri.name: ri for ri in agent_info.manifest.required_inputs}

    saved: Dict[str, str] = {}
    if agent_info and agent_info.dir:
        saved = load_saved_config(agent_info.dir)

    # Show what we're about to ask for
    ui.show_required_inputs([
        (name, declared_by_name.get(name).description if name in declared_by_name else "",
         _is_secret(name, declared_by_name.get(name)),
         saved.get(name, ""))
        for name in sorted(required.keys())
    ])

    # Always prompt every input. Saved values appear as the [default] so you can hit
    # Enter to reuse them, but nothing is ever applied silently.
    values: Dict[str, str] = {}
    for name in sorted(required.keys()):
        declared = declared_by_name.get(name)
        secret = _is_secret(name, declared)
        description = declared.description if declared else ""
        script_default = required[name]
        manifest_default = declared.default if declared else ""
        # Prefill priority: shell env > saved value > manifest default > script default.
        # Env vars set in compose/CI/shell are always the most intentional for this run.
        env_value = os.environ.get(name, "")
        prefilled = env_value or saved.get(name, "") or manifest_default or script_default

        value = ui.prompt_input(
            name=name,
            description=description,
            secret=secret,
            default=prefilled,
        )
        if not value and prefilled:
            value = prefilled
        values[name] = value

    if agent_info and agent_info.dir:
        path = save_config(agent_info.dir, values)
        ui.show_config_saved(path)

    return values
