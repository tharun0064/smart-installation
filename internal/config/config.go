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
