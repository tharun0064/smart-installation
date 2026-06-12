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
	Dir           string
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

	manifestData, err := os.ReadFile(filepath.Join(agentDir, "manifest.yaml"))
	if err != nil {
		return nil, fmt.Errorf("reading manifest: %w", err)
	}
	if err := yaml.Unmarshal(manifestData, &agent.Manifest); err != nil {
		return nil, fmt.Errorf("parsing manifest: %w", err)
	}

	scriptData, err := os.ReadFile(filepath.Join(agentDir, "install.sh"))
	if err != nil {
		return nil, fmt.Errorf("reading install.sh: %w", err)
	}
	agent.InstallScript = string(scriptData)

	agent.Knowledge.Prerequisites = readFileOrEmpty(filepath.Join(agentDir, "knowledge", "prerequisites.md"))
	agent.Knowledge.CommonFailures = readFileOrEmpty(filepath.Join(agentDir, "knowledge", "common-failures.md"))
	agent.Knowledge.References = readFileOrEmpty(filepath.Join(agentDir, "knowledge", "references.md"))

	hintsData, err := os.ReadFile(filepath.Join(agentDir, "diagnostics", "hints.yaml"))
	if err == nil {
		yaml.Unmarshal(hintsData, &agent.Hints)
	}

	indexData, err := os.ReadFile(filepath.Join(agentDir, "runbook", "index.yaml"))
	if err == nil {
		yaml.Unmarshal(indexData, &agent.RunbookIndex)
	}

	return agent, nil
}

// ListAgents returns manifests of all agents in the given directory (excluding _template).
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
