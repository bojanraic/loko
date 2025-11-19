import os
import yaml
from typing import Any, Dict
from pathlib import Path
from .config import RootConfig

def load_config(config_path: str) -> RootConfig:
    """Load configuration from a YAML file."""
    with open(config_path, "r") as f:
        raw_config = yaml.safe_load(f)
    return RootConfig(**raw_config)

def expand_env_vars(value: str) -> str:
    """Expand environment variables in a string."""
    return os.path.expandvars(value)

def deep_merge(source: Dict[str, Any], destination: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries."""
    for key, value in source.items():
        if isinstance(value, dict):
            node = destination.setdefault(key, {})
            deep_merge(value, node)
        else:
            destination[key] = value
    return destination
