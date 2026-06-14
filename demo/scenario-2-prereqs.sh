#!/bin/bash
# ============================================================
# Scenario 2: Missing Prerequisites (wget not found)
# Container has wget removed and install.sh modified to skip
# the apt-get install step. wget download fails immediately.
# AI should diagnose and suggest installing wget.
# ============================================================

set -e

# Navigate to project root (where Dockerfile lives)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "============================================"
echo " Scenario 2: Missing Prerequisites"
echo "============================================"
echo ""

# Clean up previous run
docker rm -f demo-scenario-2 2>/dev/null || true

# Build the nr-diagnose image
docker build -t nr-diagnose -f Dockerfile .

# Create a modified install script that skips prereq installation
# This simulates a real-world case where someone assumes tools are available
MODIFIED_INSTALL=$(mktemp)
cat > "$MODIFIED_INSTALL" <<'INSTALLEOF'
#!/bin/bash

# OpenTelemetry Oracle Database Receiver - Installation Script
# (Prerequisites assumed to be pre-installed)

# Step 1: Download OpenTelemetry Collector Contrib
wget -O /tmp/otelcol-contrib.tar.gz https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.127.0/otelcol-contrib_0.127.0_linux_arm64.tar.gz

# Step 2: Extract the collector binary
tar -xzf /tmp/otelcol-contrib.tar.gz -C /tmp/

# Step 3: Install binary to system path
mv /tmp/otelcol-contrib /usr/local/bin/otelcol-contrib

# Step 4: Make the binary executable
chmod +x /usr/local/bin/otelcol-contrib

# Step 5: Create configuration directory
mkdir -p /etc/otelcol-contrib

# Step 6: Test connectivity to Oracle Database
nc -zv ${ORACLE_HOST:-localhost} ${ORACLE_PORT:-1521}

# Step 7: Write OpenTelemetry Collector configuration
cat <<EOF > /etc/otelcol-contrib/config.yaml
receivers:
  oracledb:
    datasource: "oracle://${ORACLE_USERNAME}:${ORACLE_PASSWORD}@${ORACLE_HOST}:${ORACLE_PORT}/${ORACLE_SERVICE}"
    collection_interval: 60s

processors:
  batch:
    timeout: 10s

exporters:
  otlphttp:
    endpoint: https://otlp.nr-data.net
    headers:
      api-key: "${NEW_RELIC_LICENSE_KEY}"

service:
  pipelines:
    metrics:
      receivers: [oracledb]
      processors: [batch]
      exporters: [otlphttp]
EOF

# Step 8: Validate the collector configuration
/usr/local/bin/otelcol-contrib validate --config=/etc/otelcol-contrib/config.yaml

# Step 9: Installation verification
echo "OpenTelemetry Oracle DB Receiver installation complete"
echo "Config: /etc/otelcol-contrib/config.yaml"
echo "Binary: /usr/local/bin/otelcol-contrib"
INSTALLEOF

# Run with wget removed and modified install script
docker run --rm -it \
    --name demo-scenario-2 \
    --network demo-net \
    --env-file .env \
    -e ORACLE_HOST=oracledb \
    -e ORACLE_PORT=1521 \
    -e ORACLE_SERVICE=XEPDB1 \
    -e ORACLE_USERNAME=monitoring_user \
    -e ORACLE_PASSWORD=monitor_pass_123 \
    -e NEW_RELIC_LICENSE_KEY=demo_license_key_123 \
    -v "$MODIFIED_INSTALL":/app/agents/otel-oracledbreceiver/install.sh:ro \
    --entrypoint bash \
    nr-diagnose -c "
        apt-get remove -y wget >/dev/null 2>&1 || true
        hash -r
        nr-diagnose run --agent otel-oracledbreceiver
    "

rm -f "$MODIFIED_INSTALL"

echo ""
echo "Scenario 2 complete. Next: Run scenario-3-network.sh"
