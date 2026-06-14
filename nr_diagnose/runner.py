"""Main execution runner - executes steps with AI-powered failure handling."""

import re
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

from .agent import LLMAgent
from .context import OSContext, collect
from .diagnostics import run_all
from .logwatch import detect_service_start, watch_logs
from .parser import Step
from .preflight import run_preflight
from .registry import Agent as RegistryAgent
from .runbook import Manager as RunbookManager
from .schemas import LogWatchResult, RemediationPayload, RunbookEntry, StepResult
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

MAX_RETRY_ITERATIONS = 10


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
    """Determine if a step requires user approval before executing."""
    for pattern in SAFE_PATTERNS:
        if re.search(pattern, command, re.MULTILINE):
            return False

    for pattern in SYSTEM_MODIFYING_PATTERNS:
        if re.search(pattern, command, re.MULTILINE):
            return True

    return False


def _detect_env_vars(command: str) -> List[str]:
    """Find environment variables referenced in a command."""
    return list(set(ENV_VAR_PATTERN.findall(command)))


def _detect_config_path(command: str) -> Optional[str]:
    """Detect if a command writes a config file, return the path."""
    match = re.search(r"(?:cat|tee)\s+.*?>\s*(/\S+)", command)
    if match:
        return match.group(1)
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

        # --- PRE-FLIGHT CONFIG VALIDATION ---
        config_path = _detect_config_path(step.command)
        if config_path:
            ui.show_preflight_start(config_path)
            preflight_ok = _run_preflight_loop(step.command, agent_info)
            if preflight_ok == "q":
                ui.summary(result.total, result.passed, result.failed, result.skipped)
                return result
            elif preflight_ok == "s":
                result.skipped += 1
                continue

        # --- APPROVAL ---
        if needs_approval:
            approval = ui.prompt_step_approval(step_num, len(steps))
            if approval == "q":
                ui.summary(result.total, result.passed, result.failed, result.skipped)
                return result
            elif approval == "n":
                result.skipped += 1
                continue
        else:
            ui.console.print("  [dim]auto-running...[/dim]")

        # --- EXECUTE STEP ---
        step_result = _execute_step(step_num, step.command)

        if step_result.success:
            # --- POST-EXECUTION LOG MONITORING ---
            service_id = detect_service_start(step.command)
            if service_id:
                ui.show_log_monitoring(service_id)
                log_result = watch_logs(step.command, step_result, agent_info)

                if not log_result.clean:
                    ui.show_log_errors(log_result.errors_found, log_result.error_categories)
                    # Treat log errors as a failure — enter diagnosis loop
                    step_result = StepResult(
                        step_number=step_num,
                        command=step.command,
                        exit_code=1,
                        stdout=step_result.stdout,
                        stderr="\n".join(log_result.errors_found),
                        success=False,
                    )
                else:
                    ui.show_log_clean(log_result.duration_seconds)

        if step_result.success:
            ui.step_success(step_num, len(steps), step.command, step.description)
            result.passed += 1

            # Track config files and services
            if config_path:
                result.config_files.append(config_path)
            if "systemctl enable" in step.command:
                match = re.search(r"systemctl\s+enable\s+(\S+)", step.command)
                if match:
                    result.services.append(match.group(1))
            continue

        # --- STEP FAILED: ENTER DIAGNOSIS LOOP ---
        ui.step_failure(step_num, len(steps), step.command, step_result.stderr)

        resolved = _diagnose_and_fix_loop(
            step_num=step_num,
            step=step,
            initial_result=step_result,
            agent_info=agent_info,
            llm_agent=llm_agent,
            rb_mgr=rb_mgr,
            opts=opts,
            os_ctx=os_ctx,
            total_steps=len(steps),
        )

        if resolved == "passed":
            result.passed += 1
            if config_path:
                result.config_files.append(config_path)
        elif resolved == "skipped":
            result.skipped += 1
        elif resolved == "quit":
            result.failed += 1
            ui.summary(result.total, result.passed, result.failed, result.skipped)
            return result
        else:
            result.failed += 1

    ui.show_completion_summary(result, agent_info)
    return result


def _run_preflight_loop(command: str, agent_info: Optional[RegistryAgent]) -> str:
    """Run preflight validation in a loop until pass/skip/quit.

    Returns: 'ok' (passed), 's' (skip), 'q' (quit)
    """
    while True:
        preflight_result = run_preflight(command, agent_info)
        if preflight_result.passed:
            return "ok"

        choice = ui.prompt_preflight_failure()
        if choice == "f":
            ui.console.print("  [dim]Please update the values and re-checking...[/dim]\n")
            continue
        return choice


