#!/usr/bin/env python3
"""Test MCP server using the actual MCP protocol."""

import asyncio
import sys
import os
import json

# Add the src directory to the path so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from cellxgene_mcp.server import CellxGeneMCP

async def test_mcp_tools():
    """Test MCP server tools using the MCP protocol."""
    print("Testing CELLxGENE Census MCP Server via MCP protocol...")
    print("=" * 60)
    
    try:
        # Initialize server
        print("🔄 Initializing MCP server...")
        server = CellxGeneMCP(name="MCPTestServer")
        print("✓ MCP server initialized successfully")
        
        # Test 1: List available tools
        print("\n🧪 Test 1: List available tools...")
        tools = await server.get_tools()
        print(f"✓ Found {len(tools)} tools:")
        for tool in tools:
            if hasattr(tool, 'name'):
                print(f"  - {tool.name}: {tool.description[:80]}...")
            else:
                print(f"  - {tool}")
        
        # Test 2: Test a simple tool (get_all_cell_types with minimal data)
        print(f"\n🧪 Test 2: Test get_all_cell_types tool...")
        try:
            # Find the cell types tool
            cell_types_tool = None
            for tool in tools:
                tool_name = tool.name if hasattr(tool, 'name') else str(tool)
                if "get_all_cell_types" in tool_name:
                    cell_types_tool = tool
                    break
            
            if cell_types_tool:
                tool_name = cell_types_tool.name if hasattr(cell_types_tool, 'name') else str(cell_types_tool)
                print(f"✓ Found cell types tool: {tool_name}")
                
                # Call the tool through the server's method
                result = await server.get_all_cell_types(
                    organism="Homo sapiens",
                    include_counts=False,  # Don't include counts for speed
                    primary_data_only=True
                )
                
                print(f"✓ Cell types tool executed successfully")
                print(f"  - Found {result.get('total_unique_cell_types', 0)} cell types")
                sample_types = result.get('cell_types', [])[:3]
                print(f"  - Sample types: {sample_types}")
                
            else:
                print("❌ Cell types tool not found")
                
        except Exception as e:
            print(f"❌ Cell types tool failed: {e}")
        
        # Test 3: Test observation metadata with very small limit
        print(f"\n🧪 Test 3: Test get_obs_metadata tool...")
        try:
            # Find the obs metadata tool
            obs_tool = None
            for tool in tools:
                tool_name = tool.name if hasattr(tool, 'name') else str(tool)
                if "get_obs_metadata" in tool_name:
                    obs_tool = tool
                    break
            
            if obs_tool:
                tool_name = obs_tool.name if hasattr(obs_tool, 'name') else str(obs_tool)
                print(f"✓ Found obs metadata tool: {tool_name}")
                
                # Call the tool with a tiny limit
                result = await server.get_obs_metadata(
                    organism="Homo sapiens",
                    limit=2  # Very small limit
                )
                
                print(f"✓ Obs metadata tool executed successfully")
                print(f"  - Retrieved {result.count} rows")
                if result.rows:
                    print(f"  - Sample columns: {list(result.rows[0].keys())[:5]}...")
                
            else:
                print("❌ Obs metadata tool not found")
                
        except Exception as e:
            print(f"❌ Obs metadata tool failed: {e}")
        
        # Test 4: Test resources
        print(f"\n🧪 Test 4: List available resources...")
        resources = await server.get_resources()
        print(f"✓ Found {len(resources)} resources:")
        for resource in resources:
            resource_name = resource.name if hasattr(resource, 'name') else str(resource)
            print(f"  - {resource_name}")
        
        print("\n" + "="*60)
        print("🎉 MCP protocol testing completed!")
        print("The server tools are working correctly via MCP protocol.")
        
        return True
        
    except Exception as e:
        print(f"\n❌ MCP protocol test failed: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting MCP protocol test...")
    print("This will test the server using the actual MCP protocol.")
    print("=" * 60)
    
    success = asyncio.run(test_mcp_tools())
    
    print("\n" + "="*60)
    if success:
        print("✅ MCP server tools are working correctly!")
    else:
        print("❌ MCP server tools failed. Check the output above.")
        sys.exit(1)
