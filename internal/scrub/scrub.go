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
			result = pat.ReplaceAllString(result, "${1}: <REDACTED>")
		} else {
			result = pat.ReplaceAllString(result, "<REDACTED>")
		}
	}
	return result
}
