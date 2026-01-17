import pytest
import os
from unittest.mock import MagicMock, patch, mock_open
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
                "domain": "loko.local",
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
            "registry": {"name": "reg", "storage": {"size": "1Gi"}},
            "workloads": {"system": [], "user": []}
        }
    })

@patch("loko.cli.commands.secrets.get_config")
@patch("loko.cli.commands.secrets.CommandRunner")
@patch("loko.cli.commands.secrets.ensure_config_file")
@patch("loko.cli.commands.secrets.ensure_docker_running")
def test_secrets_fetch(mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value

    result = runner.invoke(app, ["secret", "fetch"])

    assert result.exit_code == 0
    mock_runner_inst.fetch_workload_secrets.assert_called_once()

@patch("loko.cli.commands.secrets.get_config")
@patch("loko.cli.commands.secrets.CommandRunner")
@patch("loko.cli.commands.secrets.ensure_config_file")
@patch("loko.cli.commands.secrets.ensure_docker_running")
def test_secrets_show_exists(mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value
    mock_runner_inst.workload_secrets_path = "/tmp/workload-secrets.txt"

    with patch("loko.cli.commands.secrets.os.path.exists", return_value=True):
        with patch("loko.cli.commands.secrets.open", mock_open(read_data="test secrets")):
            result = runner.invoke(app, ["secret", "show"])

    assert result.exit_code == 0
    assert "test secrets" in result.output
    mock_runner_inst.fetch_workload_secrets.assert_not_called()

@patch("loko.cli.commands.secrets.get_config")
@patch("loko.cli.commands.secrets.CommandRunner")
@patch("loko.cli.commands.secrets.ensure_config_file")
@patch("loko.cli.commands.secrets.ensure_docker_running")
@patch("loko.cli.commands.secrets.console")
def test_secrets_show_implicit_fetch(mock_console, mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value
    mock_runner_inst.workload_secrets_path = "/tmp/workload-secrets.txt"

    secrets_file_calls = []
    def mock_exists_logic(path):
        # Track calls only for the secrets file we care about
        if path == "/tmp/workload-secrets.txt":
            secrets_file_calls.append(path)
            # First call to secrets file returns False, second returns True
            return len(secrets_file_calls) > 1
        # For all other paths (locale files, etc.), return True to avoid side effects
        return True

    with patch("loko.cli.commands.secrets.os.path.exists", side_effect=mock_exists_logic):
        with patch("loko.cli.commands.secrets.open", mock_open(read_data="fetched secrets")):
            result = runner.invoke(app, ["secret", "show"])

    assert result.exit_code == 0
    # Verify console.print was called with the warning message
    warning_call = [call for call in mock_console.print.call_args_list
                    if "Secrets file not found" in str(call)]
    assert len(warning_call) > 0, "Warning message should be printed when secrets file is missing"
    mock_runner_inst.fetch_workload_secrets.assert_called_once()
