# Adding a New Agent Integration

This guide walks you through the full experience of adding a new monitoring agent integration to the nr-diagnose framework — from scaffolding to running the AI-powered installer.

---

## Quick Overview

```
Step 1: Scaffold      →  nr-diagnose new-agent <name>
Step 2: Define        →  Fill in manifest, install script, knowledge
Step 3: Validate      →  nr-diagnose run --agent <name> --dry-run
Step 4: Run           →  nr-diagnose run --agent <name>
Step 5: Learn         →  Fixes get saved to runbook automatically
```

---

## Step 1: Scaffold the Agent

```bash
nr-diagnose new-agent otel-mysql
```

This creates:
```
agents/otel-mysql/
├── manifest.yaml
├── install.sh
├── knowledge/
│   ├── prerequisites.md
│   ├── common-failures.md
│   └── references.md
├── diagnostics/
│   └── hints.yaml
└── runbook/
    └── index.yaml
```

---

## Step 2: Define the Agent

### 2a. Edit `manifest.yaml`

Describe what this agent is:

```yaml
name: otel-mysql
display_name: "OpenTelemetry MySQL Receiver"
description: "Installs OTel Collector with the MySQL receiver for database monitoring"
target_os: linux
ports: [3306]
services: [otelcol-contrib]
prerequisites:
  - "MySQL server running and accessible"
  - "Monitoring user with SELECT and REPLICATION CLIENT privileges"
  - "Network connectivity to New Relic OTLP endpoint"
```

### 2b. Write `install.sh`

Write the bash steps to install and configure. Each logical command is one step:

```bash
#!/bin/bash
# OTel Collector + MySQL Receiver Installation

# Step 1: Download OTel Collector
curl -sL https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.96.0/otelcol-contrib_0.96.0_linux_amd64.deb -o /tmp/otelcol-contrib.deb

# Step 2: Install OTel Collector
dpkg -i /tmp/otelcol-contrib.deb

# Step 3: Verify MySQL connectivity
mysql -u otel_monitor -p'${MYSQL_PASSWORD}' -h ${MYSQL_HOST} -e "SELECT 1"

# Step 4: Write OTel config
tee /etc/otelcol-contrib/config.yaml <<'EOF'
receivers:
  mysql:
    endpoint: "${MYSQL_HOST}:3306"
    username: "otel_monitor"
    password: "${MYSQL_PASSWORD}"
    collection_interval: 60s
exporters:
  otlp:
    endpoint: "https://otlp.nr-data.net:4317"
    headers:
      api-key: "${NEW_RELIC_LICENSE_KEY}"
service:
  pipelines:
    metrics:
      receivers: [mysql]
      exporters: [otlp]
EOF

# Step 5: Start collector
systemctl enable otelcol-contrib
systemctl start otelcol-contrib

# Step 6: Verify running
systemctl is-active otelcol-contrib
```

