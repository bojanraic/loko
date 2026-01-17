import pytest
from pydantic import ValidationError
from loko.config import RootConfig, EnvironmentConfig, ProviderConfig, KubernetesConfig, NodesConfig, RegistryConfig

def test_valid_config():
    config_data = {
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
    }
    config = RootConfig(**config_data)
    assert config.environment.name == "test-env"
    assert config.environment.cluster.kubernetes.api_port == 6443

def test_invalid_config_missing_field():
    config_data = {
        "environment": {
            "name": "test-env"
            # Missing required fields
        }
    }
    with pytest.raises(ValidationError):
        RootConfig(**config_data)
