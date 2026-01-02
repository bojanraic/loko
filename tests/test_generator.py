import pytest
import os
from unittest.mock import MagicMock, patch, call
from pathlib import Path
from loko.generator import ConfigGenerator, load_presets
from loko.config import RootConfig

@pytest.fixture
def sample_config():
    return RootConfig(**{
        "environment": {
            "name": "test-env",
            "base-dir": "/tmp/loko",
            "local-ip": "127.0.0.1",
            "local-domain": "loko.local",
            "local-lb-ports": [80, 443],
            "internal-components": [],
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
                "allow-scheduling-on-control-plane": True,
                "internal-components-on-control-plane": True
            },
            "registry": {
                "name": "registry",
                "storage": {"size": "10Gi"}
            },
            "services": {
                "system": [],
                "user": []
            }
        }
    })


@pytest.fixture
def config_with_services():
    """Config with system services."""
    return RootConfig(**{
        "environment": {
            "name": "test-env",
            "base-dir": "/tmp/loko",
            "local-ip": "127.0.0.1",
            "local-domain": "loko.local",
            "local-lb-ports": [80, 443],
            "internal-components": [{"traefik": "37.3.0"}],
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
                "allow-scheduling-on-control-plane": True,
                "internal-components-on-control-plane": True
            },
            "registry": {
                "name": "registry",
                "storage": {"size": "10Gi"}
            },
            "services": {
                "system": [],
                "user": []
            }
        }
    })


def test_generator_init(sample_config):
    """Test ConfigGenerator initialization."""
    generator = ConfigGenerator(sample_config, "config.yaml")
    assert generator.env.name == "test-env"
    assert generator.base_dir == "/tmp/loko"
    assert generator.k8s_dir == "/tmp/loko/test-env"


def test_generator_init_with_env_expansion(sample_config):
    """Test ConfigGenerator with environment variable expansion."""
    # Modify config to use env vars
    sample_config.environment.expand_env_vars = True
    sample_config.environment.base_dir = "$HOME/.loko"

    generator = ConfigGenerator(sample_config, "config.yaml")

    # Should expand $HOME
    assert generator.base_dir == os.path.expandvars("$HOME/.loko")


def test_generate_random_password_length(sample_config):
    """Test random password generation with different lengths."""
    generator = ConfigGenerator(sample_config, "config.yaml")

    password_10 = generator.generate_random_password(10)
    assert len(password_10) == 10

    password_32 = generator.generate_random_password(32)
    assert len(password_32) == 32


def test_generate_random_password_uniqueness(sample_config):
    """Test that generated passwords are unique."""
    generator = ConfigGenerator(sample_config, "config.yaml")

    passwords = [generator.generate_random_password(16) for _ in range(10)]
    # All passwords should be unique
    assert len(set(passwords)) == 10


def test_generate_random_password_charset(sample_config):
    """Test that generated passwords contain only valid characters."""
    generator = ConfigGenerator(sample_config, "config.yaml")

    password = generator.generate_random_password(100)
    # Should only contain letters and digits
    assert all(c.isalnum() for c in password)


def test_load_presets_success():
    """Test loading service presets from templates directory."""
    # Use actual templates directory
    template_dir = Path(__file__).parent.parent / "loko" / "templates"
    if template_dir.exists():
        ports, values = load_presets(template_dir)
        assert isinstance(ports, dict)
        assert isinstance(values, dict)


def test_load_presets_missing_file(temp_dir):
    """Test loading presets when file doesn't exist."""
    ports, values = load_presets(Path(temp_dir))
    assert ports == {}
    assert values == {}


def test_get_presets(sample_config):
    """Test getting presets via generator."""
    generator = ConfigGenerator(sample_config, "config.yaml")
    ports, values = generator.get_presets()
    assert isinstance(ports, dict)
    assert isinstance(values, dict)


def test_generate_chart_auth_config_mysql(sample_config):
    """Test MySQL auth config generation."""
    generator = ConfigGenerator(sample_config, "config.yaml")
    auth_config = generator._generate_chart_auth_config("mysql", "groundhog2k/mysql")

    assert 'settings' in auth_config
    assert 'rootPassword' in auth_config['settings']
    assert 'value' in auth_config['settings']['rootPassword']
    # Password should be 16 chars by default
    assert len(auth_config['settings']['rootPassword']['value']) == 16


def test_generate_chart_auth_config_postgres(sample_config):
    """Test PostgreSQL auth config generation."""
    generator = ConfigGenerator(sample_config, "config.yaml")
    auth_config = generator._generate_chart_auth_config("postgres", "groundhog2k/postgres")

    assert 'settings' in auth_config
    assert 'superuserPassword' in auth_config['settings']
    assert len(auth_config['settings']['superuserPassword']['value']) == 16


def test_generate_chart_auth_config_mongodb(sample_config):
    """Test MongoDB auth config generation."""
    generator = ConfigGenerator(sample_config, "config.yaml")
    auth_config = generator._generate_chart_auth_config("mongodb", "groundhog2k/mongodb")

    assert 'settings' in auth_config
    assert auth_config['settings']['rootUsername'] == 'root'
    assert 'rootPassword' in auth_config['settings']


