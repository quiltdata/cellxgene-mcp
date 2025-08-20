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
        """Get observation (cell) metadata from Census."""
        with start_action(action_type="get_obs_metadata", organism=organism, value_filter=value_filter) as action:
            try:
                census = self.get_census()
                try:
                    obs_df = cellxgene_census.get_obs(
                        census=census,
                        organism=organism,
                        value_filter=value_filter,
                        column_names=column_names
                    )
                    
                    # Limit results to prevent memory issues
                    if len(obs_df) > limit:
                        obs_df = obs_df.head(limit)
                        action.log(message_type="result_limited", original_count=len(obs_df), limited_count=limit)
                    
                    # Convert to list of dictionaries
                    rows = obs_df.to_dict('records')
                    
                    result = QueryResult(
                        rows=rows,
                        count=len(rows),
                        query_info={
                            "organism": organism,
                            "value_filter": value_filter,
                            "column_names": column_names,
                            "limited": len(obs_df) > limit
                        }
                    )
                    
                    action.add_success_fields(rows_count=len(rows))
                    return result
                finally:
                    census.close()
            except Exception as e:
                action.log(message_type="query_failed", error=str(e))
                raise
    
    async def get_var_metadata(
        self, 
        organism: str = "Homo sapiens",
        value_filter: Optional[str] = None,
        column_names: Optional[List[str]] = None,
        limit: int = 1000
    ) -> QueryResult:
        """Get variable (gene) metadata from Census."""
        with start_action(action_type="get_var_metadata", organism=organism, value_filter=value_filter) as action:
            try:
                census = self.get_census()
                try:
                    var_df = cellxgene_census.get_var(
                        census=census,
                        organism=organism,
                        value_filter=value_filter,
                        column_names=column_names
                    )
                    
                    # Limit results to prevent memory issues
                    if len(var_df) > limit:
                        var_df = var_df.head(limit)
                        action.log(message_type="result_limited", original_count=len(var_df), limited_count=limit)
                    
                    # Convert to list of dictionaries
                    rows = var_df.to_dict('records')
                    
                    result = QueryResult(
                        rows=rows,
                        count=len(rows),
                        query_info={
                            "organism": organism,
                            "value_filter": value_filter,
                            "column_names": column_names,
                            "limited": len(var_df) > limit
                        }
                    )
                    
                    action.add_success_fields(rows_count=len(rows))
                    return result
                finally:
                    census.close()
            except Exception as e:
                action.log(message_type="query_failed", error=str(e))
                raise
    
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

Common Query Patterns:
1. Filter by cell type: cell_type == 'T cell'
2. Filter by tissue: tissue == 'lung'
3. Filter by disease: disease == 'COVID-19'
4. Combine filters: cell_type == 'T cell' and tissue == 'lung'
5. Filter genes: feature_name in ['CD4', 'CD8A', 'CD3E']

