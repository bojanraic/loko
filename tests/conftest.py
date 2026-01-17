import pytest
import os
import shutil
import tempfile
import yaml
from pathlib import Path

@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

@pytest.fixture
def mock_config_path(temp_dir):
    """Create a mock config file."""
    config_path = os.path.join(temp_dir, "loko.yaml")
    config_data = {
        "environment": {
            "name": "test-cluster",
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
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    return config_path
