"""Loko updater comment parser for extracting version check information.

This module parses loko-updater YAML comments to extract version checking
metadata. The comment syntax is used to track which components should be
checked for updates by the `loko config upgrade` command.

Supported comment formats:
    # loko-updater: datasource=docker depName=kindest/node
    # loko-updater: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts

Extracted fields:
- datasource: Source type (docker, helm)
- depName: Component/package name
- repositoryUrl: (optional) Custom repository URL for Helm charts

The parser is stateless and uses regex to extract key-value pairs from comments.
Used by walk_yaml_for_updater() to identify which components need version checks.
"""
import re
from typing import Optional


def parse_updater_comment(comment: str) -> Optional[dict]:
    """
    Parse a loko-updater comment and extract datasource, depName, repositoryUrl, and packageName.

    Example:
        # loko-updater: datasource=docker depName=kindest/node
        # loko-updater: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts
        # loko-updater: datasource=git-tags depName=garage packageName=https://git.deuxfleurs.fr/Deuxfleurs/garage.git
    """
    if 'loko-updater:' not in comment:
        return None

    result = {}

    # Extract datasource
    datasource_match = re.search(r'datasource=([\w\-]+)', comment)
    if datasource_match:
        result['datasource'] = datasource_match.group(1)

    # Extract depName
    depname_match = re.search(r'depName=([\w\-/\.]+)', comment)
    if depname_match:
        result['depName'] = depname_match.group(1)

    # Extract repositoryUrl (optional, used by helm datasource)
    repo_match = re.search(r'repositoryUrl=(https?://[^\s]+)', comment)
    if repo_match:
        result['repositoryUrl'] = repo_match.group(1)

    # Extract packageName (optional, used by git datasources)
    package_match = re.search(r'packageName=(https?://[^\s]+)', comment)
    if package_match:
        result['packageName'] = package_match.group(1)

    return result if 'datasource' in result and 'depName' in result else None