def _diagnose_and_fix_loop(
    step_num: int,
    step: Step,
    initial_result: StepResult,
    agent_info: Optional[RegistryAgent],
    llm_agent: Optional[LLMAgent],
    rb_mgr: Optional[RunbookManager],
    opts: Options,
    os_ctx: OSContext,
    total_steps: int,
) -> str:
    """Loop: diagnose → fix → retry → check logs until resolved or quit.

    Returns: 'passed', 'failed', 'skipped', 'quit'
    """
    current_result = initial_result

    for iteration in range(1, MAX_RETRY_ITERATIONS + 1):
        if iteration > 1:
            ui.show_retry_iteration(iteration)
            ui.step_failure(step_num, total_steps, step.command, current_result.stderr)

        error_output = current_result.stderr or current_result.stdout

        # --- CHECK RUNBOOK FIRST ---
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

        # --- LLM DIAGNOSIS ---
        if remediation is None and llm_agent is not None:
            ui.diagnosing()

            try:
                # Check if this is a log-based error (service was running but had errors)
                service_id = detect_service_start(step.command)
                if service_id and current_result.stdout:
                    # Use log diagnosis (skip diagnostic commands, go straight to fix)
                    config_context = ""
                    config_path = _detect_config_path(step.command)
                    if config_path:
                        config_context = f"Config file: {config_path}"
                    remediation = llm_agent.diagnose_log_errors(
                        log_output=error_output,
                        config_context=config_context,
                        agent_info=agent_info,
                    )
                else:
                    # Standard two-turn diagnosis
                    diag_payload = llm_agent.diagnose(current_result, os_ctx, agent_info)
                    ui.show_hypothesis(diag_payload.hypothesis)

                    diag_results = {}
                    if diag_payload.diagnostic_commands:
                        ui.show_diagnostic_commands(diag_payload.diagnostic_commands)
                        diag_approval = ui.prompt_diagnostics_approval()
                        if diag_approval == "y":
                            ui.running_diagnostics()
                            diag_results = run_all(diag_payload.diagnostic_commands)
                        else:
                            ui.console.print("  [dim]Skipped diagnostics.[/dim]")

                    remediation = llm_agent.remediate(current_result, diag_results, agent_info)
            except Exception as e:
                ui.console.print(f"  [red]LLM error: {e}[/red]")
                return "failed"

        if remediation is None:
            return "failed"

        # --- SHOW REMEDIATION AND PROMPT ---
        ui.show_remediation(remediation, from_runbook, resolved_count)
        choice = ui.prompt_action(remediation.is_destructive)

        if choice == "y":
            # Execute the fix
            try:
                fix_result = subprocess.run(
                    ["bash", "-c", remediation.remediation_command],
                    capture_output=True, text=True, timeout=60,
                )
                if opts.verbose and fix_result.stdout:
                    ui.console.print(f"  [dim]Fix output: {fix_result.stdout}[/dim]")
            except Exception:
                pass

            # Re-run the failed step
            retry_result = _execute_step(step_num, step.command)

            # Check logs if this is a service-start step
            if retry_result.success:
                service_id = detect_service_start(step.command)
                if service_id:
                    ui.show_log_monitoring(service_id)
                    log_result = watch_logs(step.command, retry_result, agent_info)
                    if not log_result.clean:
                        ui.show_log_errors(log_result.errors_found, log_result.error_categories)
                        # Still has log errors — treat as failure, continue loop
                        current_result = StepResult(
                            step_number=step_num,
                            command=step.command,
                            exit_code=1,
                            stdout=retry_result.stdout,
                            stderr="\n".join(log_result.errors_found),
                            success=False,
                        )
                        ui.fix_applied(False)
                        continue
                    else:
                        ui.show_log_clean(log_result.duration_seconds)

            if retry_result.success:
                ui.fix_applied(True)
                ui.step_success(step_num, total_steps, step.command, step.description)

                # Save to runbook if LLM-driven fix
                if not from_runbook and rb_mgr:
                    agent_name = agent_info.manifest.name if agent_info else "unknown"
                    rb_mgr.write_entry(agent_name, RunbookEntry(
                        error_pattern=_extract_pattern(error_output),
                        step_failed=f"Step {step_num}: {step.command}",
                        root_cause=remediation.root_cause,
                        fix_command=remediation.remediation_command,
                    ))
                return "passed"
            else:
                ui.fix_applied(False)
                current_result = retry_result
                # Continue the loop with new error

        elif choice == "retry":
            # User fixed it manually — retry the step
            retry_result = _execute_step(step_num, step.command)

            # Check logs too
            if retry_result.success:
                service_id = detect_service_start(step.command)
                if service_id:
                    ui.show_log_monitoring(service_id)
                    log_result = watch_logs(step.command, retry_result, agent_info)
                    if not log_result.clean:
                        ui.show_log_errors(log_result.errors_found, log_result.error_categories)
                        current_result = StepResult(
                            step_number=step_num,
                            command=step.command,
                            exit_code=1,
                            stdout=retry_result.stdout,
                            stderr="\n".join(log_result.errors_found),
                            success=False,
                        )
                        ui.fix_applied(False)
                        continue
                    else:
                        ui.show_log_clean(log_result.duration_seconds)

            if retry_result.success:
                ui.fix_applied(True)
                ui.step_success(step_num, total_steps, step.command, step.description)
                return "passed"
            else:
                ui.fix_applied(False)
                current_result = retry_result

        elif choice == "n":
            return "skipped"

        elif choice == "q":
            return "quit"

    # Exhausted max iterations
    ui.console.print(f"  [red]Exhausted {MAX_RETRY_ITERATIONS} retry attempts.[/red]")
    return "failed"


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
