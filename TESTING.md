# Testing Guide

This document provides information about the test suite, coverage analysis, and how to run tests.

## Test Structure

The test suite uses `pytest` and is organized in the `tests/` directory with two main categories:

### Unit Tests

```
tests/
├── conftest.py              # Shared fixtures (temp dirs, mock configs)
├── test_cli.py              # CLI command tests (13 tests)
├── test_config.py           # Pydantic configuration model tests (2 tests)
├── test_generator.py        # ConfigGenerator tests (19 tests)
├── test_runner.py           # CommandRunner tests (12 tests)
├── test_utils.py            # Utility function tests (4 tests)
├── test_validators.py       # Validator function tests (11 tests)
├── test_parsers.py          # Renovate comment parsing tests (11 tests)
├── test_yaml_walker.py      # YAML walking logic tests (9 tests)
├── test_fetchers.py         # Version fetching tests (15 tests)
└── test_upgrader.py         # Config upgrade workflow tests (10 tests)
```

**Total: 105 unit tests**

### Integration Tests

```
tests/integration/
├── conftest.py                    # Integration test fixtures
├── test_config_workflow.py        # Config generation tests (9 tests)
├── test_init_workflow.py          # Init workflow tests (9 tests)
└── test_cluster_lifecycle.py      # Full cluster tests (7 tests)
```

**Total: 25 integration tests**

## Running Tests

### Prerequisites

#### Option 1: Using mise (Recommended)

