"""
Shared fixtures for integration tests.
"""
import pytest
import shutil
import subprocess
from pathlib import Path


@pytest.fixture(scope="session")
def loko_cli():
    """Verify loko CLI is available."""
    result = subprocess.run(["loko", "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip("loko CLI not available")
    return "loko"


@pytest.fixture(scope="function")
def integration_workspace(tmp_path):
    """
    Create isolated workspace for each integration test.
    Automatically cleaned up after test completion.
    """
    workspace = tmp_path / "loko-integration"
    workspace.mkdir(parents=True, exist_ok=True)
    yield workspace
    # Cleanup happens automatically with tmp_path


@pytest.fixture(scope="function")
def test_config_file(integration_workspace):
    """Generate a test config file in the workspace."""
    config_path = integration_workspace / "test-config.yaml"
    result = subprocess.run(
        ["loko", "generate-config", "--output", str(config_path), "--force"],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )
    if result.returncode != 0:
        pytest.fail(f"Failed to generate test config: {result.stderr}")
    return config_path


@pytest.fixture(scope="function")
def docker_available():
    """Check if Docker daemon is running."""
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        timeout=5
    )
    if result.returncode != 0:
        pytest.skip("Docker daemon not running")
    return True


@pytest.fixture(scope="function")
def kind_available():
    """Check if Kind CLI is available."""
    result = subprocess.run(
        ["kind", "version"],
        capture_output=True,
        text=True,
        timeout=5
    )
    if result.returncode != 0:
        pytest.skip("Kind CLI not available")
    return True


@pytest.fixture(scope="function")
def helm_available():
    """Check if Helm CLI is available."""
    result = subprocess.run(
        ["helm", "version"],
        capture_output=True,
        text=True,
        timeout=5
    )
    if result.returncode != 0:
        pytest.skip("Helm CLI not available")
    return True


@pytest.fixture(scope="function")
def cluster_cleanup():
    """
    Fixture to ensure cluster cleanup after tests.
    Yields cluster name, then cleans up after test.
    """
    cluster_name = None

    def _set_cluster_name(name):
        nonlocal cluster_name
        cluster_name = name

    yield _set_cluster_name

    # Cleanup
    if cluster_name:
        subprocess.run(
            ["kind", "delete", "cluster", "--name", cluster_name],
            capture_output=True,
            timeout=60
        )
