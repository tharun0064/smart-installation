#!/bin/bash
# ============================================================
# Scenario 1: Start Oracle Database (mock) container
# This sets up the prerequisite for all other scenarios
# ============================================================

set -e

# Navigate to project root (where Dockerfile lives)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "============================================"
echo " Scenario 1: Oracle Database Setup"
echo "============================================"
echo ""
echo "Starting Oracle Database mock container..."
echo ""

# Create a shared network for all demo containers
docker network create demo-net 2>/dev/null || true

# Clean up previouswget is not installed on the system, but curl is available
docker rm -f oracledb 2>/dev/null || true

# Start a lightweight container that listens on port 1521
# This simulates an Oracle DB for the demo (nc connectivity checks pass)
# On ARM Macs, real Oracle XE doesn't work under emulation
docker run -d \
    --name oracledb \
    --network demo-net \
    -p 1521:1521 \
    python:3.11-slim \
    bash -c "apt-get update -qq && apt-get install -y -qq netcat-openbsd >/dev/null 2>&1; echo 'Oracle DB mock listening on port 1521'; while true; do echo -e 'ORA-01017: invalid username/password; logon denied' | nc -l -p 1521 -q 1 2>/dev/null || nc -l -p 1521 2>/dev/null; done"

echo "Waiting for mock Oracle to be ready..."
sleep 5

# Verify it's listening
if docker exec oracledb bash -c "nc -zv localhost 1521" 2>&1 | grep -q "open\|succeeded"; then
    echo ""
    echo "Oracle DB mock is ready!"
else
    echo "Waiting a bit more..."
    sleep 10
fi

echo ""
echo "============================================"
echo " Oracle DB (Mock) Details:"
echo "   Host: oracledb (on demo-net)"
echo "   Port: 1521"
echo "   Service: XEPDB1"
echo "   Note: This is a mock for demo purposes."
echo "         It responds to connectivity tests (nc)"
echo "         and returns ORA errors for auth attempts."
echo "============================================"
echo ""
echo "Next: Run scenario-2-prereqs.sh"
