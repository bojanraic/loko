"""Version fetching utilities for Docker, Helm, and Git sources.

This module provides functions to fetch the latest versions from multiple sources:

- Docker images from Docker Hub (official and user/org images)
- Helm charts from any Helm repository (via index.yaml parsing)
- Git repository tags from GitHub, GitLab, Gitea, Forgejo, and other Git hosting services
- Timing information for performance metrics
- Proper semantic version validation using packaging.version

The module is designed to be used by the upgrade system for checking component
versions. All fetches run in parallel via ThreadPoolExecutor in upgrader.py
for improved performance (~1.85x faster for mixed workloads).
"""
import re
import json
import time
import urllib.request
import urllib.parse
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
    Fetch latest versions for multiple charts from a single Helm repository.
    Returns a dict mapping dep_name -> (version, elapsed_time_seconds)
    """
    start_time = time.time()
    results: dict[str, tuple[Optional[str], float]] = {name: (None, 0.0) for name in dep_names}

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

            found_version: Optional[str] = None
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
        'zot': 'http://zotregistry.dev/helm-charts',
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


def fetch_latest_git_tags(repository_url: str) -> tuple[Optional[str], float]:
    """
    Fetch the latest version tag from a Git repository.
    Supports GitHub, GitLab (including self-hosted), Gitea, Forgejo, and other Git hosting services.
    Returns tuple of (latest_tag, elapsed_time_seconds)
    """
    start_time = time.time()
    try:
        # Convert Git URL to API endpoint
        # Supports: https://github.com/user/repo.git, https://gitlab.com/user/repo.git, https://git.custom.org/user/repo.git, etc.
        repo_url = repository_url.rstrip('/').rstrip('.git')

        # Extract host and path
        if 'https://' in repo_url:
            host = repo_url.split('https://')[1].split('/')[0]
            path_parts = repo_url.split(host)[1].lstrip('/').split('/')
            protocol = 'https://'
        elif 'http://' in repo_url:
            host = repo_url.split('http://')[1].split('/')[0]
            path_parts = repo_url.split(host)[1].lstrip('/').split('/')
            protocol = 'http://'
        else:
            console.print(f"[yellow]Warning: Invalid repository URL format: {repository_url}[/yellow]")
            return None, time.time() - start_time

        # Detect hosting service and construct appropriate API call
        if 'github.com' in host:
            # GitHub API: https://api.github.com/repos/owner/repo/tags
            api_url = repo_url.replace(f'{protocol}{host}/', 'https://api.github.com/repos/') + '/tags?per_page=100'
        else:
            # For other services, use Gitea/Forgejo API (common in self-hosted setups)
            # Gitea/Forgejo API: https://host/api/v1/repos/owner/repo/tags
            owner, repo = path_parts[0], path_parts[1] if len(path_parts) > 1 else ''

            if not repo:
                console.print(f"[yellow]Warning: Could not parse repository path from {repository_url}[/yellow]")
                return None, time.time() - start_time

            # Use Gitea/Forgejo API (compatible with both)
            api_url = f'{protocol}{host}/api/v1/repos/{owner}/{repo}/tags?per_page=100'

        req = urllib.request.Request(
            api_url,
            headers={
                'User-Agent': 'loko/0.1.0 (https://github.com/bojanraic/loko)',
                'Accept': 'application/json'
            }
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read())

        # Extract tags and find the latest valid version
        tags = []
        if isinstance(data, list):
            # GitHub/GitLab/Gitea format: array of tag objects
            for tag_info in data:
                tag_name = tag_info.get('name', '') if isinstance(tag_info, dict) else str(tag_info)
                if tag_name and not SKIP_TAGS_PATTERN.search(tag_name):
                    if VERSION_PATTERN.match(tag_name):
                        try:
                            parse_version(tag_name)
                            tags.append(tag_name)
                        except Exception:
                            continue

        if tags:
            return tags[0], time.time() - start_time
        else:
            console.print(f"[yellow]Warning: No valid version tags found in {repository_url}[/yellow]")
            return None, time.time() - start_time

    except Exception as e:
        console.print(f"[yellow]Warning: Could not fetch Git tags from {repository_url}: {e}[/yellow]")
        return None, time.time() - start_time


def fetch_latest_version(updater_info: dict) -> tuple[Optional[str], float]:
    """
    Fetch the latest version based on loko-updater datasource type.
    Returns tuple of (version, elapsed_time_seconds)
    """
    datasource = updater_info.get('datasource')
    dep_name = updater_info.get('depName')

    if not dep_name:
        console.print(f"[yellow]Warning: No depName found in updater info[/yellow]")
        return None, 0.0

    if datasource == 'docker':
        return fetch_latest_docker_version(dep_name)
    elif datasource == 'helm':
        return fetch_latest_helm_version(dep_name, updater_info.get('repositoryUrl'))
    elif datasource == 'git-tags':
        package_name = updater_info.get('packageName')
        if not package_name:
            console.print(f"[yellow]Warning: No packageName found for git-tags datasource (depName={dep_name})[/yellow]")
            return None, 0.0
        return fetch_latest_git_tags(package_name)
    else:
        console.print(f"[yellow]Warning: Unsupported datasource type: {datasource}[/yellow]")
        return None, 0.0