Note: Queries can return large amounts of data. Use filters to limit results.
"""
    
    async def get_census_info(self) -> Dict[str, Any]:
        """Get information about available Census versions and organisms."""
        with start_action(action_type="get_census_info") as action:
            try:
                # Get available Census versions
                try:
                    versions = cellxgene_census.get_census_version_directory()
                except Exception as version_error:
                    action.log(message_type="version_directory_failed", error=str(version_error))
                    versions = []
                
                # Get information about the current/latest version
                latest_version = None
                if versions:
                    # versions is an OrderedDict, get the 'stable' version if available
                    if 'stable' in versions:
                        latest_version = versions['stable']['release_build']
                    elif 'latest' in versions:
                        latest_version = versions['latest']['release_build']
                    else:
                        # Fall back to the first available version
                        try:
                            first_key = next(iter(versions))
                            latest_version = versions[first_key]['release_build']
                        except (IndexError, KeyError, StopIteration):
                            latest_version = None
                
                # Actually open Census to get real information
                census = self.census_manager.get_census()
                try:
                    # Get actual organisms available in the Census
                    organisms = list(census["census_data"].keys())
                    
                    # Get summary statistics for each organism
                    organism_stats = {}
                    total_cells = 0
                    
                    for organism in organisms:
                        try:
                            # Get basic stats for this organism
                            exp = census["census_data"][organism]
                            
                            # Get a small sample to determine available columns and data types
                            obs_sample = exp.obs.read(column_names=None).concat().to_pandas().head(1)
                            var_sample = exp.var.read(column_names=None).concat().to_pandas().head(1)
                            
                            # Count total cells and genes for this organism
                            obs_count = len(exp.obs.read(column_names=["soma_joinid"]).concat().to_pandas())
                            var_count = len(exp.var.read(column_names=["soma_joinid"]).concat().to_pandas())
                            
                            total_cells += obs_count
                            
                            organism_stats[organism] = {
                                "total_cells": obs_count,
                                "total_genes": var_count,
                                "obs_columns": list(obs_sample.columns) if not obs_sample.empty else [],
                                "var_columns": list(var_sample.columns) if not var_sample.empty else []
                            }
                        except Exception as org_error:
                            action.log(message_type="organism_query_failed", organism=organism, error=str(org_error))
                            organism_stats[organism] = {"error": str(org_error)}
                    
                    # Try to get summary info if available
                    summary_info = {}
                    try:
                        if "census_info" in census and "summary" in census["census_info"]:
                            summary_df = census["census_info"]["summary"].read().concat().to_pandas()
                            summary_info = dict(zip(summary_df["label"], summary_df["value"]))
                    except Exception as summary_error:
                        action.log(message_type="summary_query_failed", error=str(summary_error))
                    
                    result = {
                        "available_versions": versions if versions else [],
                        "latest_stable_version": latest_version,
                        "supported_organisms": organisms,
                        "organism_statistics": organism_stats,
                        "total_cells_across_organisms": total_cells,
                        "census_summary": summary_info,
                        "version_info": versions if versions else []
                    }
                    
                    action.add_success_fields(
                        versions_count=len(versions) if versions else 0,
                        organisms_count=len(organisms),
                        total_cells=total_cells
                    )
                    return result
                finally:
                    census.close()
                
            except Exception as e:
                action.log(message_type="query_failed", error=str(e))
                raise
    
    async def get_obs_metadata(
        self,
        organism: str = "Homo sapiens",
        value_filter: Optional[str] = None,
        column_names: Optional[str] = None,
        limit: int = 1000
    ) -> QueryResult:
        """Get cell (observation) metadata from Census."""
        # Parse column names if provided as comma-separated string
        columns = None
        if column_names:
            columns = [col.strip() for col in column_names.split(',')]
        
        return await self.census_manager.get_obs_metadata(
            organism=organism,
            value_filter=value_filter,
            column_names=columns,
            limit=limit
        )
    
    async def get_var_metadata(
        self,
        organism: str = "Homo sapiens",
        value_filter: Optional[str] = None,
        column_names: Optional[str] = None,
        limit: int = 1000
    ) -> QueryResult:
        """Get gene (variable) metadata from Census."""
        # Parse column names if provided as comma-separated string
        columns = None
        if column_names:
            columns = [col.strip() for col in column_names.split(',')]
        
        return await self.census_manager.get_var_metadata(
            organism=organism,
            value_filter=value_filter,
            column_names=columns,
            limit=limit
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
        """Get all distinct cell types from Census."""
        with start_action(action_type="get_all_cell_types", organism=organism) as action:
            try:
                census = self.census_manager.get_census()
                try:
                    # Build value filter
                    value_filter = None
                    if primary_data_only:
                        value_filter = "is_primary_data == True"
                    
                    # Get cell type data
                    obs_df = cellxgene_census.get_obs(
                        census=census,
                        organism=organism,
                        column_names=["cell_type"],
                        value_filter=value_filter
                    )
                    
                    # Get unique cell types
                    unique_cell_types = obs_df['cell_type'].unique().tolist()
                    unique_cell_types.sort()  # Sort alphabetically
                    
                    result = {
                        "organism": organism,
                        "cell_types": unique_cell_types,
                        "total_unique_cell_types": len(unique_cell_types),
                        "primary_data_only": primary_data_only
                    }
                    
                    # Optionally include counts
                    if include_counts:
                        cell_type_counts = obs_df['cell_type'].value_counts()
                        result["cell_type_counts"] = cell_type_counts.to_dict()
                        result["top_10_cell_types"] = cell_type_counts.head(10).to_dict()
                    
                    action.add_success_fields(
                        unique_cell_types_count=len(unique_cell_types),
                        total_cells=len(obs_df)
                    )
                    return result
                finally:
                    census.close()
            except Exception as e:
                action.log(message_type="query_failed", error=str(e))
                raise

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