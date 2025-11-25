"""Renovate comment parser for extracting version check information.

This module parses Renovate-style YAML comments to extract version checking
metadata. Renovate is a service that keeps dependencies up-to-date by raising
pull requests. Loko uses the same comment syntax to track which components
should be checked for updates.

Supported comment formats:
    # renovate: datasource=docker depName=kindest/node
    # renovate: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts

Extracted fields:
- datasource: Source type (docker, helm)
- depName: Component/package name
- repositoryUrl: (optional) Custom repository URL for Helm charts

The parser is stateless and uses regex to extract key-value pairs from comments.
Used by walk_yaml_for_renovate() to identify which components need version checks.
"""
import re
from typing import Optional


def parse_renovate_comment(comment: str) -> Optional[dict]:
    """
    Parse a renovate comment and extract datasource, depName, and repositoryUrl.

    Example:
        # renovate: datasource=docker depName=kindest/node
        # renovate: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts
    """
    if 'renovate:' not in comment:
        return None

    result = {}

    # Extract datasource
    datasource_match = re.search(r'datasource=(\w+)', comment)
    if datasource_match:
        result['datasource'] = datasource_match.group(1)

    # Extract depName
    depname_match = re.search(r'depName=([\w\-/\.]+)', comment)
    if depname_match:
        result['depName'] = depname_match.group(1)

    # Extract repositoryUrl (optional)
    repo_match = re.search(r'repositoryUrl=(https?://[^\s]+)', comment)
    if repo_match:
        result['repositoryUrl'] = repo_match.group(1)

    return result if 'datasource' in result and 'depName' in result else None
