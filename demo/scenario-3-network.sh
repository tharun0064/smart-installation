#!/bin/bash
# ============================================================
# Scenario 3: Network Isolation
# Container NOT on demo-net — can't reach OracleDB
# AI should diagnose connectivity and suggest network fix
# ============================================================

set -e

# Navigate to project root (where Dockerfile lives)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "============================================"
echo " Scenario 3: Network Isolation"
echo "============================================"
echo ""

# Clean up previous run
docker rm -f demo-scenario-3 2>/dev/null || true

# Build the nr-diagnose image
docker build -t nr-diagnose -f Dockerfile .

# Run in a container that is NOT on demo-net (isolated network)
docker run --rm -it \
    --name demo-scenario-3 \
    --env-file .env \
    -e ORACLE_HOST=oracledb \
    -e ORACLE_PORT=1521 \
    -e ORACLE_SERVICE=XEPDB1 \
    -e ORACLE_USERNAME=monitoring_user \
    -e ORACLE_PASSWORD=monitor_pass_123 \
    -e NEW_RELIC_LICENSE_KEY=demo_license_key_123 \
    nr-diagnose run --agent otel-oracledbreceiver

echo ""
echo "Scenario 3 complete. Next: Run scenario-4-badconfig.sh"
