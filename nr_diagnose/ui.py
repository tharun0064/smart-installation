"""Terminal UI - Rich-based output for step progress and remediation display."""

import getpass
from typing import List, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from .schemas import RemediationPayload

console = Console()


def step_start(step_num: int, total: int, command: str, description: str = "", needs_approval: bool = False) -> None:
    """Display a step starting with its description."""
    console.print(f"\n{'─' * 60}")
    marker = "[yellow]?[/yellow]" if needs_approval else "[green]>[/green]"
    console.print(f"{marker} [bold]\\[{step_num}/{total}][/bold]", end=" ")
    if description:
        console.print(f"[blue]{description}[/blue]")
    else:
        console.print()

    # For long commands (heredocs), show a truncated preview
    if "\n" in command:
        first_line = command.split("\n")[0]
        line_count = len(command.split("\n"))
        console.print(f"  [dim]{first_line} ... ({line_count} lines)[/dim]")
    else:
        console.print(f"  [dim]{command}[/dim]")


def prompt_step_approval(step_num: int, total: int) -> str:
    """Prompt user before executing a step. Returns 'y', 'n' (skip), or 'q' (quit)."""
    response = Prompt.ask(
        "  Proceed? [green]\\[Y]es[/green] / [dim]\\[s]kip[/dim] / [dim]\\[q]uit[/dim]",
        default="y",
    )
    response = response.strip().lower()
    if response in ("y", "yes"):
        return "y"
    elif response in ("q", "quit"):
        return "q"
    else:
        return "n"


def step_success(step_num: int, total: int, command: str, description: str = "") -> None:
    """Display a step completing successfully."""
    label = description if description else _truncate_command(command)
    console.print(f"  [green]\u2713[/green] {label}")


def step_failure(step_num: int, total: int, command: str, stderr: str = "") -> None:
    """Display a step failure."""
    console.print(f"  [red]\u2717 FAILED[/red]")
    if stderr:
        truncated = stderr.strip()[:300]
        console.print(f"  [red]{truncated}[/red]")


def diagnosing() -> None:
    """Show that AI is diagnosing."""
    console.print(f"\n  [blue]\u27f3[/blue] [bold]AI Agent analyzing failure...[/bold]")


def running_diagnostics() -> None:
    """Show that diagnostic commands are being run."""
    console.print(f"  [blue]\u27f3[/blue] Running diagnostic commands...")


def show_hypothesis(hypothesis: str) -> None:
    """Display the AI's hypothesis."""
    console.print(f"  [blue]Hypothesis:[/blue] {hypothesis}")


def show_diagnostic_commands(commands: list) -> None:
    """Display the diagnostic commands the AI wants to run."""
    console.print("\n  [blue]To investigate, I'd like to run:[/blue]")
    for cmd in commands:
        console.print(f"    [dim]$[/dim] {cmd}")


def prompt_diagnostics_approval() -> str:
    """Ask user to approve running diagnostic commands. Returns 'y' or 'n'."""
    response = Prompt.ask(
        "\n  Run these? [green]\\[Y]es[/green] / [dim]\\[n]o[/dim]",
        default="y",
    )
    response = response.strip().lower()
    if response in ("y", "yes"):
        return "y"
    return "n"


def show_remediation(payload: RemediationPayload, from_runbook: bool = False, resolved_count: int = 0) -> None:
    """Display the remediation information."""
    console.print()

    title = "Root Cause"
    if from_runbook:
        title = "Root Cause (from runbook)"
        if resolved_count > 0:
            title = f"Root Cause (from runbook, resolved {resolved_count} times)"

    console.print(Panel(
        payload.root_cause,
        title=title,
        border_style="blue",
    ))

    console.print(f"  [blue]Explanation:[/blue] {payload.human_explanation}\n")

    if payload.is_destructive:
        console.print(Panel(
            f"Suggested Fix:\n  {payload.remediation_command}\n\n\u26a0  WARNING: This command may modify your system!",
            border_style="red",
        ))
    else:
        console.print(f"  [yellow]Suggested Fix:[/yellow]")
        console.print(f"    [bold]{payload.remediation_command}[/bold]\n")


def prompt_action(is_destructive: bool = False) -> str:
    """Prompt user for action on remediation.

    Returns:
        'y'     - execute the fix automatically
        'n'     - skip this step
        'q'     - quit execution
        'retry' - user fixed it manually, retry the step
    """
    if is_destructive:
        console.print("  [yellow]\u26a0  This command may modify your system![/yellow]")

    console.print("  [green]\\[Y]es[/green]       - run this fix for me")
    console.print("  [cyan]\\[r]etry[/cyan]     - I fixed it myself, retry the step")
    console.print("  [dim]\\[n]o (skip)[/dim] - skip this step and continue")
    console.print("  [dim]\\[q]uit[/dim]      - stop execution")

    response = Prompt.ask("\n  What would you like to do?", default="y")
    response = response.strip().lower()

    if response in ("y", "yes"):
        return "y"
    elif response in ("r", "retry", "fixed", "done"):
        return "retry"
    elif response in ("q", "quit"):
        return "q"
    else:
        return "n"


def fix_applied(success: bool) -> None:
    """Show fix result."""
    if success:
        console.print("  [green]\u2713[/green] Fix applied successfully. Re-running step...\n")
    else:
        console.print("  [red]\u2717[/red] Fix did not resolve the issue.\n")


def summary(total: int, passed: int, failed: int, skipped: int) -> None:
    """Show final execution summary."""
    console.print(f"\n{'─' * 60}")
    console.print(
        f"  Steps: {total} total, "
        f"[green]{passed} passed[/green], "
        f"[red]{failed} failed[/red], "
        f"[yellow]{skipped} skipped[/yellow]"
    )