**Tips:**
- Each comment block + command = one step
- Use environment variables for secrets (they won't be sent to LLM — scrubber redacts them)
- Heredocs (`<<'EOF' ... EOF`) are handled as single steps automatically

### 2c. Fill in `knowledge/common-failures.md`

Tell the AI what commonly goes wrong:

```markdown
# Common Failures

## MySQL connection refused
- MySQL not running or not listening on expected port
- Firewall blocking port 3306
- bind-address in my.cnf set to 127.0.0.1 (remote access blocked)

## Access denied for user
- Wrong password
- User doesn't exist
- User missing required privileges (PROCESS, REPLICATION CLIENT)

## OTel collector won't start
- Config YAML syntax error
- Port 4317 already in use
- Missing NEW_RELIC_LICENSE_KEY environment variable
```

### 2d. Fill in `knowledge/prerequisites.md`

```markdown
# Prerequisites

1. MySQL server installed and running
2. Monitoring user created:
   ```sql
   CREATE USER 'otel_monitor'@'%' IDENTIFIED BY 'your_password';
   GRANT PROCESS, REPLICATION CLIENT, SELECT ON *.* TO 'otel_monitor'@'%';
   FLUSH PRIVILEGES;
   ```
3. Network: port 3306 accessible from collector host
4. Network: outbound HTTPS to otlp.nr-data.net:4317
5. New Relic License Key available
```

### 2e. Fill in `diagnostics/hints.yaml`

Tell the AI which diagnostic commands are most useful for this agent:

```yaml
priority_commands:
  - "nc -zv localhost 3306"
  - "mysql --version"
  - "systemctl status otelcol-contrib"
  - "cat /etc/otelcol-contrib/config.yaml"
  - "ss -tlnp | grep 3306"
  - "journalctl -u otelcol-contrib --no-pager -n 20"

context_hints:
  - "MySQL default port is 3306"
  - "OTel collector runs as 'otelcol' user — check file permissions"
  - "Config YAML indentation errors are the #1 cause of collector startup failures"
  - "Check if NEW_RELIC_LICENSE_KEY env var is set for the otelcol service"
```

---

## Step 3: Validate (Dry Run)

See what steps were parsed without executing anything:

```bash
nr-diagnose run --agent otel-mysql --dry-run
```

Expected output:
```
Agent: OpenTelemetry MySQL Receiver
Description: Installs OTel Collector with the MySQL receiver for database monitoring

Parsed 6 steps

Dry-run mode: showing parsed steps without executing
  [1/6] curl -sL ... -o /tmp/otelcol-contrib.deb
  [2/6] dpkg -i /tmp/otelcol-contrib.deb
  [3/6] mysql -u otel_monitor -p'...' -h ... -e "SELECT 1"
  [4/6] tee /etc/otelcol-contrib/config.yaml <<'EOF' ...
  [5/6] systemctl enable otelcol-contrib && systemctl start otelcol-contrib
  [6/6] systemctl is-active otelcol-contrib
```

---

## Step 4: Run the Installer

```bash
nr-diagnose run --agent otel-mysql
```

The AI wrapper will:
1. Execute each step
2. On failure → check runbook for known fixes
3. If no known fix → call LLM (Turn 1: diagnose, Turn 2: remediate)
4. Show you the diagnosis and suggested fix
5. Prompt: `[Y]es / [n]o / [q]uit`
6. If you say Y and it works → save to runbook for next time

---

## Step 5: Runbook Grows Automatically

After a successful fix, it gets saved to `~/.nr-diagnose/runbook/otel-mysql/`:

```yaml
entries:
  - pattern: "access denied for user"
    entry_file: "001-access-denied-for-user.md"
```

Next time the same error occurs, the fix is applied instantly without calling the LLM.

To share with your team:
```bash
nr-diagnose sync
```

---

## Example Agents You Can Add

| Agent Name | Description | Key Ports |
|---|---|---|
| `otel-mysql` | OTel Collector + MySQL receiver | 3306 |
| `otel-oracledb` | OTel Collector + OracleDB receiver | 1521 |
| `otel-postgres` | OTel Collector + PostgreSQL receiver | 5432 |
| `otel-redis` | OTel Collector + Redis receiver | 6379 |
| `otel-mongodb` | OTel Collector + MongoDB receiver | 27017 |
| `nr-infra` | New Relic Infrastructure Agent | - |
| `nr-java-apm` | New Relic Java APM Agent | 8080 |
| `nr-dotnet-apm` | New Relic .NET APM Agent | 5000 |

---

## Full Example: Adding OTel + OracleDB

```bash
# 1. Scaffold
nr-diagnose new-agent otel-oracledb

# 2. Edit the files (see below)

# 3. Dry run
nr-diagnose run --agent otel-oracledb --dry-run

# 4. Run for real
nr-diagnose run --agent otel-oracledb
```

**`agents/otel-oracledb/manifest.yaml`:**
```yaml
name: otel-oracledb
display_name: "OpenTelemetry OracleDB Receiver"
description: "Installs OTel Collector with the OracleDB receiver for database monitoring"
target_os: linux
ports: [1521]
services: [otelcol-contrib]
prerequisites:
  - "Oracle Instant Client installed"
  - "TNS_ADMIN and ORACLE_HOME environment variables set"
  - "Network connectivity to Oracle DB on port 1521"
  - "Monitoring user with SELECT privileges on V$ views"
```

**`agents/otel-oracledb/install.sh`:**
```bash
#!/bin/bash
# OTel Collector + OracleDB Receiver Installation

# Step 1: Download OTel Collector
curl -sL https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.96.0/otelcol-contrib_0.96.0_linux_amd64.deb -o /tmp/otelcol-contrib.deb

# Step 2: Install OTel Collector
dpkg -i /tmp/otelcol-contrib.deb

# Step 3: Verify Oracle Instant Client
ls $ORACLE_HOME/lib/libclntsh.so

# Step 4: Test TNS connectivity
tnsping ORCL

# Step 5: Test Oracle DB connectivity
echo "SELECT 1 FROM DUAL;" | sqlplus -s otel_monitor/password@ORCL

# Step 6: Write OTel config
tee /etc/otelcol-contrib/config.yaml <<'EOF'
receivers:
  oracledb:
    datasource: "oracle://otel_monitor:password@localhost:1521/ORCL"
    collection_interval: 60s
exporters:
  otlp:
    endpoint: "https://otlp.nr-data.net:4317"
    headers:
      api-key: "${NEW_RELIC_LICENSE_KEY}"
service:
  pipelines:
    metrics:
      receivers: [oracledb]
      exporters: [otlp]
EOF

# Step 7: Start collector
systemctl enable otelcol-contrib
systemctl start otelcol-contrib

# Step 8: Verify running
systemctl is-active otelcol-contrib
```

**`agents/otel-oracledb/diagnostics/hints.yaml`:**
```yaml
priority_commands:
  - "tnsping ORCL"
  - "nc -zv localhost 1521"
  - "echo $TNS_ADMIN"
  - "echo $ORACLE_HOME"
  - "ls $ORACLE_HOME/lib/libclntsh.so"
  - "systemctl status otelcol-contrib"
  - "cat /etc/otelcol-contrib/config.yaml"

context_hints:
  - "TNS resolution failures are the #1 cause of OracleDB receiver issues"
  - "Check listener.ora and tnsnames.ora in $TNS_ADMIN"
  - "OTel collector runs as 'otelcol' user — needs read access to Oracle client libs"
  - "LD_LIBRARY_PATH must include $ORACLE_HOME/lib for the otelcol service"
```

---

## Tips for Writing Good Agents

1. **Keep steps atomic** — one command per step, so failures are precise
2. **Add verification steps** — after install, verify the thing works
3. **Use heredocs for config** — the parser handles `<<'EOF' ... EOF` correctly
4. **Fill in common-failures.md** — the more you tell the AI, the better its first diagnosis
5. **Seed the runbook** — if you already know fixes, put them in `runbook/index.yaml`
6. **Test with --dry-run first** — make sure the parser splits steps correctly
