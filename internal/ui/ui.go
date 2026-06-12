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
	successStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("2"))
	errorStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("1"))
	warnStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("3"))
	infoStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("4"))
	dimStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("8"))

	boxStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(lipgloss.Color("4")).
			Padding(0, 1)

	destructiveBoxStyle = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(lipgloss.Color("1")).
				Padding(0, 1)
)

func StepStart(stepNum, total int, command string) {
	fmt.Printf("%s %s\n",
		dimStyle.Render(fmt.Sprintf("[%d/%d]", stepNum, total)),
		command,
	)
}

func StepSuccess(stepNum, total int, command string) {
	fmt.Printf("%s %s %s\n",
		successStyle.Render("✓"),
		dimStyle.Render(fmt.Sprintf("[%d/%d]", stepNum, total)),
		command,
	)
}

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

func Diagnosing() {
	fmt.Printf("\n%s AI Agent diagnosing failure...\n", infoStyle.Render("⟳"))
}

func RunningDiagnostics() {
	fmt.Printf("%s Running diagnostic commands...\n", infoStyle.Render("⟳"))
}

func ShowRemediation(payload *schemas.RemediationPayload, fromRunbook bool, resolvedCount int) {
	fmt.Println()

	title := "Root Cause"
	if fromRunbook {
		title = "Root Cause (from runbook)"
		if resolvedCount > 0 {
			title = fmt.Sprintf("Root Cause (from runbook, resolved %d times)", resolvedCount)
		}
	}

	box := boxStyle.Render(fmt.Sprintf("─── %s ───\n%s", title, payload.RootCause))
	fmt.Println(box)
	fmt.Println()

	fmt.Printf("%s %s\n\n", infoStyle.Render("Explanation:"), payload.HumanExplanation)

	if payload.IsDestructive {
		dbox := destructiveBoxStyle.Render(fmt.Sprintf("Suggested Fix:\n  %s\n\n⚠  WARNING: This command is destructive!", payload.RemediationCommand))
		fmt.Println(dbox)
	} else {
		fmt.Printf("%s\n  %s\n\n", warnStyle.Render("Suggested Fix:"), payload.RemediationCommand)
	}
}

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

func FixApplied(success bool) {
	if success {
		fmt.Printf("%s Fix applied successfully. Re-running step...\n\n", successStyle.Render("✓"))
	} else {
		fmt.Printf("%s Fix did not resolve the issue.\n", errorStyle.Render("✗"))
	}
}

func Summary(total, passed, failed, skipped int) {
	fmt.Printf("\n%s\n", strings.Repeat("─", 50))
	fmt.Printf("Steps: %d total, %s passed, %s failed, %s skipped\n",
		total,
		successStyle.Render(fmt.Sprintf("%d", passed)),
		errorStyle.Render(fmt.Sprintf("%d", failed)),
		warnStyle.Render(fmt.Sprintf("%d", skipped)),
	)
}

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
