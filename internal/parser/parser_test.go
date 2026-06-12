// internal/parser/parser_test.go
package parser

import (
	"testing"
)

func TestParseScript_BasicCommands(t *testing.T) {
	script := `#!/bin/bash
# This is a comment
set -e

echo "hello"

sudo apt-get update

# Another comment
curl -s https://example.com | sudo tee /etc/foo
`
	steps := ParseScript(script)

	if len(steps) != 3 {
		t.Fatalf("expected 3 steps, got %d: %v", len(steps), steps)
	}
	if steps[0] != `echo "hello"` {
		t.Errorf("step 0: got %q", steps[0])
	}
	if steps[1] != "sudo apt-get update" {
		t.Errorf("step 1: got %q", steps[1])
	}
	if steps[2] != "curl -s https://example.com | sudo tee /etc/foo" {
		t.Errorf("step 2: got %q", steps[2])
	}
}

func TestParseScript_Continuations(t *testing.T) {
	script := `echo "line1" \
"line2" \
"line3"
`
	steps := ParseScript(script)
	if len(steps) != 1 {
		t.Fatalf("expected 1 step, got %d: %v", len(steps), steps)
	}
	expected := `echo "line1" "line2" "line3"`
	if steps[0] != expected {
		t.Errorf("got %q, want %q", steps[0], expected)
	}
}

func TestParseScript_AndChains(t *testing.T) {
	script := `apt-get update && apt-get install -y foo
echo done
`
	steps := ParseScript(script)
	if len(steps) != 2 {
		t.Fatalf("expected 2 steps, got %d: %v", len(steps), steps)
	}
	if steps[0] != "apt-get update && apt-get install -y foo" {
		t.Errorf("step 0: got %q", steps[0])
	}
}

func TestParseScript_EmptyInput(t *testing.T) {
	steps := ParseScript("")
	if len(steps) != 0 {
		t.Fatalf("expected 0 steps, got %d", len(steps))
	}
}
