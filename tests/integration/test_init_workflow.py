"""
Integration tests for init workflow.

Fast tests that generate configuration but don't create clusters.
"""
import pytest
import subprocess
import yaml
from pathlib import Path


@pytest.mark.integration
def test_init_generates_cluster_config(test_config_file, integration_workspace, loko_cli):
    """Test: init generates Kind cluster.yaml."""
    loko_dir = integration_workspace / ".loko"

    result = subprocess.run(
        [loko_cli, "init",
         "--config", str(test_config_file),
         "--base-dir", str(loko_dir)],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )

    assert result.returncode == 0, f"init failed: {result.stderr}\n{result.stdout}"

    # Verify cluster config exists
    cluster_config = loko_dir / "dev-me/config/cluster.yaml"
    assert cluster_config.exists(), f"cluster.yaml not generated at {cluster_config}"

    # Validate cluster config structure
    with open(cluster_config) as f:
        config = yaml.safe_load(f)

    assert config is not None
    assert "kind" in config
    assert config["kind"] == "Cluster"


@pytest.mark.integration
def test_init_generates_helmfile(test_config_file, integration_workspace, loko_cli):
    """Test: init generates helmfile.yaml."""
    loko_dir = integration_workspace / ".loko"

    result = subprocess.run(
        [loko_cli, "init",
         "--config", str(test_config_file),
         "--base-dir", str(loko_dir)],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )

    assert result.returncode == 0

    # Verify helmfile exists
    helmfile = loko_dir / "dev-me/config/helmfile.yaml"
    assert helmfile.exists(), f"helmfile.yaml not generated at {helmfile}"

    # Validate helmfile structure
    with open(helmfile) as f:
        config = yaml.safe_load(f)

    assert config is not None
    # Helmfile should have repositories and/or releases
    assert "repositories" in config or "releases" in config


@pytest.mark.integration
def test_init_generates_dnsmasq_config(test_config_file, integration_workspace, loko_cli):
    """Test: init generates dnsmasq.conf."""
    loko_dir = integration_workspace / ".loko"

    result = subprocess.run(
        [loko_cli, "init",
         "--config", str(test_config_file),
         "--base-dir", str(loko_dir)],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )

    assert result.returncode == 0

    # Verify dnsmasq config exists
    dnsmasq_conf = loko_dir / "dev-me/config/dnsmasq.conf"
    assert dnsmasq_conf.exists(), f"dnsmasq.conf not generated at {dnsmasq_conf}"

    # Validate dnsmasq config content
    content = dnsmasq_conf.read_text()
    assert len(content) > 0
    assert "address=" in content  # dnsmasq address directive


@pytest.mark.integration
def test_init_with_custom_output_location(integration_workspace, loko_cli):
    """Test: init creates files in correct location using --base-dir."""
    config_path = integration_workspace / "test-config.yaml"
    loko_dir = integration_workspace / ".loko"

    # Generate config
    subprocess.run(
        [loko_cli, "generate-config",
         "--output", str(config_path),
         "--force"],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )

    # Run init with custom base-dir
    result = subprocess.run(
        [loko_cli, "init",
         "--config", str(config_path),
         "--base-dir", str(loko_dir)],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )

    assert result.returncode == 0

    # Verify files created in specified base-dir
    config_dir = loko_dir / "dev-me/config"
    assert config_dir.exists()
    assert (config_dir / "cluster.yaml").exists()


@pytest.mark.integration
def test_init_idempotent(test_config_file, integration_workspace, loko_cli):
    """Test: init can run multiple times without error."""
    loko_dir = integration_workspace / ".loko"

    # First init
    result1 = subprocess.run(
        [loko_cli, "init",
         "--config", str(test_config_file),
         "--base-dir", str(loko_dir)],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )
    assert result1.returncode == 0

    # Second init (should succeed or be idempotent)
    result2 = subprocess.run(
        [loko_cli, "init",
         "--config", str(test_config_file),
         "--base-dir", str(loko_dir)],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )
    assert result2.returncode == 0


@pytest.mark.integration
def test_init_creates_directory_structure(test_config_file, integration_workspace, loko_cli):
    """Test: init creates expected directory structure."""
    loko_dir = integration_workspace / ".loko"

    result = subprocess.run(
        [loko_cli, "init",
         "--config", str(test_config_file),
         "--base-dir", str(loko_dir)],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )

    assert result.returncode == 0

    env_dir = loko_dir / "dev-me"
    config_subdir = env_dir / "config"

    assert loko_dir.exists()
    assert loko_dir.is_dir()
    assert env_dir.exists()
    assert env_dir.is_dir()
    assert config_subdir.exists()
    assert config_subdir.is_dir()
    assert (config_subdir / "containerd").exists()
    assert (config_subdir / "containerd").is_dir()


@pytest.mark.integration
def test_init_without_config_fails(integration_workspace, loko_cli):
    """Test: init without config file fails with helpful message."""
    result = subprocess.run(
        [loko_cli, "init"],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )

    assert result.returncode != 0
    # Should mention config file or loko.yaml
    output = result.stdout + result.stderr
    assert "config" in output.lower() or "loko.yaml" in output.lower()


@pytest.mark.integration
def test_init_with_nonexistent_config_fails(integration_workspace, loko_cli):
    """Test: init with nonexistent config fails."""
    nonexistent = integration_workspace / "does-not-exist.yaml"

    result = subprocess.run(
        [loko_cli, "init", "--config", str(nonexistent)],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )

    assert result.returncode != 0
    output = (result.stdout + result.stderr).lower()
    # Remove multiple spaces and newlines
    output_clean = " ".join(output.split())
    assert "not found" in output_clean
