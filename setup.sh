#!/bin/bash
# One-command setup for nr-diagnose
# Handles everything: Python install, venv, dependencies
# Usage: source setup.sh

set -e

echo "Setting up nr-diagnose..."
echo ""

# Detect OS
OS=""
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS="$ID"
elif [ "$(uname)" = "Darwin" ]; then
    OS="macos"
fi

# Function to install Python 3.11+ if missing
install_python() {
    echo "Python 3.11+ not found. Installing..."
    case "$OS" in
        ubuntu|debian)
            sudo apt update -y
            sudo apt install -y python3.11 python3.11-venv python3.11-pip python3.11-dev
            ;;
        rhel|ol|centos|rocky|almalinux|fedora|oraclelinux)
            sudo dnf install -y python3.11 python3.11-pip python3.11-devel
            ;;
        amzn)
            sudo yum install -y python3.11 python3.11-pip python3.11-devel
            ;;
        macos)
            if command -v brew &>/dev/null; then
                brew install python@3.11
            else
                echo "ERROR: Install Homebrew first: https://brew.sh"
                return 1 2>/dev/null || exit 1
            fi
            ;;
        *)
            echo "ERROR: Unsupported OS ($OS). Please install Python 3.11+ manually."
            return 1 2>/dev/null || exit 1
            ;;
    esac
    echo "Python installed successfully."
}

# Detect Python 3.11+
PYTHON=""
for candidate in python3.11 python3.12 python3.13 python3; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" --version 2>&1 | sed -n 's/Python \([0-9]*\.[0-9]*\).*/\1/p')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

# Install Python if not found
if [ -z "$PYTHON" ]; then
    install_python
    # Re-detect after install
    for candidate in python3.11 python3.12 python3.13 python3; do
        if command -v "$candidate" &>/dev/null; then
            version=$("$candidate" --version 2>&1 | sed -n 's/Python \([0-9]*\.[0-9]*\).*/\1/p')
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
                PYTHON="$candidate"
                break
            fi
        fi
    done
    if [ -z "$PYTHON" ]; then
        echo "ERROR: Python 3.11+ installation failed."
        return 1 2>/dev/null || exit 1
    fi
fi

echo "Using $PYTHON ($($PYTHON --version))"

# Ensure venv module is available (some distros package it separately)
if ! $PYTHON -m venv --help &>/dev/null; then
    echo "Installing venv module..."
    case "$OS" in
        ubuntu|debian)
            sudo apt install -y python3.11-venv
            ;;
        rhel|ol|centos|rocky|almalinux|fedora|oraclelinux)
            sudo dnf install -y python3.11-libs
            ;;
    esac
fi

# Create virtual environment if not already in one
if [ -z "$VIRTUAL_ENV" ]; then
    if [ ! -d "venv" ]; then
        echo "Creating virtual environment..."
        $PYTHON -m venv venv
    fi
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip --quiet

# Install the package (local editable install)
echo "Installing nr-diagnose and dependencies..."
pip install -e . --quiet

echo ""
echo "============================================"
echo " Setup complete!"
echo "============================================"
echo ""
echo " Run commands:"
echo "   nr-diagnose run --agent otel-oracledb"
echo "   nr-diagnose run --agent otel-oracledb --dry-run"
echo "   nr-diagnose list"
echo ""
echo " Next time, just run: source venv/bin/activate"
echo ""
