"""Runbook manager - handles loading, matching, and writing runbook entries."""

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import yaml

from .schemas import RunbookEntry, RunbookIndex, RunbookIndexEntry


class Manager:
    """Handles runbook loading, matching, and writing."""

    def __init__(self, seeded_dir: str, local_dir: str):
        self.seeded_dir = seeded_dir
        self.local_dir = local_dir
        self.seeded = _load_index(os.path.join(seeded_dir, "index.yaml")) if seeded_dir else RunbookIndex()
        self.local = _load_index(os.path.join(local_dir, "index.yaml")) if local_dir else RunbookIndex()

    def match(self, error_output: str) -> Tuple[Optional[RunbookEntry], bool]:
        """Check both seeded and local runbooks for a matching error pattern.

        Returns (entry, found).
        """
        lower_error = error_output.lower()

        entry = self._match_index(self.seeded, self.seeded_dir, lower_error)
        if entry:
            return entry, True

        entry = self._match_index(self.local, self.local_dir, lower_error)
        if entry:
            return entry, True

        return None, False

    def write_entry(self, agent_name: str, entry: RunbookEntry) -> None:
        """Save a new runbook entry to the local directory."""
        if not self.local_dir:
            raise RuntimeError("no local runbook directory configured")

        # cli.py already constructs local_dir as <data>/runbook/<agent_name>, so don't
        # nest another <agent_name> level here. agent_name is still used to derive the
        # index path passed to _save_local_index below.
        agent_runbook = self.local_dir
        os.makedirs(agent_runbook, exist_ok=True)

        entry.id = f"{len(self.local.entries) + 1:03d}"
        entry.first_seen = datetime.now(timezone.utc).isoformat()
        entry.last_seen = entry.first_seen
        entry.resolved_count = 1

        slug = _slugify(entry.root_cause)
        filename = f"{entry.id}-{slug}.md"
        entry_path = os.path.join(agent_runbook, filename)

        content = f"""---
id: "{entry.id}"
error_pattern: "{entry.error_pattern}"
step_failed: "{entry.step_failed}"
root_cause: "{entry.root_cause}"
fix_command: "{entry.fix_command}"
resolved_count: {entry.resolved_count}
first_seen: "{entry.first_seen}"
last_seen: "{entry.last_seen}"
---

## Resolution
`{entry.fix_command}`
"""
        Path(entry_path).write_text(content)

        self.local.entries.append(RunbookIndexEntry(
            pattern=entry.error_pattern,
            entry_file=filename,
        ))

        self._save_local_index(agent_runbook)

    def increment_count(self, entry: RunbookEntry) -> None:
        """Update resolved_count and last_seen for an existing entry."""
        entry.resolved_count += 1
        entry.last_seen = datetime.now(timezone.utc).isoformat()

    def _match_index(self, index: RunbookIndex, dir_path: str, lower_error: str) -> Optional[RunbookEntry]:
        for ie in index.entries:
            pattern = ie.pattern.lower()
            if pattern in lower_error:
                entry = _load_entry(os.path.join(dir_path, ie.entry_file))
                if entry:
                    return entry
        return None

    def _save_local_index(self, dir_path: str) -> None:
        data = {
            "entries": [
                {"pattern": e.pattern, "entry_file": e.entry_file}
                for e in self.local.entries
            ]
        }
        Path(os.path.join(dir_path, "index.yaml")).write_text(yaml.dump(data))


def _load_index(path: str) -> RunbookIndex:
    """Load a runbook index from a YAML file."""
    try:
        data = yaml.safe_load(Path(path).read_text()) or {}
        entries = [
            RunbookIndexEntry(pattern=e.get("pattern", ""), entry_file=e.get("entry_file", ""))
            for e in data.get("entries", [])
        ]
        return RunbookIndex(entries=entries)
    except (FileNotFoundError, OSError):
        return RunbookIndex()


def _load_entry(path: str) -> Optional[RunbookEntry]:
    """Load a runbook entry from a frontmatter markdown file."""
    try:
        content = Path(path).read_text()
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        data = yaml.safe_load(parts[1])
        if not data:
            return None

        return RunbookEntry(
            id=data.get("id", ""),
            error_pattern=data.get("error_pattern", ""),
            step_failed=data.get("step_failed", ""),
            root_cause=data.get("root_cause", ""),
            fix_command=data.get("fix_command", ""),
            resolved_count=data.get("resolved_count", 0),
            first_seen=data.get("first_seen", ""),
            last_seen=data.get("last_seen", ""),
        )
    except (FileNotFoundError, OSError):
        return None


def _slugify(s: str) -> str:
    """Convert a string to a URL-safe slug."""
    s = s.lower()
    s = re.sub(r'[^a-z0-9]', '-', s)
    s = re.sub(r'-+', '-', s)
    s = s.strip('-')
    return s[:40]
