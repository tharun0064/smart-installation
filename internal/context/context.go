package context

import (
	"fmt"
	"os/exec"
	"runtime"
	"strings"
)

// OSContext holds collected system information.
type OSContext struct {
	OS           string
	Arch         string
	Distro       string
	Kernel       string
	Hostname     string
	CurrentUser  string
	ShellVersion string
}

// Collect gathers OS information from the current system.
func Collect() *OSContext {
	ctx := &OSContext{
		OS:   runtime.GOOS,
		Arch: runtime.GOARCH,
	}

	ctx.Distro = runCmd("lsb_release", "-ds")
	if ctx.Distro == "" {
		ctx.Distro = runCmd("cat", "/etc/os-release")
	}
	ctx.Kernel = runCmd("uname", "-r")
	ctx.Hostname = runCmd("hostname")
	ctx.CurrentUser = runCmd("whoami")
	ctx.ShellVersion = runCmd("bash", "--version")

	return ctx
}

// String formats the context for inclusion in LLM prompts.
func (c *OSContext) String() string {
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("OS: %s/%s\n", c.OS, c.Arch))
	if c.Distro != "" {
		sb.WriteString(fmt.Sprintf("Distro: %s\n", firstLine(c.Distro)))
	}
	if c.Kernel != "" {
		sb.WriteString(fmt.Sprintf("Kernel: %s\n", c.Kernel))
	}
	if c.Hostname != "" {
		sb.WriteString(fmt.Sprintf("Hostname: %s\n", c.Hostname))
	}
	if c.CurrentUser != "" {
		sb.WriteString(fmt.Sprintf("User: %s\n", c.CurrentUser))
	}
	return sb.String()
}

func runCmd(name string, args ...string) string {
	out, err := exec.Command(name, args...).Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}

func firstLine(s string) string {
	if idx := strings.IndexByte(s, '\n'); idx >= 0 {
		return s[:idx]
	}
	return s
}
