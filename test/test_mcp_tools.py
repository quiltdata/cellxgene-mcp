#!/usr/bin/env python3
"""Unit tests for CELLxGENE Census MCP Server tools."""

import pytest
import asyncio
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cellxgene_mcp.server import CellxGeneMCP, CensusManager
from cellxgene_mcp.server import QueryResult, S3DataReference, S3TransferResult


class TestCensusManager:
    """Test the CensusManager class functionality."""
    
    def test_census_manager_initialization(self):
        """Test CensusManager can be initialized."""
        manager = CensusManager()
        assert manager is not None
        assert manager.census_version is None
    
    def test_census_manager_with_version(self):
        """Test CensusManager with specific version."""
        manager = CensusManager(census_version="2023-12-15")
        assert manager.census_version == "2023-12-15"
    
    @patch('cellxgene_mcp.server.cellxgene_census')
    def test_get_census_versions(self, mock_census):
        """Test getting Census versions."""
        mock_versions = {
            'stable': {'release_build': '2023-12-15'},
            'latest': {'release_build': '2024-01-15'}
        }
        mock_census.get_census_version_directory.return_value = mock_versions
        
        manager = CensusManager()
        versions = manager._get_census_versions()
        assert versions == mock_versions
    
    @patch('cellxgene_mcp.server.cellxgene_census')
    def test_get_census_connection(self, mock_census):
        """Test getting Census connection."""
        mock_census_obj = Mock()
        mock_census.open_soma.return_value = mock_census_obj
        
        manager = CensusManager()
        census = manager.get_census()
        assert census == mock_census_obj
        mock_census.open_soma.assert_called_once()


class TestQueryResult:
    """Test the QueryResult model."""
    
    def test_query_result_creation(self):
        """Test QueryResult can be created with valid data."""
        rows = [{"id": 1, "name": "test"}]
        result = QueryResult(
            rows=rows,
            count=1,
            query_info={"test": "info"}
        )
        
        assert result.rows == rows
        assert result.count == 1
        assert result.query_info["test"] == "info"
    
    def test_query_result_empty(self):
        """Test QueryResult with empty data."""
        result = QueryResult(
            rows=[],
            count=0,
            query_info={}
        )
        
        assert result.rows == []
        assert result.count == 0
        assert result.query_info == {}


class TestS3DataReference:
    """Test the S3DataReference model."""
    
    def test_s3_data_reference_creation(self):
        """Test S3DataReference can be created."""
        ref = S3DataReference(
            uri="s3://bucket/key",
            bucket="bucket",
            key="key",
            region="us-west-2",
            metadata={"version": "1.0"}
        )
        
        assert ref.uri == "s3://bucket/key"
        assert ref.bucket == "bucket"
        assert ref.key == "key"
        assert ref.region == "us-west-2"
        assert ref.metadata["version"] == "1.0"


class TestS3TransferResult:
    """Test the S3TransferResult model."""
    
    def test_s3_transfer_result_success(self):
        """Test S3TransferResult for successful transfer."""
        result = S3TransferResult(
            source_uri="s3://source/key",
            destination_uri="s3://dest/key",
            transfer_size=1024,
            success=True,
            message="Transfer completed"
        )
        
        assert result.source_uri == "s3://source/key"
        assert result.destination_uri == "s3://dest/key"
        assert result.transfer_size == 1024
        assert result.success is True
        assert result.message == "Transfer completed"
    
    def test_s3_transfer_result_failure(self):
        """Test S3TransferResult for failed transfer."""
        result = S3TransferResult(
            source_uri="s3://source/key",
            destination_uri="s3://dest/key",
            transfer_size=0,
            success=False,
            message="Transfer failed"
        )
        
        assert result.success is False
        assert result.transfer_size == 0


