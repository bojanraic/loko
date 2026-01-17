"""Registry commands: status, list-repos, show-repo, list-tags."""
import typer
from typing import Optional
from rich.console import Console
from rich.table import Table

from loko.validators import ensure_config_file, ensure_docker_running
from loko.cli_types import ConfigArg
from .lifecycle import get_config

console = Console()

app = typer.Typer(
    name="registry",
    help="Manage and inspect the local container registry",
    no_args_is_help=True,
)


def _get_registry_url(config) -> str:
    """Get the registry URL from config."""
    registry_name = config.environment.registry.name
    domain = config.environment.network.domain
    return f"https://{registry_name}.{domain}"


def _get_certs_dir(config) -> str:
    """Get the certs directory path from config."""
    import os
    base_dir = config.environment.base_dir
    env_name = config.environment.name
    # Expand environment variables if enabled
    if config.environment.expand_env_vars:
        base_dir = os.path.expandvars(base_dir)
    return os.path.join(base_dir, env_name, "certs")


def _fetch_registry_api(url: str, path: str, certs_dir: str) -> Optional[dict]:
    """Fetch data from registry API."""
    import urllib.request
    import urllib.error
    import json
    import ssl
    import os

    full_url = f"{url}{path}"

    # Create SSL context with local CA certificate
    ctx = ssl.create_default_context()
    ca_cert = os.path.join(certs_dir, "rootCA.pem")
    if os.path.exists(ca_cert):
        ctx.load_verify_locations(ca_cert)
    else:
        # Fallback: disable verification if cert not found
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(full_url)
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        console.print(f"[red]HTTP Error {e.code}: {e.reason}[/red]")
        return None
    except urllib.error.URLError as e:
        console.print(f"[red]Connection error: {e.reason}[/red]")
        console.print("[dim]Make sure the cluster is running and registry is deployed.[/dim]")
        return None
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return None


@app.command(name="status")
def registry_status(
    config_file: ConfigArg = "loko.yaml"
) -> None:
    """
    Show registry statistics and configuration.

    Displays registry URL, mirroring status, and basic statistics.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)
    registry_url = _get_registry_url(config)
    certs_dir = _get_certs_dir(config)
    registry_config = config.environment.registry

    console.print(f"\n[bold cyan]Registry Configuration[/bold cyan]")
    console.print(f"  URL: {registry_url}")
    console.print(f"  Storage Size: {registry_config.storage.size}")

    # Mirroring info
    mirroring = registry_config.mirroring
    console.print(f"\n[bold cyan]Mirroring[/bold cyan]")
    console.print(f"  Enabled: {'Yes' if mirroring.enabled else 'No'}")

    if mirroring.enabled and mirroring.sources:
        enabled_sources = [s.name for s in mirroring.sources if s.enabled]
        if enabled_sources:
            console.print(f"  Sources: {', '.join(enabled_sources)}")

    # Try to get catalog to count repos
    console.print(f"\n[bold cyan]Statistics[/bold cyan]")
    catalog = _fetch_registry_api(registry_url, "/v2/_catalog", certs_dir)

    if catalog and "repositories" in catalog:
        repos = catalog["repositories"]
        console.print(f"  Total Repositories: {len(repos)}")

        # Count by type (mirrored vs local)
        mirrored = [r for r in repos if "/" in r and not r.startswith("library/")]
        local = [r for r in repos if "/" not in r or r.startswith("library/")]
        console.print(f"  Local Images: {len(local)}")
        console.print(f"  Mirrored Images: {len(mirrored)}")
    else:
        console.print("  [dim]Could not fetch repository statistics[/dim]")

    console.print()


@app.command(name="list-repos")
def list_repos(
    config_file: ConfigArg = "loko.yaml"
) -> None:
    """
    List all repositories in the registry.

    Shows all images stored in the local registry, including mirrored images.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)
    registry_url = _get_registry_url(config)
    certs_dir = _get_certs_dir(config)

    catalog = _fetch_registry_api(registry_url, "/v2/_catalog", certs_dir)

    if not catalog or "repositories" not in catalog:
        console.print("[yellow]No repositories found or could not connect to registry.[/yellow]")
        return

    repos = sorted(catalog["repositories"])

    if not repos:
        console.print("[yellow]Registry is empty. No repositories found.[/yellow]")
        return

    console.print(f"\n[bold]Registry Repositories[/bold]")

    table = Table(show_header=True)
    table.add_column("Repository", style="cyan")
    table.add_column("Type", style="magenta")

    for repo in repos:
        # Determine if it's a mirrored image or local
        if "/" in repo and not repo.startswith("library/"):
            repo_type = "mirrored"
        else:
            repo_type = "local"

        table.add_row(repo, repo_type)

    console.print(table)
    console.print(f"\n[dim]Total: {len(repos)} repositories[/dim]")


