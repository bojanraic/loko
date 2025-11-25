import os
import pytest
from loko.utils import load_config, expand_env_vars, deep_merge, get_dns_container_name

def test_load_config(mock_config_path):
    config = load_config(mock_config_path)
    assert config.environment.name == "test-cluster"

def test_expand_env_vars():
    os.environ["TEST_VAR"] = "value"
    assert expand_env_vars("$TEST_VAR") == "value"
    assert expand_env_vars("prefix-$TEST_VAR-suffix") == "prefix-value-suffix"
    del os.environ["TEST_VAR"]

def test_deep_merge():
    source = {"a": 1, "b": {"c": 2}}
    dest = {"b": {"d": 3}, "e": 4}
    merged = deep_merge(source, dest)
    assert merged == {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}

def test_get_dns_container_name():
    assert get_dns_container_name("test") == "test-dns"
