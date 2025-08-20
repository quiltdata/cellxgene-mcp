#!/usr/bin/env python3
"""CELLxGENE Census MCP Server - Main entry point for Claude Desktop Extension."""

import sys
import os
from pathlib import Path

# Add the lib directory to the Python path so we can import our package
HERE = Path(__file__).resolve().parent
LIB_DIR = HERE / "lib"
sys.path.insert(0, str(LIB_DIR))

try:
    from cellxgene_mcp.server import cli_app_stdio
except ImportError as e:
    print(f"Error importing cellxgene_mcp.server: {e}", file=sys.stderr)
    print(f"Python path: {sys.path}", file=sys.stderr)
    print(f"Current directory: {os.getcwd()}", file=sys.stderr)
    print(f"Files in lib directory: {list(LIB_DIR.glob('*')) if LIB_DIR.exists() else 'Directory not found'}", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    # Run the stdio server for Claude Desktop
    cli_app_stdio()