[mise](https://mise.jdx.dev/) automatically installs all required tools and dependencies:

```bash
# Install mise (https://mise.jdx.dev/getting-started.html)
curl https://mise.run | sh

# Install all tools and dependencies
mise install

# Install loko in development mode
mise run install

# Verify all tools are available
mise list
loko check-prerequisites
```

#### Option 2: Manual Installation

Install test dependencies manually:

```bash
# Using uv (recommended)
uv pip install pytest pytest-cov pytest-timeout

# Or using pip
pip install -e ".[test]"

# For integration tests, also install:
# - kind (https://kind.sigs.k8s.io/)
# - kubectl (https://kubernetes.io/docs/tasks/tools/)
# - helm (https://helm.sh/docs/intro/install/)
# - helmfile (https://helmfile.readthedocs.io/)
# - mkcert (https://github.com/FiloSottile/mkcert)
```

### Test Execution by Type

#### Using mise Tasks (Recommended)

```bash
# Run unit tests with coverage
mise run test-unit

# Run fast integration tests (no cluster creation)
mise run test-integration-fast

# Run full integration tests (includes cluster creation)
mise run test-integration-full

# Run all tests
mise run test-all
```

#### Using pytest Directly

**Unit Tests Only (Fast - No External Dependencies)**

```bash
# Run all unit tests (exclude integration tests)
pytest -m "not integration"

# Run with coverage
pytest -m "not integration" --cov=loko --cov-report=term-missing

# Run specific unit test file
pytest tests/test_config.py -v
```

**Integration Tests**

```bash
# Run ALL integration tests (requires Docker, Kind, etc.)
pytest -m integration

# Run ONLY fast integration tests (no cluster creation)
pytest -m "integration and not full_cluster"

# Run ONLY slow integration tests (full cluster lifecycle)
pytest -m "integration and full_cluster"

# Run specific integration test file
pytest tests/integration/test_config_workflow.py -v
```

**All Tests**

```bash
# Run everything (unit + integration)
pytest

# Run all with verbose output
pytest -v

# Run specific test function
pytest tests/test_config.py::test_valid_config -v
```

### Coverage Reports

```bash
# Basic coverage report (unit tests only)
pytest -m "not integration" --cov=loko

# Detailed coverage with missing lines
pytest -m "not integration" --cov=loko --cov-report=term-missing

# HTML coverage report
pytest -m "not integration" --cov=loko --cov-report=html
# Open htmlcov/index.html in browser

# Multiple formats at once
pytest -m "not integration" --cov=loko --cov-report=term --cov-report=html --cov-report=xml
```

### Quick Commands

```bash
# Fast: unit tests only, no coverage
pytest -m "not integration"

# Standard: unit tests with coverage
pytest -m "not integration" --cov=loko --cov-report=term-missing

# Full: all tests including integration
pytest

# Debug: stop on first failure
pytest -x -v

# Watch mode (requires pytest-watch)
pytest-watch -m "not integration"
```

## Test Markers and Selection

The test suite uses pytest markers for selective test execution:

| Marker | Description | Usage |
|--------|-------------|-------|
| `integration` | Integration tests requiring real tools | `-m integration` |
| `slow` | Tests that take >30s to run | `-m slow` |
| `full_cluster` | Tests that create real Kind clusters | `-m "full_cluster"` |
| `requires_docker` | Requires Docker daemon running | `-m requires_docker` |
| `requires_kind` | Requires Kind CLI installed | `-m requires_kind` |
| `requires_helm` | Requires Helm CLI installed | `-m requires_helm` |

### Example Marker Combinations

```bash
# All integration tests except cluster creation
pytest -m "integration and not full_cluster"

# Only slow tests
pytest -m slow

# Fast tests only (excludes slow and integration)
pytest -m "not slow and not integration"
```

## Current Test Coverage

### Overall Statistics

- **Total Lines of Code**: ~1,703 statements
- **Lines Covered**: ~715 statements (42%)
- **Unit Tests**: 105 tests
- **Integration Tests**: 25 tests
- **Test Status**: ✅ All passing

### Module Coverage Breakdown

| Module | Coverage | Tests | Status |
|--------|----------|-------|--------|
| `loko/config.py` | 100% | ✅ 2 tests | Excellent |
| `loko/utils.py` | 100% | ✅ 4 tests | Excellent |
| `loko/cli_types.py` | 100% | ✅ Imported by CLI tests | Excellent |
| `loko/updates/parsers.py` | 100% | ✅ 11 tests | Excellent |
| `loko/updates/yaml_walker.py` | 100% | ✅ 9 tests | Excellent |
| `loko/updates/upgrader.py` | 97% | ✅ 10 tests | Excellent |
| `loko/validators.py` | 96% | ✅ 11 tests | Excellent |
| `loko/updates/fetchers.py` | 92% | ✅ 15 tests | Very Good |
| `loko/cli/__init__.py` | 72% | ✅ 13 tests | Good |
| `loko/generator.py` | 67% | ✅ 19 tests | Good |
| `loko/runner.py` | 16% | ⚠️ 12 tests | Limited - integration-heavy |
| `loko/cli/commands/*.py` | 0% | ⚠️ Integration tested | CLI commands - integration-heavy |

### What's Tested

✅ **Excellent Coverage (90-100%)** - Business Logic
- Configuration validation (Pydantic models)
- Utility functions (config loading, deep merge, env expansion)
- Validator functions (docker/config checks)
- Renovate comment parsing (Docker, Helm datasources)
- YAML traversal with comment preservation
- Parallel version fetching (Docker Hub, Helm repos)
- Config upgrade workflow with backups

✅ **Good Coverage (67-72%)** - Core Functionality
- CLI commands (help, version, basic invocation)
- Template generation (context prep, auth config)

⚠️ **Limited Coverage (16%)** - Integration-Heavy Code
- Command runner (orchestrates external tools: Kind, kubectl, Helm)
- Note: These are tested via integration tests in CI

⚠️ **Not Covered (0%)** - Integration Commands
- CLI command implementations in `loko/cli/commands/`
- Note: Full workflows tested via integration tests

## Integration Test Coverage

The integration test suite validates end-to-end workflows:

### Fast Integration Tests (No Cluster Creation)

**`test_config_workflow.py`** - 9 tests
- Config generation with custom options (name, domain, workers)
- Validation of generated YAML structure
- Overwrite protection without --force flag
- Config validation command
- Error handling for missing files

**`test_init_workflow.py`** - 9 tests
- Cluster config generation (cluster.yaml)
- Helmfile generation
- dnsmasq config generation
- Custom environment names
- Idempotent init operations
- Directory structure creation
- Error handling for missing prerequisites

### Slow Integration Tests (Full Cluster Lifecycle)

**`test_cluster_lifecycle.py`** - 7 tests
- Full lifecycle: init → create → status → destroy
- Stop and start workflows
- Cluster recreation
- Status checks for non-existent clusters
- Graceful error handling

### CI/CD Integration Test Flow

```
1. Unit Tests (All Python versions: 3.9-3.14)
   └─> Run: pytest -m "not integration"

2. Fast Integration Tests (Python 3.12 only)
   └─> Run: pytest -m "integration and not full_cluster"
   └─> Prerequisites: None (just loko CLI)

3. Full Integration Tests (Python 3.12 only)
   └─> Run: pytest -m "integration and full_cluster"
   └─> Prerequisites: Docker, Kind, kubectl, Helm, mkcert
   └─> Timeout: 30 minutes
   └─> Cleanup: Delete all Kind clusters after tests
```

## Test Quality Assessment

### Strengths

✅ **Unit Tests - Good Practices**
- Uses proper mocking with `unittest.mock`
- Isolates external dependencies (subprocess, filesystem, HTTP)
- Provides reusable fixtures in `conftest.py`
- Tests both success and failure paths
- Clear test naming conventions
- 100% coverage on core business logic (parsers, validators, utils)

✅ **Integration Tests - Comprehensive Coverage**
- Tests real CLI workflows without mocking
- Fast tests run without external dependencies
- Slow tests validate full cluster lifecycle
- Proper cleanup using fixtures and Kind cluster deletion
- Isolated workspaces prevent test interference
- Selective execution via pytest markers

✅ **Well-Structured**
- Each test file corresponds to a module
- Tests are independent and isolated
- Fixtures handle cleanup properly
- Separation between unit and integration tests
- CI/CD pipeline runs tests in appropriate order

### Testing Philosophy

The test suite follows a **layered testing strategy**:

1. **Unit Tests (42% overall coverage)** - Fast, isolated, mock external dependencies
   - Target: 90-100% coverage on pure business logic
   - Current: Achieved for parsers, validators, utils, upgrades
   - Integration-heavy code (runner.py, CLI commands) has lower coverage by design

2. **Integration Tests (25 tests)** - Validate real workflows with actual tools
   - Fast tests: Config generation, init workflow (no prerequisites)
   - Slow tests: Full cluster lifecycle (requires Docker, Kind, etc.)
   - CI/CD: Runs on every push with full prerequisites installed

### Why Not 100% Unit Test Coverage?

Some code is **integration-heavy** and benefits more from integration tests:

- **`runner.py` (16% unit coverage)**: Orchestrates external tools (Kind, kubectl, Helm)
  - Unit testing would mock away the actual behavior being tested
  - Integration tests provide better validation of real workflows

- **`loko/cli/commands/*.py` (0% unit coverage)**: Complex CLI workflows
  - These call runner.py methods and orchestrate multiple operations
  - Integration tests validate full user workflows end-to-end

**Result**: 42% unit coverage + comprehensive integration coverage = appropriate testing strategy

## CI/CD Integration

The GitHub Actions workflow (`.github/workflows/test.yml`) uses **mise** to automatically install all prerequisites.

### Jobs

#### 1. Unit Tests Job
- **Runs on**: All Python versions (3.9, 3.10, 3.11, 3.12, 3.13, 3.14)
- **Triggers**: Every push and pull request
- **Command**: `pytest -m "not integration" --cov=loko --cov-report=term --cov-report=html --cov-report=xml`
- **Duration**: ~2-5 minutes per Python version
- **Artifacts**: Coverage reports (HTML, XML, .coverage) uploaded for each Python version
- **Retention**: 30 days

#### 2. Fast Integration Tests Job
- **Runs on**: Python 3.12 only
- **Triggers**: Every push and pull request
- **Depends on**: Unit tests must pass first
- **Tool Setup**: Uses [mise-action](https://github.com/jdx/mise-action) to install all tools:
  - kind 0.30.0
  - kubectl 1.34.2
  - helm 4.0.1
  - helmfile 1.2.1
  - mkcert 1.4.4
  - yq 4.49.2, jq 1.8.1 (utilities)
- **Command**: `mise run test-integration-fast` - Tests without cluster creation
- **Duration**: ~1-3 minutes
- **Artifacts**: Integration test results (.pytest_cache, htmlcov)
- **Retention**: 7 days

#### 3. Full Integration Tests Job
- **Runs on**: Python 3.12 only
- **Triggers**: Only on `main` branch or tags (e.g., `v1.0.0`)
- **Depends on**: Unit tests must pass first
- **Tool Setup**: Same as fast integration tests
- **Command**: `mise run test-integration-full` - Full cluster lifecycle tests
- **Duration**: ~10-30 minutes (cluster creation takes time)
- **Timeout**: 30 minutes
- **Artifacts**: Full integration test results (.pytest_cache, htmlcov)
- **Retention**: 7 days
- **Cleanup**: Deletes all Kind clusters after completion

### Workflow Benefits with mise

✅ **Simplified Setup**: One action installs all tools (no manual curl/install steps)
✅ **Version Pinning**: Tool versions defined in `.mise.toml` ensure reproducibility
✅ **Caching**: mise-action caches tool installations for faster CI runs
✅ **Local/CI Parity**: Same tool versions used locally and in CI
✅ **Easy Updates**: Update tool versions in one place (`.mise.toml`)

### Workflow Optimization

- **Unit tests** run in parallel across 6 Python versions (all PRs/pushes)
- **Fast integration tests** run on every PR/push (quick feedback)
- **Full integration tests** run only on `main` or tags (save CI resources)
- mise caching speeds up tool installation
- Artifacts uploaded with appropriate retention periods

### Test Execution Matrix

| Event Type | Unit Tests | Fast Integration | Full Integration |
|------------|-----------|------------------|------------------|
| PR to any branch | ✅ All Python versions | ✅ Python 3.12 | ❌ Skipped |
| Push to `develop` | ✅ All Python versions | ✅ Python 3.12 | ❌ Skipped |
| Push to `main` | ✅ All Python versions | ✅ Python 3.12 | ✅ Python 3.12 |
| Tag (e.g., `v1.0.0`) | ✅ All Python versions | ✅ Python 3.12 | ✅ Python 3.12 |

## Writing New Tests

### Unit Test Example

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

### Integration Test Example

```python
# tests/integration/test_my_workflow.py
import pytest
import subprocess

@pytest.mark.integration
def test_my_workflow(integration_workspace, loko_cli, test_config_file):
    """Test my workflow end-to-end."""
    result = subprocess.run(
        [loko_cli, "my-command", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=60
    )
    assert result.returncode == 0
    assert "success" in result.stdout

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.full_cluster
@pytest.mark.requires_docker
@pytest.mark.requires_kind
def test_full_cluster_workflow(integration_workspace, loko_cli, test_config_file,
                                docker_available, kind_available, cluster_cleanup):
    """Test full cluster creation workflow."""
    cluster_cleanup("dev-me")  # Register for cleanup

    # Your test code here
    result = subprocess.run(
        [loko_cli, "create", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=600
    )
    assert result.returncode == 0
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
