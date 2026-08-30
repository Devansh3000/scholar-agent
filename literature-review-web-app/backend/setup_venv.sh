#!/usr/bin/env bash
# Setup script for the literature-review-web-app backend virtual environment (Linux/macOS)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

echo "Creating Python virtual environment at $VENV_DIR ..."
python3 -m venv "$VENV_DIR"

echo "Activating virtual environment ..."
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "Upgrading pip ..."
pip install --upgrade pip

echo "Installing dependencies from requirements.txt ..."
pip install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "Setup complete. Activate the virtual environment with:"
echo "  source $VENV_DIR/bin/activate"
