"""Terminal UI - Rich-based output for step progress and remediation display."""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from .schemas import RemediationPayload

console = Console()


def step_start(step_num: int, total: int, command: str) -> None:
    """Display a step starting."""
    console.print(f"[dim][{step_num}/{total}][/dim] {command}")


def step_success(step_num: int, total: int, command: str) -> None:
    """Display a step completing successfully."""
    console.print(f"[green]\u2713[/green] [dim][{step_num}/{total}][/dim] {command}")


def step_failure(step_num: int, total: int, command: str, stderr: str = "") -> None:
    """Display a step failure."""
    console.print(f"[red]\u2717[/red] [dim][{step_num}/{total}][/dim] [red]{command}[/red]")
    if stderr:
        truncated = stderr.strip()[:200]
        console.print(f"  [dim]{truncated}[/dim]")


def diagnosing() -> None:
    """Show that AI is diagnosing."""
    console.print(f"\n[blue]\u27f3[/blue] AI Agent diagnosing failure...")


def running_diagnostics() -> None:
    """Show that diagnostic commands are being run."""
    console.print(f"[blue]\u27f3[/blue] Running diagnostic commands...")


def show_hypothesis(hypothesis: str) -> None:
    """Display the AI's hypothesis."""
    console.print(f"[blue]Hypothesis:[/blue] {hypothesis}")


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

    console.print(f"[blue]Explanation:[/blue] {payload.human_explanation}\n")

    if payload.is_destructive:
        console.print(Panel(
            f"Suggested Fix:\n  {payload.remediation_command}\n\n\u26a0  WARNING: This command is destructive!",
            border_style="red",
        ))
    else:
        console.print(f"[yellow]Suggested Fix:[/yellow]")
        console.print(f"  {payload.remediation_command}\n")


def prompt_action(is_destructive: bool = False) -> str:
    """Prompt user for action on remediation. Returns 'y', 'n', or 'q'."""
    if is_destructive:
        prompt_text = "[yellow]Execute this DESTRUCTIVE fix? [Y]es / [n]o (skip step) / [q]uit[/yellow]"
    else:
        prompt_text = "Execute this fix? [Y]es / [n]o (skip step) / [q]uit"

    response = Prompt.ask(prompt_text, default="y")
    response = response.strip().lower()

    if response in ("y", "yes"):
        return "y"
    elif response in ("q", "quit"):
        return "q"
    else:
        return "n"


def fix_applied(success: bool) -> None:
    """Show fix result."""
    if success:
        console.print("[green]\u2713[/green] Fix applied successfully. Re-running step...\n")
    else:
        console.print("[red]\u2717[/red] Fix did not resolve the issue.")


def summary(total: int, passed: int, failed: int, skipped: int) -> None:
    """Show final execution summary."""
    console.print(f"\n{'─' * 50}")
    console.print(
        f"Steps: {total} total, "
        f"[green]{passed}[/green] passed, "
        f"[red]{failed}[/red] failed, "
        f"[yellow]{skipped}[/yellow] skipped"
    )
