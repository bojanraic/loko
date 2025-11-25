# Testing Guide

This document provides information about the test suite, coverage analysis, and how to run tests.

## Test Structure

The test suite uses `pytest` and is organized in the `tests/` directory:

```
tests/
├── conftest.py              # Shared fixtures (temp dirs, mock configs)
├── test_config.py           # Pydantic configuration model tests (2 tests)
├── test_generator.py        # ConfigGenerator tests (4 tests)
├── test_runner.py           # CommandRunner tests (8 tests)
├── test_utils.py            # Utility function tests (4 tests)
└── test_validators.py       # Validator function tests (7 tests)
```

**Total: 25 unit tests**

## Running Tests

### Prerequisites

Install test dependencies:

```bash
# Using uv (recommended)
uv pip install pytest pytest-cov

# Or using pip
pip install -e ".[test]"
```

### Basic Test Execution

```bash
# Run all tests
uv run pytest tests/

# Run with verbose output
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_config.py -v

# Run specific test function
uv run pytest tests/test_config.py::test_valid_config -v
```

### Coverage Reports

```bash
# Basic coverage report
uv run pytest tests/ --cov=loko

# Detailed coverage with missing lines
uv run pytest tests/ --cov=loko --cov-report=term-missing

# HTML coverage report
uv run pytest tests/ --cov=loko --cov-report=html
# Open htmlcov/index.html in browser

# Generate coverage badge data
uv run pytest tests/ --cov=loko --cov-report=json
```

### Quick Commands

```bash
# Fast: run tests without coverage
pytest tests/

# Standard: run with coverage
pytest tests/ --cov=loko --cov-report=term-missing

# Detailed: stop on first failure for debugging
pytest tests/ -x -v

# Watch mode (requires pytest-watch)
pytest-watch tests/
```

## Current Test Coverage

### Overall Statistics

- **Total Lines of Code**: ~1,703 statements
- **Lines Covered**: ~242 statements (14%)
- **Total Tests**: 25 unit tests
- **Test Status**: ✅ All passing

### Module Coverage Breakdown

| Module | Coverage | Tests | Status |
|--------|----------|-------|--------|
| `loko/config.py` | 100% | ✅ 2 tests | Excellent |
| `loko/utils.py` | 100% | ✅ 4 tests | Excellent |
| `loko/validators.py` | 71% | ⚠️ 7 tests | Good - missing edge cases |
| `loko/generator.py` | 57% | ⚠️ 4 tests | Partial - core logic only |
| `loko/runner.py` | 16% | ⚠️ 8 tests | Limited - basic methods only |
| `loko/cli/**/*.py` | 0% | ❌ No tests | CLI commands untested |
| `loko/updates/**/*.py` | 0% | ❌ No tests | Version upgrade logic untested |

### What's Tested

✅ **Well Covered (71-100%)**
- Configuration validation (Pydantic models)
- Utility functions (config loading, deep merge, env expansion)
- Validator functions (docker/config checks)

⚠️ **Partially Covered (16-57%)**
- Template generation (basic context preparation)
- Command runner (command execution, basic checks)

❌ **Not Covered (0%)**
- CLI commands (`loko/cli/commands/*.py`)
  - `lifecycle.py` (470 lines) - init, create, destroy, recreate, clean
  - `status.py` (283 lines) - status, validate
  - `config.py` (256 lines) - config upgrade, helm repo management
  - `control.py` (108 lines) - start, stop
  - `utility.py` (130 lines) - version, check-prerequisites
- Version management (`loko/updates/*.py`)
  - `upgrader.py` (131 lines) - parallel version checking
  - `fetchers.py` (174 lines) - Docker Hub and Helm API calls
  - `yaml_walker.py` (119 lines) - Renovate comment parsing
  - `parsers.py` (52 lines) - Comment syntax parsing

### Missing Test Scenarios

1. **Generator Tests** (57% coverage)
   - Template rendering for different config combinations
   - Service preset loading and merging
   - TCP routes generation
   - Helmfile generation with system and user services

2. **Runner Tests** (16% coverage)
   - Cluster creation workflow
   - Certificate setup (mkcert)
   - DNS container management
   - Service deployment (helmfile sync)
   - TCP routes deployment
   - Validation workflow
   - Secret extraction

