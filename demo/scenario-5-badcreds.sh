#!/bin/bash
# ============================================================
# Scenario 5: Wrong Credentials
# Container has correct network but wrong Oracle user/password
# AI should detect ORA-01017 in logs and ask user to fix creds
# ============================================================

set -e

# Navigate to project root (where Dockerfile lives)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "============================================"
echo " Scenario 5: Wrong Credentials"
echo "============================================"
echo ""

# Clean up previous run
docker rm -f demo-scenario-5 2>/dev/null || true

# Build the nr-diagnose image
docker build -t nr-diagnose -f Dockerfile .

# Run with wrong credentials
docker run --rm -it \
    --name demo-scenario-5 \
    --network demo-net \
    --env-file .env \
    -e ORACLE_HOST=oracledb \
    -e ORACLE_PORT=1521 \
    -e ORACLE_SERVICE=XEPDB1 \
    -e ORACLE_USERNAME=wrong_user \
    -e ORACLE_PASSWORD=wrong_password \
    -e NEW_RELIC_LICENSE_KEY=demo_license_key_123 \
    nr-diagnose run --agent otel-oracledbreceiver

echo ""
echo "Scenario 5 complete."
