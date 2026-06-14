"""Data schemas for the diagnostic system."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AgentManifest:
    name: str = ""
    display_name: str = ""
    description: str = ""
    target_os: str = ""
    ports: List[int] = field(default_factory=list)
    services: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)


@dataclass
class DiagnosticHints:
    priority_commands: List[str] = field(default_factory=list)
    context_hints: List[str] = field(default_factory=list)


@dataclass
class DiagnosticPayload:
    """Turn 1 output: LLM tells us what diagnostic commands to run."""
    hypothesis: str = ""
    diagnostic_commands: List[str] = field(default_factory=list)


@dataclass
class RemediationPayload:
    """Turn 2 output: LLM provides the fix after seeing diagnostic results."""
    root_cause: str = ""
    human_explanation: str = ""
    remediation_command: str = ""
    is_destructive: bool = False


@dataclass
class StepResult:
    """Captures the result of executing a single script step."""
    step_number: int = 0
    command: str = ""
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    success: bool = False


@dataclass
class RunbookEntry:
    """A single resolved issue in the runbook."""
    id: str = ""
    error_pattern: str = ""
    step_failed: str = ""
    root_cause: str = ""
    fix_command: str = ""
    resolved_count: int = 0
    first_seen: str = ""
    last_seen: str = ""


@dataclass
class RunbookIndexEntry:
    """Maps an error pattern to a runbook entry file."""
    pattern: str = ""
    entry_file: str = ""


@dataclass
class RunbookIndex:
    """Lookup table mapping error patterns to entry files."""
    entries: List[RunbookIndexEntry] = field(default_factory=list)


@dataclass
class ConfigVar:
    """A configuration variable extracted from a config template."""
    name: str = ""
    current_value: str = ""
    required: bool = True
    validation_type: str = "string"  # host, port, license_key, password, string


@dataclass
class PreflightResult:
    """Result of the config validation phase."""
    passed: bool = False
    vars_validated: dict = field(default_factory=dict)
    connectivity_results: dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


@dataclass
class LogWatchResult:
    """Result of post-service-start log monitoring."""
    clean: bool = True
    errors_found: List[str] = field(default_factory=list)
    error_categories: List[str] = field(default_factory=list)
    full_output: str = ""
    duration_seconds: int = 15
