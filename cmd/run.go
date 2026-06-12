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

var RunCmd = &cobra.Command{
	Use:   "run [script-path]",
	Short: "Run an installation script with AI-powered diagnostics",
	Long:  "Execute an agent install script step-by-step. On failure, the AI agent diagnoses the issue and suggests a fix.",
	Args:  cobra.MaximumNArgs(1),
	RunE:  runExecute,
}

func init() {
	RunCmd.Flags().StringVar(&agentName, "agent", "", "Agent name (e.g., otel-oracledb)")
	RunCmd.Flags().BoolVar(&verbose, "verbose", false, "Show all step output")
	RunCmd.Flags().BoolVar(&dryRun, "dry-run", false, "Parse and show steps without executing")
	RunCmd.Flags().StringVar(&model, "model", "", "LLM model to use (overrides config)")
}

func runExecute(cmd *cobra.Command, args []string) error {
	cfg, err := config.Load()
	if err != nil {
		return fmt.Errorf("loading config: %w", err)
	}
	if model != "" {
		cfg.Model = model
	}

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