3. **Validators Tests** (71% coverage)
   - `ensure_base_dir_writable` error cases
   - `check_base_dir_writable` with non-writable directories

4. **CLI Commands** (0% coverage)
   - All command functions are integration-tested in CI but have no unit tests
   - Configuration override logic
   - Service state management
   - Error handling and user feedback

5. **Version Management** (0% coverage)
   - Renovate comment parsing
   - Parallel version fetching
   - YAML walking and updates
   - Backup creation

## Test Quality Assessment

### Strengths

✅ **Good Practices**
- Uses proper mocking with `unittest.mock`
- Isolates external dependencies (subprocess, filesystem)
- Provides reusable fixtures in `conftest.py`
- Tests both success and failure paths
- Clear test naming conventions

✅ **Well-Structured**
- Each test file corresponds to a module
- Tests are independent and isolated
- Fixtures handle cleanup properly

### Areas for Improvement

⚠️ **Coverage Gaps**
- Only 14% overall coverage
- Core business logic in `runner.py` is mostly untested (16%)
- No tests for CLI layer or version management
- Generator tests cover only basic functionality

⚠️ **Missing Test Types**
- No integration tests (handled by CI workflow instead)
- No end-to-end tests
- No test for error conditions in complex workflows

⚠️ **Limited Assertions**
- Some tests only check method was called, not behavior
- Example: `test_generate_configs` checks files opened but not content

## Recommended Testing Priorities

To improve coverage and test quality, focus on these areas in order:

### High Priority (Core Business Logic)

1. **`loko/updates/` modules** (0% → 70%+ target)
   - Test `parsers.py` - simple string parsing, easy to test
   - Test `yaml_walker.py` - YAML traversal logic
   - Test `fetchers.py` - mock HTTP responses for Docker/Helm APIs
   - Test `upgrader.py` - orchestration and backup logic

2. **`loko/generator.py`** (57% → 85%+ target)
   - Test template rendering with various service configurations
   - Test preset loading and merging
   - Test TCP routes generation
   - Test error handling for invalid templates

3. **`loko/runner.py`** (16% → 60%+ target)
   - Test cluster lifecycle methods
   - Test DNS container management
   - Test service deployment workflow
   - Focus on business logic, not subprocess details

### Medium Priority (CLI Layer)

4. **CLI command functions** (0% → 40%+ target)
   - Test configuration override logic in `lifecycle.py`
   - Test service state management
   - Test error handling and user feedback
   - Use `typer.testing.CliRunner` for CLI testing

### Low Priority (Edge Cases)

5. **Improve existing coverage**
   - Complete validator edge cases
   - Add error path testing
   - Add integration-style tests

## CI/CD Integration

The GitHub Actions workflow (`.github/workflows/test.yml`) runs:

1. Unit tests with coverage (`pytest --cov=loko tests/`)
2. Integration tests (CLI help commands, config generation, init workflow)
3. Prerequisite checks
4. Multi-Python version testing (3.9, 3.10, 3.11, 3.12, 3.13, 3.14)

## Writing New Tests

### Example: Testing a Function

```python
# tests/test_mymodule.py
import pytest
from unittest.mock import patch, MagicMock
from loko.mymodule import my_function

@patch("loko.mymodule.external_call")
def test_my_function_success(mock_external):
    """Test my_function with successful external call."""
    mock_external.return_value = "success"
    result = my_function("input")
    assert result == "expected_output"
    mock_external.assert_called_once_with("input")

def test_my_function_failure():
    """Test my_function with invalid input."""
    with pytest.raises(ValueError, match="Invalid input"):
        my_function(None)
```

### Example: Testing CLI Commands

```python
# tests/test_cli_commands.py
from typer.testing import CliRunner
from loko.cli import app

runner = CliRunner()

def test_version_command():
    """Test loko version command."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "loko version" in result.stdout
```

## Useful pytest Options

```bash
# Stop on first failure
pytest -x

# Show test durations
pytest --durations=10

# Show local variables on failure
pytest -l

# Run only tests matching pattern
pytest -k "test_config"

# Show print statements
pytest -s

# Parallel execution (requires pytest-xdist)
pytest -n auto
```

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [unittest.mock guide](https://docs.python.org/3/library/unittest.mock.html)
- [Typer testing guide](https://typer.tiangolo.com/tutorial/testing/)
