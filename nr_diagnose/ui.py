"""Terminal UI - Rich-based output for step progress and remediation display."""

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


def show_preflight_start(config_path: str) -> None:
    """Show config validation starting."""
    console.print(f"\n  [blue]⚙[/blue] [bold]Pre-flight config validation[/bold] for {config_path}")


def prompt_config_var(var_name: str, current_value: str, validation_type: str) -> str:
    """Prompt user to confirm/provide a config variable."""
    if validation_type == "password" and current_value:
        display = current_value[:3] + "***"
    else:
        display = current_value or "[not set]"
    return Prompt.ask(f"    {var_name} ({display})", default=current_value)


def show_preflight_check(description: str, passed: bool) -> None:
    """Show pass/fail for a single preflight check."""
    mark = "[green]✓[/green]" if passed else "[red]✗[/red]"
    console.print(f"    {mark} {description}")


def show_preflight_summary(result) -> None:
    """Summary of all preflight checks."""
    if result.passed:
        console.print(f"  [green]✓[/green] All pre-flight checks passed")
    else:
        console.print(f"  [red]✗[/red] {len(result.errors)} pre-flight check(s) failed:")
        for err in result.errors:
            console.print(f"    [red]• {err}[/red]")


def prompt_preflight_failure() -> str:
    """When preflight fails. Returns 'f', 's', or 'q'."""
    response = Prompt.ask(
        "\n  [green]\\[f]ix[/green] and re-check / [dim]\\[s]kip[/dim] / [dim]\\[q]uit[/dim]",
        default="f",
    )
    r = response.strip().lower()
    if r in ("f", "fix"):
        return "f"
    elif r in ("q", "quit"):
        return "q"
    return "s"


def show_log_monitoring(service_id: str, duration: int = 15) -> None:
    """Show log monitoring starting."""
    console.print(f"\n  [blue]⏱[/blue] Monitoring [bold]{service_id}[/bold] logs for {duration}s...")


def show_log_errors(errors_found: list, error_categories: list) -> None:
    """Display detected errors from log monitoring."""
    console.print(f"\n  [red]⚠[/red] [bold]Errors detected in service logs:[/bold]")
    for error in errors_found[:5]:
        console.print(f"    [red]{error.strip()[:120]}[/red]")
    if error_categories:
        cats = list(set(error_categories))
        console.print(f"  [dim]Categories: {', '.join(cats)}[/dim]")


def show_log_clean(duration: int) -> None:
    """Show logs were clean."""
    console.print(f"  [green]✓[/green] Logs clean for {duration}s — proceeding")


def show_retry_iteration(iteration: int) -> None:
    """Show retry loop iteration number."""
    console.print(f"\n  [yellow]↻[/yellow] [bold]Diagnosis attempt #{iteration}[/bold]")


def _truncate_command(command: str, max_len: int = 80) -> str:
    """Truncate a command for display."""
    if "\n" in command:
        return command.split("\n")[0][:max_len] + "..."
    if len(command) > max_len:
        return command[:max_len] + "..."
    return command
