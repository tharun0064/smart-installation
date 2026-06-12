// internal/agent/agent.go
package agent

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

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
di
Analyze the diagnostic output, isolate the definitive root cause, and provide:
- A precise root cause statement
- A plain-English explanation for the developer
- A single, concrete terminal command to fix the issue
- Whether that command is destructive

Keep explanations punchy, empathetic, and developer-centric.

You MUST respond with ONLY a valid JSON object in this exact format:
{"root_cause": "...", "human_explanation": "...", "remediation_command": "...", "is_destructive": false}
`

type chatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type chatRequest struct {
	Model    string        `json:"model"`
	Messages []chatMessage `json:"messages"`
}

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
		client: &http.Client{Timeout: 30 * time.Second},
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

func extractJSON(s string) string {
	s = strings.TrimSpace(s)
	if strings.HasPrefix(s, "```json") {
		s = strings.TrimPrefix(s, "```json")
		s = strings.TrimSuffix(s, "```")
		s = strings.TrimSpace(s)
	} else if strings.HasPrefix(s, "```") {
		s = strings.TrimPrefix(s, "```")
		s = strings.TrimSuffix(s, "```")
		s = strings.TrimSpace(s)
	}
	start := strings.Index(s, "{")
	end := strings.LastIndex(s, "}")
	if start >= 0 && end > start {
		return s[start : end+1]
	}
	return s
}
