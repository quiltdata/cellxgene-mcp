#!/usr/bin/env python3
"""CELLxGENE Census MCP Server - Query interface for CELLxGENE Census single-cell data."""

import asyncio
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from contextlib import asynccontextmanager
import sys
import argparse
import tempfile
import json
import boto3
from botocore.exceptions import NoCredentialsError, ClientError

from fastmcp import FastMCP
from pydantic import BaseModel, Field
from eliot import start_action
import cellxgene_census
import pandas as pd
import numpy as np
from anndata import AnnData

# Configuration
DEFAULT_HOST = os.getenv("MCP_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.getenv("MCP_PORT", "3001"))
DEFAULT_TRANSPORT = os.getenv("MCP_TRANSPORT", "streamable-http")

class QueryResult(BaseModel):
    """Result from a Census query."""
    rows: List[Dict[str, Any]] = Field(description="Query result rows")
    count: int = Field(description="Number of rows returned")
    query_info: Dict[str, Any] = Field(description="Information about the query that was executed")

class S3DataReference(BaseModel):
    """Reference to data stored in S3."""
    uri: str = Field(description="S3 URI of the data")
    bucket: str = Field(description="S3 bucket name")
    key: str = Field(description="S3 object key")
    region: str = Field(description="S3 region")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata about the data")

class S3TransferResult(BaseModel):
    """Result of an S3-to-S3 transfer operation."""
    source_uri: str = Field(description="Source S3 URI")
    destination_uri: str = Field(description="Destination S3 URI")
    transfer_size: int = Field(description="Size of transferred data in bytes")
    success: bool = Field(description="Whether the transfer was successful")
    message: str = Field(description="Status message or error description")

class CensusManager:
    """Manages CELLxGENE Census connections and queries."""
    
    def __init__(self, census_version: Optional[str] = None):
        self.census_version = census_version
        self._census = None
        self._s3_client = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._census:
            self._census.close()
    
    def get_census(self):
        """Get a Census connection."""
        try:
            # If no specific version is provided, try to get the latest available
            if self.census_version is None:
                try:
                    versions = cellxgene_census.get_census_version_directory()
                    if versions:
                        # versions is an OrderedDict, get the 'stable' version if available
                        if 'stable' in versions:
                            self.census_version = versions['stable']['release_build']
                        elif 'latest' in versions:
                            self.census_version = versions['latest']['release_build']
                        else:
                            # Fall back to the first available version
                            first_key = next(iter(versions))
                            self.census_version = versions[first_key]['release_build']
                except Exception:
                    # If we can't get versions, use a default
                    self.census_version = "latest"
            
            census = cellxgene_census.open_soma(census_version=self.census_version)
            return census
        except Exception as e:
            raise RuntimeError(f"Failed to open Census: {e}")
    
    def get_s3_client(self, region: str = "us-west-2"):
        """Get an S3 client for the specified region."""
        if self._s3_client is None or self._s3_client.meta.region_name != region:
            try:
                self._s3_client = boto3.client('s3', region_name=region)
            except NoCredentialsError:
                # For public data access, we can use unsigned requests
                from botocore import UNSIGNED
                from botocore.config import Config
                self._s3_client = boto3.client('s3', 
                                             region_name=region,
                                             config=Config(signature_version=UNSIGNED))
        return self._s3_client
    
    def parse_s3_uri(self, s3_uri: str) -> tuple[str, str, str]:
        """Parse S3 URI into bucket, key, and region components."""
        if not s3_uri.startswith("s3://"):
            raise ValueError(f"Invalid S3 URI format: {s3_uri}")
        
        # Remove s3:// prefix
        path = s3_uri[5:]
        parts = path.split('/', 1)
        
        if len(parts) != 2:
            raise ValueError(f"Invalid S3 URI format: {s3_uri}")
            
        bucket = parts[0]
        key = parts[1]
        
        # Extract region from bucket name if it follows Census naming convention
        region = "us-west-2"  # Default for CELLxGENE Census
        if "us-west-2" in bucket:
            region = "us-west-2"
        elif "us-east-1" in bucket:
            region = "us-east-1"
            
        return bucket, key, region
    
    async def get_s3_data_reference(self, organism: str = "Homo sapiens", data_type: str = "obs") -> S3DataReference:
        """Get S3 reference for Census data without downloading."""
        with start_action(action_type="get_s3_data_reference", organism=organism, data_type=data_type) as action:
            try:
                # Get version directory to find S3 URIs
                versions = cellxgene_census.get_census_version_directory()
                if not versions:
                    raise RuntimeError("No Census versions available")
                
                # Use stable version if available, otherwise latest
                version_key = 'stable' if 'stable' in versions else 'latest'
                version_info = versions[version_key]
                
                # Extract S3 URI information
                soma_uri = version_info['soma']['uri']
                region = version_info['soma']['s3_region']
                
                # Construct data-specific S3 path
                organism_key = organism.lower().replace(" ", "_")
                data_path = f"{soma_uri}census_data/{organism_key}/{data_type}/"
                
                bucket, key, _ = self.parse_s3_uri(data_path)
                
                s3_ref = S3DataReference(
                    uri=data_path,
                    bucket=bucket,
                    key=key,
                    region=region,
                    metadata={
                        "organism": organism,
                        "data_type": data_type,
                        "census_version": version_info['release_build'],
                        "version_key": version_key
                    }
                )
                
                action.add_success_fields(uri=data_path, organism=organism, data_type=data_type)
                return s3_ref
                
            except Exception as e:
                action.log(message_type="s3_reference_failed", error=str(e))
                raise
    
    async def list_s3_objects(self, s3_reference: S3DataReference, max_keys: int = 1000) -> List[Dict[str, Any]]:
        """List objects in S3 without downloading them."""
        with start_action(action_type="list_s3_objects", bucket=s3_reference.bucket, key=s3_reference.key) as action:
            try:
                s3_client = self.get_s3_client(s3_reference.region)
                
                response = s3_client.list_objects_v2(
                    Bucket=s3_reference.bucket,
                    Prefix=s3_reference.key,
                    MaxKeys=max_keys
                )
                
                objects = []
                if 'Contents' in response:
                    for obj in response['Contents']:
                        objects.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'last_modified': obj['LastModified'].isoformat(),
                            'etag': obj['ETag'].strip('"'),
                            's3_uri': f"s3://{s3_reference.bucket}/{obj['Key']}"
                        })
                
                action.add_success_fields(object_count=len(objects))
                return objects
                
            except Exception as e:
                action.log(message_type="s3_list_failed", error=str(e))
                raise
    
    async def prepare_s3_transfer(self, source_s3_uri: str, destination_bucket: str, destination_key: str) -> S3TransferResult:
        """Prepare an S3-to-S3 transfer operation."""
        with start_action(action_type="prepare_s3_transfer", source=source_s3_uri, destination=f"s3://{destination_bucket}/{destination_key}") as action:
            try:
                source_bucket, source_key, source_region = self.parse_s3_uri(source_s3_uri)
                destination_uri = f"s3://{destination_bucket}/{destination_key}"
                
                # Get source object info
                s3_client = self.get_s3_client(source_region)
                
                try:
                    response = s3_client.head_object(Bucket=source_bucket, Key=source_key)
                    transfer_size = response['ContentLength']
                    
                    # For this implementation, we'll return the transfer information
                    # In a real implementation, you'd initiate the actual S3-to-S3 copy
                    result = S3TransferResult(
                        source_uri=source_s3_uri,
                        destination_uri=destination_uri,
                        transfer_size=transfer_size,
                        success=True,
                        message=f"Transfer prepared: {transfer_size} bytes from {source_s3_uri} to {destination_uri}"
                    )
                    
                    action.add_success_fields(transfer_size=transfer_size)
                    return result
                    
                except ClientError as e:
                    if e.response['Error']['Code'] == '404':
                        return S3TransferResult(
                            source_uri=source_s3_uri,
                            destination_uri=destination_uri,
                            transfer_size=0,
                            success=False,
                            message=f"Source object not found: {source_s3_uri}"
                        )
                    else:
                        raise
                        
            except Exception as e:
                action.log(message_type="s3_transfer_prep_failed", error=str(e))
                raise
    
    async def get_obs_metadata(
        self, 
        organism: str = "Homo sapiens",
        value_filter: Optional[str] = None,
        column_names: Optional[List[str]] = None,
        limit: int = 1000
    ) -> QueryResult:
        """Get observation (cell) metadata from Census using S3 approach."""
        with start_action(action_type="get_obs_metadata", organism=organism, value_filter=value_filter) as action:
            try:
                # Since we're using S3 directly, we can't execute complex SOMA queries
                # Instead, we'll provide S3 paths and guidance for data access
                
                # Get S3 client for direct access
                s3_client = self.get_s3_client(region="us-west-2")
                base_bucket = "cellxgene-census-public-us-west-2"
                
                # Get available versions from S3
                try:
                    versions_response = s3_client.list_objects_v2(
                        Bucket=base_bucket,
                        Prefix="cell-census/",
                        Delimiter='/',
                        MaxKeys=1000
                    )
                    
                    available_versions = []
                    if 'CommonPrefixes' in versions_response:
                        for prefix_info in versions_response['CommonPrefixes']:
                            prefix = prefix_info['Prefix']
                            version_tag = prefix.replace("cell-census/", '').rstrip('/')
                            if version_tag and version_tag != '':
                                available_versions.append(version_tag)
                    
                    # Sort versions (newest first)
                    available_versions.sort(reverse=True)
                    latest_version = available_versions[0] if available_versions else None
                    
                except Exception as s3_error:
                    action.log(message_type="s3_versions_failed", error=str(s3_error))
                    # Fall back to hardcoded version
                    latest_version = "2025-01-30"
                
                # Construct S3 paths for the organism
                organism_key = organism.lower().replace(" ", "_")
                s3_base_path = f"s3://{base_bucket}/cell-census/{latest_version}"
                soma_path = f"{s3_base_path}/soma/census_data/{organism_key}/"
                h5ads_path = f"{s3_base_path}/h5ads/"
                
                # Check if organism data exists in S3
                try:
                    org_response = s3_client.list_objects_v2(
                        Bucket=base_bucket,
                        Prefix=f"cell-census/{latest_version}/soma/census_data/{organism_key}/",
                        MaxKeys=5
                    )
                    organism_accessible = len(org_response.get('Contents', [])) > 0
                except Exception:
                    organism_accessible = False
                
                # Since we can't execute SOMA queries directly, provide S3 access information
                result = QueryResult(
                    rows=[],  # No actual data rows since we're not querying
                    count=0,
                    query_info={
                        "organism": organism,
                        "value_filter": value_filter,
                        "column_names": column_names,
                        "limited": False,
                        "note": "S3-based access - use provided S3 paths for data access",
                        "s3_access": {
                            "bucket": base_bucket,
                            "version": latest_version,
                            "organism_key": organism_key,
                            "soma_path": soma_path,
                            "h5ads_path": h5ads_path,
                            "organism_accessible": organism_accessible
                        },
                        "access_methods": [
                            "Direct S3 access via AWS CLI",
                            "Download H5AD files for local analysis",
                            "Use TileDB-SOMA API with S3 URIs"
                        ],
                        "aws_cli_examples": {
                            "download_soma": f"aws s3 sync --no-sign-request {soma_path} ./soma/",
                            "download_h5ads": f"aws s3 sync --no-sign-request {h5ads_path} ./h5ads/",
                            "list_organism_data": f"aws s3 ls --no-sign-request {soma_path}"
                        },
                        "python_example": f"""
# For direct S3 access with TileDB-SOMA:
import tiledbsoma
import cellxgene_census

# Open Census from S3
census = cellxgene_census.open_soma(uri="{soma_path}")

# Query observation metadata
obs_df = cellxgene_census.get_obs(
    census=census,
    organism="{organism}",
    value_filter="{value_filter or 'None'}",
    column_names={column_names or 'None'}
)
"""
                    }
                )
                
                action.add_success_fields(
                    rows_count=0,
                    s3_version=latest_version,
                    organism_accessible=organism_accessible
                )
                return result
                
            except Exception as e:
                action.log(message_type="query_failed", error=str(e))
                # Return error information
                return QueryResult(
                    rows=[],
                    count=0,
                    query_info={
                        "organism": organism,
                        "value_filter": value_filter,
                        "column_names": column_names,
                        "error": str(e),
                        "note": "Failed to get S3 metadata information"
                    }
                )
    
    async def get_var_metadata(
        self, 
        organism: str = "Homo sapiens",
        value_filter: Optional[str] = None,
        column_names: Optional[List[str]] = None,
        limit: int = 1000
    ) -> QueryResult:
        """Get variable (gene) metadata from Census using S3 approach."""
        with start_action(action_type="get_var_metadata", organism=organism, value_filter=value_filter) as action:
            try:
                # Since we're using S3 directly, we can't execute complex SOMA queries
                # Instead, we'll provide S3 paths and guidance for data access
                
                # Get S3 client for direct access
                s3_client = self.get_s3_client(region="us-west-2")
                base_bucket = "cellxgene-census-public-us-west-2"
                
                # Get available versions from S3
                try:
                    versions_response = s3_client.list_objects_v2(
                        Bucket=base_bucket,
                        Prefix="cell-census/",
                        Delimiter='/',
                        MaxKeys=1000
                    )
                    
                    available_versions = []
                    if 'CommonPrefixes' in versions_response:
                        for prefix_info in versions_response['CommonPrefixes']:
                            prefix = prefix_info['Prefix']
                            version_tag = prefix.replace("cell-census/", '').rstrip('/')
                            if version_tag and version_tag != '':
                                available_versions.append(version_tag)
                    
                    # Sort versions (newest first)
                    available_versions.sort(reverse=True)
                    latest_version = available_versions[0] if available_versions else None
                    
                except Exception as s3_error:
                    action.log(message_type="s3_versions_failed", error=str(s3_error))
                    # Fall back to hardcoded version
                    latest_version = "2025-01-30"
                
                # Construct S3 paths for the organism
                organism_key = organism.lower().replace(" ", "_")
                s3_base_path = f"s3://{base_bucket}/cell-census/{latest_version}"
                soma_path = f"{s3_base_path}/soma/census_data/{organism_key}/"
                h5ads_path = f"{s3_base_path}/h5ads/"
                
                # Check if organism data exists in S3
                try:
                    org_response = s3_client.list_objects_v2(
                        Bucket=base_bucket,
                        Prefix=f"cell-census/{latest_version}/soma/census_data/{organism_key}/",
                        MaxKeys=5
                    )
                    organism_accessible = len(org_response.get('Contents', [])) > 0
                except Exception:
                    organism_accessible = False
                
                # Since we can't execute SOMA queries directly, provide S3 access information
                result = QueryResult(
                    rows=[],  # No actual data rows since we're not querying
                    count=0,
                    query_info={
                        "organism": organism,
                        "value_filter": value_filter,
                        "column_names": column_names,
                        "limited": False,
                        "note": "S3-based access - use provided S3 paths for data access",
                        "s3_access": {
                            "bucket": base_bucket,
                            "version": latest_version,
                            "organism_key": organism_key,
                            "soma_path": soma_path,
                            "h5ads_path": h5ads_path,
                            "organism_accessible": organism_accessible
                        },
                        "access_methods": [
                            "Direct S3 access via AWS CLI",
                            "Download H5AD files for local analysis",
                            "Use TileDB-SOMA API with S3 URIs"
                        ],
                        "aws_cli_examples": {
                            "download_soma": f"aws s3 sync --no-sign-request {soma_path} ./soma/",
                            "download_h5ads": f"aws s3 sync --no-sign-request {h5ads_path} ./h5ads/",
                            "list_organism_data": f"aws s3 ls --no-sign-request {soma_path}"
                        },
                        "python_example": f"""
# For direct S3 access with TileDB-SOMA:
import tiledbsoma
import cellxgene_census

# Open Census from S3
census = cellxgene_census.open_soma(uri="{soma_path}")

# Query variable (gene) metadata
var_df = cellxgene_census.get_var(
    census=census,
    organism="{organism}",
    value_filter="{value_filter or 'None'}",
    column_names={column_names or 'None'}
)
"""
                    }
                )
                
                action.add_success_fields(
                    rows_count=0,
                    s3_version=latest_version,
                    organism_accessible=organism_accessible
                )
                return result
                
            except Exception as e:
                action.log(message_type="query_failed", error=str(e))
                # Return error information
                return QueryResult(
                    rows=[],
                    count=0,
                    query_info={
                        "organism": organism,
                        "value_filter": value_filter,
                        "column_names": column_names,
                        "error": str(e),
                        "note": "Failed to get S3 metadata information"
                    }
                )
    
    async def get_anndata_slice(
        self,
        organism: str = "Homo sapiens",
        obs_value_filter: Optional[str] = None,
        var_value_filter: Optional[str] = None,
        obs_column_names: Optional[List[str]] = None,
        var_column_names: Optional[List[str]] = None,
        max_cells: int = 10000,
        max_genes: int = 2000
    ) -> Dict[str, Any]:
        """Get a slice of Census data as AnnData summary."""
        with start_action(action_type="get_anndata_slice", organism=organism) as action:
            try:
                census = self.get_census()
                try:
                    # Get a slice of the data
                    adata = cellxgene_census.get_anndata(
                        census=census,
                        organism=organism,
                        obs_value_filter=obs_value_filter,
                        var_value_filter=var_value_filter,
                        column_names={
                            "obs": obs_column_names,
                            "var": var_column_names
                        } if obs_column_names or var_column_names else None
                    )
                    
                    # Limit the data size
                    if adata.n_obs > max_cells:
                        adata = adata[:max_cells, :]
                        action.log(message_type="cells_limited", original_count=adata.n_obs, limited_count=max_cells)
                    
                    if adata.n_vars > max_genes:
                        adata = adata[:, :max_genes]
                        action.log(message_type="genes_limited", original_count=adata.n_vars, limited_count=max_genes)
                    
                    # Return summary information instead of raw data
                    result = {
                        "n_obs": adata.n_obs,
                        "n_vars": adata.n_vars,
                        "obs_columns": list(adata.obs.columns),
                        "var_columns": list(adata.var.columns),
                        "obs_sample": adata.obs.head(5).to_dict('records') if adata.n_obs > 0 else [],
                        "var_sample": adata.var.head(5).to_dict('records') if adata.n_vars > 0 else [],
                        "query_info": {
                            "organism": organism,
                            "obs_value_filter": obs_value_filter,
                            "var_value_filter": var_value_filter,
                            "cells_limited": adata.n_obs == max_cells,
                            "genes_limited": adata.n_vars == max_genes
                        }
                    }
                    
                    action.add_success_fields(n_obs=adata.n_obs, n_vars=adata.n_vars)
                    return result
                finally:
                    census.close()
            except Exception as e:
                action.log(message_type="query_failed", error=str(e))
                raise