def _resolve_repo_name(repo_name: str, registry_url: str, certs_dir: str) -> Optional[str]:
    """Resolve a repo name, looking up the full path with mirror prefix if needed.

    If the exact repo name exists, return it. Otherwise, search the catalog
    for a repo that ends with the given name (to handle mirror prefixes).
    """
    # First try exact match
    tags_data = _fetch_registry_api(registry_url, f"/v2/{repo_name}/tags/list", certs_dir)
    if tags_data:
        return repo_name

    # If not found, search catalog for matching repo
    catalog = _fetch_registry_api(registry_url, "/v2/_catalog", certs_dir)
    if not catalog or "repositories" not in catalog:
        return None

    repos = catalog["repositories"]

    # Look for repos that end with the given name (e.g., ghcr/org/repo matches org/repo)
    matches = [r for r in repos if r.endswith(f"/{repo_name}") or r == repo_name]

    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        console.print(f"[yellow]Multiple matches found for '{repo_name}':[/yellow]")
        for m in matches:
            console.print(f"  - {m}")
        console.print("[dim]Please specify the full repository path.[/dim]")
        return None

    return None


@app.command(name="show-repo")
def show_repo(
    repo_name: str = typer.Argument(..., help="Repository name (e.g., 'myapp' or 'controlplaneio-fluxcd/flux-operator')"),
    config_file: ConfigArg = "loko.yaml"
) -> None:
    """
    Show details about a specific repository.

    Displays available tags and manifest information for the given repository.
    For mirrored repos, the mirror prefix is automatically resolved.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)
    registry_url = _get_registry_url(config)
    certs_dir = _get_certs_dir(config)

    resolved_name = _resolve_repo_name(repo_name, registry_url, certs_dir)

    if not resolved_name:
        console.print(f"[yellow]Repository '{repo_name}' not found.[/yellow]")
        return

    tags_data = _fetch_registry_api(registry_url, f"/v2/{resolved_name}/tags/list", certs_dir)

    if not tags_data:
        console.print(f"[yellow]Repository '{repo_name}' not found.[/yellow]")
        return

    # Show resolved name if different from input
    if resolved_name != repo_name:
        console.print(f"[dim]Resolved to: {resolved_name}[/dim]")

    tags = tags_data.get("tags", [])

    console.print(f"\n[bold cyan]Repository: {resolved_name}[/bold cyan]")

    # Determine type based on resolved name
    if "/" in resolved_name and not resolved_name.startswith("library/"):
        console.print(f"  Type: mirrored")
    else:
        console.print(f"  Type: local")

    console.print(f"  Tags: {len(tags) if tags else 0}")

    if tags:
        console.print(f"\n[bold]Available Tags:[/bold]")
        # Show tags in a table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Tag", style="green")

        for tag in sorted(tags):
            table.add_row(tag)

        console.print(table)
    else:
        console.print("  [dim]No tags available[/dim]")

    console.print()


@app.command(name="list-tags")
def list_tags(
    repo_name: str = typer.Argument(..., help="Repository name (e.g., 'myapp' or 'controlplaneio-fluxcd/flux-operator')"),
    config_file: ConfigArg = "loko.yaml"
) -> None:
    """
    List all tags for a repository.

    Shows all available tags for the specified repository.
    For mirrored repos, the mirror prefix is automatically resolved.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)
    registry_url = _get_registry_url(config)
    certs_dir = _get_certs_dir(config)

    resolved_name = _resolve_repo_name(repo_name, registry_url, certs_dir)

    if not resolved_name:
        console.print(f"[yellow]Repository '{repo_name}' not found.[/yellow]")
        return

    # Show resolved name if different from input
    if resolved_name != repo_name:
        console.print(f"[dim]Resolved to: {resolved_name}[/dim]")

    tags_data = _fetch_registry_api(registry_url, f"/v2/{resolved_name}/tags/list", certs_dir)

    if not tags_data:
        console.print(f"[yellow]Repository '{repo_name}' not found.[/yellow]")
        return

    tags = tags_data.get("tags", [])

    if not tags:
        console.print(f"[yellow]No tags found for repository '{resolved_name}'.[/yellow]")
        return

    # Print title separately to avoid wrapping to narrow table width
    console.print(f"\n[bold]Tags for {resolved_name}[/bold]")

    table = Table(show_header=True)
    table.add_column("Tag", style="green")

    for tag in sorted(tags):
        table.add_row(tag)

    console.print(table)
    console.print(f"\n[dim]Total: {len(tags)} tags[/dim]")
