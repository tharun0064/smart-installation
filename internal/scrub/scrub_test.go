package scrub

import (
	"strings"
	"testing"
)

func TestScrub_LicenseKey(t *testing.T) {
	input := `license_key: abc123def456ghi789jkl012mno345pqr678stu`
	result := Scrub(input)
	if result == input {
		t.Error("expected scrubbing to change the input")
	}
	if !strings.Contains(result, "<REDACTED>") {
		t.Errorf("expected <REDACTED> in output, got: %s", result)
	}
}

func TestScrub_APIKey(t *testing.T) {
	input := `api_key: NRAK-XXXXXXXXXXXXXXXXXXXXXXXXXXXX`
	result := Scrub(input)
	if !strings.Contains(result, "<REDACTED>") {
		t.Errorf("expected <REDACTED> in output, got: %s", result)
	}
}

func TestScrub_Password(t *testing.T) {
	input := `password: "my_secret_pass123"`
	result := Scrub(input)
	if !strings.Contains(result, "<REDACTED>") {
		t.Errorf("expected <REDACTED> in output, got: %s", result)
	}
}

func TestScrub_NoSensitiveData(t *testing.T) {
	input := "just a normal log line with no secrets"
	result := Scrub(input)
	if result != input {
		t.Errorf("expected no change, got: %s", result)
	}
}
