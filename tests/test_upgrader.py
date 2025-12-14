import pytest
import os
from unittest.mock import patch, MagicMock, mock_open
from loko.updates.upgrader import upgrade_config


@pytest.fixture
def sample_config_with_renovate(temp_dir):
    """Create a sample config file with renovate comments."""
    config_path = os.path.join(temp_dir, "loko.yaml")
    config_content = """environment:
  kubernetes:
    image: kindest/node
    # renovate: datasource=docker depName=kindest/node
    tag: v1.32.0
  internal-components:
    # renovate: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts
    - traefik: "31.0.0"
"""
    with open(config_path, 'w') as f:
        f.write(config_content)
    return config_path


@patch('loko.updates.upgrader.fetch_latest_helm_versions_batch')
@patch('loko.updates.upgrader.fetch_latest_version')
@patch('shutil.copy')
def test_upgrade_config_with_updates(mock_copy, mock_fetch, mock_fetch_batch, sample_config_with_renovate):
    """Test upgrading config when updates are available."""
    # Mock version fetching to return newer versions
    def fetch_side_effect(renovate_info):
        if renovate_info['depName'] == 'kindest/node':
            return ("v1.34.0", 0.5)
        elif renovate_info['depName'] == 'traefik':
            return ("37.3.0", 1.2)
        return (None, 0.0)

    mock_fetch.side_effect = fetch_side_effect

    # Mock batch fetching for Helm charts
    def batch_fetch_side_effect(repo_url, dep_names):
        results = {}
        for dep_name in dep_names:
            if dep_name == 'traefik':
                results[dep_name] = ("37.3.0", 1.2)
        return results

    mock_fetch_batch.side_effect = batch_fetch_side_effect

    upgrade_config(sample_config_with_renovate)

    # Verify backup was created
    mock_copy.assert_called_once()

    # Verify updated values in the file
    with open(sample_config_with_renovate, 'r') as f:
        content = f.read()
        assert 'v1.34.0' in content
        assert '37.3.0' in content
        # Old values should be replaced
        assert 'v1.32.0' not in content
        assert '31.0.0' not in content


@patch('loko.updates.upgrader.fetch_latest_helm_versions_batch')
@patch('loko.updates.upgrader.fetch_latest_version')
def test_upgrade_config_no_updates(mock_fetch, mock_fetch_batch, sample_config_with_renovate):
    """Test upgrading config when no updates available."""
    # Mock version fetching to return same versions
    def fetch_side_effect(renovate_info):
        if renovate_info['depName'] == 'kindest/node':
            return ("v1.32.0", 0.5)
        elif renovate_info['depName'] == 'traefik':
            return ("31.0.0", 1.2)
        return (None, 0.0)

    mock_fetch.side_effect = fetch_side_effect

    # Mock batch fetching to return current versions (no updates)
    def batch_fetch_side_effect(repo_url, dep_names):
        results = {}
        for dep_name in dep_names:
            if dep_name == 'traefik':
                results[dep_name] = ("31.0.0", 1.2)
        return results

    mock_fetch_batch.side_effect = batch_fetch_side_effect

    with patch('shutil.copy') as mock_copy:
        upgrade_config(sample_config_with_renovate)

        # No backup should be created if no updates
        mock_copy.assert_not_called()


@patch('loko.updates.upgrader.fetch_latest_helm_versions_batch')
@patch('loko.updates.upgrader.fetch_latest_version')
def test_upgrade_config_partial_updates(mock_fetch, mock_fetch_batch, sample_config_with_renovate):
    """Test upgrading config when only some components have updates."""
    # Mock one component with update, one without
    def fetch_side_effect(renovate_info):
        if renovate_info['depName'] == 'kindest/node':
            return ("v1.34.0", 0.5)  # Update available
        elif renovate_info['depName'] == 'traefik':
            return ("31.0.0", 1.2)  # Same version
        return (None, 0.0)

    mock_fetch.side_effect = fetch_side_effect

    # Mock batch fetching to return current version (no update)
    def batch_fetch_side_effect(repo_url, dep_names):
        results = {}
        for dep_name in dep_names:
            if dep_name == 'traefik':
                results[dep_name] = ("31.0.0", 1.2)
        return results

    mock_fetch_batch.side_effect = batch_fetch_side_effect

    with patch('shutil.copy') as mock_copy:
        upgrade_config(sample_config_with_renovate)

        # Backup should be created
        mock_copy.assert_called_once()

        # Verify k8s version updated but traefik unchanged
        with open(sample_config_with_renovate, 'r') as f:
            content = f.read()
            assert 'v1.34.0' in content
            assert '31.0.0' in content


@patch('loko.updates.upgrader.fetch_latest_version')
def test_upgrade_config_fetch_error(mock_fetch, sample_config_with_renovate):
    """Test upgrading config when fetch fails for some components."""
    # Mock one success, one failure
    def fetch_side_effect(renovate_info):
        if renovate_info['depName'] == 'kindest/node':
            return ("v1.34.0", 0.5)
        elif renovate_info['depName'] == 'traefik':
            raise Exception("Network error")
        return (None, 0.0)

    mock_fetch.side_effect = fetch_side_effect

    with patch('shutil.copy') as mock_copy:
        # Should not crash, should handle error gracefully
        upgrade_config(sample_config_with_renovate)

        # Should still create backup for successful update
        mock_copy.assert_called_once()


