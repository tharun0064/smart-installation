"""OS context collection - gathers system information for LLM prompts."""

import platform
import subprocess
from dataclasses import dataclass


@dataclass
class OSContext:
    os_name: str = ""
    arch: str = ""
    distro: str = ""
    kernel: str = ""
    hostname: str = ""
    current_user: str = ""
    shell_version: str = ""

    def to_string(self) -> str:
        """Format the context for inclusion in LLM prompts."""
        parts = [f"OS: {self.os_name}/{self.arch}"]
        if self.distro:
            parts.append(f"Distro: {self.distro.split(chr(10))[0]}")
        if self.kernel:
            parts.append(f"Kernel: {self.kernel}")
        if self.hostname:
            parts.append(f"Hostname: {self.hostname}")
        if self.current_user:
            parts.append(f"User: {self.current_user}")
        return "\n".join(parts)


def _run_cmd(*args: str) -> str:
    """Run a command and return its stripped output, or empty string on failure."""
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return ""


def collect() -> OSContext:
    """Gather OS information from the current system."""
    ctx = OSContext(
        os_name=platform.system().lower(),
        arch=platform.machine(),
    )

    ctx.distro = _run_cmd("lsb_release", "-ds")
    if not ctx.distro:
        ctx.distro = _run_cmd("cat", "/etc/os-release")

    ctx.kernel = _run_cmd("uname", "-r")
    ctx.hostname = _run_cmd("hostname")
    ctx.current_user = _run_cmd("whoami")
    ctx.shell_version = _run_cmd("bash", "--version")

    return ctx
