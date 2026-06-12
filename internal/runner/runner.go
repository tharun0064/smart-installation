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
	if len(errorOutput) > 80 {
		return errorOutput[:80]
	}
	return errorOutput
}
