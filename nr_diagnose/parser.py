"""Shell script parser - splits scripts into individual executable steps."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

# Matches heredoc start: <<EOF, <<'EOF', <<"EOF", <<-EOF etc.
HEREDOC_PATTERN = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")


@dataclass
class Step:
    """A parsed step with its command and human-readable description."""
    command: str
    description: str = ""

    def __str__(self):
        return self.command


def parse_script(content: str) -> List[Step]:
    """Split a shell script into individual executable steps.

    Skips empty lines, shebangs, and set directives.
    Captures comments preceding a command as the step description.
    Joins continuation lines (ending with \\) and preserves pipes and && chains.
    Handles heredocs (<<EOF ... EOF) as single steps.
    """
    lines = content.split("\n")
    steps: List[Step] = []
    current: List[str] = []
    heredoc_delimiter = None
    heredoc_lines: List[str] = []
    last_comment = ""

    i = 0
    while i < len(lines):
        line = lines[i]

        # If we're inside a heredoc, collect lines until delimiter
        if heredoc_delimiter is not None:
            heredoc_lines.append(line)
            if line.strip() == heredoc_delimiter:
                # End of heredoc — join all lines as one step
                steps.append(Step(command="\n".join(heredoc_lines), description=last_comment))
                heredoc_delimiter = None
                heredoc_lines = []
                last_comment = ""
            i += 1
            continue

        line = line.rstrip(" \t\r")

        # Empty line: flush accumulated continuation
        if line == "":
            if current:
                steps.append(Step(command=" ".join(current), description=last_comment))
                current = []
                last_comment = ""
            i += 1
            continue

        trimmed = line.strip()

        # Skip shebangs and set directives
        if not trimmed or trimmed.startswith("#!/") or trimmed.startswith("set "):
            i += 1
            continue

        # Capture comments as step description
        if trimmed.startswith("#"):
            # Strip the # prefix and common patterns like "Step N:"
            comment_text = re.sub(r"^#\s*", "", trimmed)
            comment_text = re.sub(r"^Step\s+\d+:\s*", "", comment_text)
            if comment_text:
                last_comment = comment_text
            i += 1
            continue

        # Check for heredoc start
        heredoc_match = HEREDOC_PATTERN.search(trimmed)
        if heredoc_match:
            heredoc_delimiter = heredoc_match.group(1)
            # Start collecting: first line is the command itself
            heredoc_lines = [line]
            i += 1
            continue

        # Handle line continuations (trailing backslash)
        if line.endswith("\\"):
            line_without_backslash = line[:-1].strip()
            current.append(line_without_backslash)
            i += 1
            continue

        # Normal line
        if current:
            current.append(trimmed)
            steps.append(Step(command=" ".join(current), description=last_comment))
            current = []
        else:
            steps.append(Step(command=trimmed, description=last_comment))

        last_comment = ""
        i += 1

    # Flush remaining
    if current:
        steps.append(Step(command=" ".join(current), description=last_comment))
    if heredoc_lines:
        steps.append(Step(command="\n".join(heredoc_lines), description=last_comment))

    return steps


def parse_script_file(path: str) -> List[Step]:
    """Read a file and parse it into steps."""
    content = Path(path).read_text()
    return parse_script(content)