class CellxGeneMCP(FastMCP):
    """CELLxGENE Census MCP Server with Census query tools."""
    
    def __init__(
        self, 
        name: str = "CELLxGENE Census MCP Server",
        census_version: Optional[str] = None,
        prefix: str = "cellxgene_",
        **kwargs
    ):
        """Initialize the CELLxGENE Census MCP server."""
        super().__init__(name=name, **kwargs)
        
        self.census_manager = CensusManager(census_version=census_version)
        self.prefix = prefix
        
        # Register tools and resources
        self._register_cellxgene_tools()
        self._register_cellxgene_resources()
    
    def _register_cellxgene_tools(self):
        """Register CELLxGENE Census-specific tools."""
        self.tool(
            name=f"{self.prefix}get_census_info", 
            description="Get information about available Census versions and organisms"
        )(self.get_census_info)
        
        self.tool(
            name=f"{self.prefix}get_obs_metadata", 
            description="Get cell (observation) metadata from CELLxGENE Census. Use this to explore available cell types, tissues, diseases, etc."
        )(self.get_obs_metadata)
        
        self.tool(
            name=f"{self.prefix}get_var_metadata", 
            description="Get gene (variable) metadata from CELLxGENE Census. Use this to explore available genes and their annotations."
        )(self.get_var_metadata)
        
        self.tool(
            name=f"{self.prefix}get_data_slice", 
            description="Get a summary of a data slice from CELLxGENE Census based on cell and gene filters. Returns data dimensions and sample metadata."
        )(self.get_data_slice)
        
        self.tool(
            name=f"{self.prefix}get_all_cell_types", 
            description="Get all distinct cell types available in CELLxGENE Census for a specific organism. Optionally includes cell counts for each type."
        )(self.get_all_cell_types)
        
        # New H5AD-specific tools
        self.tool(
            name=f"{self.prefix}get_h5ad_uri", 
            description="Get the URI for a specific dataset's H5AD file from CELLxGENE Census. Requires dataset_id and organism."
        )(self.get_h5ad_uri)
        
        self.tool(
            name=f"{self.prefix}download_h5ad", 
            description="Download a specific dataset's H5AD file from CELLxGENE Census to a local file. Requires dataset_id, organism, and output filename."
        )(self.download_h5ad)
        
        self.tool(
            name=f"{self.prefix}list_available_datasets", 
            description="List available datasets in CELLxGENE Census for a specific organism. Returns dataset IDs and basic information."
        )(self.list_available_datasets)
        
        # New S3-specific tools
        self.tool(
            name=f"{self.prefix}list_s3_versions", 
            description="List available Census versions directly from S3. Returns version tags and S3 paths for TileDB-SOMA and H5AD files."
        )(self.list_s3_versions)
        
        self.tool(
            name=f"{self.prefix}get_s3_paths", 
            description="Get S3 paths for a specific Census version. Returns paths for soma/, h5ads/, and organism-specific data."
        )(self.get_s3_paths)
        
        self.tool(
            name=f"{self.prefix}check_s3_access", 
            description="Check S3 access to Census data. Verifies connectivity and lists available data without downloading."
        )(self.check_s3_access)
        
        # New Quilt integration tool
        self.tool(
            name=f"{self.prefix}get_quilt_s3_paths", 
            description="Get S3 paths specifically formatted for Quilt MCP tools. Returns S3 URIs that can be passed directly to Quilt package creation tools."
        )(self.get_quilt_s3_paths)
    
    def _register_cellxgene_resources(self):
        """Register CELLxGENE Census-specific resources."""
        
        @self.resource(f"resource://{self.prefix}census-info")
        def get_census_resource() -> str:
            """
            Get information about the CELLxGENE Census database.
            
            This resource contains information about:
            - Available Census versions
            - Supported organisms
            - Data schema and available metadata fields
            - Usage guidelines for querying the Census
            
            Returns:
                Information about the Census database
            """
            return """
CELLxGENE Census Information:

The CELLxGENE Census is a comprehensive collection of single-cell RNA sequencing data from CZ CELLxGENE Discover.

Data Format: H5AD (AnnData)
The Census provides data in H5AD format, which is the standard format for single-cell data analysis.

Available Organisms:
- "Homo sapiens" (human)
- "Mus musculus" (mouse)

Key Metadata Fields:
Observation (cell) metadata:
- cell_type: Cell type annotation
- tissue: Tissue of origin
- disease: Disease state
- sex: Biological sex
- organism: Species
- assay: Sequencing assay used
- suspension_type: Cell or nucleus
- ethnicity: Self-reported ethnicity (human only)
- development_stage: Developmental stage

Variable (gene) metadata:
- feature_id: Ensembl gene ID
- feature_name: Gene symbol
- feature_length: Gene length

Access Methods:
1. get_h5ad_uri - Get URI for H5AD file download
2. download_h5ad - Download H5AD file directly
3. list_available_datasets - Discover available datasets

Usage Workflow:
1. Use get_census_info to see available versions
2. Use list_available_datasets to find datasets of interest
3. Use get_h5ad_uri to get download URI for specific dataset
4. Use download_h5ad to download the H5AD file
5. Analyze the H5AD file using standard tools (scanpy, anndata, etc.)

Note: H5AD files can be large. Use appropriate storage and memory management.
"""
    
    async def get_census_info(self) -> Dict[str, Any]:
        """Get information about available Census versions and organisms using S3 directly."""
        with start_action(action_type="get_census_info") as action:
            try:
                # Use S3 directly instead of API calls that can hang
                # Based on AWS documentation: s3://cellxgene-census-public-us-west-2/cell-census/[tag]/soma/
                
                # Get S3 client for direct access
                s3_client = self.census_manager.get_s3_client(region="us-west-2")
                
                # Define the base S3 bucket and paths
                base_bucket = "cellxgene-census-public-us-west-2"
                base_prefix = "cell-census/"
                
                # List available Census versions by checking S3 prefixes
                try:
                    response = s3_client.list_objects_v2(
                        Bucket=base_bucket,
                        Prefix=base_prefix,
                        Delimiter='/',
                        MaxKeys=1000
                    )
                    
                    # Extract version tags from the prefixes
                    versions = {}
                    if 'CommonPrefixes' in response:
                        for prefix_info in response['CommonPrefixes']:
                            prefix = prefix_info['Prefix']
                            # Extract version tag from prefix like "cell-census/2023-07-25/"
                            version_tag = prefix.replace(base_prefix, '').rstrip('/')
                            if version_tag and version_tag != '':
                                versions[version_tag] = {
                                    'release_build': version_tag,
                                    's3_path': f"s3://{base_bucket}/{prefix}",
                                    'soma_path': f"s3://{base_bucket}/{prefix}soma/",
                                    'h5ads_path': f"s3://{base_bucket}/{prefix}h5ads/"
                                }
                    
                    # Sort versions by date (newest first)
                    sorted_versions = dict(sorted(versions.items(), reverse=True))
                    
                except Exception as s3_error:
                    action.log(message_type="s3_list_failed", error=str(s3_error))
                    # Fall back to hardcoded known versions
                    sorted_versions = {
                        "2025-01-30": {
                            'release_build': "2025-01-30",
                            's3_path': "s3://cellxgene-census-public-us-west-2/cell-census/2025-01-30/",
                            'soma_path': "s3://cellxgene-census-public-us-west-2/cell-census/2025-01-30/soma/",
                            'h5ads_path': "s3://cellxgene-census-public-us-west-2/cell-census/2025-01-30/h5ads/"
                        },
                        "2023-07-25": {
                            'release_build': "2023-07-25",
                            's3_path': "s3://cellxgene-census-public-us-west-2/cell-census/2023-07-25/",
                            'soma_path': "s3://cellxgene-census-public-us-west-2/cell-census/2023-07-25/soma/",
                            'h5ads_path': "s3://cellxgene-census-public-us-west-2/cell-census/2023-07-25/h5ads/"
                        }
                    }
                
                # Get latest version
                latest_version = next(iter(sorted_versions)) if sorted_versions else None
                
                # Define supported organisms (these are standard for CELLxGENE Census)
                organisms = ["Homo sapiens", "Mus musculus"]
                organism_stats = {}
                
                # Get organism information from S3
                for organism in organisms:
                    try:
                        # Check if we can access organism data in S3
                        organism_key = organism.lower().replace(" ", "_")
                        
                        # Try to list a small sample to verify access
                        sample_response = s3_client.list_objects_v2(
                            Bucket=base_bucket,
                            Prefix=f"{base_prefix}{latest_version}/soma/census_data/{organism_key}/",
                            MaxKeys=5
                        )
                        
                        organism_stats[organism] = {
                            "total_cells": "Available via S3",
                            "total_genes": "Available via S3",
                            "data_format": "TileDB-SOMA + H5AD",
                            "access_method": "Direct S3 access",
                            "s3_accessible": len(sample_response.get('Contents', [])) > 0,
                            "s3_path": f"s3://{base_bucket}/{base_prefix}{latest_version}/soma/census_data/{organism_key}/"
                        }
                        
                    except Exception as org_error:
                        action.log(message_type="organism_s3_check_failed", organism=organism, error=str(org_error))
                        organism_stats[organism] = {
                            "total_cells": "Unknown",
                            "total_genes": "Unknown", 
                            "data_format": "TileDB-SOMA + H5AD",
                            "access_method": "Direct S3 access",
                            "s3_accessible": False,
                            "error": str(org_error)
                        }
                
                # Get summary info
                summary_info = {
                    "data_source": "AWS S3 Public Bucket",
                    "bucket": base_bucket,
                    "region": "us-west-2",
                    "access_method": "Direct S3 (no authentication required)",
                    "formats_available": ["TileDB-SOMA", "H5AD"],
                    "aws_cli_example": f"aws s3 sync --no-sign-request s3://{base_bucket}/cell-census/{latest_version}/h5ads/ ./h5ads/"
                }
                
                result = {
                    "available_versions": sorted_versions,
                    "latest_stable_version": latest_version,
                    "supported_organisms": organisms,
                    "organism_statistics": organism_stats,
                    "total_cells_across_organisms": "Available via S3",
                    "census_summary": summary_info,
                    "version_info": sorted_versions,
                    "api_status": "connected",
                    "data_format": "TileDB-SOMA + H5AD",
                    "access_method": "Direct S3",
                    "s3_bucket": base_bucket,
                    "s3_region": "us-west-2",
                    "aws_cli_ready": True
                }
                
                action.add_success_fields(
                    versions_count=len(sorted_versions),
                    organisms_count=len(organisms),
                    s3_bucket=base_bucket
                )
                return result
                
            except Exception as e:
                action.log(message_type="query_failed", error=str(e))
                # Return basic information even if there's an error
                return {
                    "available_versions": {},
                    "latest_stable_version": None,
                    "supported_organisms": ["Homo sapiens", "Mus musculus"],
                    "organism_statistics": {},
                    "total_cells_across_organisms": "Unknown",
                    "census_summary": {},
                    "version_info": {},
                    "api_status": "error",
                    "data_format": "TileDB-SOMA + H5AD",
                    "access_method": "Direct S3",
                    "error": str(e),
                    "note": "Falling back to hardcoded information due to S3 access error"
                }
    
    async def get_obs_metadata(
        self,
        organism: str = "Homo sapiens",
        value_filter: Optional[str] = None,
        column_names: Optional[str] = None,
        limit: int = 1000
    ) -> QueryResult:
        """Get cell (observation) metadata from Census using S3 approach."""
        # Parse column names if provided as comma-separated string
        columns = None
        if column_names:
            columns = [col.strip() for col in column_names.split(',')]
        
        # Since we're using S3 directly, we can't execute complex SOMA queries
        # Instead, we'll provide S3 paths and guidance for data access
        with start_action(action_type="get_obs_metadata", organism=organism, value_filter=value_filter) as action:
            try:
                # Get S3 client for direct access
                s3_client = self.census_manager.get_s3_client(region="us-west-2")
                base_bucket = "cellxgene-census-public-us-west-2"
                
                # Get available versions from S3
                try:
                    versions_response = s3_client.list_objects_v2(
                        Bucket=base_bucket,
                        Prefix="cell-census/",
                        Delimiter='/',
                        MaxKeys=1000
                    )
                    
                    available_versions = []
                    if 'CommonPrefixes' in versions_response:
                        for prefix_info in versions_response['CommonPrefixes']:
                            prefix = prefix_info['Prefix']
                            version_tag = prefix.replace("cell-census/", '').rstrip('/')
                            if version_tag and version_tag != '':
                                available_versions.append(version_tag)
                    
                    # Sort versions (newest first)
                    available_versions.sort(reverse=True)
                    latest_version = available_versions[0] if available_versions else None
                    
                except Exception as s3_error:
                    action.log(message_type="s3_versions_failed", error=str(s3_error))
                    # Fall back to hardcoded version
                    latest_version = "2025-01-30"
                
                # Construct S3 paths for the organism
                organism_key = organism.lower().replace(" ", "_")
                s3_base_path = f"s3://{base_bucket}/cell-census/{latest_version}"
                soma_path = f"{s3_base_path}/soma/census_data/{organism_key}/"
                h5ads_path = f"{s3_base_path}/h5ads/"
                
                # Check if organism data exists in S3
                try:
                    org_response = s3_client.list_objects_v2(
                        Bucket=base_bucket,
                        Prefix=f"cell-census/{latest_version}/soma/census_data/{organism_key}/",
                        MaxKeys=5
                    )
                    organism_accessible = len(org_response.get('Contents', [])) > 0
                except Exception:
                    organism_accessible = False
                
                # Since we can't execute SOMA queries directly, provide S3 access information
                result = QueryResult(
                    rows=[],  # No actual data rows since we're not querying
                    count=0,
                    query_info={
                        "organism": organism,
                        "value_filter": value_filter,
                        "column_names": columns,
                        "limited": False,
                        "note": "S3-based access - use provided S3 paths for Quilt package creation",
                        "s3_access": {
                            "bucket": base_bucket,
                            "version": latest_version,
                            "organism_key": organism_key,
                            "s3_path": soma_path,
                            "h5ads_path": h5ads_path,
                            "organism_accessible": organism_accessible
                        },
                        "quilt_integration": {
                            "s3_uris_for_quilt": [
                                f"s3://{base_bucket}/cell-census/{latest_version}/soma/",
                                f"s3://{base_bucket}/cell-census/{latest_version}/h5ads/",
                                f"s3://{base_bucket}/cell-census/{latest_version}/soma/census_data/{organism_key}/"
                            ],
                            "quilt_package_suggestions": [
                                f"Use s3://{base_bucket}/cell-census/{latest_version}/h5ads/ for individual H5AD files",
                                f"Use s3://{base_bucket}/cell-census/{latest_version}/soma/ for full Census data",
                                f"Use s3://{base_bucket}/cell-census/{latest_version}/soma/census_data/{organism_key}/ for organism-specific data"
                            ],
                            "quilt_mcp_ready": True
                        },
                        "access_methods": [
                            "Direct S3 access via AWS CLI",
                            "Download H5AD files for local analysis",
                            "Use TileDB-SOMA API with S3 URIs",
                            "Pass S3 URIs directly to Quilt MCP tools"
                        ],
                        "aws_cli_examples": {
                            "download_soma": f"aws s3 sync --no-sign-request {soma_path} ./soma/",
                            "download_h5ads": f"aws s3 sync --no-sign-request {h5ads_path} ./h5ads/",
                            "list_organism_data": f"aws s3 ls --no-sign-request {soma_path}",
                            "list_h5ad_files": f"aws s3 ls --no-sign-request {h5ads_path} --recursive | grep .h5ad"
                        },
                        "python_example": f"""
# For direct S3 access with TileDB-SOMA (then upload to Quilt):
import tiledbsoma
import cellxgene_census

# Open Census from S3
census = cellxgene_census.open_soma(uri="{soma_path}")

# Query observation metadata
obs_df = cellxgene_census.get_obs(
    census=census,
    organism="{organism}",
    value_filter="{value_filter or 'None'}",
    column_names={columns or 'None'}
)

# Now you can process this data and upload to Quilt using Quilt MCP tools
# The S3 URIs above can be passed directly to Quilt package creation tools
""",
                        "quilt_workflow": f"""
# Recommended Quilt Package Creation Workflow:

1. Use the S3 URIs above with Quilt MCP tools:
   - soma: s3://{base_bucket}/cell-census/{latest_version}/soma/
   - h5ads: s3://{base_bucket}/cell-census/{latest_version}/h5ads/
   - organism-specific: s3://{base_bucket}/cell-census/{latest_version}/soma/census_data/{organism_key}/

2. For H5AD files (recommended for Quilt):
   - List available files: aws s3 ls --no-sign-request s3://{base_bucket}/cell-census/{latest_version}/h5ads/ --recursive
   - Download specific files or use S3 URIs directly in Quilt

3. For full Census data:
   - Use the soma/ path for comprehensive data access
   - Process with TileDB-SOMA then upload results to Quilt
"""
                    }
                )
                
                action.add_success_fields(
                    rows_count=0,
                    s3_version=latest_version,
                    organism_accessible=organism_accessible
                )
                return result
                
            except Exception as e:
                action.log(message_type="query_failed", error=str(e))
                # Return error information
                return QueryResult(
                    rows=[],
                    count=0,
                    query_info={
                        "organism": organism,
                        "value_filter": value_filter,
                        "column_names": columns,
                        "error": str(e),
                        "note": "Failed to get S3 metadata information"
                    }
                )
    
    async def get_var_metadata(
        self,
        organism: str = "Homo sapiens",
        value_filter: Optional[str] = None,
        column_names: Optional[str] = None,
        limit: int = 1000
    ) -> QueryResult:
        """Get gene (variable) metadata from Census using S3 approach."""
        # Parse column names if provided as comma-separated string
        columns = None
        if column_names:
            columns = [col.strip() for col in column_names.split(',')]
        
        # Since we're using S3 directly, we can't execute complex SOMA queries
        # Instead, we'll provide S3 paths and guidance for data access
        with start_action(action_type="get_var_metadata", organism=organism, value_filter=value_filter) as action:
            try:
                # Get S3 client for direct access
                s3_client = self.census_manager.get_s3_client(region="us-west-2")
                base_bucket = "cellxgene-census-public-us-west-2"
                
                # Get available versions from S3
                try:
                    versions_response = s3_client.list_objects_v2(
                        Bucket=base_bucket,
                        Prefix="cell-census/",
                        Delimiter='/',
                        MaxKeys=1000
                    )
                    
                    available_versions = []
                    if 'CommonPrefixes' in versions_response:
                        for prefix_info in versions_response['CommonPrefixes']:
                            prefix = prefix_info['Prefix']
                            version_tag = prefix.replace("cell-census/", '').rstrip('/')
                            if version_tag and version_tag != '':
                                available_versions.append(version_tag)
                    
                    # Sort versions (newest first)
                    available_versions.sort(reverse=True)
                    latest_version = available_versions[0] if available_versions else None
                    
                except Exception as s3_error:
                    action.log(message_type="s3_versions_failed", error=str(s3_error))
                    # Fall back to hardcoded version
                    latest_version = "2025-01-30"
                
                # Construct S3 paths for the organism
                organism_key = organism.lower().replace(" ", "_")
                s3_base_path = f"s3://{base_bucket}/cell-census/{latest_version}"
                soma_path = f"{s3_base_path}/soma/census_data/{organism_key}/"
                h5ads_path = f"{s3_base_path}/h5ads/"
                
                # Check if organism data exists in S3
                try:
                    org_response = s3_client.list_objects_v2(
                        Bucket=base_bucket,
                        Prefix=f"cell-census/{latest_version}/soma/census_data/{organism_key}/",
                        MaxKeys=5
                    )
                    organism_accessible = len(org_response.get('Contents', [])) > 0
                except Exception:
                    organism_accessible = False
                
                # Since we can't execute SOMA queries directly, provide S3 access information
                result = QueryResult(
                    rows=[],  # No actual data rows since we're not querying
                    count=0,
                    query_info={
                        "organism": organism,
                        "value_filter": value_filter,
                        "column_names": columns,
                        "limited": False,
                        "note": "S3-based access - use provided S3 paths for data access",
                        "s3_access": {
                            "bucket": base_bucket,
                            "version": latest_version,
                            "organism_key": organism_key,
                            "soma_path": soma_path,
                            "h5ads_path": h5ads_path,
                            "organism_accessible": organism_accessible
                        },
                        "access_methods": [
                            "Direct S3 access via AWS CLI",
                            "Download H5AD files for local analysis",
                            "Use TileDB-SOMA API with S3 URIs"
                        ],
                        "aws_cli_examples": {
                            "download_soma": f"aws s3 sync --no-sign-request {soma_path} ./soma/",
                            "download_h5ads": f"aws s3 sync --no-sign-request {h5ads_path} ./h5ads/",
                            "list_organism_data": f"aws s3 ls --no-sign-request {soma_path}"
                        },
                        "python_example": f"""
# For direct S3 access with TileDB-SOMA:
import tiledbsoma
import cellxgene_census

# Open Census from S3
census = cellxgene_census.open_soma(uri="{soma_path}")

# Query variable (gene) metadata
var_df = cellxgene_census.get_var(
    census=census,
    organism="{organism}",
    value_filter="{value_filter or 'None'}",
    column_names={columns or 'None'}
)
"""
                    }
                )
                
                action.add_success_fields(
                    rows_count=0,
                    s3_version=latest_version,
                    organism_accessible=organism_accessible
                )
                return result
                
            except Exception as e:
                action.log(message_type="query_failed", error=str(e))
                # Return error information
                return QueryResult(
                    rows=[],
                    count=0,
                    query_info={
                        "organism": organism,
                        "value_filter": value_filter,
                        "column_names": columns,
                        "error": str(e),
                        "note": "Failed to get S3 metadata information"
                    }
                )
    
    async def get_data_slice(
        self,
        organism: str = "Homo sapiens",
        obs_value_filter: Optional[str] = None,
        var_value_filter: Optional[str] = None,
        obs_column_names: Optional[str] = None,
        var_column_names: Optional[str] = None,
        max_cells: int = 10000,
        max_genes: int = 2000
    ) -> Dict[str, Any]:
        """Get a summary of a data slice from Census."""
        # Parse column names if provided as comma-separated strings
        obs_columns = None
        if obs_column_names:
            obs_columns = [col.strip() for col in obs_column_names.split(',')]
        
        var_columns = None
        if var_column_names:
            var_columns = [col.strip() for col in var_column_names.split(',')]
        
        return await self.census_manager.get_anndata_slice(
            organism=organism,
            obs_value_filter=obs_value_filter,
            var_value_filter=var_value_filter,
            obs_column_names=obs_columns,
            var_column_names=var_columns,
            max_cells=max_cells,
            max_genes=max_genes
        )
    
    async def get_all_cell_types(
        self,
        organism: str = "Homo sapiens",
        include_counts: bool = False,
        primary_data_only: bool = True
    ) -> Dict[str, Any]:
        """Get all distinct cell types from Census using H5AD approach."""
        with start_action(action_type="get_all_cell_types", organism=organism) as action:
            try:
                # For H5AD approach, we need to get the source H5AD URI first
                # Then we can analyze the file to get cell types
                
                # Get available Census versions
                versions = cellxgene_census.get_census_version_directory()
                if not versions:
                    return {
                        "organism": organism,
                        "cell_types": [],
                        "total_unique_cell_types": 0,
                        "primary_data_only": primary_data_only,
                        "total_cells_queried": 0,
                        "error": "No Census versions available",
                        "api_status": "error",
                        "data_format": "H5AD"
                    }
                
                # Use stable version if available, otherwise latest
                version_key = 'stable' if 'stable' in versions else 'latest'
                version_info = versions[version_key]
                census_version = version_info['release_build']
                
                # Get the source H5AD URI for the organism
                # Note: This requires a dataset_id, which we don't have
                # For now, we'll return information about how to access the data
                
                result = {
                    "organism": organism,
                    "cell_types": "Available via H5AD download",
                    "total_unique_cell_types": "Unknown - requires H5AD analysis",
                    "primary_data_only": primary_data_only,
                    "total_cells_queried": "Unknown - requires H5AD analysis",
                    "census_version": census_version,
                    "data_format": "H5AD",
                    "access_method": "Use get_source_h5ad_uri with dataset_id to get H5AD file",
                    "note": "Cell type information requires downloading and analyzing the H5AD file",
                    "api_status": "info"
                }
                
                action.add_success_fields(
                    organism=organism,
                    census_version=census_version,
                    data_format="H5AD"
                )
                return result
                
            except Exception as e:
                action.log(message_type="query_failed", error=str(e))
                # Return error information instead of raising
                return {
                    "organism": organism,
                    "cell_types": [],
                    "total_unique_cell_types": 0,
                    "primary_data_only": primary_data_only,
                    "total_cells_queried": 0,
                    "error": str(e),
                    "api_status": "error",
                    "data_format": "H5AD"
                }
    
    async def get_h5ad_uri(
        self,
        dataset_id: str,
        organism: str = "Homo sapiens"
    ) -> Dict[str, Any]:
        """Get the URI for a specific dataset's H5AD file."""
        with start_action(action_type="get_h5ad_uri", dataset_id=dataset_id, organism=organism) as action:
            try:
                # Get available Census versions
                versions = cellxgene_census.get_census_version_directory()
                if not versions:
                    return {
                        "dataset_id": dataset_id,
                        "organism": organism,
                        "h5ad_uri": None,
                        "error": "No Census versions available",
                        "api_status": "error"
                    }
                
                # Use stable version if available, otherwise latest
                version_key = 'stable' if 'stable' in versions else 'latest'
                version_info = versions[version_key]
                census_version = version_info['release_build']
                
                try:
                    # Get the source H5AD URI using the official API
                    h5ad_uri = cellxgene_census.get_source_h5ad_uri(
                        dataset_id=dataset_id,
                        census_version=census_version
                    )
                    
                    result = {
                        "dataset_id": dataset_id,
                        "organism": organism,
                        "h5ad_uri": h5ad_uri,
                        "census_version": census_version,
                        "api_status": "success"
                    }
                    
                    action.add_success_fields(uri=h5ad_uri, dataset_id=dataset_id)
                    return result
                    
                except Exception as uri_error:
                    return {
                        "dataset_id": dataset_id,
                        "organism": organism,
                        "h5ad_uri": None,
                        "census_version": census_version,
                        "error": f"Failed to get H5AD URI: {str(uri_error)}",
                        "api_status": "error"
                    }
                    
            except Exception as e:
                action.log(message_type="query_failed", error=str(e))
                return {
                    "dataset_id": dataset_id,
                    "organism": organism,
                    "h5ad_uri": None,
                    "error": str(e),
                    "api_status": "error"
                }
    
    async def download_h5ad(
        self,
        dataset_id: str,
        output_filename: str,
        organism: str = "Homo sapiens"
    ) -> Dict[str, Any]:
        """Download a specific dataset's H5AD file."""
        with start_action(action_type="download_h5ad", dataset_id=dataset_id, output_filename=output_filename, organism=organism) as action:
            try:
                # Get available Census versions
                versions = cellxgene_census.get_census_version_directory()
                if not versions:
                    return {
                        "dataset_id": dataset_id,
                        "organism": organism,
                        "output_filename": output_filename,
                        "download_success": False,
                        "error": "No Census versions available",
                        "api_status": "error"
                    }
                
                # Use stable version if available, otherwise latest
                version_key = 'stable' if 'stable' in versions else 'latest'
                version_info = versions[version_key]
                census_version = version_info['release_build']
                
                try:
                    # Download the source H5AD file using the official API
                    cellxgene_census.download_source_h5ad(
                        dataset_id=dataset_id,
                        census_version=census_version,
                        output_filename=output_filename
                    )
                    
                    # Check if file was downloaded successfully
                    import os
                    if os.path.exists(output_filename):
                        file_size = os.path.getsize(output_filename)
                        
                        result = {
                            "dataset_id": dataset_id,
                            "organism": organism,
                            "output_filename": output_filename,
                            "download_success": True,
                            "census_version": census_version,
                            "file_size_bytes": file_size,
                            "file_size_mb": round(file_size / (1024 * 1024), 2),
                            "api_status": "success"
                        }
                        
                        action.add_success_fields(
                            filename=output_filename, 
                            file_size=file_size,
                            dataset_id=dataset_id
                        )
                        return result
                    else:
                        return {
                            "dataset_id": dataset_id,
                            "organism": organism,
                            "output_filename": output_filename,
                            "download_success": False,
                            "census_version": census_version,
                            "error": "File download completed but file not found",
                            "api_status": "error"
                        }
                        
                except Exception as download_error:
                    return {
                        "dataset_id": dataset_id,
                        "organism": organism,
                        "output_filename": output_filename,
                        "download_success": False,
                        "census_version": census_version,
                        "error": f"Download failed: {str(download_error)}",
                        "api_status": "error"
                    }
                    
            except Exception as e:
                action.log(message_type="query_failed", error=str(e))
                return {
                    "dataset_id": dataset_id,
                    "organism": organism,
                    "output_filename": output_filename,
                    "download_success": False,
                    "error": str(e),
                    "api_status": "error"
                }
    
    async def list_available_datasets(
        self,
        organism: str = "Homo sapiens"
    ) -> Dict[str, Any]:
        """List available datasets in CELLxGENE Census for a specific organism."""
        with start_action(action_type="list_available_datasets", organism=organism) as action:
            try:
                # Get available Census versions
                versions = cellxgene_census.get_census_version_directory()
                if not versions:
                    return {
                        "organism": organism,
                        "datasets": [],
                        "total_datasets": 0,
                        "error": "No Census versions available",
                        "api_status": "error"
                    }
                
                # Use stable version if available, otherwise latest
                version_key = 'stable' if 'stable' in versions else 'latest'
                version_info = versions[version_key]
                census_version = version_info['release_build']
                
                # Note: The current API doesn't provide a direct way to list all datasets
                # This would require additional metadata or a different approach
                # For now, we'll return information about how to discover datasets
                
                result = {
                    "organism": organism,
                    "datasets": "Use get_h5ad_uri with known dataset_id",
                    "total_datasets": "Unknown - requires dataset discovery",
                    "census_version": census_version,
                    "note": "Dataset discovery requires known dataset IDs. Check CELLxGENE Discover for available datasets.",
                    "discovery_methods": [
                        "CELLxGENE Discover website",
                        "CELLxGENE Census documentation",
                        "Known dataset IDs from publications"
                    ],
                    "api_status": "info"
                }
                
                action.add_success_fields(
                    organism=organism,
                    census_version=census_version
                )
                return result
                
            except Exception as e:
                action.log(message_type="query_failed", error=str(e))
                return {
                    "organism": organism,
                    "datasets": [],
                    "total_datasets": 0,
                    "error": str(e),
                    "api_status": "error"
                }
    
    async def list_s3_versions(self) -> Dict[str, Any]:
        """List available Census versions directly from S3."""
        with start_action(action_type="list_s3_versions") as action:
            try:
                s3_client = self.census_manager.get_s3_client(region="us-west-2")
                base_bucket = "cellxgene-census-public-us-west-2"
                base_prefix = "cell-census/"
                
                # List available versions from S3
                response = s3_client.list_objects_v2(
                    Bucket=base_bucket,
                    Prefix=base_prefix,
                    Delimiter='/',
                    MaxKeys=1000
                )
                
                versions = {}
                if 'CommonPrefixes' in response:
                    for prefix_info in response['CommonPrefixes']:
                        prefix = prefix_info['Prefix']
                        version_tag = prefix.replace(base_prefix, '').rstrip('/')
                        if version_tag and version_tag != '':
                            versions[version_tag] = {
                                'release_build': version_tag,
                                's3_path': f"s3://{base_bucket}/{prefix}",
                                'soma_path': f"s3://{base_bucket}/{prefix}soma/",
                                'h5ads_path': f"s3://{base_bucket}/{prefix}h5ads/",
                                'aws_cli_soma': f"aws s3 sync --no-sign-request s3://{base_bucket}/{prefix}soma/ ./soma/",
                                'aws_cli_h5ads': f"aws s3 sync --no-sign-request s3://{base_bucket}/{prefix}h5ads/ ./h5ads/"
                            }
                
                # Sort by date (newest first)
                sorted_versions = dict(sorted(versions.items(), reverse=True))
                
                result = {
                    "available_versions": sorted_versions,
                    "total_versions": len(sorted_versions),
                    "s3_bucket": base_bucket,
                    "s3_region": "us-west-2",
                    "access_method": "Direct S3 (no authentication required)",
                    "api_status": "success"
                }
                
                action.add_success_fields(versions_count=len(sorted_versions))
                return result
                
            except Exception as e:
                action.log(message_type="s3_versions_failed", error=str(e))
                return {
                    "available_versions": {},
                    "total_versions": 0,
                    "error": str(e),
                    "api_status": "error"
                }
    
    async def get_s3_paths(self, version: str) -> Dict[str, Any]:
        """Get S3 paths for a specific Census version."""
        with start_action(action_type="get_s3_paths", version=version) as action:
            try:
                base_bucket = "cellxgene-census-public-us-west-2"
                base_prefix = f"cell-census/{version}/"
                
                s3_client = self.census_manager.get_s3_client(region="us-west-2")
                
                # Check if version exists
                response = s3_client.list_objects_v2(
                    Bucket=base_bucket,
                    Prefix=base_prefix,
                    MaxKeys=1
                )
                
                if not response.get('Contents'):
                    return {
                        "version": version,
                        "exists": False,
                        "error": f"Version {version} not found in S3",
                        "api_status": "error"
                    }
                
                # Get organism-specific paths
                organisms = ["homo_sapiens", "mus_musculus"]
                organism_paths = {}
                
                for organism in organisms:
                    organism_prefix = f"{base_prefix}soma/census_data/{organism}/"
                    org_response = s3_client.list_objects_v2(
                        Bucket=base_bucket,
                        Prefix=organism_prefix,
                        MaxKeys=5
                    )
                    
                    organism_paths[organism] = {
                        "s3_path": f"s3://{base_bucket}/{organism_prefix}",
                        "accessible": len(org_response.get('Contents', [])) > 0,
                        "sample_keys": [obj['Key'] for obj in org_response.get('Contents', [])[:3]]
                    }
                
                result = {
                    "version": version,
                    "exists": True,
                    "s3_bucket": base_bucket,
                    "s3_region": "us-west-2",
                    "paths": {
                        "base": f"s3://{base_bucket}/{base_prefix}",
                        "soma": f"s3://{base_bucket}/{base_prefix}soma/",
                        "h5ads": f"s3://{base_bucket}/{base_prefix}h5ads/",
                        "organisms": organism_paths
                    },
                    "aws_cli_examples": {
                        "download_soma": f"aws s3 sync --no-sign-request s3://{base_bucket}/{base_prefix}soma/ ./soma/",
                        "download_h5ads": f"aws s3 sync --no-sign-request s3://{base_bucket}/{base_prefix}h5ads/ ./h5ads/"
                    },
                    "api_status": "success"
                }
                
                action.add_success_fields(version=version)
                return result
                
            except Exception as e:
                action.log(message_type="s3_paths_failed", error=str(e))
                return {
                    "version": version,
                    "exists": False,
                    "error": str(e),
                    "api_status": "error"
                }
    
    async def check_s3_access(self) -> Dict[str, Any]:
        """Check S3 access to Census data."""
        with start_action(action_type="check_s3_access") as action:
            try:
                s3_client = self.census_manager.get_s3_client(region="us-west-2")
                base_bucket = "cellxgene-census-public-us-west-2"
                
                # Test basic S3 access
                test_response = s3_client.list_objects_v2(
                    Bucket=base_bucket,
                    Prefix="cell-census/",
                    MaxKeys=1
                )
                
                access_status = "accessible" if test_response.get('Contents') else "no_access"
                
                # Get bucket info
                try:
                    bucket_response = s3_client.head_bucket(Bucket=base_bucket)
                    bucket_info = {
                        "name": base_bucket,
                        "region": bucket_response.get('ResponseMetadata', {}).get('HTTPHeaders', {}).get('x-amz-bucket-region', 'us-west-2'),
                        "accessible": True
                    }
                except Exception as bucket_error:
                    bucket_info = {
                        "name": base_bucket,
                        "region": "us-west-2",
                        "accessible": False,
                        "error": str(bucket_error)
                    }
                
                result = {
                    "s3_access": access_status,
                    "bucket_info": bucket_info,
                    "test_timestamp": "now",
                    "recommended_region": "us-west-2",
                    "authentication_required": False,
                    "api_status": "success" if access_status == "accessible" else "limited"
                }
                
                action.add_success_fields(access_status=access_status)
                return result
                
            except Exception as e:
                action.log(message_type="s3_access_check_failed", error=str(e))
                return {
                    "s3_access": "failed",
                    "error": str(e),
                    "api_status": "error"
                }

    async def get_quilt_s3_paths(self, version: str) -> Dict[str, Any]:
        """Get S3 paths specifically formatted for Quilt MCP tools."""
        with start_action(action_type="get_quilt_s3_paths", version=version) as action:
            try:
                base_bucket = "cellxgene-census-public-us-west-2"
                base_prefix = f"cell-census/{version}/"
                
                s3_client = self.census_manager.get_s3_client(region="us-west-2")
                
                # Check if version exists
                response = s3_client.list_objects_v2(
                    Bucket=base_bucket,
                    Prefix=base_prefix,
                    MaxKeys=1
                )
                
                if not response.get('Contents'):
                    return {
                        "version": version,
                        "exists": False,
                        "error": f"Version {version} not found in S3",
                        "api_status": "error"
                    }
                
                # Get organism-specific paths
                organisms = ["homo_sapiens", "mus_musculus"]
                organism_paths = {}
                
                for organism in organisms:
                    organism_prefix = f"{base_prefix}soma/census_data/{organism}/"
                    org_response = s3_client.list_objects_v2(
                        Bucket=base_bucket,
                        Prefix=organism_prefix,
                        MaxKeys=5
                    )
                    
                    organism_paths[organism] = {
                        "s3_path": f"s3://{base_bucket}/{organism_prefix}",
                        "accessible": len(org_response.get('Contents', [])) > 0,
                        "sample_keys": [obj['Key'] for obj in org_response.get('Contents', [])[:3]]
                    }
                
                result = {
                    "version": version,
                    "exists": True,
                    "s3_bucket": base_bucket,
                    "s3_region": "us-west-2",
                    "paths": {
                        "base": f"s3://{base_bucket}/{base_prefix}",
                        "soma": f"s3://{base_bucket}/{base_prefix}soma/",
                        "h5ads": f"s3://{base_bucket}/{base_prefix}h5ads/",
                        "organisms": organism_paths
                    },
                    "aws_cli_examples": {
                        "download_soma": f"aws s3 sync --no-sign-request s3://{base_bucket}/{base_prefix}soma/ ./soma/",
                        "download_h5ads": f"aws s3 sync --no-sign-request s3://{base_bucket}/{base_prefix}h5ads/ ./h5ads/"
                    },
                    "api_status": "success"
                }
                
                action.add_success_fields(version=version)
                return result
                
            except Exception as e:
                action.log(message_type="s3_paths_failed", error=str(e))
                return {
                    "version": version,
                    "exists": False,
                    "error": str(e),
                    "api_status": "error"
                }

def cli_app():
    """CLI application for HTTP transport."""
    parser = argparse.ArgumentParser(description="CELLxGENE Census MCP Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind to")
    parser.add_argument("--census-version", help="Specific Census version to use")
    args = parser.parse_args()
    
    server = CellxGeneMCP(census_version=args.census_version)
    server.run(transport="fastapi", host=args.host, port=args.port)

def cli_app_stdio():
    """CLI application for stdio transport."""
    parser = argparse.ArgumentParser(description="CELLxGENE Census MCP Server (stdio)")
    parser.add_argument("--census-version", help="Specific Census version to use")
    args = parser.parse_args()
    
    server = CellxGeneMCP(census_version=args.census_version)
    server.run(transport="stdio")

def cli_app_sse():
    """CLI application for SSE transport."""
    parser = argparse.ArgumentParser(description="CELLxGENE Census MCP Server (SSE)")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind to")
    parser.add_argument("--census-version", help="Specific Census version to use")
    args = parser.parse_args()
    
    server = CellxGeneMCP(census_version=args.census_version)
    server.run(transport="sse", host=args.host, port=args.port)

if __name__ == "__main__":
    cli_app_stdio() 