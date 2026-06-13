#!/bin/bash
# One-command setup for nr-diagnose
# Usage: source setup.sh

set -e

echo "Setting up nr-diagnose..."

# Install dependencies and package
pip3 install -e . --quiet

# Get pip bin directory
PIP_BIN=$(python3 -c "import sysconfig; print(sysconfig.get_path('scripts'))")

# Add to PATH for this session
export PATH="$PIP_BIN:$PATH"

# Add to shell rc if not already there
SHELL_RC="$HOME/.zshrc"
if [ -n "$BASH_VERSION" ]; then
    SHELL_RC="$HOME/.bashrc"
fi

if ! grep -q "$PIP_BIN" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# nr-diagnose" >> "$SHELL_RC"
    echo "export PATH=\"$PIP_BIN:\$PATH\"" >> "$SHELL_RC"
    echo "Added $PIP_BIN to $SHELL_RC"
fi

echo ""
echo "Setup complete! You can now run:"
echo "  nr-diagnose run --agent otel-oracledb"
echo "  nr-diagnose list"
echo "  nr-diagnose run --agent otel-oracledb --dry-run"
echo ""
echo "Note: run 'source $SHELL_RC' or open a new terminal for PATH to persist."
