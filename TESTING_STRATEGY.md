# Testing Strategy for CELLxGENE Census MCP Server

> **⚠️ NOTE: Tests are temporarily disabled** - The test framework is in place but execution is currently skipped. Tests will be re-enabled once the underlying issues are resolved.

## 🎯 Overview

This document outlines our comprehensive testing strategy to ensure all MCP tools work as expected. We've implemented a multi-layered testing approach that covers unit testing, integration testing, protocol compliance, and continuous integration.

## 🧪 Testing Pyramid

```
                    ┌─────────────────┐
                    │   E2E Tests     │ ← Manual DXT testing
                    └─────────────────┘
                           │
                    ┌─────────────────┐
                    │ Integration     │ ← MCP protocol tests
                    │   Tests         │
                    └─────────────────┘
                           │
                    ┌─────────────────┘
                    │   Unit Tests    │ ← Individual tool tests
                    └─────────────────┘
```

## 🔧 Test Categories

### 1. Unit Tests (`test_mcp_tools.py`)

**Purpose**: Test individual components in isolation
**Coverage**: All MCP tools, data models, and utility classes

#### MCP Tools Tested:
- ✅ `get_census_info` - Census metadata and statistics
- ✅ `get_obs_metadata` - Observation (cell) metadata  
- ✅ `get_var_metadata` - Variable (gene) metadata
- ✅ `get_data_slice` - Data subset extraction
- ✅ `get_all_cell_types` - Cell type enumeration

#### Components Tested:
- ✅ `CensusManager` - Census connection management
- ✅ `CellxGeneMCP` - Main server class
- ✅ Data models (`QueryResult`, `S3DataReference`, `S3TransferResult`)
- ✅ Error handling and edge cases

### 2. Integration Tests

**Purpose**: Test component interactions and data flow
**Coverage**: Tool chains, error propagation, async operations

#### Test Scenarios:
- Census data flow through multiple tools
- Error handling across tool boundaries
- Async operation coordination
- Resource management and cleanup

### 3. Protocol Tests

**Purpose**: Verify MCP protocol compliance
**Coverage**: Tool registration, resource availability, async handling

#### Protocol Verification:
- Tools properly registered with correct names
- Resources accessible via MCP protocol
- Async methods properly awaited
- Error responses follow MCP standards

### 4. Error Handling Tests

**Purpose**: Ensure robust error handling
**Coverage**: Network failures, invalid inputs, edge cases

#### Error Scenarios:
- Census connection failures
- Invalid organism parameters
- Malformed query filters
- S3 connectivity issues
- Memory and timeout conditions

## 🚀 Test Execution

### Local Development

```bash
# Quick test run
python test/run_tests.py

# Specific test types
python test/run_tests.py --type unit
python test/run_tests.py --type integration
python test/run_tests.py --coverage

# Direct pytest usage
uv run pytest test/ -v
uv run pytest test/ --cov=cellxgene_mcp
```

### Continuous Integration

**GitHub Actions Workflows**:
1. **Test Suite** - Matrix testing across Python versions
2. **MCP Protocol Tests** - Protocol compliance verification
3. **Dependency Tests** - Import and connectivity validation
4. **Code Quality** - Linting, formatting, type checking
5. **Security Scan** - Vulnerability detection

## 🎭 Mocking Strategy

### Why Mock?

- **Reliability**: Tests don't depend on external services
- **Speed**: No network calls or slow operations
- **Control**: Predictable test data and error conditions
- **Isolation**: Test individual units without dependencies

### What We Mock:

```python
# Census connections
@patch('cellxgene_mcp.server.cellxgene_census')
def test_census_functionality(mock_census):
    mock_census.get_census_version_directory.return_value = {...}
    
# S3 operations  
@patch('cellxgene_mcp.server.boto3')
def test_s3_functionality(mock_boto3):
    mock_boto3.client.return_value = Mock()
    
# Async operations
@pytest.mark.asyncio
async def test_async_tool():
    result = await server.async_tool()
```

## 📊 Coverage Goals

### Target Metrics:
- **Line Coverage**: >90%
- **Branch Coverage**: >85%  
- **Function Coverage**: >95%

