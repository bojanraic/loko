import os
import pytest
from unittest.mock import patch, MagicMock
from loko.validators import check_docker_running, check_config_file, check_base_dir_writable, ensure_docker_running, ensure_config_file, ensure_base_dir_writable, check_ports_available, ensure_ports_available

@patch("subprocess.run")
def test_check_docker_running_success(mock_run):
    mock_run.return_value.returncode = 0
    assert check_docker_running() is True

@patch("subprocess.run")
def test_check_docker_running_failure(mock_run):
    mock_run.return_value.returncode = 1
    assert check_docker_running() is False

def test_check_config_file(mock_config_path):
    assert check_config_file(mock_config_path) is True
    assert check_config_file("non_existent_file.yaml") is False

def test_check_base_dir_writable(temp_dir):
    assert check_base_dir_writable(temp_dir) is True
    # Testing non-writable dir is tricky without root or specific OS setup, skipping for now

@patch("loko.validators.check_docker_running")
@patch("sys.exit")
def test_ensure_docker_running_success(mock_exit, mock_check):
    mock_check.return_value = True
    ensure_docker_running()
    mock_exit.assert_not_called()

@patch("loko.validators.check_docker_running")
@patch("sys.exit")
def test_ensure_docker_running_failure(mock_exit, mock_check):
    mock_check.return_value = False
    ensure_docker_running()
    mock_exit.assert_called_with(1)

@patch("loko.validators.check_config_file")
@patch("sys.exit")
def test_ensure_config_file_failure(mock_exit, mock_check):
    mock_check.return_value = False
    ensure_config_file("config.yaml")
    mock_exit.assert_called_with(1)


@patch("loko.validators.check_config_file")
@patch("sys.exit")
def test_ensure_config_file_success(mock_exit, mock_check):
    """Test ensure_config_file when file exists."""
    mock_check.return_value = True
    ensure_config_file("config.yaml")
    mock_exit.assert_not_called()


@patch("loko.validators.check_base_dir_writable")
@patch("sys.exit")
def test_ensure_base_dir_writable_success(mock_exit, mock_check):
    """Test ensure_base_dir_writable when directory is writable."""
    mock_check.return_value = True
    ensure_base_dir_writable("/tmp/test")
    mock_exit.assert_not_called()


@patch("loko.validators.check_base_dir_writable")
@patch("sys.exit")
def test_ensure_base_dir_writable_failure(mock_exit, mock_check):
    """Test ensure_base_dir_writable when directory is not writable."""
    mock_check.return_value = False
    ensure_base_dir_writable("/tmp/test")
    mock_exit.assert_called_with(1)


def test_check_base_dir_writable_nonexistent():
    """Test checking writable status of non-existent directory."""
    result = check_base_dir_writable("/nonexistent/path/to/dir")
    assert result is False


@patch("loko.validators._is_port_in_use")
def test_check_ports_available_all_free(mock_port_check, mock_config_path):
    """Test port checking when all ports are available."""
    from loko.utils import load_config

    # All ports are free
    mock_port_check.return_value = False

    config = load_config(mock_config_path)
    available, conflicts = check_ports_available(config)

    assert available is True
    assert conflicts == {}


@patch("loko.validators._is_port_in_use")
def test_check_ports_available_dns_conflict(mock_port_check, mock_config_path):
    """Test port checking when DNS port is in use."""
    from loko.utils import load_config

    config = load_config(mock_config_path)
    dns_port = config.environment.local_dns_port

    # Only DNS port is in use
    mock_port_check.side_effect = lambda port: port == dns_port

    available, conflicts = check_ports_available(config)

    assert available is False
    assert 'dns' in conflicts
    assert dns_port in conflicts['dns']


@patch("loko.validators._is_port_in_use")
def test_check_ports_available_lb_conflict(mock_port_check, mock_config_path):
    """Test port checking when load balancer ports are in use."""
    from loko.utils import load_config

    config = load_config(mock_config_path)
    lb_ports = config.environment.local_lb_ports

    # Only LB ports are in use
    mock_port_check.side_effect = lambda port: port in lb_ports

    available, conflicts = check_ports_available(config)

    assert available is False
    assert 'load_balancer' in conflicts
    for port in lb_ports:
        assert port in conflicts['load_balancer']


@patch("loko.validators._is_port_in_use")
def test_check_ports_available_service_conflict(mock_port_check, mock_config_path):
    """Test port checking when service ports are in use."""
    from loko.utils import load_config

    config = load_config(mock_config_path)

    # Find an enabled service with ports
    enabled_services = [svc for svc in config.environment.services.system if svc.enabled and svc.ports]

    if enabled_services:
        service_port = enabled_services[0].ports[0]

        # Only service port is in use
        mock_port_check.side_effect = lambda port: port == service_port

        available, conflicts = check_ports_available(config)

        assert available is False
        assert 'services' in conflicts
        assert service_port in conflicts['services']


@patch("loko.validators._is_port_in_use")
def test_check_ports_available_multiple_conflicts(mock_port_check, mock_config_path):
    """Test port checking when multiple types of ports are in use."""
    from loko.utils import load_config

    config = load_config(mock_config_path)
    dns_port = config.environment.local_dns_port
    lb_ports = config.environment.local_lb_ports

    # DNS and LB ports are in use
    conflict_ports = [dns_port] + lb_ports
    mock_port_check.side_effect = lambda port: port in conflict_ports

    available, conflicts = check_ports_available(config)

    assert available is False
    assert 'dns' in conflicts
    assert 'load_balancer' in conflicts
    assert dns_port in conflicts['dns']
    for port in lb_ports:
        assert port in conflicts['load_balancer']


@patch("loko.validators.check_ports_available")
@patch("sys.exit")
def test_ensure_ports_available_success(mock_exit, mock_check, mock_config_path):
    """Test ensure_ports_available when all ports are free."""
    from loko.utils import load_config

    config = load_config(mock_config_path)
    mock_check.return_value = (True, {})

    ensure_ports_available(config)

    mock_exit.assert_not_called()


@patch("loko.validators.check_ports_available")
@patch("sys.exit")
def test_ensure_ports_available_failure(mock_exit, mock_check, mock_config_path):
    """Test ensure_ports_available when ports are in use."""
    from loko.utils import load_config

    config = load_config(mock_config_path)
    conflicts = {
        'dns': [53],
        'load_balancer': [80, 443],
        'services': [5432]
    }
    mock_check.return_value = (False, conflicts)

    ensure_ports_available(config)

    mock_exit.assert_called_with(1)
