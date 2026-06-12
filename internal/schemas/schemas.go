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
