"""Main execution runner - executes steps with AI-powered failure handling."""

import re
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

from .agent import LLMAgent
from .context import OSContext, collect
from .diagnostics import run_all
from .parser import Step
from .registry import Agent as RegistryAgent
from .runbook import Manager as RunbookManager
from .schemas import RemediationPayload, RunbookEntry, StepResult
from . import ui


# Commands that modify the system and require user approval
SYSTEM_MODIFYING_PATTERNS = [
    r"\bapt-get\s+update\b",
    r"\bapt-get\s+install\b",
    r"\byum\s+install\b",
    r"\bdnf\s+install\b",
    r"\bpip\s+install\b",
    r"\bwget\b",
    r"\bcurl\s+.*-[oO]\b",
    r"\bcurl\s+.*-fsSL\b",
    r"\bcat\s+.*>\s*/",         # writing config files
    r"\btee\s+/",              # writing via tee
    r"\bmv\b.*\s+/usr/",      # moving to system dirs
    r"\bmv\b.*\s+/etc/",
    r"\bcp\b.*\s+/etc/",
    r"\bsystemctl\s+(start|stop|restart|enable|disable|daemon-reload)\b",
    r"\bservice\s+\w+\s+(start|stop|restart)\b",
    r"\buseradd\b",
    r"\bgroupadd\b",
    r"\bchown\b.*\s+/",
    r"\bchmod\b.*\s+/etc/",
    r"\bchmod\b.*\s+/usr/",
    r"<<['\"]?\w+['\"]?",      # heredocs (writing files)
]

# Commands that are safe to auto-run (read-only / informational)
SAFE_PATTERNS = [
    r"^\s*echo\s",
    r"^\s*sleep\s",
    r"^\s*mkdir\s+-p\s",
    r"^\s*printf\s",
    r"^\s*ps\s",
    r"^\s*systemctl\s+status\b",
    r"^\s*systemctl\s+is-active\b",
    r"^\s*journalctl\b",
    r"^\s*cat\s+/etc/",        # reading (not writing) config
    r"^\s*ls\b",
    r"^\s*which\b",
    r"^\s*command\s+-v\b",
]

# Environment variable pattern
ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


@dataclass
class Options:
    verbose: bool = False
    dry_run: bool = False


@dataclass
class Result:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    config_files: List[str] = field(default_factory=list)
    services: List[str] = field(default_factory=list)
    env_vars_used: List[str] = field(default_factory=list)


def _requires_approval(command: str) -> bool:
    """Determine if a step requires user approval before executing.

    Returns True for system-modifying commands (installs, config writes, service ops).
    Returns False for safe/read-only commands (echo, sleep, status checks).
    """
    # Check if it's explicitly safe first
    for pattern in SAFE_PATTERNS:
        if re.search(pattern, command, re.MULTILINE):
            return False

    # Check if it matches any system-modifying pattern
    for pattern in SYSTEM_MODIFYING_PATTERNS:
        if re.search(pattern, command, re.MULTILINE):
            return True

    # Default: auto-run (most commands that don't match either list are benign)
    return False


def _detect_env_vars(command: str) -> List[str]:
    """Find environment variables referenced in a command."""
    return list(set(ENV_VAR_PATTERN.findall(command)))


def _detect_config_path(command: str) -> Optional[str]:
    """Detect if a command writes a config file, return the path."""
    # cat > /path or cat >> /path
    match = re.search(r"(?:cat|tee)\s+.*?>\s*(/\S+)", command)
    if match:
        return match.group(1)
    # heredoc: cat <<'EOF' > /path
    match = re.search(r">\s*(/\S+)\s*<<", command)
    if match:
        return match.group(1)
    return None


