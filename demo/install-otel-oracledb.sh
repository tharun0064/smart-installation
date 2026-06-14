#!/bin/bash

# OpenTelemetry Oracle Database Receiver Installation Script
# Installs and configures the OpenTelemetry Collector with Oracle DB receiver

# Step 1: Update package index
apt-get update

# Step 2: Install required dependencies
apt-get install -y wget curl

# Step 3: Download OpenTelemetry Collector Contrib
wget -O /tmp/otelcol-contrib.tar.gz https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.127.0/otelcol-contrib_0.127.0_linux_arm64.tar.gz

# Step 4: Extract the binary
tar -xzf /tmp/otelcol-contrib.tar.gz -C /tmp/

# Step 5: Install binary to system path
mv /tmp/otelcol-contrib /usr/local/bin/otelcol-contrib
chmod +x /usr/local/bin/otelcol-contrib

# Step 6: Create configuration directory
mkdir -p /etc/otelcol-contrib

# Step 7: Test connectivity to Oracle Database
nc -zv ${ORACLE_HOST:-oracledb} ${ORACLE_PORT:-1521}

# Step 8: Write OpenTelemetry Collector configuration
cat <<'EOF' > /etc/otelcol-contrib/config.yaml
receivers:
  oracledb:
    endpoint: "${ORACLE_HOST}:${ORACLE_PORT}/${ORACLE_SERVICE}"
    username: "${ORACLE_USERNAME}"
    password: "${ORACLE_PASSWORD}"
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

# Step 9: Validate the configuration
/usr/local/bin/otelcol-contrib validate --config=/etc/otelcol-contrib/config.yaml

# Step 10: Start the collector in test mode (foreground, 10s timeout)
timeout 10 /usr/local/bin/otelcol-contrib --config=/etc/otelcol-contrib/config.yaml 2>&1 | head -50

echo ""
echo "Installation complete. Check collector logs for connectivity status."
