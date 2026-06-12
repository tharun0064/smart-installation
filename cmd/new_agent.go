// cmd/new_agent.go
package cmd

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/newrelic/nr-diagnose/internal/config"
	"github.com/spf13/cobra"
)

var NewAgentCmd = &cobra.Command{
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

		installSh := "#!/bin/bash\n# TODO: Add installation steps\necho \"Installation script for " + name + "\"\n"

		prereqs := "# Prerequisites\n\nTODO: List what must be true before running install.\n"
		failures := "# Common Failures\n\nTODO: Document known failure modes and their fixes.\n"
		refs := "# References\n\nTODO: Add links to official docs and troubleshooting guides.\n"
		hints := "priority_commands: []\ncontext_hints: []\n"
		index := "entries: []\n"

		files := map[string]string{
			filepath.Join(agentDir, "manifest.yaml"):                   manifest,
			filepath.Join(agentDir, "install.sh"):                      installSh,
			filepath.Join(agentDir, "knowledge", "prerequisites.md"):   prereqs,
			filepath.Join(agentDir, "knowledge", "common-failures.md"): failures,
			filepath.Join(agentDir, "knowledge", "references.md"):      refs,
			filepath.Join(agentDir, "diagnostics", "hints.yaml"):       hints,
			filepath.Join(agentDir, "runbook", "index.yaml"):           index,
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
