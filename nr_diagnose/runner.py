"""Main execution runner - executes steps with AI-powered failure handling."""

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .agent import LLMAgent
from .context import OSContext, collect
from .diagnostics import run_all
from .parser import Step, parse_script
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
    env_vars: Optional[Dict[str, str]] = None,
) -> Result:
    """Execute all steps with AI-powered failure handling."""
    result = Result(total=len(steps))
    env_vars = env_vars or {}

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

        step_result = _execute_step(step_num, step.command, env_vars)

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

        # Step failed — delegate to shared handler (handles runbook, LLM, fix, retry, update)
        ui.step_failure(step_num, len(steps), step.command, step_result.stderr)

        outcome = _handle_failure(
            step_num=step_num,
            command=step.command,
            description=step.description,
            step_result=step_result,
            agent_info=agent_info,
            llm_agent=llm_agent,
            rb_mgr=rb_mgr,
            opts=opts,
            env_vars=env_vars,
            os_ctx=os_ctx,
            step_label=f"Step {step_num}: {step.command}",
            install_steps=steps,
            install_step_idx=i,
        )

        if outcome == "fixed":
            ui.step_success(step_num, len(steps), step.command, step.description)
            result.passed += 1
        elif outcome == "skipped":
            result.skipped += 1
        elif outcome == "quit":
            result.failed += 1
            ui.summary(result.total, result.passed, result.failed, result.skipped)
            return result
        else:  # "failed"
            result.failed += 1

    ui.show_completion_summary(result, agent_info)
    return result


def validate(
    agent_info: Optional[RegistryAgent],
    llm_agent: Optional[LLMAgent],
    rb_mgr: Optional[RunbookManager],
    opts: Options,
    env_vars: Optional[Dict[str, str]] = None,
    max_rounds: int = 3,
) -> Result:
    """Run priority_commands as post-install validation; on failure, reuse runbook→LLM→prompt path.

    Loops up to max_rounds times so a fix that resolves one check can re-run the rest.
    """
    env_vars = env_vars or {}
    if not agent_info or not agent_info.hints.priority_commands:
        return Result()

    commands = list(agent_info.hints.priority_commands)
    if opts.dry_run:
        ui.console.print("\n[bold]Dry-run:[/bold] would run validation checks:")
        for c in commands:
            ui.console.print(f"  [dim]$[/dim] {c}")
        return Result(total=len(commands))

    os_ctx = collect()
    last = Result(total=len(commands))

    # Parse install.sh once so the update flow can re-render config files when an input changes.
    install_steps = parse_script(agent_info.install_script) if agent_info.install_script else []

    for round_num in range(1, max_rounds + 1):
        ui.validation_start(len(commands))
        last = Result(total=len(commands))
        any_failed = False

        for idx, command in enumerate(commands, 1):
            ui.validation_check_start(idx, len(commands), command)
            check_result = _execute_step(idx, command, env_vars)

            if check_result.success:
                ui.validation_check_pass(command)
                last.passed += 1
                continue

            any_failed = True
            last.failed += 1
            ui.validation_check_fail(command, check_result.stderr)

            outcome = _handle_failure(
                step_num=idx,
                command=command,
                description=f"validation: {command}",
                step_result=check_result,
                agent_info=agent_info,
                llm_agent=llm_agent,
                rb_mgr=rb_mgr,
                opts=opts,
                env_vars=env_vars,
                os_ctx=os_ctx,
                step_label=f"validation: {command}",
                install_steps=install_steps,
                install_step_idx=None,  # validation can re-run any install step
            )

            if outcome == "quit":
                ui.validation_summary(last.passed, last.failed)
                return last
            if outcome == "fixed":
                last.passed += 1
                last.failed -= 1

        ui.validation_summary(last.passed, last.failed)
        if not any_failed:
            return last
        if round_num < max_rounds and last.failed > 0:
            ui.console.print(f"\n  [dim]Re-running validation (round {round_num + 1}/{max_rounds})...[/dim]")

    return last


