"""
Integration tests for configuration workflow.

Fast tests that don't require cluster creation.
"""
import pytest
import subprocess
import yaml
from pathlib import Path


@pytest.mark.integration
def test_generate_config_creates_valid_yaml(integration_workspace, loko_cli):
    """Test: config generate creates valid YAML file."""
    config_path = integration_workspace / "generated-config.yaml"

    result = subprocess.run(
        [loko_cli, "config", "generate", "--output", str(config_path), "--force"],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )

    assert result.returncode == 0, f"config generate failed: {result.stderr}"
    assert config_path.exists(), "Config file was not created"

    # Validate YAML structure
    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert config is not None, "Config is empty"
    assert "environment" in config, "Missing 'environment' key"
    assert "name" in config["environment"], "Missing environment name"
    assert "cluster" in config["environment"], "Missing cluster config"
    assert "provider" in config["environment"]["cluster"], "Missing provider config"


@pytest.mark.integration
def test_generate_config_with_custom_output_path(integration_workspace, loko_cli):
    """Test: config generate with custom output path."""
    custom_dir = integration_workspace / "configs"
    custom_dir.mkdir()
    config_path = custom_dir / "my-config.yaml"

    result = subprocess.run(
        [loko_cli, "config", "generate",
         "--output", str(config_path),
         "--force"],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )

    assert result.returncode == 0
    assert config_path.exists()

    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert "environment" in config
    assert config["environment"]["name"] == "dev-me"


@pytest.mark.integration
def test_generate_config_yaml_structure(integration_workspace, loko_cli):
    """Test: generated config has expected YAML structure."""
    config_path = integration_workspace / "structure-test-config.yaml"

    result = subprocess.run(
        [loko_cli, "config", "generate",
         "--output", str(config_path),
         "--force"],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )

    assert result.returncode == 0
    assert config_path.exists()

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Verify full structure (using actual defaults: dev.me domain, dev-me name)
    assert config["environment"]["network"]["domain"] == "dev.me"
    assert config["environment"]["name"] == "dev-me"
    assert config["environment"]["cluster"]["nodes"]["workers"] == 1  # Default is 1 worker
    assert config["environment"]["cluster"]["nodes"]["servers"] == 1
    assert "kubernetes" in config["environment"]["cluster"]
    assert "workloads" in config["environment"]


@pytest.mark.integration
def test_generate_config_refuses_overwrite_without_force(integration_workspace, loko_cli):
    """Test: config generate fails without --force if file exists."""
    config_path = integration_workspace / "existing-config.yaml"

    # Create initial config
    result1 = subprocess.run(
        [loko_cli, "config", "generate", "--output", str(config_path), "--force"],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )
    assert result1.returncode == 0

    # Try to overwrite without --force
    result2 = subprocess.run(
        [loko_cli, "config", "generate", "--output", str(config_path)],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )

    assert result2.returncode != 0, "Should fail without --force"
    assert "exists" in result2.stderr.lower() or "exists" in result2.stdout.lower()


@pytest.mark.integration
def test_validate_generated_config(test_config_file, loko_cli, integration_workspace):
    """Test: validate command on generated config."""
    result = subprocess.run(
        [loko_cli, "validate", "--config", str(test_config_file)],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )

    # validate command may return 0 (all valid) or 1 (warnings/missing tools)
    # Just check it doesn't crash
    assert result.returncode in [0, 1]


@pytest.mark.integration
def test_validate_nonexistent_config_fails(integration_workspace, loko_cli):
    """Test: validate command with nonexistent config file."""
    nonexistent = integration_workspace / "does-not-exist.yaml"

    result = subprocess.run(
        [loko_cli, "validate", "--config", str(nonexistent)],
        capture_output=True,
        text=True,
        cwd=integration_workspace
    )

    assert result.returncode != 0
    output = (result.stdout + result.stderr).lower()
    # Remove multiple spaces and newlines
    output_clean = " ".join(output.split())
    assert "not found" in output_clean


@pytest.mark.integration
def test_check_prerequisites_runs(loko_cli):
    """Test: check-prerequisites command executes."""
    result = subprocess.run(
        [loko_cli, "check-prerequisites"],
        capture_output=True,
        text=True
    )

    # Returns 0 if all present, 1 if some missing
    assert result.returncode in [0, 1]
    # Should output something about each tool
    output = result.stdout + result.stderr
    assert len(output) > 0
