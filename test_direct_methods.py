#!/usr/bin/env python3
"""Test MCP server methods directly to verify functionality."""

import sys
import os
import time

# Add the src directory to the path so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from cellxgene_mcp.server import CellxGeneMCP

def test_census_directly():
    """Test Census access directly without async methods."""
    print("Testing CELLxGENE Census access directly...")
    print("=" * 60)
    
    try:
        # Initialize server
        print("🔄 Initializing server...")
        start_time = time.time()
        server = CellxGeneMCP(name="DirectTestServer")
        init_time = time.time() - start_time
        print(f"✓ Server initialized successfully in {init_time:.2f}s")
        
        # Access census manager directly
        print("\n🔄 Accessing census manager...")
        census_manager = server.census_manager
        print("✓ Census manager accessed")
        
        # Try to get census object
        print("🔄 Getting census object...")
        start_time = time.time()
        census = census_manager.get_census()
        census_time = time.time() - start_time
        print(f"✓ Census object retrieved in {census_time:.2f}s")
        
        # Check what's in the census
        print(f"\n📊 Census Object Analysis:")
        print(f"  - Census type: {type(census)}")
        print(f"  - Census keys: {list(census.keys())}")
        
        if "census_data" in census:
            organisms = list(census["census_data"].keys())
            print(f"  - Available organisms: {organisms}")
            
            # Check first organism
            if organisms:
                first_org = organisms[0]
                print(f"\n🔍 Analyzing organism: {first_org}")
                
                exp = census["census_data"][first_org]
                print(f"  - Experiment type: {type(exp)}")
                
                if hasattr(exp, 'keys'):
                    print(f"  - Experiment keys: {list(exp.keys())}")
                    
                    # Check if obs and var exist
                    if 'obs' in exp:
                        print(f"  - Observations (obs) available: {type(exp.obs)}")
                        
                        # Try to get obs info without full loading
                        try:
                            print("  - Attempting to read obs metadata...")
                            obs_info = exp.obs.read(column_names=["soma_joinid"]).concat().to_pandas()
                            print(f"  - Obs data shape: {obs_info.shape}")
                            print(f"  - Obs columns: {list(obs_info.columns)}")
                            print(f"  - Total cells: {len(obs_info):,}")
                        except Exception as e:
                            print(f"  - Error reading obs data: {e}")
                            print(f"    Error type: {type(e).__name__}")
                    
                    if 'var' in exp:
                        print(f"  - Variables (var) available: {type(exp.var)}")
                        
                        # Try to get var info without full loading
                        try:
                            print("  - Attempting to read var metadata...")
                            var_info = exp.var.read(column_names=["soma_joinid"]).concat().to_pandas()
                            print(f"  - Var data shape: {var_info.shape}")
                            print(f"  - Var columns: {list(var_info.columns)}")
                            print(f"  - Total genes: {len(var_info):,}")
                        except Exception as e:
                            print(f"  - Error reading var data: {e}")
                            print(f"    Error type: {type(e).__name__}")
                else:
                    print(f"  - Experiment has no keys method")
        
        # Close census
        print("\n🔄 Closing census...")
        census.close()
        print("✓ Census closed")
        
        print("\n" + "="*60)
        print("🎉 Direct Census testing completed!")
        print("This shows what data is actually available in the Census.")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting direct Census access test...")
    print("This will test Census access without the problematic async methods.")
    print("=" * 60)
    
    success = test_census_directly()
    
    print("\n" + "="*60)
    if success:
        print("✅ Census access is working correctly!")
    else:
        print("❌ Census access failed. Check the output above.")
        sys.exit(1)