def test_upgrade_config_no_renovate_comments(temp_dir):
    """Test upgrading config with no renovate comments."""
    config_path = os.path.join(temp_dir, "loko.yaml")
    config_content = """environment:
  kubernetes:
    image: kindest/node
    tag: v1.32.0
"""
    with open(config_path, 'w') as f:
        f.write(config_content)

    with patch('shutil.copy') as mock_copy:
        upgrade_config(config_path)

        # No backup should be created
        mock_copy.assert_not_called()


@patch('loko.updates.upgrader.fetch_latest_version')
@patch('shutil.copy')
def test_upgrade_config_preserves_comments(mock_copy, mock_fetch, sample_config_with_renovate):
    """Test that upgrade preserves YAML comments and formatting."""
    mock_fetch.return_value = ("v1.34.0", 0.5)

    # Read original for comparison
    with open(sample_config_with_renovate, 'r') as f:
        original = f.read()

    upgrade_config(sample_config_with_renovate)

    # Read updated config
    with open(sample_config_with_renovate, 'r') as f:
        updated = f.read()

    # Renovate comments should still be present
    assert '# renovate: datasource=docker' in updated
    assert '# renovate: datasource=helm' in updated


@patch('loko.updates.upgrader.fetch_latest_version')
def test_upgrade_config_backup_filename(mock_fetch, sample_config_with_renovate):
    """Test that backup filename is correct."""
    mock_fetch.return_value = ("v1.34.0", 0.5)

    with patch('shutil.copy') as mock_copy:
        upgrade_config(sample_config_with_renovate)

        # Check backup filename
        backup_path = sample_config_with_renovate.replace('.yaml', '-prev.yaml')
        mock_copy.assert_called_once_with(sample_config_with_renovate, backup_path)


def test_upgrade_config_invalid_file():
    """Test handling invalid config file."""
    with pytest.raises(SystemExit):
        upgrade_config("/nonexistent/config.yaml")


@patch('loko.updates.upgrader.fetch_latest_helm_versions_batch')
@patch('loko.updates.upgrader.fetch_latest_version')
@patch('shutil.copy')
def test_upgrade_config_multiple_components(mock_copy, mock_fetch, mock_fetch_batch, temp_dir):
    """Test upgrading config with multiple components."""
    config_path = os.path.join(temp_dir, "loko.yaml")
    config_content = """environment:
  kubernetes:
    image: kindest/node
    # renovate: datasource=docker depName=kindest/node
    tag: v1.32.0
  internal-components:
    # renovate: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts
    - traefik: "31.0.0"
    # renovate: datasource=helm depName=metrics-server repositoryUrl=https://kubernetes-sigs.github.io/metrics-server
    - metrics-server: "3.10.0"
  services:
    system:
      - name: mysql
        config:
          chart: groundhog2k/mysql
          # renovate: datasource=helm depName=mysql repositoryUrl=https://groundhog2k.github.io/helm-charts
          version: 3.0.5
"""
    with open(config_path, 'w') as f:
        f.write(config_content)

    # Mock different versions for different components
    def fetch_side_effect(renovate_info):
        versions = {
            'kindest/node': ("v1.34.0", 0.5),
            'traefik': ("37.3.0", 1.0),
            'metrics-server': ("3.12.0", 0.8),
            'mysql': ("3.0.7", 1.2)
        }
        return versions.get(renovate_info['depName'], (None, 0.0))

    mock_fetch.side_effect = fetch_side_effect

    # Mock batch fetching for Helm charts
    def batch_fetch_side_effect(repo_url, dep_names):
        results = {}
        version_map = {
            'traefik': ("37.3.0", 1.0),
            'metrics-server': ("3.12.0", 0.8),
            'mysql': ("3.0.7", 1.2)
        }
        for dep_name in dep_names:
            if dep_name in version_map:
                results[dep_name] = version_map[dep_name]
        return results

    mock_fetch_batch.side_effect = batch_fetch_side_effect

    upgrade_config(config_path)

    # Verify all components updated
    with open(config_path, 'r') as f:
        content = f.read()
        assert 'v1.34.0' in content
        assert '37.3.0' in content
        assert '3.12.0' in content
        assert '3.0.7' in content


@patch('loko.updates.upgrader.fetch_latest_version')
@patch('shutil.copy')
def test_upgrade_config_timing_metrics(mock_copy, mock_fetch, sample_config_with_renovate, capsys):
    """Test that timing metrics are displayed."""
    # Mock with specific timing values
    def fetch_side_effect(renovate_info):
        if renovate_info['datasource'] == 'docker':
            return ("v1.34.0", 0.5)
        elif renovate_info['datasource'] == 'helm':
            return ("37.3.0", 1.5)
        return (None, 0.0)

    mock_fetch.side_effect = fetch_side_effect

    upgrade_config(sample_config_with_renovate)

    # Check that timing info is in output
    captured = capsys.readouterr()
    assert 'fetch time' in captured.out.lower()