def _handle_failure(
    step_num: int,
    command: str,
    description: str,
    step_result: StepResult,
    agent_info: Optional[RegistryAgent],
    llm_agent: Optional[LLMAgent],
    rb_mgr: Optional[RunbookManager],
    opts: Options,
    env_vars: Dict[str, str],
    os_ctx: OSContext,
    step_label: str,
    install_steps: Optional[List[Step]] = None,
    install_step_idx: Optional[int] = None,
) -> str:
    """Shared failure-handling: runbook → LLM → prompt → fix/update → save.

    Outcomes:
      - 'fixed'   retry succeeded after fix or input update
      - 'failed'  fix tried but didn't work, or no remediation available
      - 'skipped' user chose to skip the step
      - 'quit'    user asked to exit
    """
    error_output = step_result.stderr or step_result.stdout

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

    if remediation is None and llm_agent is not None:
        ui.diagnosing()
        try:
            diag_payload = llm_agent.diagnose(step_result, os_ctx, agent_info)
            ui.show_hypothesis(diag_payload.hypothesis)

            diag_results = {}
            if diag_payload.diagnostic_commands:
                ui.show_diagnostic_commands(diag_payload.diagnostic_commands)
                if ui.prompt_diagnostics_approval() == "y":
                    ui.running_diagnostics()
                    diag_results = run_all(diag_payload.diagnostic_commands)
                else:
                    ui.console.print("  [dim]Skipped diagnostics.[/dim]")

            available_inputs = sorted(env_vars.keys())
            remediation = llm_agent.remediate(step_result, diag_results, agent_info, available_inputs)
            # Deterministic anti-drift: if stderr contains a known error code declared in
            # the agent's hints, enforce the routing rule and override the LLM if it drifted.
            remediation, was_corrected = _enforce_error_routing(remediation, step_result, agent_info)
            if was_corrected:
                ui.console.print(
                    "  [yellow]⚠[/yellow] [dim]Detected LLM drift — root cause auto-corrected from agent's error-code routing rules.[/dim]"
                )
        except Exception as e:
            print(f"  LLM error: {e}")
            return "failed"

    if remediation is None:
        return "failed"

    ui.show_remediation(remediation, from_runbook, resolved_count)
    choice = ui.prompt_action(remediation.is_destructive, bad_inputs=remediation.bad_inputs)

    if choice == "update":
        return _apply_input_update(
            step_num=step_num,
            command=command,
            error_output=error_output,
            remediation=remediation,
            from_runbook=from_runbook,
            agent_info=agent_info,
            rb_mgr=rb_mgr,
            env_vars=env_vars,
            step_label=step_label,
            install_steps=install_steps,
            install_step_idx=install_step_idx,
        )

    if choice == "y":
        try:
            subprocess.run(
                ["bash", "-c", remediation.remediation_command],
                capture_output=True, text=True, timeout=60,
                env=_build_subprocess_env(env_vars),
            )
        except Exception:
            pass

        retry_result = _execute_step(step_num, command, env_vars)
        if retry_result.success:
            ui.fix_applied(True)
            if not from_runbook and rb_mgr:
                agent_name = agent_info.manifest.name if agent_info else "unknown"
                rb_mgr.write_entry(agent_name, RunbookEntry(
                    error_pattern=_extract_pattern(error_output),
                    step_failed=step_label,
                    root_cause=remediation.root_cause,
                    fix_command=remediation.remediation_command,
                ))
            return "fixed"
        ui.fix_applied(False)
        return "failed"

    if choice == "retry":
        retry_result = _execute_step(step_num, command, env_vars)
        if retry_result.success:
            ui.fix_applied(True)
            return "fixed"
        ui.fix_applied(False)
        return "failed"

    if choice == "q":
        return "quit"

    return "skipped"


def _apply_input_update(
    step_num: int,
    command: str,
    error_output: str,
    remediation: RemediationPayload,
    from_runbook: bool,
    agent_info: Optional[RegistryAgent],
    rb_mgr: Optional[RunbookManager],
    env_vars: Dict[str, str],
    step_label: str,
    install_steps: Optional[List[Step]],
    install_step_idx: Optional[int],
) -> str:
    """Re-prompt for the inputs flagged in remediation.bad_inputs, persist them,
    re-run any earlier install steps that reference the changed inputs (so generated
    config files like config.yaml get regenerated), and retry the failed step."""
    from .inputs import _is_secret, load_saved_config, save_config

    declared_by_name = {}
    if agent_info:
        declared_by_name = {ri.name: ri for ri in agent_info.manifest.required_inputs}

    new_values: Dict[str, str] = {}
    for name in remediation.bad_inputs:
        declared = declared_by_name.get(name)
        secret = _is_secret(name, declared)
        desc = declared.description if declared else ""
        current = env_vars.get(name, "")

        new_value = ui.prompt_input(name=name, description=desc, secret=secret, default=current)
        if not new_value:
            new_value = current
        if new_value != current:
            new_values[name] = new_value

    if not new_values:
        ui.console.print("  [yellow]No values changed — nothing to retry.[/yellow]")
        return "failed"

    env_vars.update(new_values)
    if agent_info and agent_info.dir:
        all_saved = load_saved_config(agent_info.dir)
        all_saved.update(env_vars)
        save_config(agent_info.dir, all_saved)
        ui.show_config_saved(f"{agent_info.dir}/.config.env")

    if install_steps:
        ok = _rerender_affected_steps(
            install_steps,
            install_step_idx,
            set(new_values.keys()),
            env_vars,
        )
        if not ok:
            return "failed"

    retry_result = _execute_step(step_num, command, env_vars)
    updated_names = sorted(new_values.keys())
    if retry_result.success:
        ui.update_succeeded(step_label, updated_names)
        if not from_runbook and rb_mgr:
            agent_name = agent_info.manifest.name if agent_info else "unknown"
            rb_mgr.write_entry(agent_name, RunbookEntry(
                error_pattern=_extract_pattern(error_output),
                step_failed=step_label,
                root_cause=remediation.root_cause,
                fix_command=f"re-prompt input(s): {', '.join(remediation.bad_inputs)}",
            ))
        return "fixed"
    ui.update_failed(step_label, updated_names, retry_result.stderr or retry_result.stdout)
    return "failed"