### Coverage Reports:
```bash
# Generate HTML report
uv run pytest test/ --cov=cellxgene_mcp --cov-report=html

# View in browser
open htmlcov/index.html
```

## 🔍 Test Discovery

### Naming Conventions:
- **Test Files**: `test_*.py`
- **Test Classes**: `Test{ComponentName}`
- **Test Methods**: `test_{description}`
- **Async Tests**: `@pytest.mark.asyncio`

### Test Organization:
```
test/
├── conftest.py              # Pytest configuration
├── test_mcp_tools.py        # Main test suite
├── test_basic_imports.py    # Import validation
├── run_tests.py             # Test runner
├── requirements-test.txt     # Test dependencies
└── README.md                # Test documentation
```

## 🚨 Error Testing Patterns

### Exception Testing:
```python
# Test specific exceptions
with pytest.raises(ValueError) as exc_info:
    server.invalid_operation()
assert "Invalid parameter" in str(exc_info.value)

# Test error handling
try:
    result = await server.risky_operation()
except Exception as e:
    assert "Expected error" in str(e)
```

### Edge Case Testing:
```python
# Empty data
result = await server.get_metadata(limit=0)
assert result.count == 0

# Invalid parameters
with pytest.raises(ValueError):
    await server.get_data(organism="Invalid")
```

## 🔄 Continuous Testing

### Pre-commit Hooks:
- Run unit tests
- Check code formatting
- Verify type hints
- Run security scans

### Pull Request Validation:
- Full test suite execution
- Coverage reporting
- Code quality checks
- Security vulnerability scanning

### Release Validation:
- Integration test suite
- Performance benchmarks
- DXT build verification
- End-to-end workflow testing

## 📈 Test Metrics

### Success Criteria:
- ✅ All unit tests pass
- ✅ Integration tests validate workflows
- ✅ Protocol tests verify MCP compliance
- ✅ Coverage meets minimum thresholds
- ✅ Code quality checks pass
- ✅ Security scans show no critical issues

### Monitoring:
- Test execution time
- Coverage trends
- Failure patterns
- Performance regressions

## 🛠️ Debugging Tests

### Verbose Output:
```bash
# Detailed test output
python test/run_tests.py -v

# Single test execution
uv run pytest test/test_mcp_tools.py::TestMCPTools::test_get_census_info -v -s
```

### Test Isolation:
```bash
# Run specific test class
uv run pytest test/test_mcp_tools.py::TestCensusManager -v

# Run tests matching pattern
uv run pytest test/ -k "census" -v
```

## 🎯 Future Enhancements

### Planned Improvements:
1. **Performance Testing** - Benchmark tool execution times
2. **Load Testing** - Test with large datasets
3. **Concurrency Testing** - Multiple simultaneous requests
4. **Memory Testing** - Memory usage optimization
5. **API Testing** - REST endpoint validation (if applicable)

### Test Data Management:
1. **Fixture Factories** - Generate realistic test data
2. **Data Versioning** - Track test data changes
3. **Performance Baselines** - Establish performance standards
4. **Regression Detection** - Automated regression testing

## 📚 Resources

### Documentation:
- [Test Suite README](test/README.md)
- [Pytest Documentation](https://docs.pytest.org/)
- [MCP Protocol Spec](https://modelcontextprotocol.io/)

### Tools:
- **pytest** - Test framework
- **pytest-asyncio** - Async test support
- **pytest-cov** - Coverage reporting
- **pytest-mock** - Mocking utilities

### Best Practices:
- Test one thing at a time
- Use descriptive test names
- Mock external dependencies
- Test both success and failure paths
- Maintain high test coverage
- Run tests frequently

---

## 🎉 Summary

Our testing strategy provides:

1. **Comprehensive Coverage** - All MCP tools and components tested
2. **Reliable Execution** - Mocked dependencies for consistent results
3. **Continuous Validation** - Automated testing on every change
4. **Quality Assurance** - Code quality and security scanning
5. **Developer Experience** - Easy local testing and debugging
6. **Documentation** - Clear testing patterns and examples

This ensures that all MCP tools work as expected and provides confidence in the server's reliability and functionality.
