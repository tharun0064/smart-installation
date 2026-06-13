"""Shell script parser - splits scripts into individual executable steps."""

from pathlib import Path
from typing import List


def parse_script(content: str) -> List[str]:
    """Split a shell script into individual executable steps.

    Skips comments, empty lines, shebangs, and set directives.
    Joins continuation lines (ending with \\) and preserves pipes and && chains.
    """
    lines = content.split("\n")
    steps: List[str] = []
    current: List[str] = []

    for line in lines:
        line = line.rstrip(" \t\r")

        # Empty line: flush accumulated continuation
        if line == "":
            if current:
                steps.append(" ".join(current))
                current = []
            continue

        trimmed = line.strip()

        # Skip shebangs, comments, and set directives
        if not trimmed or trimmed.startswith("#") or trimmed.startswith("set "):
            continue

        # Handle line continuations (trailing backslash)
        if line.endswith("\\"):
            line_without_backslash = line[:-1].strip()
            current.append(line_without_backslash)
            continue

        # Normal line
        if current:
            current.append(trimmed)
            steps.append(" ".join(current))
            current = []
        else:
            steps.append(trimmed)

    # Flush remaining
    if current:
        steps.append(" ".join(current))

    return steps


def parse_script_file(path: str) -> List[str]:
    """Read a file and parse it into steps."""
    content = Path(path).read_text()
    return parse_script(content)
