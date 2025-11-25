import pytest
from pydantic import ValidationError
from loko.config import RootConfig, EnvironmentConfig, ProviderConfig, KubernetesConfig, NodesConfig, RegistryConfig

def test_valid_config():
    config_data = {
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
    }
    config = RootConfig(**config_data)
    assert config.environment.name == "test-env"
    assert config.environment.kubernetes.api_port == 6443

def test_invalid_config_missing_field():
    config_data = {
        "environment": {
            "name": "test-env"
            # Missing required fields
        }
    }
    with pytest.raises(ValidationError):
        RootConfig(**config_data)
