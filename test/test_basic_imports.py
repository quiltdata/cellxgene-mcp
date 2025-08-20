#!/usr/bin/env python3
"""Basic import and initialization tests for CELLxGENE Census MCP Server."""

import sys
import asyncio
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_imports():
    """Test that all required modules can be imported."""
    try:
        import cellxgene_mcp
        print("✅ cellxgene_mcp imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import cellxgene_mcp: {e}")
        return False
    
    try:
        from cellxgene_mcp.server import CellxGeneMCP
        print("✅ CellxGeneMCP class imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import CellxGeneMCP: {e}")
        return False
    
    try:
        from cellxgene_mcp.server import CensusManager
        print("✅ CensusManager class imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import CensusManager: {e}")
        return False
    
    return True

def test_server_initialization():
    """Test that the MCP server can be initialized."""
    try:
        from cellxgene_mcp.server import CellxGeneMCP
        
        server = CellxGeneMCP(name="TestServer")
        print(f"✅ Server initialized: {server.name}")
        print(f"✅ Server prefix: {server.prefix}")
        print(f"✅ Census manager: {server.census_manager}")
        
        return True
    except Exception as e:
        print(f"❌ Failed to initialize server: {e}")
        return False

async def test_tools_registration():
    """Test that tools are properly registered."""
    try:
        from cellxgene_mcp.server import CellxGeneMCP
        
        server = CellxGeneMCP(name="TestServer")
        tools = await server.get_tools()
        
        print(f"✅ Tools registered: {len(tools)}")
        for tool in tools:
            if hasattr(tool, 'name'):
                print(f"  - {tool.name}: {tool.description[:60]}...")
            else:
                print(f"  - {tool}")
        
        return True
    except Exception as e:
        print(f"❌ Failed to get tools: {e}")
        return False

async def test_resources_registration():
    """Test that resources are properly registered."""
    try:
        from cellxgene_mcp.server import CellxGeneMCP
        
        server = CellxGeneMCP(name="TestServer")
        resources = await server.get_resources()
        
        print(f"✅ Resources registered: {len(resources)}")
        for resource in resources:
            if hasattr(resource, 'name'):
                print(f"  - {resource.name}")
            else:
                print(f"  - {resource}")
        
        return True
    except Exception as e:
        print(f"❌ Failed to get resources: {e}")
        return False

async def run_async_tests():
    """Run async tests."""
    print("\n📋 Running: Tools Registration")
    print("-" * 30)
    tools_result = await test_tools_registration()
    
    print("\n📋 Running: Resources Registration")
    print("-" * 30)
    resources_result = await test_resources_registration()
    
    return tools_result, resources_result

def main():
    """Run all basic tests."""
    print("🧪 Basic Import and Initialization Tests")
    print("=" * 50)
    
    # Run sync tests
    tests = [
        ("Import Tests", test_imports),
        ("Server Initialization", test_server_initialization),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        print("-" * 30)
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append((test_name, False))
    
    # Run async tests
    print("\n🔄 Running Async Tests...")
    try:
        tools_result, resources_result = asyncio.run(run_async_tests())
        results.append(("Tools Registration", tools_result))
        results.append(("Resources Registration", resources_result))
    except Exception as e:
        print(f"❌ Async tests failed: {e}")
        results.append(("Tools Registration", False))
        results.append(("Resources Registration", False))
    
    print("\n" + "=" * 50)
    print("📊 Test Results Summary")
    print("=" * 50)
    
    all_passed = True
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not result:
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 All basic tests passed!")
        return True
    else:
        print("💥 Some tests failed. Check the output above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
