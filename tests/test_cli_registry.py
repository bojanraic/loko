import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from loko.cli import app
from loko.config import RootConfig

runner = CliRunner()


@pytest.fixture
def mock_config():
    return RootConfig(**{
        "environment": {
            "name": "test-env",
            "base-dir": "/tmp",
            "cluster": {
                "provider": {"name": "kind", "runtime": "docker"},
                "kubernetes": {"api-port": 6443, "image": "kindest/node", "tag": "v1.27.3"},
                "nodes": {
                    "servers": 1,
                    "workers": 0,
                    "scheduling": {
                        "control-plane": {
                            "allow-workloads": True,
                            "isolate-internal-components": True
                        },
                        "workers": {
                            "isolate-workloads": False
                        }
                    }
                }
            },
            "network": {
                "ip": "127.0.0.1",
                "domain": "dev.me",
                "dns-port": 53,
                "subdomain": {"enabled": True, "value": "apps"},
                "lb-ports": [80]
            },
            "internal-components": {
                "traefik": {"version": "37.3.0"},
                "zot": {"version": "0.1.66"},
                "dnsmasq": {"version": "2.90"},
                "metrics-server": {"version": "3.13.0", "enabled": False}
            },
            "registry": {
                "name": "cr",
                "storage": {"size": "5Gi"},
                "mirroring": {
                    "enabled": True,
                    "sources": [
                        {"name": "docker_hub", "enabled": True},
                        {"name": "ghcr", "enabled": True},
                    ]
                }
            },
            "workloads": {"system": [], "user": []}
        }
    })


class TestRegistryStatus:
    """Tests for loko registry status command."""

    @patch("loko.cli.commands.registry._fetch_registry_api")
    @patch("loko.cli.commands.registry.get_config")
    @patch("loko.cli.commands.registry.ensure_config_file")
    @patch("loko.cli.commands.registry.ensure_docker_running")
    def test_registry_status_success(self, mock_docker, mock_ensure_config, mock_get_config, mock_fetch_api, mock_config):
        mock_get_config.return_value = mock_config
        mock_fetch_api.return_value = {"repositories": ["myapp", "ghcr/org/repo"]}

        result = runner.invoke(app, ["registry", "status"])

        assert result.exit_code == 0
        assert "Registry Configuration" in result.output
        assert "https://cr.dev.me" in result.output
        assert "Mirroring" in result.output
        assert "Yes" in result.output  # Mirroring enabled

    @patch("loko.cli.commands.registry._fetch_registry_api")
    @patch("loko.cli.commands.registry.get_config")
    @patch("loko.cli.commands.registry.ensure_config_file")
    @patch("loko.cli.commands.registry.ensure_docker_running")
    def test_registry_status_no_repos(self, mock_docker, mock_ensure_config, mock_get_config, mock_fetch_api, mock_config):
        mock_get_config.return_value = mock_config
        mock_fetch_api.return_value = None

        result = runner.invoke(app, ["registry", "status"])

        assert result.exit_code == 0
        assert "Could not fetch" in result.output


class TestRegistryListRepos:
    """Tests for loko registry list-repos command."""

    @patch("loko.cli.commands.registry._fetch_registry_api")
    @patch("loko.cli.commands.registry.get_config")
    @patch("loko.cli.commands.registry.ensure_config_file")
    @patch("loko.cli.commands.registry.ensure_docker_running")
    def test_list_repos_success(self, mock_docker, mock_ensure_config, mock_get_config, mock_fetch_api, mock_config):
        mock_get_config.return_value = mock_config
        mock_fetch_api.return_value = {"repositories": ["myapp", "ghcr/org/repo", "dockerhub/library/nginx"]}

        result = runner.invoke(app, ["registry", "list-repos"])

        assert result.exit_code == 0
        assert "myapp" in result.output
        assert "ghcr/org/repo" in result.output
        assert "local" in result.output
        assert "mirrored" in result.output
        assert "Total: 3" in result.output

    @patch("loko.cli.commands.registry._fetch_registry_api")
    @patch("loko.cli.commands.registry.get_config")
    @patch("loko.cli.commands.registry.ensure_config_file")
    @patch("loko.cli.commands.registry.ensure_docker_running")
    def test_list_repos_empty(self, mock_docker, mock_ensure_config, mock_get_config, mock_fetch_api, mock_config):
        mock_get_config.return_value = mock_config
        mock_fetch_api.return_value = {"repositories": []}

        result = runner.invoke(app, ["registry", "list-repos"])

        assert result.exit_code == 0
        assert "empty" in result.output.lower()