def show_completion_summary(result, agent_info=None) -> None:
    """Show a comprehensive end-of-run summary."""
    console.print(f"\n{'═' * 60}")

    if result.failed == 0 and result.passed > 0:
        console.print("[bold green]  Installation Complete![/bold green]")
    elif result.failed > 0:
        console.print("[bold yellow]  Installation Finished (with issues)[/bold yellow]")
    else:
        console.print("[bold]  Installation Summary[/bold]")

    console.print(f"{'─' * 60}")
    console.print(
        f"  Steps: {result.total} total, "
        f"[green]{result.passed} passed[/green], "
        f"[red]{result.failed} failed[/red], "
        f"[yellow]{result.skipped} skipped[/yellow]"
    )

    if result.config_files:
        console.print(f"\n  [bold]Configuration files:[/bold]")
        for f in result.config_files:
            console.print(f"    {f}")

    if result.services:
        console.print(f"\n  [bold]Services enabled:[/bold]")
        for s in result.services:
            console.print(f"    {s}")

    if agent_info:
        console.print(f"\n  [bold]Next steps:[/bold]")
        if result.failed == 0:
            console.print("    1. Verify credentials in the environment/config file")
            console.print("    2. Restart the service after updating credentials")
            console.print("    3. Check logs to confirm data is flowing")
            if result.services:
                svc = result.services[0]
                console.print(f"\n  [dim]Monitor logs:  journalctl -u {svc} -f[/dim]")
                console.print(f"  [dim]Check status:  systemctl status {svc}[/dim]")
        else:
            console.print("    1. Fix the failed steps above")
            console.print("    2. Re-run: nr-diagnose run --agent " +
                          (agent_info.manifest.name if agent_info else "<name>"))

    console.print(f"{'═' * 60}\n")


def show_required_inputs(rows: List[Tuple[str, str, bool, str]]) -> None:
    """Print the list of inputs we'll prompt for. Each row: (name, description, secret, saved_value)."""
    if not rows:
        return
    console.print(f"\n{'─' * 60}")
    console.print("[bold]Configuration inputs[/bold]")
    console.print("[dim]These values will be substituted into the install script.[/dim]\n")
    for name, description, secret, saved in rows:
        tag = " [yellow](secret)[/yellow]" if secret else ""
        status = " [green]✓ saved[/green]" if saved else ""
        line = f"  [cyan]{name}[/cyan]{tag}{status}"
        if description:
            line += f"  [dim]— {description}[/dim]"
        console.print(line)


def prompt_use_saved_config() -> bool:
    """Ask whether to reuse previously-saved values."""
    response = Prompt.ask(
        "\n  Saved values found. Use them? [green]\\[Y]es[/green] / [dim]\\[n]o, re-prompt[/dim]",
        default="y",
    )
    return response.strip().lower() in ("y", "yes", "")


def prompt_input(name: str, description: str = "", secret: bool = False, default: str = "") -> str:
    """Prompt for a single input. Masks secrets via getpass."""
    label = f"  [cyan]{name}[/cyan]"
    if description:
        label += f" [dim]({description})[/dim]"
    if default and not secret:
        label += f" [dim]\\[{default}][/dim]"
    elif default and secret:
        label += " [dim]\\[saved, press Enter to keep][/dim]"
    console.print(label)

    if secret:
        try:
            value = getpass.getpass("    > ")
        except (EOFError, KeyboardInterrupt):
            value = ""
    else:
        try:
            value = input("    > ")
        except (EOFError, KeyboardInterrupt):
            value = ""

    return value.strip()


def show_input_reused(name: str, secret: bool, value: str) -> None:
    """Confirm that a saved input was reused."""
    shown = "*" * 8 if secret else value
    console.print(f"  [green]✓[/green] [cyan]{name}[/cyan] = [dim]{shown}[/dim]")


def show_config_saved(path: str) -> None:
    """Confirm that inputs were saved."""
    console.print(f"\n  [green]✓[/green] Saved inputs to [dim]{path}[/dim]")


def validation_start(total: int) -> None:
    """Header before the post-install validation pass."""
    console.print(f"\n{'═' * 60}")
    console.print(f"[bold]Post-install validation[/bold] [dim]({total} checks)[/dim]")
    console.print(f"{'═' * 60}")


def validation_check_start(idx: int, total: int, command: str) -> None:
    """Show a validation check starting."""
    console.print(f"\n  [blue]⟳[/blue] [bold]\\[{idx}/{total}][/bold] [dim]{command}[/dim]")


def validation_check_pass(command: str) -> None:
    """Show a validation check passing."""
    console.print(f"  [green]✓[/green] [dim]{command}[/dim]")


def validation_check_fail(command: str, stderr: str) -> None:
    """Show a validation check failing."""
    console.print(f"  [red]✗ FAILED[/red] [dim]{command}[/dim]")
    if stderr:
        console.print(f"  [red]{stderr.strip()[:300]}[/red]")


def validation_summary(passed: int, failed: int) -> None:
    """End-of-validation summary."""
    console.print(f"\n{'─' * 60}")
    if failed == 0:
        console.print(f"  [bold green]✓ All {passed} validation checks passed.[/bold green]")
    else:
        console.print(
            f"  [green]{passed} passed[/green], "
            f"[red]{failed} failed[/red]"
        )


def _truncate_command(command: str, max_len: int = 80) -> str:
    """Truncate a command for display."""
    if "\n" in command:
        return command.split("\n")[0][:max_len] + "..."
    if len(command) > max_len:
        return command[:max_len] + "..."
    return command
