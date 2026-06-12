package diagnostics

import (
	"fmt"
	"os/exec"
	"strings"
)

var allowedCommands = map[string]bool{
	"ping":       true,
	"nc":         true,
	"netstat":    true,
	"ss":         true,
	"curl":       true,
	"traceroute": true,
	"nslookup":   true,
	"dig":        true,
	"ps":         true,
	"lsof":       true,
	"df":         true,
	"free":       true,
	"dpkg":       true,
	"apt":        true,
	"rpm":        true,
	"cat":        true,
	"ufw":        true,
	"iptables":   true,
	"systemctl":  true,
	"wget":       true,
}

// IsAllowed checks if a command is safe to execute as a diagnostic.
func IsAllowed(cmd string) bool {
	parts := strings.Fields(cmd)
	if len(parts) == 0 {
		return false
	}

	base := parts[0]
	if base == "sudo" && len(parts) > 1 {
		return false
	}

	if !allowedCommands[base] {
		return false
	}

	switch base {
	case "systemctl":
		if len(parts) < 2 || parts[1] != "status" {
			return false
		}
	case "ufw":
		if len(parts) < 2 || parts[1] != "status" {
			return false
		}
	case "iptables":
		if !containsFlag(parts, "-L") {
			return false
		}
	case "cat":
		if len(parts) < 2 || !strings.HasPrefix(parts[len(parts)-1], "/etc/") {
			return false
		}
	case "wget":
		if containsFlag(parts, "-O") {
			return false
		}
	}

	return true
}

// RunDiagnostic executes a single diagnostic command and returns its output.
func RunDiagnostic(cmd string) (string, error) {
	if !IsAllowed(cmd) {
		return "", fmt.Errorf("command not allowed: %q", cmd)
	}

	out, err := exec.Command("bash", "-c", cmd).CombinedOutput()
	output := string(out)
	if err != nil {
		return output, nil
	}
	return output, nil
}

// RunAll executes multiple diagnostic commands and returns combined output.
func RunAll(commands []string) map[string]string {
	results := make(map[string]string)
	for _, cmd := range commands {
		output, err := RunDiagnostic(cmd)
		if err != nil {
			results[cmd] = fmt.Sprintf("[BLOCKED] %s", err.Error())
		} else {
			results[cmd] = output
		}
	}
	return results
}

func containsFlag(parts []string, flag string) bool {
	for _, p := range parts {
		if p == flag {
			return true
		}
	}
	return false
}