class TestCellxGeneMCP:
    """Test the main MCP server class."""
    
    @pytest.fixture
    def mcp_server(self):
        """Create a test MCP server instance."""
        return CellxGeneMCP(name="TestServer")
    
    def test_server_initialization(self, mcp_server):
        """Test MCP server can be initialized."""
        assert mcp_server.name == "TestServer"
        assert mcp_server.prefix == "cellxgene_"
        assert mcp_server.census_manager is not None
    
    def test_server_tools_registration(self, mcp_server):
        """Test that all expected tools are registered."""
        # Get the tools (this might be async in some implementations)
        tools = mcp_server.get_tools()
        
        # Check that expected tools exist
        tool_names = [tool.name for tool in tools]
        expected_tools = [
            "cellxgene_get_census_info",
            "cellxgene_get_obs_metadata", 
            "cellxgene_get_var_metadata",
            "cellxgene_get_data_slice",
            "cellxgene_get_all_cell_types"
        ]
        
        for expected_tool in expected_tools:
            assert expected_tool in tool_names, f"Tool {expected_tool} not found"
    
    def test_server_resources_registration(self, mcp_server):
        """Test that expected resources are registered."""
        resources = mcp_server.get_resources()
        
        # Check that expected resources exist
        resource_names = [resource.name for resource in resources]
        expected_resources = [
            "resource://cellxgene_census-info"
        ]
        
        for expected_resource in expected_resources:
            assert expected_resource in resource_names, f"Resource {expected_resource} not found"


class TestMCPTools:
    """Test individual MCP tool functionality."""
    
    @pytest.fixture
    def mock_census(self):
        """Create a mock Census object."""
        mock = Mock()
        
        # Mock census_data structure
        mock.census_data = {
            "homo_sapiens": Mock(),
            "mus_musculus": Mock()
        }
        
        # Mock census_info
        mock.census_info = {
            "summary": Mock()
        }
        
        return mock
    
    @pytest.fixture
    def mcp_server_with_mock(self, mock_census):
        """Create MCP server with mocked Census."""
        server = CellxGeneMCP(name="TestServer")
        
        # Mock the census manager to return our mock
        server.census_manager.get_census = Mock(return_value=mock_census)
        
        return server
    
    @pytest.mark.asyncio
    async def test_get_census_info(self, mcp_server_with_mock, mock_census):
        """Test get_census_info tool."""
        # Mock the version directory
        with patch('cellxgene_mcp.server.cellxgene_census.get_census_version_directory') as mock_versions:
            mock_versions.return_value = {
                'stable': {'release_build': '2023-12-15'},
                'latest': {'release_build': '2024-01-15'}
            }
            
            # Mock the summary data
            mock_summary = Mock()
            mock_summary.read.return_value.concat.return_value.to_pandas.return_value = Mock()
            mock_census.census_info["summary"] = mock_summary
            
            # Mock organism data
            mock_org = Mock()
            mock_org.obs.read.return_value.concat.return_value.to_pandas.return_value = Mock()
            mock_org.var.read.return_value.concat.return_value.to_pandas.return_value = Mock()
            mock_census.census_data["homo_sapiens"] = mock_org
            
            result = await mcp_server_with_mock.get_census_info()
            
            assert result is not None
            assert "supported_organisms" in result
            assert "available_versions" in result
    
    @pytest.mark.asyncio
    async def test_get_all_cell_types(self, mcp_server_with_mock, mock_census):
        """Test get_all_cell_types tool."""
        # Mock the cell type data
        mock_obs = Mock()
        mock_obs.read.return_value.concat.return_value.to_pandas.return_value = Mock()
        mock_obs.read.return_value.concat.return_value.to_pandas.return_value.__len__ = Mock(return_value=100)
        mock_obs.read.return_value.concat.return_value.to_pandas.return_value.unique.return_value = ["T cell", "B cell", "NK cell"]
        mock_obs.read.return_value.concat.return_value.to_pandas.return_value.value_counts.return_value = {"T cell": 50, "B cell": 30, "NK cell": 20}
        
        mock_census.census_data["homo_sapiens"].obs = mock_obs
        
        result = await mcp_server_with_mock.get_all_cell_types(
            organism="Homo sapiens",
            include_counts=True,
            primary_data_only=True
        )
        
        assert result is not None
        assert "cell_types" in result
        assert "total_unique_cell_types" in result
        assert len(result["cell_types"]) == 3
    
    @pytest.mark.asyncio
    async def test_get_obs_metadata(self, mcp_server_with_mock, mock_census):
        """Test get_obs_metadata tool."""
        # Mock observation data
        mock_obs = Mock()
        mock_df = Mock()
        mock_df.__len__ = Mock(return_value=50)
        mock_df.to_dict.return_value = "records"
        mock_df.head.return_value = mock_df
        
        mock_obs.read.return_value.concat.return_value.to_pandas.return_value = mock_df
        
        mock_census.census_data["homo_sapiens"].obs = mock_obs
        
        result = await mcp_server_with_mock.get_obs_metadata(
            organism="Homo sapiens",
            limit=10
        )
        
        assert result is not None
        assert result.count == 50
        assert hasattr(result, 'rows')
    
    @pytest.mark.asyncio
    async def test_get_var_metadata(self, mcp_server_with_mock, mock_census):
        """Test get_var_metadata tool."""
        # Mock variable data
        mock_var = Mock()
        mock_df = Mock()
        mock_df.__len__ = Mock(return_value=100)
        mock_df.to_dict.return_value = "records"
        mock_df.head.return_value = mock_df
        
        mock_var.read.return_value.concat.return_value.to_pandas.return_value = mock_df
        
        mock_census.census_data["homo_sapiens"].var = mock_var
        
        result = await mcp_server_with_mock.get_var_metadata(
            organism="Homo sapiens",
            limit=20
        )
        
        assert result is not None
        assert result.count == 100
        assert hasattr(result, 'rows')
    
    @pytest.mark.asyncio
    async def test_get_data_slice(self, mcp_server_with_mock, mock_census):
        """Test get_data_slice tool."""
        # Mock the data slice functionality
        mock_census_manager = Mock()
        mock_census_manager.get_anndata_slice.return_value = {
            "obs_count": 1000,
            "var_count": 500,
            "obs_columns": ["cell_type", "tissue"],
            "var_columns": ["feature_id", "feature_name"]
        }
        
        mcp_server_with_mock.census_manager = mock_census_manager
        
        result = await mcp_server_with_mock.get_data_slice(
            organism="Homo sapiens",
            max_cells=1000,
            max_genes=500
        )
        
        assert result is not None
        assert "obs_count" in result
        assert "var_count" in result


