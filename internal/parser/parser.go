// internal/parser/parser.go
package parser

import (
	"os"
	"strings"
)

// ParseScript splits a shell script into individual executable steps.
// It skips comments, empty lines, shebangs, and set directives.
// It joins continuation lines (ending with \) and preserves pipes and && chains as single steps.
func ParseScript(content string) []string {
	lines := strings.Split(content, "\n")
	var steps []string
	var current strings.Builder

	for i := 0; i < len(lines); i++ {
		line := strings.TrimRight(lines[i], " \t\r")

		// Skip empty lines (flush any accumulated continuation)
		if line == "" {
			if current.Len() > 0 {
				steps = append(steps, current.String())
				current.Reset()
			}
			continue
		}

		// Skip shebangs, comments, and set directives
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") || strings.HasPrefix(trimmed, "set ") {
			continue
		}

		// Handle line continuations (trailing backslash)
		if strings.HasSuffix(line, "\\") {
			if current.Len() > 0 {
				current.WriteString(" ")
			}
			// Remove the backslash and trim the resulting line
			lineWithoutBackslash := strings.TrimSuffix(line, "\\")
			current.WriteString(strings.TrimSpace(lineWithoutBackslash))
			continue
		}

		// Normal line — append to any continuation or emit standalone
		if current.Len() > 0 {
			current.WriteString(" ")
			current.WriteString(strings.TrimSpace(line))
			steps = append(steps, current.String())
			current.Reset()
		} else {
			steps = append(steps, trimmed)
		}
	}

	// Flush remaining
	if current.Len() > 0 {
		steps = append(steps, current.String())
	}

	return steps
}

// ParseScriptFile reads a file and parses it into steps.
func ParseScriptFile(path string) ([]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	return ParseScript(string(data)), nil
}
