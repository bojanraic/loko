"""
Integration tests for full cluster lifecycle.

Slow tests that create and destroy actual Kind clusters.
These tests require Docker, Kind, and other prerequisites.
"""
import pytest
import subprocess
import time
from pathlib import Path


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.full_cluster
@pytest.mark.requires_docker
@pytest.mark.requires_kind
def test_create_and_destroy_cluster(test_config_file, integration_workspace, loko_cli,
                                    docker_available, kind_available, cluster_cleanup):
    """Test: Full lifecycle - init → create → status → destroy."""
    # Init
    result_init = subprocess.run(
        [loko_cli, "init", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=60
    )
    assert result_init.returncode == 0, f"init failed: {result_init.stderr}"

    # Register for cleanup
    cluster_cleanup("dev-me")

    # Create cluster
    result_create = subprocess.run(
        [loko_cli, "create", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=600  # 10 minutes for cluster creation
    )
    assert result_create.returncode == 0, f"create failed: {result_create.stderr}"

    # Verify cluster exists via kind
    result_kind_get = subprocess.run(
        ["kind", "get", "clusters"],
        capture_output=True,
        text=True,
        timeout=30
    )
    assert "dev-me" in result_kind_get.stdout, "Cluster not found in kind list"

    # Status check
    result_status = subprocess.run(
        [loko_cli, "status", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=60
    )
    assert result_status.returncode == 0, f"status failed: {result_status.stderr}"

    # Destroy cluster
    result_destroy = subprocess.run(
        [loko_cli, "destroy", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=120
    )
    assert result_destroy.returncode == 0, f"destroy failed: {result_destroy.stderr}"

    # Verify cluster no longer exists
    result_kind_check = subprocess.run(
        ["kind", "get", "clusters"],
        capture_output=True,
        text=True,
        timeout=30
    )
    assert "dev-me" not in result_kind_check.stdout, "Cluster still exists after destroy"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.full_cluster
@pytest.mark.requires_docker
@pytest.mark.requires_kind
def test_create_auto_runs_init(test_config_file, integration_workspace, loko_cli,
                                docker_available, kind_available, cluster_cleanup):
    """Test: create automatically runs init if not already done."""
    # Register for cleanup
    cluster_cleanup("dev-me")

    # Create should succeed even without explicit init
    result = subprocess.run(
        [loko_cli, "create", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=600  # Full cluster creation timeout
    )

    # Should succeed because create auto-runs init
    assert result.returncode == 0, f"create failed: {result.stderr}"

    # Cleanup
    subprocess.run(
        [loko_cli, "destroy", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=120
    )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.full_cluster
@pytest.mark.requires_docker
@pytest.mark.requires_kind
def test_stop_and_start_cluster(test_config_file, integration_workspace, loko_cli,
                                docker_available, kind_available, cluster_cleanup):
    """Test: create → stop → start workflow."""
    # Init and create
    subprocess.run(
        [loko_cli, "init", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=60
    )

    cluster_cleanup("dev-me")

    result_create = subprocess.run(
        [loko_cli, "create", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=600
    )
    assert result_create.returncode == 0

    # Stop cluster
    result_stop = subprocess.run(
        [loko_cli, "stop", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=120
    )
    assert result_stop.returncode == 0, f"stop failed: {result_stop.stderr}"

    # Start cluster
    result_start = subprocess.run(
        [loko_cli, "start", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=120
    )
    assert result_start.returncode == 0, f"start failed: {result_start.stderr}"

    # Verify cluster is running
    result_status = subprocess.run(
        [loko_cli, "status", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=60
    )
    assert result_status.returncode == 0

    # Cleanup
    subprocess.run(
        [loko_cli, "destroy", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=120
    )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.full_cluster
@pytest.mark.requires_docker
@pytest.mark.requires_kind
def test_recreate_cluster(test_config_file, integration_workspace, loko_cli,
                         docker_available, kind_available, cluster_cleanup):
    """Test: create → recreate workflow."""
    # Init and create
    subprocess.run(
        [loko_cli, "init", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=60
    )

    cluster_cleanup("dev-me")

    result_create = subprocess.run(
        [loko_cli, "create", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=600
    )
    assert result_create.returncode == 0

    # Recreate cluster
    result_recreate = subprocess.run(
        [loko_cli, "recreate", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=600
    )
    assert result_recreate.returncode == 0, f"recreate failed: {result_recreate.stderr}"

    # Verify cluster still exists
    result_kind_get = subprocess.run(
        ["kind", "get", "clusters"],
        capture_output=True,
        text=True,
        timeout=30
    )
    assert "dev-me" in result_kind_get.stdout

    # Cleanup
    subprocess.run(
        [loko_cli, "destroy", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=120
    )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.full_cluster
@pytest.mark.requires_docker
@pytest.mark.requires_kind
def test_status_nonexistent_cluster(test_config_file, integration_workspace, loko_cli,
                                    docker_available, kind_available):
    """Test: status command for non-existent cluster."""
    # Init but don't create
    subprocess.run(
        [loko_cli, "init", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=60
    )

    result = subprocess.run(
        [loko_cli, "status", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=60
    )

    # Status should report cluster doesn't exist
    # Exit code could be 0 with message, or non-zero
    output = result.stdout + result.stderr
    assert "not found" in output.lower() or "does not exist" in output.lower() or "not running" in output.lower()


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.full_cluster
@pytest.mark.requires_docker
@pytest.mark.requires_kind
def test_destroy_nonexistent_cluster(test_config_file, integration_workspace, loko_cli,
                                     docker_available, kind_available):
    """Test: destroy command for non-existent cluster."""
    # Init but don't create
    subprocess.run(
        [loko_cli, "init", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=60
    )

    result = subprocess.run(
        [loko_cli, "destroy", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace,
        timeout=60
    )

    # Should handle gracefully (either succeed with message or fail cleanly)
    # Just verify it doesn't crash
    assert result.returncode in [0, 1]
