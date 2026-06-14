"""Log monitoring - detect service starts and watch for errors in logs."""

import re
import subprocess
import time
from typing import List, Optional, Tuple

from .diagnostics import run_diagnostic
from .registry import Agent as RegistryAgent
from .schemas import LogWatchResult, StepResult

LOG_ERROR_PATTERNS: List[Tuple[str, str]] = [
    (r"ORA-\d{5}", "Oracle error"),
    (r"(?i)connection refused", "Connection refused"),
    (r"(?i)permission denied", "Permission denied"),
    (r"(?i)GRANT\s+\w+.*failed", "Grant/privilege error"),
    (r"(?i)authentication fail", "Authentication failure"),
    (r"(?i)invalid (username|password|credentials)", "Invalid credentials"),
    (r"(?i)\b(FATAL|panic)\b", "Fatal error"),
    (r"(?i)bind:\s*address already in use", "Port conflict"),
    (r"(?i)no such file or directory", "Missing file"),
    (r"(?i)access denied", "Access denied"),
]

SERVICE_START_PATTERNS = [
    (r"systemctl\s+(start|restart)\s+(\S+)", 2),
    (r"service\s+(\S+)\s+(start|restart)", 1),
    (r"timeout\s+\d+\s+(\S+)", 1),
]


def detect_service_start(command: str) -> Optional[str]:
    """Detect if a command starts a service. Returns service identifier or None."""
    for pattern, group_idx in SERVICE_START_PATTERNS:
        match = re.search(pattern, command)
        if match:
            return match.group(group_idx)
    return None


def _scan_for_errors(output: str) -> Tuple[List[str], List[str]]:
    """Scan text for error patterns. Returns (matching_lines, categories)."""
    errors_found = []
    categories = []

    for line in output.split("\n"):
        for pattern, category in LOG_ERROR_PATTERNS:
            if re.search(pattern, line):
                errors_found.append(line.strip())
                categories.append(category)
                break

    return errors_found, categories


def watch_logs(
    command: str,
    step_result: StepResult,
    agent_info: Optional[RegistryAgent],
    duration: int = 15,
) -> LogWatchResult:
    """Monitor logs after a service start for errors.

    For commands that capture output inline (timeout ... > logfile), scans
    the step's stdout/stderr. For systemd services, queries journalctl.
    """
    full_output = ""

    # Check if step result already has captured output (inline pattern)
    if step_result.stdout or step_result.stderr:
        full_output = (step_result.stdout or "") + "\n" + (step_result.stderr or "")

    # For systemd services, also check journalctl
    service_name = _extract_systemd_service(command)
    if service_name:
        time.sleep(2)
        journal_cmd = f"journalctl -u {service_name} --since '{duration} seconds ago' --no-pager -n 100"
        journal_output, _ = run_diagnostic(journal_cmd)
        if journal_output:
            full_output += "\n" + journal_output

    # Check for explicit log file references
    log_file = _extract_log_file(command)
    if log_file:
        cat_cmd = f"cat {log_file}"
        if log_file.startswith("/tmp/") or log_file.startswith("/var/log/"):
            log_output, _ = run_diagnostic(cat_cmd)
            if log_output:
                full_output += "\n" + log_output

    errors_found, categories = _scan_for_errors(full_output)

    return LogWatchResult(
        clean=len(errors_found) == 0,
        errors_found=errors_found,
        error_categories=categories,
        full_output=full_output,
        duration_seconds=duration,
    )


def _extract_systemd_service(command: str) -> Optional[str]:
    """Extract systemd service name from a systemctl command."""
    match = re.search(r"systemctl\s+(?:start|restart)\s+(\S+)", command)
    if match:
        return match.group(1)
    match = re.search(r"service\s+(\S+)\s+(?:start|restart)", command)
    if match:
        return match.group(1)
    return None


def _extract_log_file(command: str) -> Optional[str]:
    """Extract log file path from a command that redirects output."""
    match = re.search(r">\s*(/\S+\.log)", command)
    if match:
        return match.group(1)
    match = re.search(r"2>&1\s*\|\s*tee\s+(/\S+\.log)", command)
    if match:
        return match.group(1)
    return None
