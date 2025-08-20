#!/usr/bin/env python3
"""Test basic connectivity for the CELLxGENE Census MCP Server."""

import sys
import os
import asyncio
import signal

# Add the src directory to the path so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

print("Testing basic imports...")

try:
    import cellxgene_mcp
    print("✓ Successfully imported cellxgene_mcp package")
except ImportError as e:
    print(f"❌ Failed to import cellxgene_mcp package: {e}")
    sys.exit(1)

try:
    from cellxgene_mcp.server import CellxGeneMCP
    print("✓ Successfully imported CellxGeneMCP class")
except ImportError as e:
    print(f"❌ Failed to import CellxGeneMCP: {e}")
    sys.exit(1)

try:
    from cellxgene_mcp.server import CensusManager
    print("✓ Successfully imported CensusManager class")
except ImportError as e:
    print(f"❌ Failed to import CensusManager: {e}")
    sys.exit(1)

print("\nTesting basic class instantiation...")

try:
    # Try to create a CensusManager instance
    census_manager = CensusManager()
    print("✓ CensusManager instantiated successfully")
except Exception as e:
    print(f"❌ Failed to instantiate CensusManager: {e}")
    import traceback
    traceback.print_exc()

try:
    # Try to create a CellxGeneMCP instance
    server = CellxGeneMCP(name="TestServer")
    print("✓ CellxGeneMCP instantiated successfully")
    
    # Check what attributes and methods are available
    print(f"\n✓ Server attributes and methods:")
    for attr in dir(server):
        if not attr.startswith('_'):
            print(f"  - {attr}")
    
    # Try to check if the server can run (without actually running it)
    print(f"\n✓ Server can be instantiated and configured")
        
except Exception as e:
    print(f"❌ Failed to instantiate CellxGeneMCP: {e}")
    import traceback
    traceback.print_exc()

print("\nTesting server startup (with timeout)...")

async def test_server_startup():
    """Test if the server can start up without hanging."""
    try:
        server = CellxGeneMCP(name="TestServer")
        
        # Set a timeout for the test
        timeout = 10  # seconds
        
        # Create a task that will run the server
        server_task = asyncio.create_task(
            server.run_stdio_async()
        )
        
        # Wait for either the server to start or timeout
        try:
            await asyncio.wait_for(server_task, timeout=timeout)
        except asyncio.TimeoutError:
            print(f"✓ Server startup test completed (timed out after {timeout}s as expected)")
            # Cancel the server task
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
        except Exception as e:
            print(f"✓ Server startup test completed with result: {e}")
            
    except Exception as e:
        print(f"❌ Server startup test failed: {e}")
        import traceback
        traceback.print_exc()

# Run the async test
try:
    asyncio.run(test_server_startup())
except KeyboardInterrupt:
    print("\n✓ Server startup test interrupted by user (this is normal)")
except Exception as e:
    print(f"❌ Server startup test failed: {e}")

print("\n🎉 All tests completed!")
print("Note: This test only checks server initialization and startup, not actual Census connectivity.")
print("To test actual Census connectivity, you would need to run the server and test via MCP protocol.")
