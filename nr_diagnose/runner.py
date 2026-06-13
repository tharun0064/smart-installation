"""Main execution runner - executes steps with AI-powered failure handling."""

import subprocess
from dataclasses import dataclass
from typing import List, Optional

from .agent import LLMAgent
from .context import OSContext, collect
from .diagnostics import run_all
from .registry import Agent as RegistryAgent
from .runbook import Manager as RunbookManager
from .schemas import RemediationPayload, RunbookEntry, StepResult
from . import ui


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


def run(
    steps: List[str],
    agent_info: Optional[RegistryAgent],
    llm_agent: Optional[LLMAgent],
    rb_mgr: Optional[RunbookManager],
    opts: Options,
) -> Result:
    """Execute all steps with AI-powered failure handling."""
    result = Result(total=len(steps))

    if opts.dry_run:
        print("Dry-run mode: showing parsed steps without executing")
        for i, step in enumerate(steps, 1):
            print(f"  [{i}/{len(steps)}] {step}")
        return result

    os_ctx = collect()

    for i, step in enumerate(steps):
        step_num = i + 1
        ui.step_start(step_num, len(steps), step)

        step_result = _execute_step(step_num, step)

        if step_result.success:
            ui.step_success(step_num, len(steps), step)
            result.passed += 1
            continue

        # Step failed
        ui.step_failure(step_num, len(steps), step, step_result.stderr)
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
                ui.running_diagnostics()

                # Execute diagnostics
                diag_results = run_all(diag_payload.diagnostic_commands)

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
            # Execute the fix
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
            retry_result = _execute_step(step_num, step)
            if retry_result.success:
                ui.fix_applied(True)
                ui.step_success(step_num, len(steps), step)
                result.passed += 1

                # Save to runbook if this was an LLM-driven fix
                if not from_runbook and rb_mgr:
                    agent_name = agent_info.manifest.name if agent_info else "unknown"
                    rb_mgr.write_entry(agent_name, RunbookEntry(
                        error_pattern=_extract_pattern(error_output),
                        step_failed=f"Step {step_num}: {step}",
                        root_cause=remediation.root_cause,
                        fix_command=remediation.remediation_command,
                    ))
            else:
                ui.fix_applied(False)
                result.failed += 1

        elif choice == "n":
            result.skipped += 1

        elif choice == "q":
            result.failed += 1
            ui.summary(result.total, result.passed, result.failed, result.skipped)
            return result

    ui.summary(result.total, result.passed, result.failed, result.skipped)
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
