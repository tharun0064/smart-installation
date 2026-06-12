#!/bin/bash
# OTel Collector + OracleDB Receiver Installation

# Step 1: Download OTel Collector Contrib
curl -sL https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.96.0/otelcol-contrib_0.96.0_linux_amd64.deb -o /tmp/otelcol-contrib.deb

# Step 2: Install OTel Collector
sudo dpkg -i /tmp/otelcol-contrib.deb

# Step 3: Verify Oracle Instant Client
ls $ORACLE_HOME/lib/libclntsh.so

# Step 4: Verify TNS configuration
tnsping ORCL

# Step 5: Test Oracle connectivity
echo "SELECT 1 FROM DUAL;" | sqlplus -s otel_monitor/password@ORCL

# Step 6: Write OTel config
sudo tee /etc/otelcol-contrib/config.yaml <<'EOF'
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

# Step 7: Start OTel Collector
sudo systemctl enable otelcol-contrib
sudo systemctl start otelcol-contrib

# Step 8: Verify collector is running
systemctl is-active otelcol-contrib
