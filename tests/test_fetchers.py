import pytest
from unittest.mock import patch, MagicMock
from loko.updates.fetchers import (
    fetch_latest_docker_version,
    fetch_latest_helm_version,
    fetch_latest_version
)


@patch('urllib.request.urlopen')
def test_fetch_latest_docker_version_official_image(mock_urlopen):
    """Test fetching Docker version for official image (no slash)."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'''{
        "results": [
            {"name": "v1.34.0"},
            {"name": "v1.33.2"},
            {"name": "latest"}
        ]
    }'''
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    version, elapsed = fetch_latest_docker_version("node")

    assert version == "v1.34.0"
    assert elapsed >= 0
    assert "library/node" in mock_urlopen.call_args[0][0].full_url


@patch('urllib.request.urlopen')
def test_fetch_latest_docker_version_user_image(mock_urlopen):
    """Test fetching Docker version for user/org image."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'''{
        "results": [
            {"name": "v1.34.0"},
            {"name": "v1.33.2"}
        ]
    }'''
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    version, elapsed = fetch_latest_docker_version("kindest/node")

    assert version == "v1.34.0"
    assert elapsed >= 0
    assert "kindest/node" in mock_urlopen.call_args[0][0].full_url


@patch('urllib.request.urlopen')
def test_fetch_latest_docker_version_filters_invalid_tags(mock_urlopen):
    """Test that invalid tags like 'latest', 'dev' are filtered."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'''{
        "results": [
            {"name": "latest"},
            {"name": "nightly"},
            {"name": "dev"},
            {"name": "v1.34.0"},
            {"name": "v1.33.2"}
        ]
    }'''
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    version, elapsed = fetch_latest_docker_version("kindest/node")

    assert version == "v1.34.0"


@patch('urllib.request.urlopen')
def test_fetch_latest_docker_version_no_valid_versions(mock_urlopen):
    """Test handling when no valid versions found."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'''{
        "results": [
            {"name": "latest"},
            {"name": "dev"}
        ]
    }'''
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    version, elapsed = fetch_latest_docker_version("kindest/node")

    assert version is None
    assert elapsed >= 0


@patch('urllib.request.urlopen')
def test_fetch_latest_docker_version_network_error(mock_urlopen):
    """Test handling network errors gracefully."""
    mock_urlopen.side_effect = Exception("Network error")

    version, elapsed = fetch_latest_docker_version("kindest/node")

    assert version is None
    assert elapsed >= 0


@patch('time.sleep')
@patch('urllib.request.urlopen')
def test_fetch_latest_helm_version_with_repo_url(mock_urlopen, mock_sleep):
    """Test fetching Helm version with explicit repository URL."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'''
entries:
  traefik:
    - version: "37.3.0"
    - version: "37.2.0"
    - version: "36.0.0"
'''
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    version, elapsed = fetch_latest_helm_version(
        "traefik",
        "https://traefik.github.io/charts"
    )

    assert version == "37.3.0"
    assert elapsed >= 0
    assert "traefik.github.io/charts/index.yaml" in mock_urlopen.call_args[0][0].full_url


@patch('time.sleep')
@patch('urllib.request.urlopen')
def test_fetch_latest_helm_version_filters_prerelease(mock_urlopen, mock_sleep):
    """Test that prerelease versions are filtered out."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'''
entries:
  traefik:
    - version: "37.4.0-rc1"
    - version: "37.3.0"
    - version: "37.2.0"
'''
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    version, elapsed = fetch_latest_helm_version(
        "traefik",
        "https://traefik.github.io/charts"
    )

    assert version == "37.3.0"


@patch('time.sleep')
@patch('urllib.request.urlopen')
def test_fetch_latest_helm_version_default_repo(mock_urlopen, mock_sleep):
    """Test fetching Helm version using default repository mapping."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'''
entries:
  mysql:
    - version: "3.0.7"
    - version: "3.0.6"
'''
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    version, elapsed = fetch_latest_helm_version("mysql")

    assert version == "3.0.7"
    assert "groundhog2k.github.io" in mock_urlopen.call_args[0][0].full_url


@patch('time.sleep')
@patch('urllib.request.urlopen')
def test_fetch_latest_helm_version_no_repo_url(mock_urlopen, mock_sleep):
    """Test handling when no repository URL available."""
    version, elapsed = fetch_latest_helm_version("unknown-chart")

    assert version is None
    assert elapsed >= 0
    mock_urlopen.assert_not_called()


@patch('time.sleep')
@patch('urllib.request.urlopen')
def test_fetch_latest_helm_version_chart_not_found(mock_urlopen, mock_sleep):
    """Test handling when chart not found in repository."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'''
entries:
  other-chart:
    - version: "1.0.0"
'''
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    version, elapsed = fetch_latest_helm_version(
        "traefik",
        "https://traefik.github.io/charts"
    )

    assert version is None
    assert elapsed >= 0


@patch('time.sleep')
@patch('urllib.request.urlopen')
def test_fetch_latest_helm_version_network_error(mock_urlopen, mock_sleep):
    """Test handling network errors gracefully."""
    mock_urlopen.side_effect = Exception("Network error")

    version, elapsed = fetch_latest_helm_version(
        "traefik",
        "https://traefik.github.io/charts"
    )

    assert version is None
    assert elapsed >= 0


@patch('loko.updates.fetchers.fetch_latest_docker_version')
def test_fetch_latest_version_docker(mock_fetch_docker):
    """Test fetch_latest_version with docker datasource."""
    mock_fetch_docker.return_value = ("v1.34.0", 0.5)

    renovate_info = {
        'datasource': 'docker',
        'depName': 'kindest/node'
    }

    version, elapsed = fetch_latest_version(renovate_info)

    assert version == "v1.34.0"
    assert elapsed == 0.5
    mock_fetch_docker.assert_called_once_with('kindest/node')


@patch('loko.updates.fetchers.fetch_latest_helm_version')
def test_fetch_latest_version_helm(mock_fetch_helm):
    """Test fetch_latest_version with helm datasource."""
    mock_fetch_helm.return_value = ("37.3.0", 1.2)

    renovate_info = {
        'datasource': 'helm',
        'depName': 'traefik',
        'repositoryUrl': 'https://traefik.github.io/charts'
    }

    version, elapsed = fetch_latest_version(renovate_info)

    assert version == "37.3.0"
    assert elapsed == 1.2
    mock_fetch_helm.assert_called_once_with('traefik', 'https://traefik.github.io/charts')


def test_fetch_latest_version_unsupported_datasource():
    """Test handling unsupported datasource type."""
    renovate_info = {
        'datasource': 'npm',
        'depName': 'react'
    }

    version, elapsed = fetch_latest_version(renovate_info)

    assert version is None
    assert elapsed == 0.0


@patch('time.sleep')
@patch('urllib.request.urlopen')
def test_fetch_latest_helm_version_empty_entries(mock_urlopen, mock_sleep):
    """Test handling empty chart entries."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'entries: {}'
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    version, elapsed = fetch_latest_helm_version(
        "traefik",
        "https://traefik.github.io/charts"
    )

    assert version is None
