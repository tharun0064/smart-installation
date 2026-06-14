#!/bin/bash
# ============================================================
# Cleanup: Remove all demo containers and network
# ============================================================

# Navigate to project root (where Dockerfile lives)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "Cleaning up demo environment..."

docker rm -f oracledb demo-scenario-2 demo-scenario-3 demo-scenario-4 demo-scenario-5 2>/dev/null || true
docker network rm demo-net 2>/dev/null || true

echo "Done. All demo containers and network removed."
