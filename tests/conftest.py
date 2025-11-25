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
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    return config_path
