import pytest
from unittest.mock import MagicMock, patch, call
from loko.runner import CommandRunner
from loko.config import RootConfig
import subprocess

@pytest.fixture
def sample_config():
    return RootConfig(**{
        "environment": {
            "name": "test-env",
            "base-dir": "/tmp/loko",
            "cluster": {
                "provider": {
                    "name": "kind",
                    "runtime": "docker"
                },
                "kubernetes": {
                    "api-port": 6443,
                    "image": "kindest/node",
                    "tag": "v1.27.3"
                },
                "nodes": {
                    "servers": 1,
                    "workers": 2,
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
                "subdomain": {
                    "enabled": True,
                    "value": "apps"
                },
                "lb-ports": [80, 443]
            },
            "internal-components": {
                "traefik": {"version": "37.3.0"},
                "zot": {"version": "0.1.66"},
                "dnsmasq": {"version": "2.90"},
                "metrics-server": {"version": "3.13.0", "enabled": False}
            },
            "registry": {
                "name": "registry",
                "storage": {"size": "10Gi"}
            },
            "workloads": {
                "system": [],
                "user": []
            }
        }
    })

@patch("subprocess.run")
def test_run_command_success(mock_run, sample_config):
    runner = CommandRunner(sample_config)
    mock_run.return_value.returncode = 0
    runner.run_command(["echo", "hello"])
    mock_run.assert_called_with(["echo", "hello"], check=True, capture_output=False, text=True)

@patch("subprocess.run")
def test_run_command_failure(mock_run, sample_config):
    runner = CommandRunner(sample_config)
    mock_run.side_effect = subprocess.CalledProcessError(1, ["ls"])
    with pytest.raises(subprocess.CalledProcessError):
        runner.run_command(["ls"], check=True)

@patch("shutil.which")
@patch("subprocess.run")
def test_check_runtime_success(mock_run, mock_which, sample_config):
    runner = CommandRunner(sample_config)
    mock_which.return_value = "/usr/bin/docker"
    mock_run.return_value.returncode = 0
    runner.check_runtime()
    mock_run.assert_called()

@patch("shutil.which")
def test_check_runtime_not_found(mock_which, sample_config):
    runner = CommandRunner(sample_config)
    mock_which.return_value = None
    with pytest.raises(RuntimeError, match="docker not found"):
        runner.check_runtime()

@patch("subprocess.run")
def test_ensure_network_exists(mock_run, sample_config):
    runner = CommandRunner(sample_config)
    # Mock network ls output
    mock_run.return_value.stdout = "kind\nother\n"
    runner.ensure_network()
    # Should check for network but not create it
    assert mock_run.call_count == 1
    assert "create" not in mock_run.call_args[0][0]

@patch("subprocess.run")
def test_ensure_network_create(mock_run, sample_config):
    runner = CommandRunner(sample_config)
    # Mock network ls output (kind network missing)
    mock_run.side_effect = [
        MagicMock(stdout="other\n"), # First call: network ls
        MagicMock(returncode=0)      # Second call: network create
    ]
    runner.ensure_network()
    assert mock_run.call_count == 2
    assert "create" in mock_run.call_args_list[1][0][0]

@patch("subprocess.run")
def test_cluster_exists_true(mock_run, sample_config):
    runner = CommandRunner(sample_config)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "test-env\nother-cluster\n"
    mock_run.return_value = mock_result
    assert runner.cluster_exists() is True

@patch("subprocess.run")
def test_cluster_exists_false(mock_run, sample_config):
    runner = CommandRunner(sample_config)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "other-cluster\n"
    mock_run.return_value = mock_result
    assert runner.cluster_exists() is False

@patch("subprocess.run")
def test_cluster_exists_error(mock_run, sample_config):
    runner = CommandRunner(sample_config)
    mock_run.side_effect = Exception("Command failed")
    assert runner.cluster_exists() is False

@patch.object(CommandRunner, 'cluster_exists')
@patch("subprocess.run")
def test_create_cluster_exists(mock_run, mock_cluster_exists, sample_config):
    runner = CommandRunner(sample_config)
    mock_cluster_exists.return_value = True
    runner.create_cluster()
    mock_run.assert_not_called()

@patch.object(CommandRunner, 'fetch_kubeconfig')
@patch.object(CommandRunner, '_apply_node_labels')
@patch.object(CommandRunner, 'cluster_exists')
@patch("subprocess.run")
def test_create_cluster_new(mock_run, mock_cluster_exists, mock_apply_labels, mock_fetch_kubeconfig, sample_config):
    runner = CommandRunner(sample_config)
    mock_cluster_exists.return_value = False
    runner.create_cluster()
    # Verify cluster creation was called
    mock_run.assert_called_once()
    assert "create" in mock_run.call_args[0][0]
    assert "cluster" in mock_run.call_args[0][0]
    # Verify kubeconfig was fetched
    mock_fetch_kubeconfig.assert_called_once()
    # Verify node labels were applied
    mock_apply_labels.assert_called_once()

@patch.object(CommandRunner, 'cluster_exists')
@patch.object(CommandRunner, 'run_command')
def test_delete_cluster_exists(mock_run_command, mock_cluster_exists, sample_config):
    runner = CommandRunner(sample_config)
    mock_cluster_exists.return_value = True
    runner.delete_cluster()
    mock_run_command.assert_called_once()
    assert "delete" in mock_run_command.call_args[0][0]
    assert "cluster" in mock_run_command.call_args[0][0]

@patch.object(CommandRunner, 'cluster_exists')
@patch.object(CommandRunner, 'run_command')
def test_delete_cluster_not_exists(mock_run_command, mock_cluster_exists, sample_config):
    runner = CommandRunner(sample_config)
    mock_cluster_exists.return_value = False
    runner.delete_cluster()
    mock_run_command.assert_not_called()


def test_runner_initialization(sample_config):
    """Test CommandRunner initialization."""
    runner = CommandRunner(sample_config)
    assert runner.config == sample_config
    assert runner.env == sample_config.environment


@patch("shutil.which")
def test_check_prerequisites(mock_which, sample_config):
    """Test checking for required tools."""
    runner = CommandRunner(sample_config)
    mock_which.return_value = "/usr/bin/kind"

    # Should not raise error when tools are available
    # Note: check_runtime is already tested above


# Secrets file management tests

def test_parse_secrets_file_empty(sample_config, tmp_path):
    """Test parsing when secrets file doesn't exist."""
    runner = CommandRunner(sample_config)
    runner.k8s_dir = str(tmp_path)

    workloads = runner._parse_secrets_file()
    assert workloads == {}


def test_parse_secrets_file_with_workloads(sample_config, tmp_path):
    """Test parsing secrets file with multiple workloads."""
    runner = CommandRunner(sample_config)
    runner.k8s_dir = str(tmp_path)

    # Create a secrets file
    secrets_file = tmp_path / "workload-secrets.txt"
    secrets_file.write_text("""# Workload Credentials for test-env
# Generated: 2026-01-03 14:00:00

Workload: rabbitmq
Namespace: common-services
Username: admin
Password: test123

==================================================

Workload: garage
Access Key: GK123
Secret Key: secret456
Endpoint: https://s3.dev.me
""")

    workloads = runner._parse_secrets_file()
    assert len(workloads) == 2
    assert 'rabbitmq' in workloads
    assert 'garage' in workloads
    assert 'Password: test123' in workloads['rabbitmq']
    assert 'Access Key: GK123' in workloads['garage']


def test_write_secrets_file(sample_config, tmp_path):
    """Test writing secrets file with clean structure."""
    runner = CommandRunner(sample_config)
    runner.k8s_dir = str(tmp_path)

    workloads = {
        'garage': 'Workload: garage\nAccess Key: GK123\nSecret Key: secret456',
        'rabbitmq': 'Workload: rabbitmq\nNamespace: common-services\nPassword: test123'
    }

    runner._write_secrets_file(workloads)

    secrets_file = tmp_path / "workload-secrets.txt"
    assert secrets_file.exists()

    content = secrets_file.read_text()
    assert '# Workload Credentials for test-env' in content
    assert 'Workload: garage' in content
    assert 'Workload: rabbitmq' in content
    # Should be sorted alphabetically
    assert content.index('garage') < content.index('rabbitmq')


def test_remove_workload_secrets(sample_config, tmp_path):
    """Test removing specific workloads from secrets file."""
    runner = CommandRunner(sample_config)
    runner.k8s_dir = str(tmp_path)

    # Create initial secrets file with two workloads
    secrets_file = tmp_path / "workload-secrets.txt"
    secrets_file.write_text("""# Workload Credentials for test-env
# Generated: 2026-01-03 14:00:00

Workload: rabbitmq
Password: test123

==================================================

Workload: garage
Access Key: GK123
""")

    # Remove rabbitmq
    runner.remove_workload_secrets(['rabbitmq'])

    # Check that only garage remains
    workloads = runner._parse_secrets_file()
    assert len(workloads) == 1
    assert 'garage' in workloads
    assert 'rabbitmq' not in workloads


def test_remove_all_workloads(sample_config, tmp_path):
    """Test that file is removed when all workloads are deleted."""
    runner = CommandRunner(sample_config)
    runner.k8s_dir = str(tmp_path)

    # Create secrets file with one workload
    secrets_file = tmp_path / "workload-secrets.txt"
    secrets_file.write_text("""# Workload Credentials for test-env

Workload: rabbitmq
Password: test123
""")

    # Remove the only workload
    runner.remove_workload_secrets(['rabbitmq'])

    # File should be removed
    assert not secrets_file.exists()
