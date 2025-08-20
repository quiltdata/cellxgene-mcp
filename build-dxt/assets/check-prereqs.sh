#!/bin/bash

# CELLxGENE Census MCP DXT Prerequisites Check
# This script validates that your system meets the requirements to run the DXT

set -e

echo "🔍 Checking prerequisites for CELLxGENE Census MCP DXT..."
echo "=================================================="

# Check Python version
echo "🐍 Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    
    if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 10 ]; then
        echo "✅ Python $PYTHON_VERSION found (Python 3.10+ required)"
    else
        echo "❌ Python $PYTHON_VERSION found, but Python 3.10+ is required"
        exit 1
    fi
else
    echo "❌ Python 3 not found. Please install Python 3.10 or later."
    exit 1
fi

# Check pip
echo "📦 Checking pip..."
if command -v pip3 &> /dev/null; then
    echo "✅ pip3 found"
elif command -v pip &> /dev/null; then
    echo "✅ pip found"
else
    echo "❌ pip not found. Please install pip."
    exit 1
fi

# Check virtual environment support
echo "🏗️  Checking virtual environment support..."
if python3 -m venv --help &> /dev/null; then
    echo "✅ Python venv module available"
else
    echo "❌ Python venv module not available. Please ensure your Python installation includes venv."
    exit 1
fi

# Check available disk space (need at least 1GB for dependencies)
echo "💾 Checking available disk space..."
AVAILABLE_SPACE=$(df . | awk 'NR==2 {print $4}')
AVAILABLE_SPACE_GB=$((AVAILABLE_SPACE / 1024 / 1024))

if [ $AVAILABLE_SPACE_GB -ge 1 ]; then
    echo "✅ Available disk space: ${AVAILABLE_SPACE_GB}GB (1GB+ required)"
else
    echo "❌ Insufficient disk space: ${AVAILABLE_SPACE_GB}GB available, 1GB+ required"
    exit 1
fi

# Check internet connectivity (needed for downloading dependencies)
echo "🌐 Checking internet connectivity..."
if ping -c 1 pypi.org &> /dev/null; then
    echo "✅ Internet connectivity confirmed (PyPI reachable)"
else
    echo "⚠️  Internet connectivity check failed. Please ensure you have internet access for installing dependencies."
fi

# Check if running on supported platform
echo "🖥️  Checking platform compatibility..."
PLATFORM=$(uname -s)
if [[ "$PLATFORM" == "Darwin" || "$PLATFORM" == "Linux" ]]; then
    echo "✅ Platform $PLATFORM is supported"
else
    echo "⚠️  Platform $PLATFORM may not be fully supported. Testing recommended."
fi

echo ""
echo "=================================================="
echo "🎉 Prerequisites check completed successfully!"
echo ""
echo "Your system is ready to run the CELLxGENE Census MCP DXT."
echo ""
echo "Next steps:"
echo "1. Install the DXT file in Claude Desktop"
echo "2. Configure your Census version preferences (optional)"
echo "3. Start using CELLxGENE Census data through Claude!"
echo ""
echo "For support, visit: https://github.com/quiltdata/cellxgene-mcp"