def test_generate_chart_auth_config_rabbitmq(sample_config):
    """Test RabbitMQ auth config generation."""
    generator = ConfigGenerator(sample_config, "config.yaml")
    auth_config = generator._generate_chart_auth_config("rabbitmq", "groundhog2k/rabbitmq")

    assert 'authentication' in auth_config
    assert auth_config['authentication']['user']['value'] == 'admin'
    assert len(auth_config['authentication']['password']['value']) == 16
    # Erlang cookie should be 32 chars
    assert len(auth_config['authentication']['erlangCookie']['value']) == 32


def test_generate_chart_auth_config_valkey(sample_config):
    """Test Valkey auth config generation."""
    generator = ConfigGenerator(sample_config, "config.yaml")
    auth_config = generator._generate_chart_auth_config("valkey", "groundhog2k/valkey")

    assert 'useDeploymentWhenNonHA' in auth_config
    assert auth_config['useDeploymentWhenNonHA'] is False


def test_generate_chart_auth_config_unknown(sample_config):
    """Test auth config for unknown service returns empty dict."""
    generator = ConfigGenerator(sample_config, "config.yaml")
    auth_config = generator._generate_chart_auth_config("unknown", "unknown/chart")

    assert auth_config == {}


@patch("loko.generator.load_presets")
def test_prepare_context_basic(mock_load_presets, sample_config):
    """Test basic context preparation."""
    mock_load_presets.return_value = ({}, {})
    generator = ConfigGenerator(sample_config, "config.yaml")
    context = generator.prepare_context()

    assert context["env_name"] == "test-env"
    assert context["local_ip"] == "127.0.0.1"
    assert context["local_domain"] == "loko.local"
    assert context["runtime"] == "docker"


@patch("loko.generator.load_presets")
def test_prepare_context_with_services(mock_load_presets, config_with_services):
    """Test context preparation with services."""
    mock_load_presets.return_value = (
        {"mysql": 3306, "postgres": 5432},
        {"mysql": {"image": {"pullPolicy": "IfNotPresent"}}}
    )

    generator = ConfigGenerator(config_with_services, "config.yaml")
    context = generator.prepare_context()

    # Check that context includes basic fields
    assert context["env_name"] == "test-env"
    assert context["local_ip"] == "127.0.0.1"


@patch("loko.generator.os.makedirs")
@patch("builtins.open", new_callable=MagicMock)
@patch("loko.generator.load_presets")
def test_generate_configs_creates_directories(mock_load_presets, mock_open, mock_makedirs, sample_config):
    """Test that generate_configs creates necessary directories."""
    mock_load_presets.return_value = ({}, {})

    with patch("jinja2.Environment.get_template") as mock_get_template:
        mock_template = MagicMock()
        mock_template.render.return_value = "rendered content"
        mock_get_template.return_value = mock_template

        generator = ConfigGenerator(sample_config, "config.yaml")
        generator.generate_configs()

        # Should create config directory
        assert mock_makedirs.call_count >= 1


def test_jinja_env_setup(sample_config):
    """Test Jinja environment is set up correctly."""
    generator = ConfigGenerator(sample_config, "config.yaml")

    assert generator.jinja_env is not None
    assert 'to_yaml' in generator.jinja_env.filters
    assert generator.jinja_env.keep_trailing_newline is True
    assert generator.jinja_env.trim_blocks is True


def test_to_yaml_filter(sample_config):
    """Test to_yaml Jinja filter."""
    generator = ConfigGenerator(sample_config, "config.yaml")

    test_data = {"key": "value", "nested": {"foo": "bar"}}
    yaml_output = generator.jinja_env.filters['to_yaml'](test_data)

    assert "key: value" in yaml_output
    assert "nested:" in yaml_output

def test_generate_mirroring_configs(sample_config, temp_dir):
    """Test that multiple hosts.toml files are generated when mirroring is enabled."""
    sample_config.environment.registry.mirroring.enabled = True
    sample_config.environment.registry.mirroring.docker_hub = True
    sample_config.environment.local_domain = "loko.local"
    sample_config.environment.registry.name = "registry"
    
    # Use a real ConfigGenerator but mock the file writing if needed, 
    # or just let it write to temp_dir
    generator = ConfigGenerator(sample_config, "config.yaml")
    generator.k8s_dir = temp_dir
    
    # We need to ensure the templates are picked up correctly
    generator.generate_configs()
    
    containerd_dir = Path(temp_dir) / "config" / "containerd"
    assert containerd_dir.exists()
    
    # Local registry
    assert (containerd_dir / "registry.loko.local" / "hosts.toml").exists()
    
    # Docker Hub mirror
    assert (containerd_dir / "docker.io" / "hosts.toml").exists()
    with open(containerd_dir / "docker.io" / "hosts.toml") as f:
        content = f.read()
        assert 'server = "https://registry-1.docker.io"' in content
        assert 'host."https://registry.loko.local/v2/dockerhub"' in content
