"""CLI commands - Typer-based entry points for nr-diagnose."""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import typer

from . import config as cfg_module
from .agent import LLMAgent
from .parser import parse_script
from .registry import find_agent_dir, list_agents, load_agent
from .runbook import Manager as RunbookManager
from .runner import Options, run

app = typer.Typer(
    name="nr-diagnose",
    help="Intelligent CLI diagnostics for New Relic agent installations",
    add_completion=False,
)


def _resolve_agents_dir(agents_dir: str) -> str:
    """Resolve the agents directory path."""
    if agents_dir:
        return agents_dir

    # Try relative to script location, then cwd
    script_dir = Path(__file__).parent.parent.parent
    candidates = [
        script_dir / "agents",
        Path.cwd() / "agents",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return str(Path.cwd() / "agents")


@app.command("run")
def run_cmd(
    script_path: Optional[str] = typer.Argument(None, help="Path to installation script"),
    agent: str = typer.Option("", "--agent", "-a", help="Agent name (e.g., otel-oracledb)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show all step output"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse and show steps without executing"),
    model: str = typer.Option("", "--model", "-m", help="LLM model to use (overrides config)"),
):
    """Run an installation script with AI-powered diagnostics."""
    config = cfg_module.load()
    if model:
        config.model = model

    agents_dir = _resolve_agents_dir(config.agents_dir)

    agent_info = None
    script_content = ""

    if agent:
        # Load agent from registry
        try:
            agent_dir = find_agent_dir(agents_dir, agent)
            agent_info = load_agent(agent_dir)
        except (FileNotFoundError, Exception) as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

        script_content = agent_info.install_script
        typer.echo(f"Agent: {agent_info.manifest.display_name}")
        typer.echo(f"Description: {agent_info.manifest.description}\n")
    elif script_path:
        # Load script from file
        try:
            script_content = Path(script_path).read_text()
        except (FileNotFoundError, OSError) as e:
            typer.echo(f"Error reading script: {e}", err=True)
            raise typer.Exit(1)
    else:
        typer.echo("Error: provide --agent <name> or a script path", err=True)
        raise typer.Exit(1)

    # Parse script into steps
    steps = parse_script(script_content)
    if not steps:
        typer.echo("Error: no executable steps found in script", err=True)
        raise typer.Exit(1)

    typer.echo(f"Parsed {len(steps)} steps\n")

    # Set up runbook manager
    seeded_runbook_dir = ""
    local_runbook_dir = os.path.join(config.local_data, "runbook")
    if agent_info:
        seeded_runbook_dir = os.path.join(agent_info.dir, "runbook")
        local_runbook_dir = os.path.join(config.local_data, "runbook", agent_info.manifest.name)
    os.makedirs(local_runbook_dir, exist_ok=True)
    rb_mgr = RunbookManager(seeded_runbook_dir, local_runbook_dir)

    # Set up LLM agent
    llm_agent = None
    if not dry_run:
        llm_agent = LLMAgent(config)

    # Run
    result = run(steps, agent_info, llm_agent, rb_mgr, Options(verbose=verbose, dry_run=dry_run))

    if result.failed > 0:
        raise typer.Exit(1)


@app.command("list")
def list_cmd():
    """List available agents."""
    config = cfg_module.load()
    agents_dir = _resolve_agents_dir(config.agents_dir)

    agents = list_agents(agents_dir)
    if not agents:
        typer.echo("No agents found. Use 'nr-diagnose new-agent <name>' to create one.")
        return

    typer.echo(f"Available agents ({len(agents)}):\n")
    for a in agents:
        typer.echo(f"  {a.name:<20} {a.description}")


@app.command("new-agent")
def new_agent_cmd(name: str = typer.Argument(..., help="Name for the new agent")):
    """Scaffold a new agent from template."""
    config = cfg_module.load()
    agents_dir = _resolve_agents_dir(config.agents_dir)

    agent_dir = Path(agents_dir) / name
    if agent_dir.exists():
        typer.echo(f'Error: agent "{name}" already exists at {agent_dir}', err=True)
        raise typer.Exit(1)

    # Create directory structure
    for subdir in ["knowledge", "diagnostics", "runbook"]:
        (agent_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Write template files
    files = {
        "manifest.yaml": f'''name: {name}
display_name: "{name}"
description: "TODO: Add description"
target_os: linux
ports: []
services: []
prerequisites: []
''',
        "install.sh": f'#!/bin/bash\n# TODO: Add installation steps\necho "Installation script for {name}"\n',
        "knowledge/prerequisites.md": "# Prerequisites\n\nTODO: List what must be true before running install.\n",
        "knowledge/common-failures.md": "# Common Failures\n\nTODO: Document known failure modes and their fixes.\n",
        "knowledge/references.md": "# References\n\nTODO: Add links to official docs and troubleshooting guides.\n",
        "diagnostics/hints.yaml": "priority_commands: []\ncontext_hints: []\n",
        "runbook/index.yaml": "entries: []\n",
    }

    for filepath, content in files.items():
        (agent_dir / filepath).write_text(content)

    typer.echo(f'Created agent "{name}" at {agent_dir}')
    typer.echo("Next steps:")
    typer.echo("  1. Edit manifest.yaml with agent metadata")
    typer.echo("  2. Write install.sh with installation steps")
    typer.echo("  3. Fill in knowledge/ files with domain context")


@app.command("sync")
def sync_cmd():
    """Sync local runbook entries to the shared repository."""
    config = cfg_module.load()
    agents_dir = _resolve_agents_dir(config.agents_dir)

    local_runbook_base = os.path.join(config.local_data, "runbook")
    if not os.path.exists(local_runbook_base):
        typer.echo("No local runbook entries to sync.")
        return

    total_copied = 0
    for entry in os.scandir(local_runbook_base):
        if not entry.is_dir():
            continue
        agent_name = entry.name
        local_dir = os.path.join(local_runbook_base, agent_name)
        repo_dir = os.path.join(agents_dir, agent_name, "runbook")

        if not os.path.exists(repo_dir):
            typer.echo(f"  Skipping {agent_name} (agent not in repo)")
            continue

        # Copy .md files from local to repo
        for f in os.scandir(local_dir):
            if f.is_dir() or not f.name.endswith(".md"):
                continue
            dst = os.path.join(repo_dir, f.name)
            if os.path.exists(dst):
                continue
            shutil.copy2(f.path, dst)
            total_copied += 1

        # Copy index.yaml
        local_index = os.path.join(local_dir, "index.yaml")
        if os.path.exists(local_index):
            shutil.copy2(local_index, os.path.join(repo_dir, "index.yaml"))

    if total_copied == 0:
        typer.echo("No new entries to sync.")
        return

    typer.echo(f"Copied {total_copied} runbook entries to repo.")

    # Git add + commit
    try:
        subprocess.run(["git", "add", agents_dir], check=True, capture_output=True)
        msg = f"runbook: sync {total_copied} local entries"
        subprocess.run(["git", "commit", "-m", msg], check=True, capture_output=True)
        typer.echo("Committed. Run 'git push' to share with team.")
    except subprocess.CalledProcessError:
        typer.echo("Note: git commit failed -- stage and commit manually.")


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
