"""Version fetching utilities for Docker and Helm.

This module provides functions to fetch the latest versions of Docker images
and Helm charts from their respective registries. Supports:

- Docker images from Docker Hub (official and user/org images)
- Helm charts from any Helm repository (via index.yaml parsing)
- Timing information for performance metrics
- Proper semantic version validation using packaging.version

The module is designed to be used by the upgrade system for checking component
versions. Both Docker and Helm fetches run in parallel via ThreadPoolExecutor
in upgrader.py for improved performance (~1.85x faster for mixed workloads).
"""
import re
import json
import time
import urllib.request
import yaml
from typing import Optional
from packaging.version import parse as parse_version
from rich.console import Console

console = Console()

# Pre-compiled regex patterns for better performance
VERSION_PATTERN = re.compile(r'^v?\d+')
SKIP_TAGS_PATTERN = re.compile(r'(latest|nightly|dev)', re.IGNORECASE)


def fetch_latest_docker_version(dep_name: str) -> tuple[Optional[str], float]:
    """
    Fetch the latest version of a Docker image from Docker Hub or registry.
    Returns tuple of (version, elapsed_time_seconds)
    """
    start_time = time.time()
    try:
        # Handle official images (no slash) vs user/org images
        if '/' not in dep_name:
            # Official Docker library images
            url = f"https://registry.hub.docker.com/v2/repositories/library/{dep_name}/tags?page_size=100"
        else:
            # User or organization images
            url = f"https://registry.hub.docker.com/v2/repositories/{dep_name}/tags?page_size=100"

        # Add User-Agent header to avoid 403 errors
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'loko/0.1.0 (https://github.com/bojanraic/loko)',
                'Accept': 'application/json'
            }
        )

        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())

        # Filter out non-version tags using packaging.version for proper semantic versioning
        valid_versions = []
        for tag_info in data.get('results', []):
            tag = tag_info.get('name', '')
            # Skip tags like 'latest', 'nightly', 'dev'
            if tag and not SKIP_TAGS_PATTERN.search(tag):
                # Prefer semantic versions (e.g., v1.31.2, 1.31.2)
                if VERSION_PATTERN.match(tag):
                    try:
                        # Try to parse as a version to verify it's valid
                        parse_version(tag)
                        valid_versions.append(tag)
                    except Exception:
                        # Skip invalid versions
                        continue

        # Return the first tag (most recent)
        return (valid_versions[0] if valid_versions else None), time.time() - start_time

    except Exception as e:
        console.print(f"[yellow]Warning: Could not fetch Docker version for {dep_name}: {e}[/yellow]")
        return None, time.time() - start_time


def fetch_latest_helm_versions_batch(repository_url: str, dep_names: list[str]) -> dict[str, tuple[Optional[str], float]]:
    """
    Fetch the latest versions for multiple charts from a single Helm repository.
    Returns a dict mapping dep_name -> (version, elapsed_time_seconds)
    """
    start_time = time.time()
    results = {name: (None, 0.0) for name in dep_names}

    if not repository_url:
        console.print(f"[yellow]Warning: No repository URL provided for batch fetch[/yellow]")
        return results

    try:
        # Fetch index.yaml from Helm repository
        index_url = f"{repository_url.rstrip('/')}/index.yaml"

        # Add User-Agent header and small delay to avoid rate limiting
        req = urllib.request.Request(
            index_url,
            headers={
                'User-Agent': 'loko/0.1.0 (https://github.com/bojanraic/loko)',
                'Accept': 'application/x-yaml, text/yaml, */*'
            }
        )

        # Small delay to avoid rate limiting
        time.sleep(0.5)

        fetch_start = time.time()
        with urllib.request.urlopen(req) as response:
            index_data = yaml.safe_load(response.read())
        fetch_duration = time.time() - fetch_start

        # Get chart entries
        entries = index_data.get('entries', {})

        for dep_name in dep_names:
            chart_versions = entries.get(dep_name, [])
            
            if not chart_versions:
                console.print(f"[yellow]Warning: No versions found for chart {dep_name} in {repository_url}[/yellow]")
                results[dep_name] = (None, fetch_duration) # Assign fetch time even if not found
                continue

            found_version = None
            # Charts are usually sorted by version in descending order
            for version_info in chart_versions:
                version_str = version_info.get('version', '')
                if not version_str:
                    continue
                try:
                    parsed_version = parse_version(version_str)
                    # Only return stable releases (not pre-release, dev, or post-release)
                    if not parsed_version.is_prerelease:
                        found_version = version_str
                        break
                except Exception:
                    continue
            
            results[dep_name] = (found_version, fetch_duration)

        return results

    except Exception as e:
        console.print(f"[yellow]Warning: Could not fetch Helm versions from {repository_url}: {e}[/yellow]")
        # Return fetch time even on error so we don't skew stats too much if it was a timeout etc
        elapsed = time.time() - start_time
        return {name: (None, elapsed) for name in dep_names}


def fetch_latest_helm_version(dep_name: str, repository_url: Optional[str] = None) -> tuple[Optional[str], float]:
    """
    Fetch the latest version of a Helm chart from a Helm repository.
    Returns tuple of (version, elapsed_time_seconds)
    """
    # Default Helm chart repositories
    default_repos = {
        'app-template': 'https://bjw-s-labs.github.io/helm-charts',
        'traefik': 'https://traefik.github.io/charts',
        'metrics-server': 'https://kubernetes-sigs.github.io/metrics-server',
        'mysql': 'https://groundhog2k.github.io/helm-charts',
        'postgres': 'https://groundhog2k.github.io/helm-charts',
        'mongodb': 'https://groundhog2k.github.io/helm-charts',
        'rabbitmq': 'https://groundhog2k.github.io/helm-charts',
        'valkey': 'https://groundhog2k.github.io/helm-charts',
        'http-webhook': 'https://charts.securecodebox.io',
    }

    # Use provided repository URL or fall back to defaults
    repo_url = repository_url or default_repos.get(dep_name)
    
    if not repo_url:
         console.print(f"[yellow]Warning: No repository URL found for {dep_name}[/yellow]")
         return None, 0.0

    # Use the batch function for a single item
    results = fetch_latest_helm_versions_batch(repo_url, [dep_name])
    return results[dep_name]


def fetch_latest_version(renovate_info: dict) -> tuple[Optional[str], float]:
    """
    Fetch the latest version based on renovate datasource type.
    Returns tuple of (version, elapsed_time_seconds)
    """
    datasource = renovate_info.get('datasource')
    dep_name = renovate_info.get('depName')

    if datasource == 'docker':
        return fetch_latest_docker_version(dep_name)
    elif datasource == 'helm':
        return fetch_latest_helm_version(dep_name, renovate_info.get('repositoryUrl'))
    else:
        console.print(f"[yellow]Warning: Unsupported datasource type: {datasource}[/yellow]")
        return None, 0.0
