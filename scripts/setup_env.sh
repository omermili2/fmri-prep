#!/bin/bash

# Setup Environment Script
# Use this script when migrating the project to a new computer.
# It checks for prerequisites and sets up the Python environment.

echo "=== fMRI Project Setup ==="

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install it first."
    exit 1
else
    echo "✅ Python 3 found: $(python3 --version)"
fi

# 2. Check dcm2niix
if ! command -v dcm2niix &> /dev/null; then
    echo "⚠️  dcm2niix is NOT installed."
    echo "   Please install it manually:"
    echo "   - macOS: brew install dcm2niix"
    echo "   - Linux: apt-get install dcm2niix (or see github.com/rordenlab/dcm2niix)"
else
    echo "✅ dcm2niix found."
fi

# 3. Check Docker
if ! command -v docker &> /dev/null; then
    echo "⚠️  Docker is NOT installed."
    echo "   fMRIPrep requires Docker. Please install Docker Desktop."
else
    echo "✅ Docker found."
fi

# 4. Create Virtual Environment
echo "--- Setting up Python Virtual Environment ---"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Created 'venv' directory."
else
    echo "'venv' already exists."
fi

# 5. Install Dependencies
source venv/bin/activate
echo "Installing dependencies from requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "=== Setup Complete ==="
echo "To start working:"
echo "  source venv/bin/activate"

