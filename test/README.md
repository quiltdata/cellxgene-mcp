# Test Suite Documentation

This directory contains comprehensive tests for the CELLxGENE Census MCP Server to ensure all tools work as expected.

## 🧪 Test Structure

### Core Test Files

- **`test_mcp_tools.py`** - Main test suite for MCP tools and functionality
- **`conftest.py`** - Pytest configuration and shared fixtures
- **`run_tests.py`** - Test runner script for local execution

### Test Categories

1. **Unit Tests** - Test individual components in isolation
2. **Integration Tests** - Test component interactions
3. **Protocol Tests** - Test MCP protocol compliance
4. **Error Handling Tests** - Test error scenarios and edge cases

## 🚀 Running Tests

### Prerequisites

Install test dependencies:
```bash
uv pip install -r test/requirements-test.txt
```

### Quick Test Run

```bash
# Run all tests
python test/run_tests.py

# Run with verbose output
python test/run_tests.py -v

# Run specific test types
python test/run_tests.py --type unit
python test/run_tests.py --type integration
python test/run_tests.py --type fast

# Run with coverage
python test/run_tests.py --coverage
```

### Using pytest directly

```bash
# Run all tests
uv run pytest test/ -v

# Run specific test file
uv run pytest test/test_mcp_tools.py -v

# Run tests matching pattern
uv run pytest test/ -k "test_get_census_info" -v

# Run with coverage
uv run pytest test/ --cov=cellxgene_mcp --cov-report=html
```

## 📋 Test Coverage

### MCP Tools Tested

- ✅ `get_census_info` - Census metadata and statistics
- ✅ `get_obs_metadata` - Observation (cell) metadata
- ✅ `get_var_metadata` - Variable (gene) metadata  
- ✅ `get_data_slice` - Data subset extraction
- ✅ `get_all_cell_types` - Cell type enumeration

### MCP Resources Tested

- ✅ `resource://cellxgene_census-info` - Census information resource

### Components Tested

- ✅ `CensusManager` - Census connection and version management
- ✅ `CellxGeneMCP` - Main MCP server class
- ✅ Data models (`QueryResult`, `S3DataReference`, `S3TransferResult`)
- ✅ Error handling and edge cases
- ✅ Async/await functionality

## 🔧 Test Configuration

### Pytest Configuration (`conftest.py`)

- **Event Loop Setup** - Proper async test configuration
- **Path Management** - Automatic src directory inclusion
- **Shared Fixtures** - Common test data and mocks
- **Plugin Configuration** - pytest-asyncio integration

### Mock Strategy

Tests use comprehensive mocking to:
- **Isolate Components** - Test individual units without external dependencies
- **Simulate Census Data** - Mock Census responses for consistent testing
- **Control Error Conditions** - Test error handling paths
- **Avoid Network Calls** - Fast, reliable test execution

## 🎯 Test Patterns

### Async Testing

```python
@pytest.mark.asyncio
async def test_async_tool():
    result = await server.async_tool()
    assert result is not None
```

### Mocking External Dependencies

```python
@patch('cellxgene_mcp.server.cellxgene_census')
def test_with_mock(mock_census):
    mock_census.get_census_version_directory.return_value = {...}
    # Test implementation
```

### Fixture Usage

```python
def test_with_fixture(sample_census_data):
    assert "homo_sapiens" in sample_census_data
    assert sample_census_data["homo_sapiens"]["obs_count"] == 1000
```

## 🚨 Error Testing

### Expected Error Scenarios

- **Census Connection Failures** - Network issues, authentication errors
- **Invalid Parameters** - Wrong organism names, invalid filters
- **Data Processing Errors** - Malformed data, memory issues
- **S3 Connectivity Issues** - AWS service problems

### Error Handling Verification

```python
with pytest.raises(Exception) as exc_info:
    await server.get_census_info()
assert "Census connection failed" in str(exc_info.value)
```

## 📊 Coverage Goals

### Target Coverage

- **Line Coverage**: >90%
- **Branch Coverage**: >85%
- **Function Coverage**: >95%

### Coverage Reports

Generate coverage reports:
```bash
uv run pytest test/ --cov=cellxgene_mcp --cov-report=html --cov-report=term-missing
```

View HTML report: `htmlcov/index.html`

## 🔍 Continuous Integration

### GitHub Actions Integration

Tests run automatically on:
- **Push to main/develop** - Full test suite
- **Pull Requests** - Pre-merge validation
- **Feature Branches** - Early error detection

### CI Pipeline Stages

1. **Unit Tests** - Fast component tests
2. **Integration Tests** - Component interaction tests
3. **Protocol Tests** - MCP compliance verification
4. **Dependency Tests** - Import and connectivity checks
5. **Code Quality** - Linting and formatting
6. **Security Scan** - Vulnerability detection

## 🛠️ Debugging Tests

### Verbose Output

```bash
python test/run_tests.py -v --type unit
```

### Single Test Execution

```bash
uv run pytest test/test_mcp_tools.py::TestMCPTools::test_get_census_info -v -s
```

### Test Isolation

```bash
# Run only one test class
uv run pytest test/test_mcp_tools.py::TestCensusManager -v

# Run tests matching pattern
uv run pytest test/ -k "census" -v
```

## 📝 Adding New Tests

### Test File Structure

```python
class TestNewFeature:
    """Test the new feature functionality."""
    
    @pytest.fixture
    def setup_data(self):
        """Setup test data."""
        return {"test": "data"}
    
    def test_basic_functionality(self, setup_data):
        """Test basic functionality."""
        assert setup_data["test"] == "data"
    
    @pytest.mark.asyncio
    async def test_async_functionality(self):
        """Test async functionality."""
        result = await some_async_function()
        assert result is not None
```

### Test Naming Conventions

- **Test Classes**: `Test{ComponentName}`
- **Test Methods**: `test_{description}`
- **Async Tests**: Use `@pytest.mark.asyncio`
- **Fixtures**: Descriptive names with `@pytest.fixture`

## 🎉 Success Criteria

Tests pass when:
- ✅ All unit tests execute successfully
- ✅ Integration tests validate component interactions
- ✅ Error handling tests verify proper exception handling
- ✅ Coverage meets minimum thresholds
- ✅ Code quality checks pass
- ✅ Security scans show no critical vulnerabilities

## 📚 Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Python Mocking](https://docs.python.org/3/library/unittest.mock.html)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
