"""Agent registry - loads agent definitions from disk."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

import yaml

from .schemas import AgentManifest, DiagnosticHints, RunbookIndex, RunbookIndexEntry


@dataclass
class AgentKnowledge:
    prerequisites: str = ""
    common_failures: str = ""
    references: str = ""


@dataclass
class Agent:
    manifest: AgentManifest = field(default_factory=AgentManifest)
    install_script: str = ""
    knowledge: AgentKnowledge = field(default_factory=AgentKnowledge)
    hints: DiagnosticHints = field(default_factory=DiagnosticHints)
    runbook_index: RunbookIndex = field(default_factory=RunbookIndex)
    dir: str = ""


def load_agent(agent_dir: str) -> Agent:
    """Load an agent definition from a directory."""
    agent = Agent(dir=agent_dir)
    agent_path = Path(agent_dir)

    # Load manifest
    manifest_data = yaml.safe_load((agent_path / "manifest.yaml").read_text())
    agent.manifest = AgentManifest(
        name=manifest_data.get("name", ""),
        display_name=manifest_data.get("display_name", ""),
        description=manifest_data.get("description", ""),
        target_os=manifest_data.get("target_os", ""),
        ports=manifest_data.get("ports", []),
        services=manifest_data.get("services", []),
        prerequisites=manifest_data.get("prerequisites", []),
    )

    # Load install script
    agent.install_script = (agent_path / "install.sh").read_text()

    # Load knowledge files
    agent.knowledge = AgentKnowledge(
        prerequisites=_read_file_or_empty(agent_path / "knowledge" / "prerequisites.md"),
        common_failures=_read_file_or_empty(agent_path / "knowledge" / "common-failures.md"),
        references=_read_file_or_empty(agent_path / "knowledge" / "references.md"),
    )

    # Load diagnostic hints
    hints_path = agent_path / "diagnostics" / "hints.yaml"
    if hints_path.exists():
        hints_data = yaml.safe_load(hints_path.read_text()) or {}
        agent.hints = DiagnosticHints(
            priority_commands=hints_data.get("priority_commands", []),
            context_hints=hints_data.get("context_hints", []),
        )

    # Load runbook index
    index_path = agent_path / "runbook" / "index.yaml"
    if index_path.exists():
        index_data = yaml.safe_load(index_path.read_text()) or {}
        entries = [
            RunbookIndexEntry(pattern=e.get("pattern", ""), entry_file=e.get("entry_file", ""))
            for e in index_data.get("entries", [])
        ]
        agent.runbook_index = RunbookIndex(entries=entries)

    return agent


def list_agents(agents_dir: str) -> List[AgentManifest]:
    """Return manifests of all agents in the directory (excluding _template)."""
    agents: List[AgentManifest] = []
    agents_path = Path(agents_dir)

    if not agents_path.exists():
        return agents

    for entry in sorted(agents_path.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        manifest_path = entry / "manifest.yaml"
        if not manifest_path.exists():
            continue
        try:
            data = yaml.safe_load(manifest_path.read_text())
            agents.append(AgentManifest(
                name=data.get("name", ""),
                display_name=data.get("display_name", ""),
                description=data.get("description", ""),
                target_os=data.get("target_os", ""),
                ports=data.get("ports", []),
                services=data.get("services", []),
                prerequisites=data.get("prerequisites", []),
            ))
        except Exception:
            continue

    return agents


def find_agent_dir(agents_dir: str, agent_name: str) -> str:
    """Locate an agent directory by name within the agents folder."""
    dir_path = Path(agents_dir) / agent_name
    if not (dir_path / "manifest.yaml").exists():
        raise FileNotFoundError(f'agent "{agent_name}" not found in {agents_dir}')
    return str(dir_path)


def _read_file_or_empty(path: Path) -> str:
    """Read a file or return empty string if it doesn't exist."""
    try:
        return path.read_text()
    except (FileNotFoundError, OSError):
        return ""
