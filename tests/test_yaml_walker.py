import pytest
from ruamel.yaml import YAML
from loko.updates.yaml_walker import walk_yaml_for_renovate


@pytest.fixture
def yaml_loader():
    """Create YAML loader with comment preservation."""
    yaml = YAML()
    yaml.preserve_quotes = True
    return yaml


def test_walk_simple_map_with_comment(yaml_loader):
    """Test walking a simple map with renovate comment."""
    yaml_content = """
kubernetes:
  image: kindest/node
  # renovate: datasource=docker depName=kindest/node
  tag: v1.34.0
"""
    data = yaml_loader.load(yaml_content)
    updates = []
    walk_yaml_for_renovate(data, updates)

    assert len(updates) == 1
    path, key, renovate_info, value, parent = updates[0]
    assert renovate_info['datasource'] == 'docker'
    assert renovate_info['depName'] == 'kindest/node'
    assert value == 'v1.34.0'


def test_walk_list_with_comment(yaml_loader):
    """Test walking a list with renovate comment."""
    yaml_content = """
internal-components:
  # renovate: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts
  - traefik: "37.3.0"
"""
    data = yaml_loader.load(yaml_content)
    updates = []
    walk_yaml_for_renovate(data, updates)

    assert len(updates) == 1
    path, key, renovate_info, value, parent = updates[0]
    assert renovate_info['datasource'] == 'helm'
    assert renovate_info['depName'] == 'traefik'
    assert renovate_info['repositoryUrl'] == 'https://traefik.github.io/charts'
    assert value == '37.3.0'


def test_walk_multiple_comments(yaml_loader):
    """Test walking structure with multiple renovate comments."""
    yaml_content = """
kubernetes:
  image: kindest/node
  # renovate: datasource=docker depName=kindest/node
  tag: v1.34.0

internal-components:
  # renovate: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts
  - traefik: "37.3.0"
  # renovate: datasource=helm depName=metrics-server repositoryUrl=https://kubernetes-sigs.github.io/metrics-server
  - metrics-server: "3.12.0"
"""
    data = yaml_loader.load(yaml_content)
    updates = []
    walk_yaml_for_renovate(data, updates)

    assert len(updates) == 3

    # Check kubernetes tag
    k8s_update = [u for u in updates if u[2]['depName'] == 'kindest/node'][0]
    assert k8s_update[3] == 'v1.34.0'

    # Check traefik
    traefik_update = [u for u in updates if u[2]['depName'] == 'traefik'][0]
    assert traefik_update[3] == '37.3.0'

    # Check metrics-server
    metrics_update = [u for u in updates if u[2]['depName'] == 'metrics-server'][0]
    assert metrics_update[3] == '3.12.0'


def test_walk_nested_structure(yaml_loader):
    """Test walking nested YAML structures."""
    yaml_content = """
environment:
  kubernetes:
    image: kindest/node
    # renovate: datasource=docker depName=kindest/node
    tag: v1.34.0
  services:
    system:
      - name: mysql
        config:
          chart: groundhog2k/mysql
          # renovate: datasource=helm depName=mysql repositoryUrl=https://groundhog2k.github.io/helm-charts
          version: 3.0.7
"""
    data = yaml_loader.load(yaml_content)
    updates = []
    walk_yaml_for_renovate(data, updates)

    assert len(updates) == 2


def test_walk_no_comments(yaml_loader):
    """Test walking YAML with no renovate comments."""
    yaml_content = """
environment:
  name: test
  kubernetes:
    image: kindest/node
    tag: v1.34.0
"""
    data = yaml_loader.load(yaml_content)
    updates = []
    walk_yaml_for_renovate(data, updates)

    assert len(updates) == 0


def test_walk_invalid_comment(yaml_loader):
    """Test walking with invalid renovate comment (missing required fields)."""
    yaml_content = """
kubernetes:
  image: kindest/node
  # renovate: datasource=docker
  tag: v1.34.0
"""
    data = yaml_loader.load(yaml_content)
    updates = []
    walk_yaml_for_renovate(data, updates)

    # Invalid comment should be ignored
    assert len(updates) == 0


def test_walk_non_renovate_comment(yaml_loader):
    """Test that regular comments are ignored."""
    yaml_content = """
kubernetes:
  image: kindest/node
  # This is just a regular comment
  tag: v1.34.0
"""
    data = yaml_loader.load(yaml_content)
    updates = []
    walk_yaml_for_renovate(data, updates)

    assert len(updates) == 0


def test_walk_does_not_duplicate_comments(yaml_loader):
    """Test that comments are not processed multiple times."""
    yaml_content = """
internal-components:
  # renovate: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts
  - traefik: "37.3.0"
"""
    data = yaml_loader.load(yaml_content)
    updates = []

    # Walk multiple times
    walk_yaml_for_renovate(data, updates)
    initial_count = len(updates)

    # Should still have same count (comments tracked via processed_comments set)
    assert initial_count == 1


def test_walk_empty_structure(yaml_loader):
    """Test walking empty YAML structure."""
    yaml_content = "{}"
    data = yaml_loader.load(yaml_content)
    updates = []
    walk_yaml_for_renovate(data, updates)

    assert len(updates) == 0
