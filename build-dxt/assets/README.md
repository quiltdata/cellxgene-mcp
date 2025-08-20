# CELLxGENE Census MCP DXT

A Claude Desktop Extension (DXT) that provides access to CELLxGENE Census data through the Model Context Protocol (MCP).

## What is CELLxGENE Census?

The CELLxGENE Census is a comprehensive collection of single-cell RNA sequencing data from CZ CELLxGENE Discover. It provides access to:

- **Human and mouse single-cell data**
- **Over 100 million cells** across multiple studies
- **Rich metadata** including cell types, tissues, diseases, and more
- **Gene expression data** for analysis and exploration

## Installation

### Prerequisites

1. **Python 3.10+** - Required for the MCP server
2. **Claude Desktop** - Latest version recommended
3. **Internet connection** - For downloading dependencies and accessing Census data

### Quick Start

1. **Download the DXT file** from this release
2. **Run prerequisites check**: `./check-prereqs.sh`
3. **Install in Claude Desktop**: Double-click the `.dxt` file
4. **Start using**: Ask Claude to access CELLxGENE Census data!

## Configuration

The DXT supports the following configuration options:

- **Census Version**: Specify a particular Census version (optional, defaults to latest)
- **Log Level**: Set logging verbosity (info, debug, error)

## Usage Examples

Once installed, you can ask Claude to:

- "Show me available cell types in the human Census"
- "What tissues are available in the mouse Census?"
- "Get metadata for T cells from lung tissue"
- "Find studies related to COVID-19"
- "Show me gene expression data for specific genes"

## Available Tools

The DXT provides several MCP tools:

- **`get_census_info`** - Get information about available Census versions and organisms
- **`get_obs_metadata`** - Retrieve cell (observation) metadata
- **`get_var_metadata`** - Retrieve gene (variable) metadata  
- **`get_data_slice`** - Get summary data slices based on filters
- **`get_all_cell_types`** - List all available cell types

## Data Access

The DXT connects to the CELLxGENE Census through the official API, providing:

- **Fast access** to Census data
- **Efficient filtering** by cell type, tissue, disease, etc.
- **S3-optimized** data transfer for large datasets
- **Local caching** for improved performance

## Troubleshooting

### Common Issues

1. **Dependencies not installing**: Ensure you have Python 3.10+ and internet access
2. **Server not starting**: Check the prerequisites script output
3. **Data access errors**: Verify your internet connection and Census API status

### Getting Help

- **Check prerequisites**: Run `./check-prereqs.sh` to validate your system
- **View logs**: Check Claude Desktop's extension logs for error details
- **GitHub Issues**: Report problems at [quiltdata/cellxgene-mcp](https://github.com/quiltdata/cellxgene-mcp)

## Development

This DXT is built using:

- **FastMCP** - MCP server framework
- **cellxgene-census** - Official Census Python client
- **Anthropic DXT CLI** - Official DXT packaging tools

## License

Apache 2.0 - See LICENSE file for details.

## Support

For questions and support:

- **GitHub**: [quiltdata/cellxgene-mcp](https://github.com/quiltdata/cellxgene-mcp)
- **Documentation**: [CELLxGENE Census](https://census.cellxgene.cziscience.com/)
- **Quilt Data**: [quiltdata.com](https://quiltdata.com)
