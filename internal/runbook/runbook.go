package runbook

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/newrelic/nr-diagnose/internal/schemas"
	"gopkg.in/yaml.v3"
)

// Manager handles runbook loading, matching, and writing.
type Manager struct {
	seededDir string
	localDir  string
	seeded    schemas.RunbookIndex
	local     schemas.RunbookIndex
}

// NewManager creates a runbook manager from seeded and local directories.
func NewManager(seededDir, localDir string) (*Manager, error) {
	m := &Manager{
		seededDir: seededDir,
		localDir:  localDir,
	}

	if seededDir != "" {
		m.seeded = loadIndex(filepath.Join(seededDir, "index.yaml"))
	}

	if localDir != "" {
		m.local = loadIndex(filepath.Join(localDir, "index.yaml"))
	}

	return m, nil
}

// Match checks both seeded and local runbooks for a matching error pattern.
func (m *Manager) Match(errorOutput string) (schemas.RunbookEntry, bool) {
	lowerError := strings.ToLower(errorOutput)

	if entry, found := m.matchIndex(m.seeded, m.seededDir, lowerError); found {
		return entry, true
	}

	if entry, found := m.matchIndex(m.local, m.localDir, lowerError); found {
		return entry, true
	}

	return schemas.RunbookEntry{}, false
}

// WriteEntry saves a new runbook entry to the local directory.
func (m *Manager) WriteEntry(agentName string, entry schemas.RunbookEntry) error {
	if m.localDir == "" {
		return fmt.Errorf("no local runbook directory configured")
	}

	agentRunbook := filepath.Join(m.localDir, agentName)
	os.MkdirAll(agentRunbook, 0755)

	entry.ID = fmt.Sprintf("%03d", len(m.local.Entries)+1)
	entry.FirstSeen = time.Now().UTC().Format(time.RFC3339)
	entry.LastSeen = entry.FirstSeen
	entry.ResolvedCount = 1

	slug := slugify(entry.RootCause)
	filename := fmt.Sprintf("%s-%s.md", entry.ID, slug)
	entryPath := filepath.Join(agentRunbook, filename)

	content := fmt.Sprintf("---\nid: \"%s\"\nerror_pattern: \"%s\"\nstep_failed: \"%s\"\nroot_cause: \"%s\"\nfix_command: \"%s\"\nresolved_count: %d\nfirst_seen: \"%s\"\nlast_seen: \"%s\"\n---\n\n## Resolution\n`%s`\n", entry.ID, entry.ErrorPattern, entry.StepFailed, entry.RootCause, entry.FixCommand, entry.ResolvedCount, entry.FirstSeen, entry.LastSeen, entry.FixCommand)

	if err := os.WriteFile(entryPath, []byte(content), 0644); err != nil {
		return err
	}

	m.local.Entries = append(m.local.Entries, schemas.RunbookIndexEntry{
		Pattern:   entry.ErrorPattern,
		EntryFile: filename,
	})

	return m.saveLocalIndex(agentRunbook)
}

// IncrementCount updates the resolved_count and last_seen for an existing entry.
func (m *Manager) IncrementCount(entry *schemas.RunbookEntry) {
	entry.ResolvedCount++
	entry.LastSeen = time.Now().UTC().Format(time.RFC3339)
}

func (m *Manager) matchIndex(index schemas.RunbookIndex, dir string, lowerError string) (schemas.RunbookEntry, bool) {
	for _, ie := range index.Entries {
		pattern := strings.ToLower(ie.Pattern)
		if strings.Contains(lowerError, pattern) {
			entry, err := loadEntry(filepath.Join(dir, ie.EntryFile))
			if err == nil {
				return entry, true
			}
		}
	}
	return schemas.RunbookEntry{}, false
}

func (m *Manager) saveLocalIndex(dir string) error {
	data, err := yaml.Marshal(m.local)
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(dir, "index.yaml"), data, 0644)
}

func loadIndex(path string) schemas.RunbookIndex {
	data, err := os.ReadFile(path)
	if err != nil {
		return schemas.RunbookIndex{}
	}
	var index schemas.RunbookIndex
	yaml.Unmarshal(data, &index)
	return index
}

func loadEntry(path string) (schemas.RunbookEntry, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return schemas.RunbookEntry{}, err
	}

	content := string(data)
	parts := strings.SplitN(content, "---", 3)
	if len(parts) < 3 {
		return schemas.RunbookEntry{}, fmt.Errorf("invalid frontmatter in %s", path)
	}

	var entry schemas.RunbookEntry
	if err := yaml.Unmarshal([]byte(parts[1]), &entry); err != nil {
		return schemas.RunbookEntry{}, err
	}
	return entry, nil
}

func slugify(s string) string {
	s = strings.ToLower(s)
	s = strings.Map(func(r rune) rune {
		if r >= 'a' && r <= 'z' || r >= '0' && r <= '9' {
			return r
		}
		return '-'
	}, s)
	for strings.Contains(s, "--") {
		s = strings.ReplaceAll(s, "--", "-")
	}
	s = strings.Trim(s, "-")
	if len(s) > 40 {
		s = s[:40]
	}
	return s
}
