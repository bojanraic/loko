import pytest
from unittest.mock import MagicMock, patch
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

@patch("loko.cli.commands.workloads.get_config")
@patch("loko.cli.commands.workloads.CommandRunner")
@patch("loko.cli.commands.workloads.ensure_config_file")
@patch("loko.cli.commands.workloads.ensure_docker_running")
def test_workloads_list(mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value
    mock_runner_inst.get_workloads_status.return_value = [
        {"name": "test-wkld", "type": "user", "namespace": "default", "status": "deployed", "pods": "1/1", "chart": "test-chart"}
    ]

    result = runner.invoke(app, ["workload", "list"])

    assert result.exit_code == 0
    assert "test-wkld" in result.output
    assert "deployed" in result.output
    mock_runner_inst.get_workloads_status.assert_called_once()

@patch("loko.cli.commands.workloads.get_config")
@patch("loko.cli.commands.workloads.CommandRunner")
@patch("loko.cli.commands.workloads.ensure_config_file")
@patch("loko.cli.commands.workloads.ensure_docker_running")
def test_workloads_deploy_specific(mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value

    result = runner.invoke(app, ["workload", "deploy", "my-wkld"])

    assert result.exit_code == 0
    mock_runner_inst.deploy_workloads.assert_called_with(["my-wkld"])
    mock_runner_inst.fetch_workload_secrets.assert_called_once()
    mock_runner_inst.configure_workloads.assert_called_once()

@patch("loko.cli.commands.workloads.get_config")
@patch("loko.cli.commands.workloads.CommandRunner")
@patch("loko.cli.commands.workloads.ensure_config_file")
@patch("loko.cli.commands.workloads.ensure_docker_running")
def test_workloads_deploy_default(mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value
    mock_runner_inst.get_all_workloads.return_value = [
        {"name": "sys-wkld", "type": "system", "enabled": True},
        {"name": "user-wkld", "type": "user", "enabled": True},
        {"name": "int-wkld", "type": "internal", "enabled": True}
    ]

    result = runner.invoke(app, ["workload", "deploy"])

    assert result.exit_code == 0
    # Default should be user + system
    called_names = mock_runner_inst.deploy_workloads.call_args[0][0]
    assert "sys-wkld" in called_names
    assert "user-wkld" in called_names
    assert "int-wkld" not in called_names

@patch("loko.cli.commands.workloads.get_config")
@patch("loko.cli.commands.workloads.CommandRunner")
@patch("loko.cli.commands.workloads.ensure_config_file")
@patch("loko.cli.commands.workloads.ensure_docker_running")
def test_workloads_undeploy_internal(mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value
    mock_runner_inst.get_all_workloads.return_value = [
        {"name": "int-wkld", "type": "internal", "enabled": True}
    ]

    result = runner.invoke(app, ["workload", "undeploy", "--internal"])

    assert result.exit_code == 0
    mock_runner_inst.destroy_workloads.assert_called_with(["int-wkld"])

@patch("loko.cli.commands.workloads.get_config")
@patch("loko.cli.commands.workloads.CommandRunner")
@patch("loko.cli.commands.workloads.ensure_config_file")
@patch("loko.cli.commands.workloads.ensure_docker_running")
@patch("loko.cli.commands.workloads.console")
def test_workloads_deploy_disabled_error(mock_console, mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    """Test that deploying a disabled workload exits with error."""
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value
    mock_runner_inst.get_all_workloads.return_value = [
        {"name": "disabled-wkld", "type": "user", "enabled": False},
        {"name": "enabled-wkld", "type": "user", "enabled": True}
    ]

    result = runner.invoke(app, ["workload", "deploy", "disabled-wkld"])

    # Should exit with error code 1
    assert result.exit_code == 1
    # Verify error message was printed
    error_calls = [call for call in mock_console.print.call_args_list
                   if "cannot deploy" in str(call).lower() or "disabled" in str(call).lower()]
    assert len(error_calls) > 0, "Should show error when deploying disabled workload"
    # Workload should NOT be deployed
    mock_runner_inst.deploy_workloads.assert_not_called()

@patch("loko.cli.commands.workloads.get_config")
@patch("loko.cli.commands.workloads.CommandRunner")
@patch("loko.cli.commands.workloads.ensure_config_file")
@patch("loko.cli.commands.workloads.ensure_docker_running")
@patch("loko.cli.commands.workloads.console")
def test_workloads_deploy_enabled_no_warning(mock_console, mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    """Test that deploying an enabled workload does not show a warning."""
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value
    mock_runner_inst.get_all_workloads.return_value = [
        {"name": "enabled-wkld", "type": "user", "enabled": True}
    ]

    result = runner.invoke(app, ["workload", "deploy", "enabled-wkld"])

    assert result.exit_code == 0
    # Verify no warning was printed
    warning_calls = [call for call in mock_console.print.call_args_list
                     if "disabled in config" in str(call).lower()]
    assert len(warning_calls) == 0, "Should not warn when deploying enabled workload"
    mock_runner_inst.deploy_workloads.assert_called_with(["enabled-wkld"])
