# CELLxGENE Census MCP DXT Build System

This directory contains the build system for creating Claude Desktop Extensions (DXT) from the CELLxGENE Census MCP server.

## What is a DXT?

A DXT (Desktop Extension) is a package that allows Claude Desktop to use external tools and data sources through the Model Context Protocol (MCP). This DXT provides access to the CELLxGENE Census, a comprehensive collection of single-cell RNA sequencing data.

## Prerequisites

To build the DXT, you need:

- **Node.js 18+** (for the DXT CLI tools)
- **Python 3.11+** (for the MCP server)
- **uv** package manager (for Python dependency management)

## Quick Build

```bash
# Check if you have the required tools
make check-tools

# Build the DXT package
make build

# The DXT file will be created in dist/
```

## Available Make Targets

- **`make help`** - Show all available targets
- **`make check-tools`** - Verify required tools are installed
- **`make build`** - Build the DXT package
- **`make test`** - Test the build before packaging
- **`make validate`** - Validate the DXT package
- **`make release`** - Create a complete release package
- **`make clean`** - Clean build artifacts
- **`make debug`** - Show build configuration

## Build Process

The build process:

1. **Copies assets** (manifest, bootstrap script, etc.)
2. **Copies source code** from `../src/cellxgene_mcp/`
3. **Installs dependencies** using uv
4. **Packages everything** using the official DXT CLI
5. **Creates the .dxt file** ready for Claude Desktop

## Testing

Before building, you can test the components:

```bash
# Test the bootstrap script
make test

# Test the prerequisites checker
make assess
```

## GitHub Actions

The DXT is automatically built and released through GitHub Actions:

- **Feature branches**: Build DXT and upload as artifacts
- **Main branch**: Build DXT for testing
- **Version tags**: Create GitHub releases with DXT files

## Manual Release

To create a release manually:

```bash
# Set version and build release
make release VERSION=1.0.0

# This creates:
# - dist/cellxgene-mcp-1.0.0.dxt
# - dist/cellxgene-mcp-1.0.0-release.zip
```

## Installation

Once built, the DXT can be installed in Claude Desktop:

1. Double-click the `.dxt` file
2. Follow the installation prompts
3. Configure any required settings
4. Start using CELLxGENE Census data through Claude!

## Troubleshooting

### Build Issues

- **Missing tools**: Run `make check-tools` to verify requirements
- **Python errors**: Ensure you have Python 3.11+ and uv installed
- **Node.js errors**: Install Node.js 18+ for DXT CLI tools

### Runtime Issues

- **Import errors**: Check that dependencies were installed correctly
- **Server not starting**: Run `./check-prereqs.sh` to validate system
- **Census access**: Verify internet connectivity and Census API status

## Development

To modify the DXT:

1. **Edit assets** in the `assets/` directory
2. **Update source** in `../src/cellxgene_mcp/`
3. **Rebuild** with `make clean && make build`
4. **Test** with `make test`

## Structure

```
build-dxt/
├── assets/           # DXT configuration and scripts
│   ├── manifest.json # DXT manifest
│   ├── bootstrap.py  # Environment setup script
│   ├── dxt_main.py  # Server entry point
│   ├── requirements.txt # Python dependencies
│   ├── check-prereqs.sh # System validation
│   └── README.md    # User documentation
├── Makefile         # Build automation
└── .gitignore      # Exclude build artifacts
```
