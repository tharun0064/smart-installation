#!/bin/bash
# ============================================================
# Scenario 4: Bad Configuration File
# Container has a malformed config — AI should detect
# the validation error and suggest the correct configuration
# ============================================================

set -e

# Navigate to project root (where Dockerfile lives)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "============================================"
echo " Scenario 4: Bad Configuration"
echo "============================================"
echo ""

# Clean up previous run
docker rm -f demo-scenario-4 2>/dev/null || true

# Build the nr-diagnose image
docker build -t nr-diagnose -f Dockerfile .

# Create a modified install script that assumes config already exists
# (skips config write step, goes straight to validation)
MODIFIED_INSTALL=$(mktemp)
cat > "$MODIFIED_INSTALL" <<'INSTALLEOF'
#!/bin/bash

# OpenTelemetry Oracle Database Receiver - Installation Script
# (Config is pre-existing, skip to validation)

# Step 1: Update package index
apt-get update

# Step 2: Install required tools (wget, curl)
apt-get install -y wget curl

# Step 3: Download OpenTelemetry Collector Contrib
wget -O /tmp/otelcol-contrib.tar.gz https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.127.0/otelcol-contrib_0.127.0_linux_arm64.tar.gz

# Step 4: Extract the collector binary
tar -xzf /tmp/otelcol-contrib.tar.gz -C /tmp/

# Step 5: Install binary to system path
mv /tmp/otelcol-contrib /usr/local/bin/otelcol-contrib

# Step 6: Make the binary executable
chmod +x /usr/local/bin/otelcol-contrib

# Step 7: Verify config exists
ls -la /etc/otelcol-contrib/config.yaml

# Step 8: Validate the collector configuration
/usr/local/bin/otelcol-contrib validate --config=/etc/otelcol-contrib/config.yaml

# Step 9: Start the collector (test run, 15 seconds)
timeout 15 /usr/local/bin/otelcol-contrib --config=/etc/otelcol-contrib/config.yaml 2>&1 | tail -30

# Step 10: Installation verification
echo "OpenTelemetry Oracle DB Receiver installation complete"
echo "Config: /etc/otelcol-contrib/config.yaml"
INSTALLEOF

# Create the broken config file to mount
BROKEN_CONFIG=$(mktemp)
cat > "$BROKEN_CONFIG" <<'BADEOF'
receivers:
  oracledb:
    endpoint: "oracledb:1521/XEPDB1"
    username: "monitoring_user"
    password: "monitor_pass_123"
  collection_interval: 60s

processors:
batch:
    timeout: 10s

exporters:
  otlphttp:
    endpoint: https://otlp.nr-data.net
    headers:
      api-key: "demo_license_key_123"
    invalid_key: true

service:
  pipelines:
    metrics:
      receivers: [oracledb]
      processors: [batch]
      exporters: [otlphttp, nonexistent_exporter]
BADEOF

# Run with broken config and modified install script
docker run --rm -it \
    --name demo-scenario-4 \
    --network demo-net \
    --env-file .env \
    -e ORACLE_HOST=oracledb \
    -e ORACLE_PORT=1521 \
    -e ORACLE_SERVICE=XEPDB1 \
    -e ORACLE_USERNAME=monitoring_user \
    -e ORACLE_PASSWORD=monitor_pass_123 \
    -e NEW_RELIC_LICENSE_KEY=demo_license_key_123 \
    -v "$MODIFIED_INSTALL":/app/agents/otel-oracledbreceiver/install.sh:ro \
    -v "$BROKEN_CONFIG":/tmp/broken-config:ro \
    --entrypoint bash \
    nr-diagnose -c "
        mkdir -p /etc/otelcol-contrib
        cp /tmp/broken-config /etc/otelcol-contrib/config.yaml
        nr-diagnose run --agent otel-oracledbreceiver
    "

rm -f "$MODIFIED_INSTALL" "$BROKEN_CONFIG"

echo ""
echo "Scenario 4 complete. Next: Run scenario-5-badcreds.sh"
