package runbook

import (
	"os"
	"path/filepath"
	"testing"
)

func TestMatch_SubstringMatch(t *testing.T) {
	dir := t.TempDir()
	indexContent := `entries:
  - pattern: "ORA-12541"
    entry_file: "001-listener.md"
  - pattern: "connection refused"
    entry_file: "002-firewall.md"
`
	os.WriteFile(filepath.Join(dir, "index.yaml"), []byte(indexContent), 0644)
	os.WriteFile(filepath.Join(dir, "001-listener.md"), []byte("---\nid: \"001\"\nerror_pattern: \"ORA-12541\"\nroot_cause: \"Listener down\"\nfix_command: \"sudo lsnrctl start\"\nresolved_count: 2\nfirst_seen: \"2026-01-01T00:00:00Z\"\nlast_seen: \"2026-06-01T00:00:00Z\"\n---\n# Fix\n"), 0644)

	mgr, err := NewManager(dir, "")
	if err != nil {
		t.Fatalf("NewManager failed: %v", err)
	}

	entry, found := mgr.Match("Error: ORA-12541: TNS:no listener")
	if !found {
		t.Fatal("expected match")
	}
	if entry.RootCause != "Listener down" {
		t.Errorf("root_cause: got %q", entry.RootCause)
	}
}

func TestMatch_NoMatch(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "index.yaml"), []byte("entries: []\n"), 0644)

	mgr, err := NewManager(dir, "")
	if err != nil {
		t.Fatalf("NewManager failed: %v", err)
	}

	_, found := mgr.Match("some random error")
	if found {
		t.Error("expected no match")
	}
}

func TestMatch_CaseInsensitive(t *testing.T) {
	dir := t.TempDir()
	indexContent := `entries:
  - pattern: "connection refused"
    entry_file: "001.md"
`
	os.WriteFile(filepath.Join(dir, "index.yaml"), []byte(indexContent), 0644)
	os.WriteFile(filepath.Join(dir, "001.md"), []byte("---\nid: \"001\"\nerror_pattern: \"connection refused\"\nroot_cause: \"Port blocked\"\nfix_command: \"ufw allow 5432/tcp\"\nresolved_count: 1\nfirst_seen: \"2026-01-01T00:00:00Z\"\nlast_seen: \"2026-01-01T00:00:00Z\"\n---\n"), 0644)

	mgr, err := NewManager(dir, "")
	if err != nil {
		t.Fatalf("NewManager failed: %v", err)
	}

	_, found := mgr.Match("Connection Refused on port 5432")
	if !found {
		t.Error("expected case-insensitive match")
	}
}
