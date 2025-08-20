#!/usr/bin/env python3
"""Test runner for CELLxGENE Census MCP Server."""

import sys
import subprocess
import argparse
from pathlib import Path

def run_tests(test_type="all", verbose=False, coverage=False):
    """Run the test suite."""
    test_dir = Path(__file__).parent
    
    # Base pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Add test directory
    cmd.append(str(test_dir))
    
    # Add verbosity
    if verbose:
        cmd.append("-v")
    
    # Add coverage if requested
    if coverage:
        cmd.append("--cov=cellxgene_mcp")
        cmd.append("--cov-report=html")
        cmd.append("--cov-report=term-missing")
    
    # Filter tests by type
    if test_type == "unit":
        cmd.append("-k")
        cmd.append("not integration")
    elif test_type == "integration":
        cmd.append("-k")
        cmd.append("integration")
    elif test_type == "fast":
        cmd.append("-k")
        cmd.append("not slow")
    
    # Add test discovery
    cmd.append("--tb=short")
    
    print(f"Running tests: {' '.join(cmd)}")
    print("=" * 60)
    
    try:
        result = subprocess.run(cmd, check=True)
        print("=" * 60)
        print("✅ All tests passed!")
        return True
    except subprocess.CalledProcessError as e:
        print("=" * 60)
        print(f"❌ Tests failed with exit code {e.returncode}")
        return False
    except FileNotFoundError:
        print("❌ pytest not found. Please install pytest and pytest-asyncio:")
        print("   pip install pytest pytest-asyncio")
        return False

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run CELLxGENE Census MCP Server tests")
    parser.add_argument(
        "--type", 
        choices=["all", "unit", "integration", "fast"],
        default="all",
        help="Type of tests to run"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Generate coverage report"
    )
    
    args = parser.parse_args()
    
    print("🧪 CELLxGENE Census MCP Server Test Suite")
    print("=" * 60)
    
    success = run_tests(
        test_type=args.type,
        verbose=args.verbose,
        coverage=args.coverage
    )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