def run(
    steps: List[Step],
    agent_info: Optional[RegistryAgent],
    llm_agent: Optional[LLMAgent],
    rb_mgr: Optional[RunbookManager],
    opts: Options,
) -> Result:
    """Execute all steps with AI-powered failure handling."""
    result = Result(total=len(steps))

    if opts.dry_run:
        ui.console.print("\n[bold]Dry-run mode:[/bold] showing parsed steps without executing\n")
        for i, step in enumerate(steps, 1):
            needs_approval = _requires_approval(step.command)
            marker = "[yellow]*[/yellow]" if needs_approval else "[dim]>[/dim]"
            desc = f" [blue]{step.description}[/blue]" if step.description else ""
            ui.console.print(f"  {marker} [dim]\\[{i}/{len(steps)}][/dim]{desc}")
            # Show truncated command for heredocs
            if "\n" in step.command:
                first_line = step.command.split("\n")[0]
                line_count = len(step.command.split("\n"))
                ui.console.print(f"    [dim]{first_line} ... ({line_count} lines)[/dim]")
            else:
                ui.console.print(f"    [dim]{step.command}[/dim]")
        ui.console.print("\n  [yellow]*[/yellow] = requires approval    [dim]>[/dim] = auto-run")
        return result

    os_ctx = collect()

    for i, step in enumerate(steps):
        step_num = i + 1
        needs_approval = _requires_approval(step.command)

        ui.step_start(step_num, len(steps), step.command, step.description, needs_approval)

        if needs_approval:
            # Ask user for approval before executing
            approval = ui.prompt_step_approval(step_num, len(steps))
            if approval == "q":
                ui.summary(result.total, result.passed, result.failed, result.skipped)
                return result
            elif approval == "n":
                result.skipped += 1
                continue
        else:
            # Auto-run safe commands silently
            ui.console.print("  [dim]auto-running...[/dim]")

        step_result = _execute_step(step_num, step.command)

        if step_result.success:
            ui.step_success(step_num, len(steps), step.command, step.description)
            result.passed += 1

            # Track config files and services for summary
            config_path = _detect_config_path(step.command)
            if config_path:
                result.config_files.append(config_path)
            if "systemctl enable" in step.command:
                match = re.search(r"systemctl\s+enable\s+(\S+)", step.command)
                if match:
                    result.services.append(match.group(1))

            continue

        # Step failed
        ui.step_failure(step_num, len(steps), step.command, step_result.stderr)
        error_output = step_result.stderr or step_result.stdout

        # Check runbook first
        remediation: Optional[RemediationPayload] = None
        from_runbook = False
        resolved_count = 0

        if rb_mgr:
            entry, found = rb_mgr.match(error_output)
            if found and entry:
                remediation = RemediationPayload(
                    root_cause=entry.root_cause,
                    human_explanation=f"This is a known issue (seen {entry.resolved_count} times before).",
                    remediation_command=entry.fix_command,
                    is_destructive=False,
                )
                from_runbook = True
                resolved_count = entry.resolved_count

        # If no runbook match, use LLM
        if remediation is None and llm_agent is not None:
            ui.diagnosing()

            try:
                # Turn 1: Get diagnostic commands
                diag_payload = llm_agent.diagnose(step_result, os_ctx, agent_info)
                ui.show_hypothesis(diag_payload.hypothesis)

                # Show diagnostic commands and ask for approval
                diag_results = {}
                if diag_payload.diagnostic_commands:
                    ui.show_diagnostic_commands(diag_payload.diagnostic_commands)
                    diag_approval = ui.prompt_diagnostics_approval()
                    if diag_approval == "y":
                        ui.running_diagnostics()
                        diag_results = run_all(diag_payload.diagnostic_commands)
                    else:
                        ui.console.print("  [dim]Skipped diagnostics.[/dim]")

                # Turn 2: Get remediation
                remediation = llm_agent.remediate(step_result, diag_results, agent_info)
            except Exception as e:
                print(f"  LLM error: {e}")
                result.failed += 1
                continue

        if remediation is None:
            result.failed += 1
            continue

        # Show remediation and prompt
        ui.show_remediation(remediation, from_runbook, resolved_count)
        choice = ui.prompt_action(remediation.is_destructive)

        if choice == "y":
            # Execute the fix automatically
            try:
                fix_result = subprocess.run(
                    ["bash", "-c", remediation.remediation_command],
                    capture_output=True, text=True, timeout=60,
                )
                if opts.verbose and fix_result.stdout:
                    print(f"  Fix output: {fix_result.stdout}")
            except Exception:
                pass

            # Re-run the failed step
            retry_result = _execute_step(step_num, step.command)
            if retry_result.success:
                ui.fix_applied(True)
                ui.step_success(step_num, len(steps), step.command, step.description)
                result.passed += 1

                # Save to runbook if this was an LLM-driven fix
                if not from_runbook and rb_mgr:
                    agent_name = agent_info.manifest.name if agent_info else "unknown"
                    rb_mgr.write_entry(agent_name, RunbookEntry(
                        error_pattern=_extract_pattern(error_output),
                        step_failed=f"Step {step_num}: {step.command}",
                        root_cause=remediation.root_cause,
                        fix_command=remediation.remediation_command,
                    ))
            else:
                ui.fix_applied(False)
                result.failed += 1

        elif choice == "retry":
            # User fixed it manually — just retry the step
            retry_result = _execute_step(step_num, step.command)
            if retry_result.success:
                ui.fix_applied(True)
                ui.step_success(step_num, len(steps), step.command, step.description)
                result.passed += 1
            else:
                ui.fix_applied(False)
                result.failed += 1

        elif choice == "n":
            result.skipped += 1

        elif choice == "q":
            result.failed += 1
            ui.summary(result.total, result.passed, result.failed, result.skipped)
            return result

    ui.show_completion_summary(result, agent_info)
    return result


def _execute_step(step_num: int, command: str) -> StepResult:
    """Execute a single step via bash and capture results."""
    try:
        proc = subprocess.run(
            ["bash", "-c", command],
            capture_output=True, text=True, timeout=120,
        )
        return StepResult(
            step_number=step_num,
            command=command,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            success=proc.returncode == 0,
        )
    except subprocess.TimeoutExpired:
        return StepResult(
            step_number=step_num,
            command=command,
            exit_code=1,
            stdout="",
            stderr="Command timed out after 120 seconds",
            success=False,
        )
    except Exception as e:
        return StepResult(
            step_number=step_num,
            command=command,
            exit_code=1,
            stdout="",
            stderr=str(e),
            success=False,
        )


def _extract_pattern(error_output: str) -> str:
    """Get a short, matchable pattern from the error output."""
    for line in error_output.split("\n"):
        line = line.strip()
        if line:
            return line[:80]
    return error_output[:80]
