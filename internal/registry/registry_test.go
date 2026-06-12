package registry

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadAgent_ValidManifest(t *testing.T) {
	dir := t.TempDir()
	agentDir := filepath.Join(dir, "test-agent")
	os.MkdirAll(filepath.Join(agentDir, "knowledge"), 0755)
	os.MkdirAll(filepath.Join(agentDir, "diagnostics"), 0755)
	os.MkdirAll(filepath.Join(agentDir, "runbook"), 0755)

	manifest := `name: test-agent
display_name: "Test Agent"
description: "A test agent"
target_os: linux
ports: [5432]
services: [postgresql]
prerequisites:
  - "PostgreSQL installed"
`
	os.WriteFile(filepath.Join(agentDir, "manifest.yaml"), []byte(manifest), 0644)
	os.WriteFile(filepath.Join(agentDir, "install.sh"), []byte("echo hello\n"), 0644)
	os.WriteFile(filepath.Join(agentDir, "knowledge", "common-failures.md"), []byte("# Failures\n"), 0644)
	os.WriteFile(filepath.Join(agentDir, "knowledge", "prerequisites.md"), []byte("# Pre\n"), 0644)
	os.WriteFile(filepath.Join(agentDir, "diagnostics", "hints.yaml"), []byte("priority_commands: []\ncontext_hints: []\n"), 0644)
	os.WriteFile(filepath.Join(agentDir, "runbook", "index.yaml"), []byte("entries: []\n"), 0644)

	agent, err := LoadAgent(agentDir)
	if err != nil {
		t.Fatalf("LoadAgent failed: %v", err)
	}
	if agent.Manifest.Name != "test-agent" {
		t.Errorf("name: got %q, want %q", agent.Manifest.Name, "test-agent")
	}
	if agent.Manifest.Ports[0] != 5432 {
		t.Errorf("port: got %d, want 5432", agent.Manifest.Ports[0])
	}
	if agent.InstallScript == "" {
		t.Error("install script should not be empty")
	}
}

func TestListAgents(t *testing.T) {
	dir := t.TempDir()
	for _, name := range []string{"agent-a", "agent-b"} {
		agentDir := filepath.Join(dir, name)
		os.MkdirAll(agentDir, 0755)
		manifest := "name: " + name + "\ndisplay_name: \"" + name + "\"\ndescription: test\ntarget_os: linux\n"
		os.WriteFile(filepath.Join(agentDir, "manifest.yaml"), []byte(manifest), 0644)
	}
	os.MkdirAll(filepath.Join(dir, "_template"), 0755)
	os.WriteFile(filepath.Join(dir, "_template", "manifest.yaml"), []byte("name: template\n"), 0644)

	agents, err := ListAgents(dir)
	if err != nil {
		t.Fatalf("ListAgents failed: %v", err)
	}
	if len(agents) != 2 {
		t.Fatalf("expected 2 agents, got %d", len(agents))
	}
}