class TestErrorHandling:
    """Test error handling in MCP tools."""
    
    @pytest.fixture
    def mcp_server_with_errors(self):
        """Create MCP server that will generate errors."""
        server = CellxGeneMCP(name="TestServer")
        
        # Mock census manager to raise errors
        server.census_manager.get_census = Mock(side_effect=Exception("Census connection failed"))
        
        return server
    
    @pytest.mark.asyncio
    async def test_census_connection_error(self, mcp_server_with_errors):
        """Test handling of Census connection errors."""
        with pytest.raises(Exception) as exc_info:
            await mcp_server_with_errors.get_census_info()
        
        assert "Census connection failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_invalid_organism(self, mcp_server_with_errors):
        """Test handling of invalid organism parameter."""
        # This should handle the error gracefully
        with pytest.raises(Exception):
            await mcp_server_with_errors.get_all_cell_types(organism="Invalid organism")


class TestIntegration:
    """Integration tests for the MCP server."""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test a complete workflow through the MCP server."""
        server = CellxGeneMCP(name="IntegrationTestServer")
        
        # Test that the server can be initialized
        assert server is not None
        
        # Test that tools are registered
        tools = server.get_tools()
        assert len(tools) > 0
        
        # Test that resources are registered
        resources = server.get_resources()
        assert len(resources) > 0


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v"])
