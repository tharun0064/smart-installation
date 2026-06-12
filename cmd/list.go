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

var ListCmd = &cobra.Command{
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