class TestRegistryListTags:
    """Tests for loko registry list-tags command."""

    @patch("loko.cli.commands.registry._fetch_registry_api")
    @patch("loko.cli.commands.registry.get_config")
    @patch("loko.cli.commands.registry.ensure_config_file")
    @patch("loko.cli.commands.registry.ensure_docker_running")
    def test_list_tags_success(self, mock_docker, mock_ensure_config, mock_get_config, mock_fetch_api, mock_config):
        mock_get_config.return_value = mock_config
        # First call for exact match, second for tags
        mock_fetch_api.return_value = {"tags": ["v1.0.0", "v1.1.0", "latest"]}

        result = runner.invoke(app, ["registry", "list-tags", "myapp"])

        assert result.exit_code == 0
        assert "v1.0.0" in result.output
        assert "v1.1.0" in result.output
        assert "latest" in result.output
        assert "Total: 3 tags" in result.output

    @patch("loko.cli.commands.registry._fetch_registry_api")
    @patch("loko.cli.commands.registry.get_config")
    @patch("loko.cli.commands.registry.ensure_config_file")
    @patch("loko.cli.commands.registry.ensure_docker_running")
    def test_list_tags_not_found(self, mock_docker, mock_ensure_config, mock_get_config, mock_fetch_api, mock_config):
        mock_get_config.return_value = mock_config
        # Return None for exact match, then empty catalog for resolution
        mock_fetch_api.side_effect = [None, {"repositories": []}]

        result = runner.invoke(app, ["registry", "list-tags", "nonexistent"])

        assert result.exit_code == 0
        assert "not found" in result.output.lower()

    @patch("loko.cli.commands.registry._fetch_registry_api")
    @patch("loko.cli.commands.registry.get_config")
    @patch("loko.cli.commands.registry.ensure_config_file")
    @patch("loko.cli.commands.registry.ensure_docker_running")
    def test_list_tags_resolves_mirror_prefix(self, mock_docker, mock_ensure_config, mock_get_config, mock_fetch_api, mock_config):
        mock_get_config.return_value = mock_config

        # Sequence of calls:
        # 1. _resolve_repo_name tries exact match -> None
        # 2. _resolve_repo_name fetches catalog -> repos with ghcr prefix
        # 3. list_tags fetches tags with resolved name -> tags
        mock_fetch_api.side_effect = [
            None,  # Exact match for org/repo fails
            {"repositories": ["ghcr/org/repo"]},  # Catalog lookup
            {"tags": ["v1.0.0"]},  # Tags for resolved name
        ]

        result = runner.invoke(app, ["registry", "list-tags", "org/repo"])

        assert result.exit_code == 0
        assert "Resolved to: ghcr/org/repo" in result.output
        assert "v1.0.0" in result.output


class TestRegistryShowRepo:
    """Tests for loko registry show-repo command."""

    @patch("loko.cli.commands.registry._fetch_registry_api")
    @patch("loko.cli.commands.registry.get_config")
    @patch("loko.cli.commands.registry.ensure_config_file")
    @patch("loko.cli.commands.registry.ensure_docker_running")
    def test_show_repo_success(self, mock_docker, mock_ensure_config, mock_get_config, mock_fetch_api, mock_config):
        mock_get_config.return_value = mock_config
        mock_fetch_api.return_value = {"tags": ["v1.0.0", "latest"]}

        result = runner.invoke(app, ["registry", "show-repo", "myapp"])

        assert result.exit_code == 0
        assert "myapp" in result.output
        assert "local" in result.output.lower()
        assert "Tags: 2" in result.output

    @patch("loko.cli.commands.registry._fetch_registry_api")
    @patch("loko.cli.commands.registry.get_config")
    @patch("loko.cli.commands.registry.ensure_config_file")
    @patch("loko.cli.commands.registry.ensure_docker_running")
    def test_show_repo_mirrored(self, mock_docker, mock_ensure_config, mock_get_config, mock_fetch_api, mock_config):
        mock_get_config.return_value = mock_config
        mock_fetch_api.return_value = {"tags": ["v1.0.0"]}

        result = runner.invoke(app, ["registry", "show-repo", "ghcr/org/repo"])

        assert result.exit_code == 0
        assert "ghcr/org/repo" in result.output
        assert "mirrored" in result.output.lower()
