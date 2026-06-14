#!/bin/bash

# OpenTelemetry Oracle Database Receiver - Installation Script

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

# Step 7: Create configuration directory
mkdir -p /etc/otelcol-contrib

# Step 8: Test connectivity to Oracle Database
nc -zv ${ORACLE_HOST:-localhost} ${ORACLE_PORT:-1521}

# Step 9: Write OpenTelemetry Collector configuration
cat <<EOF > /etc/otelcol-contrib/config.yaml
receivers:
  oracledb:
    datasource: "oracle://${ORACLE_USERNAME}:${ORACLE_PASSWORD}@${ORACLE_HOST}:${ORACLE_PORT}/${ORACLE_SERVICE}"
    collection_interval: 60s
    metrics:
      oracledb.cpu_time:
        enabled: true
      oracledb.sessions.usage:
        enabled: true
      oracledb.tablespace_size.usage:
        enabled: true

processors:
  batch:
    timeout: 10s
  resource:
    attributes:
      - key: service.name
        value: oracledb-monitoring
        action: upsert

exporters:
  otlphttp:
    endpoint: ${NEW_RELIC_OTLP_ENDPOINT}
    headers:
      api-key: "${NEW_RELIC_LICENSE_KEY}"

service:
  pipelines:
    metrics:
      receivers: [oracledb]
      processors: [batch, resource]
      exporters: [otlphttp]
  telemetry:
    logs:
      level: info
EOF

# Step 10: Validate the collector configuration
/usr/local/bin/otelcol-contrib validate --config=/etc/otelcol-contrib/config.yaml

# Step 11: Start the collector and verify no errors (2-minute smoke test — long enough for ~2 export cycles at collection_interval: 60s)
timeout 120 /usr/local/bin/otelcol-contrib --config=/etc/otelcol-contrib/config.yaml > /tmp/otel-test.log 2>&1; OTEL_EXIT=$?; cat /tmp/otel-test.log | tail -30; if grep -qi "error\|ORA-\|failed" /tmp/otel-test.log; then echo "ERROR: Collector reported errors during test run"; exit 1; fi; if [ $OTEL_EXIT -ne 0 ] && [ $OTEL_EXIT -ne 124 ]; then exit $OTEL_EXIT; fi

# Step 12: Installation verification
echo "OpenTelemetry Oracle DB Receiver installation complete"
echo "Config: /etc/otelcol-contrib/config.yaml"
echo "Binary: /usr/local/bin/otelcol-contrib"
