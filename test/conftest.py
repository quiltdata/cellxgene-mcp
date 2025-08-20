"""Pytest configuration for CELLxGENE Census MCP Server tests."""

import pytest
import sys
from pathlib import Path

# Add src directory to Python path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Test configuration
pytest_plugins = ["pytest_asyncio"]

# Configure pytest-asyncio
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

# Common test fixtures
@pytest.fixture
def sample_census_data():
    """Sample Census data for testing."""
    return {
        "homo_sapiens": {
            "obs_count": 1000,
            "var_count": 500,
            "cell_types": ["T cell", "B cell", "NK cell"],
            "tissues": ["lung", "blood", "brain"]
        },
        "mus_musculus": {
            "obs_count": 500,
            "var_count": 300,
            "cell_types": ["T cell", "B cell"],
            "tissues": ["lung", "spleen"]
        }
    }

@pytest.fixture
def sample_query_filters():
    """Sample query filters for testing."""
    return {
        "cell_type": "T cell",
        "tissue": "lung",
        "disease": "COVID-19",
        "organism": "Homo sapiens"
    }
