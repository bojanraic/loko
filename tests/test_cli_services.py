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
            "local-ip": "127.0.0.1",
            "local-domain": "loko.local",
            "local-lb-ports": [80],
            "internal-components": [],
            "provider": {"name": "kind", "runtime": "docker"},
            "kubernetes": {"api-port": 6443, "image": "kindest/node", "tag": "v1.27.3"},
            "nodes": {
                "servers": 1, 
                "workers": 0,
                "allow-scheduling-on-control-plane": True,
                "internal-components-on-control-plane": True
            },
            "registry": {"name": "reg", "storage": {"size": "1Gi"}},
            "internal-components": [],
            "services": {"system": [], "user": []}
        }
    })

@patch("loko.cli.commands.services.get_config")
@patch("loko.cli.commands.services.CommandRunner")
@patch("loko.cli.commands.services.ensure_config_file")
@patch("loko.cli.commands.services.ensure_docker_running")
def test_services_list(mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value
    mock_runner_inst.get_services_status.return_value = [
        {"name": "test-svc", "type": "user", "namespace": "default", "status": "deployed", "pods": "1/1", "chart": "test-chart"}
    ]
    
    result = runner.invoke(app, ["service", "list"])
    
    assert result.exit_code == 0
    assert "test-svc" in result.output
    assert "deployed" in result.output
    mock_runner_inst.get_services_status.assert_called_once()

@patch("loko.cli.commands.services.get_config")
@patch("loko.cli.commands.services.CommandRunner")
@patch("loko.cli.commands.services.ensure_config_file")
@patch("loko.cli.commands.services.ensure_docker_running")
def test_services_deploy_specific(mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value
    
    result = runner.invoke(app, ["service", "deploy", "my-svc"])
    
    assert result.exit_code == 0
    mock_runner_inst.deploy_services.assert_called_with(["my-svc"])
    mock_runner_inst.fetch_service_secrets.assert_called_once()
    mock_runner_inst.configure_services.assert_called_once()

@patch("loko.cli.commands.services.get_config")
@patch("loko.cli.commands.services.CommandRunner")
@patch("loko.cli.commands.services.ensure_config_file")
@patch("loko.cli.commands.services.ensure_docker_running")
def test_services_deploy_default(mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value
    mock_runner_inst.get_all_services.return_value = [
        {"name": "sys-svc", "type": "system", "enabled": True},
        {"name": "user-svc", "type": "user", "enabled": True},
        {"name": "int-svc", "type": "internal", "enabled": True}
    ]
    
    result = runner.invoke(app, ["service", "deploy"])
    
    assert result.exit_code == 0
    # Default should be user + system
    called_names = mock_runner_inst.deploy_services.call_args[0][0]
    assert "sys-svc" in called_names
    assert "user-svc" in called_names
    assert "int-svc" not in called_names

@patch("loko.cli.commands.services.get_config")
@patch("loko.cli.commands.services.CommandRunner")
@patch("loko.cli.commands.services.ensure_config_file")
@patch("loko.cli.commands.services.ensure_docker_running")
def test_services_undeploy_internal(mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value
    mock_runner_inst.get_all_services.return_value = [
        {"name": "int-svc", "type": "internal", "enabled": True}
    ]

    result = runner.invoke(app, ["service", "undeploy", "--internal"])

    assert result.exit_code == 0
    mock_runner_inst.destroy_services.assert_called_with(["int-svc"])

@patch("loko.cli.commands.services.get_config")
@patch("loko.cli.commands.services.CommandRunner")
@patch("loko.cli.commands.services.ensure_config_file")
@patch("loko.cli.commands.services.ensure_docker_running")
@patch("loko.cli.commands.services.console")
def test_services_deploy_disabled_error(mock_console, mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    """Test that deploying a disabled service exits with error."""
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value
    mock_runner_inst.get_all_services.return_value = [
        {"name": "disabled-svc", "type": "user", "enabled": False},
        {"name": "enabled-svc", "type": "user", "enabled": True}
    ]

    result = runner.invoke(app, ["service", "deploy", "disabled-svc"])

    # Should exit with error code 1
    assert result.exit_code == 1
    # Verify error message was printed
    error_calls = [call for call in mock_console.print.call_args_list
                   if "cannot deploy" in str(call).lower() or "disabled" in str(call).lower()]
    assert len(error_calls) > 0, "Should show error when deploying disabled service"
    # Service should NOT be deployed
    mock_runner_inst.deploy_services.assert_not_called()

@patch("loko.cli.commands.services.get_config")
@patch("loko.cli.commands.services.CommandRunner")
@patch("loko.cli.commands.services.ensure_config_file")
@patch("loko.cli.commands.services.ensure_docker_running")
@patch("loko.cli.commands.services.console")
def test_services_deploy_enabled_no_warning(mock_console, mock_docker, mock_ensure_config, mock_command_runner, mock_get_config, mock_config):
    """Test that deploying an enabled service does not show a warning."""
    mock_get_config.return_value = mock_config
    mock_runner_inst = mock_command_runner.return_value
    mock_runner_inst.get_all_services.return_value = [
        {"name": "enabled-svc", "type": "user", "enabled": True}
    ]

    result = runner.invoke(app, ["service", "deploy", "enabled-svc"])

    assert result.exit_code == 0
    # Verify no warning was printed
    warning_calls = [call for call in mock_console.print.call_args_list
                     if "disabled in config" in str(call).lower()]
    assert len(warning_calls) == 0, "Should not warn when deploying enabled service"
    mock_runner_inst.deploy_services.assert_called_with(["enabled-svc"])