def _rerender_affected_steps(
    install_steps: List[Step],
    upper_bound: Optional[int],
    updated_inputs: Set[str],
    env_vars: Dict[str, str],
) -> bool:
    """Re-execute install steps that reference any of `updated_inputs`.

    upper_bound: if set, only consider steps[0:upper_bound] (used during install phase
    so we don't pre-run a step we haven't gotten to yet). None = all install steps
    (used during validation phase, where we want to regen every affected step).

    Returns True if all affected steps re-executed successfully.
    """
    from .inputs import scan_required_vars

    upper = upper_bound if upper_bound is not None else len(install_steps)
    upper = min(upper, len(install_steps))

    affected: List[tuple] = []
    for i in range(upper):
        step = install_steps[i]
        refs = set(scan_required_vars([step]).keys())
        if refs & updated_inputs:
            affected.append((i, step))

    if not affected:
        return True

    ui.rerender_start(sorted(updated_inputs))
    for i, step in affected:
        result = _execute_step(i + 1, step.command, env_vars)
        label = step.description or step.command.split("\n")[0][:60]
        ui.rerender_step(i + 1, len(install_steps), label, result.success)
        if not result.success:
            ui.console.print(f"  [red]Re-run failed: {(result.stderr or '').strip()[:200]}[/red]")
            return False
    return True


def _enforce_error_routing(
    remediation: RemediationPayload,
    step_result: StepResult,
    agent_info: Optional[RegistryAgent],
) -> tuple:
    """Override the LLM's remediation when it drifts away from a known error code.

    Looks at agent_info.hints.error_code_routing — each rule has `patterns` to match in
    stderr/stdout and an authoritative `bad_inputs` list. If a rule matches the failure
    output but the LLM's `bad_inputs` doesn't intersect with the rule's expected inputs,
    we replace bad_inputs/root_cause/remediation_command with the rule's authoritative
    values. The rule with the most specific (longest) matched pattern wins.

    Returns (remediation, was_corrected).
    """
    if not agent_info or not agent_info.hints.error_code_routing:
        return remediation, False

    haystack = (step_result.stderr or "") + "\n" + (step_result.stdout or "")
    if not haystack.strip():
        return remediation, False

    # Find the most specific matching rule (longest pattern that appears in haystack).
    best_match = None  # (rule, matched_pattern)
    for rule in agent_info.hints.error_code_routing:
        for pat in rule.patterns:
            if pat and pat in haystack:
                if best_match is None or len(pat) > len(best_match[1]):
                    best_match = (rule, pat)

    if best_match is None:
        return remediation, False

    rule, _ = best_match
    expected = set(rule.bad_inputs or [])
    actual = set(remediation.bad_inputs or [])

    # If the LLM already flagged at least one of the expected inputs, trust it.
    if expected and (expected & actual):
        return remediation, False

    # Drift detected — replace the structured fields with the rule's authoritative values.
    overridden = RemediationPayload(
        root_cause=rule.root_cause or remediation.root_cause,
        human_explanation=rule.explanation or remediation.human_explanation,
        remediation_command="",  # routing rules represent re-prompt-style fixes; clear any sed/etc.
        is_destructive=False,
        bad_inputs=list(expected),
    )
    return overridden, True


def _build_subprocess_env(extra: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Merge user-supplied inputs into the parent env so heredocs interpolate them."""
    env = os.environ.copy()
    if extra:
        for k, v in extra.items():
            if v is not None:
                env[k] = v
    return env


def _execute_step(step_num: int, command: str, env_vars: Optional[Dict[str, str]] = None) -> StepResult:
    """Execute a single step via bash and capture results."""
    try:
        proc = subprocess.run(
            ["bash", "-c", command],
            capture_output=True, text=True, timeout=120,
            env=_build_subprocess_env(env_vars),
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
