"""Safe diagnostic command execution with allowlist."""

import subprocess
from typing import Dict, List, Optional, Tuple

ALLOWED_COMMANDS = {
    "ping", "nc", "netstat", "ss", "curl", "traceroute",
    "nslookup", "dig", "ps", "lsof", "df", "free",
    "dpkg", "apt", "rpm", "cat", "ufw", "iptables",
    "systemctl", "wget", "tnsping", "echo",
}


def is_allowed(cmd: str) -> bool:
    """Check if a command is safe to execute as a diagnostic."""
    parts = cmd.split()
    if not parts:
        return False

    base = parts[0]

    # No sudo
    if base == "sudo":
        return False

    if base not in ALLOWED_COMMANDS:
        return False

    # Additional restrictions per command
    if base == "systemctl":
        if len(parts) < 2 or parts[1] != "status":
            return False
    elif base == "ufw":
        if len(parts) < 2 or parts[1] != "status":
            return False
    elif base == "iptables":
        if "-L" not in parts:
            return False
    elif base == "cat":
        if len(parts) < 2 or not parts[-1].startswith("/etc/"):
            return False
    elif base == "wget":
        if "-O" in parts:
            return False

    return True


def run_diagnostic(cmd: str) -> Tuple[str, Optional[str]]:
    """Execute a single diagnostic command and return (output, error_msg).

    Returns (output, None) on success or blocked output,
    (error_message, error_message) if not allowed.
    """
    if not is_allowed(cmd):
        return f"[BLOCKED] command not allowed: {cmd!r}", f"command not allowed: {cmd!r}"

    try:
        result = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True, text=True, timeout=30
        )
        # Return combined output regardless of exit code
        output = result.stdout + result.stderr
        return output.strip(), None
    except subprocess.TimeoutExpired:
        return "[TIMEOUT] command timed out after 30s", None
    except Exception as e:
        return f"[ERROR] {e}", None


def run_all(commands: List[str]) -> Dict[str, str]:
    """Execute multiple diagnostic commands and return combined output."""
    results: Dict[str, str] = {}
    for cmd in commands:
        output, error = run_diagnostic(cmd)
        if error:
            results[cmd] = f"[BLOCKED] {error}"
        else:
            results[cmd] = output
    return results
