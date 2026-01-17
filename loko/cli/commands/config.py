"""Config commands: generate, upgrade, validate, port-check, helm-repo management."""
import os
import re
import sys
from pathlib import Path
from typing import Optional, List
from typing_extensions import Annotated
import typer
from rich.console import Console
from rich.table import Table
from ruamel.yaml import YAML
from pydantic import ValidationError

from loko.validators import ensure_config_file, check_ports_available
from loko.updates import upgrade_config
from loko.cli_types import ConfigArg
from loko.utils import load_config
from .lifecycle import _detect_local_ip


console = Console()


def generate_config(
    output: Annotated[str, typer.Option("--output", "-o", help="Output file path")] = "loko.yaml",
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing file")] = False
) -> None:
    """
    Generate a default configuration file with auto-detected local IP.
    """
    template_path = Path(__file__).parent.parent.parent / "templates" / "loko.yaml.example"

    if not template_path.exists():
        console.print("[bold red]Error: Default configuration template not found.[/bold red]")
        sys.exit(1)

    if os.path.exists(output) and not force:
        if not typer.confirm(f"File '{output}' already exists. Overwrite?"):
            console.print("[yellow]Operation cancelled.[/yellow]")
            sys.exit(0)

    # Auto-detect local IP
    detected_ip = _detect_local_ip()

    # Read template and replace IP
    with open(template_path, 'r') as f:
        content = f.read()

    # Replace the hardcoded IP with detected IP
    content = re.sub(
        r'ip:\s+\d+\.\d+\.\d+\.\d+',
        f'ip: {detected_ip}',
        content
    )

    # Write to output file
    with open(output, 'w') as f:
        f.write(content)

    console.print(f"[bold green]Generated configuration at '{output}'[/bold green]")
    console.print(f"[cyan]Detected local IP: {detected_ip}[/cyan]")
    console.print("[dim]You can modify the local-ip setting in the config file if needed.[/dim]")


def detect_ip() -> None:
    """
    Detect and display the local IP address.

    Uses multiple detection methods (default route, socket) to find the local IP
    that should be used for DNS resolution and wildcard certificates.
    """
    detected_ip = _detect_local_ip()
    console.print(f"[bold cyan]Detected local IP:[/bold cyan] {detected_ip}")
    console.print()
    console.print("[dim]If this IP is not correct, update the 'ip' value in your config file manually.[/dim]")


def config_upgrade(
    config_file: ConfigArg = "loko.yaml",
) -> None:
    """
    Upgrade component versions in config file by checking loko-updater comments.

    This command reads loko-updater comments in the config file and queries
    the appropriate datasources (Docker Hub, Helm repositories) to find the
    latest versions of components.
    """
    ensure_config_file(config_file)
    upgrade_config(config_file)


def config_validate(
    config_file: ConfigArg = "loko.yaml",
) -> None:
    """
    Validate the configuration file structure and values.

    This command loads the config file and validates it against the Pydantic
    schema to ensure all required fields are present and values are valid.
    """
    ensure_config_file(config_file)

    try:
        config = load_config(config_file)
        console.print(f"[bold green]✓ Configuration file '{config_file}' is valid[/bold green]")
        console.print(f"\n[cyan]Environment:[/cyan] {config.environment.name}")
        console.print(f"[cyan]Kubernetes:[/cyan] {config.environment.cluster.kubernetes.image}:{config.environment.cluster.kubernetes.tag}")
        console.print(f"[cyan]Domain:[/cyan] {config.environment.network.domain}")

        # Count enabled workloads
        system_enabled = sum(1 for w in config.environment.workloads.system if w.enabled)
        user_enabled = sum(1 for w in config.environment.workloads.user if w.enabled)
        console.print(f"[cyan]Workloads:[/cyan] {system_enabled} system, {user_enabled} user enabled")

    except ValidationError as e:
        console.print(f"[bold red]✗ Configuration file '{config_file}' is invalid[/bold red]\n")
        for error in e.errors():
            location = " → ".join(str(loc) for loc in error['loc'])
            console.print(f"[red]  • {location}:[/red] {error['msg']}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]✗ Error loading configuration: {e}[/bold red]")
        sys.exit(1)


def config_port_check(
    config_file: ConfigArg = "loko.yaml",
) -> None:
    """
    Check availability of all configured ports.

    Validates that DNS port, load balancer ports, and workload ports
    are available before cluster creation.
    """
    ensure_config_file(config_file)

    try:
        config = load_config(config_file)
    except Exception as e:
        console.print(f"[bold red]✗ Error loading configuration: {e}[/bold red]")
        sys.exit(1)

    env = config.environment
    available, conflicts = check_ports_available(config)

    # Build a table of all ports to check
    table = Table(title="Port Availability Check", show_header=True, header_style="bold magenta")
    table.add_column("Category", style="cyan")
    table.add_column("Port", style="yellow", justify="right")
    table.add_column("Status", style="green")
    table.add_column("Used By", style="dim")

    # DNS port
    dns_port = env.network.dns_port
    dns_status = "[red]✗ In use[/red]" if 'dns' in conflicts and dns_port in conflicts['dns'] else "[green]✓ Available[/green]"
    table.add_row("DNS", str(dns_port), dns_status, "dnsmasq")

    # Load balancer ports
    for port in env.network.lb_ports:
        lb_status = "[red]✗ In use[/red]" if 'load_balancer' in conflicts and port in conflicts['load_balancer'] else "[green]✓ Available[/green]"
        table.add_row("Load Balancer", str(port), lb_status, "traefik")

    # Workload ports
    enabled_workloads = (
        [wkld for wkld in env.workloads.system if wkld.enabled] +
        [wkld for wkld in env.workloads.user if wkld.enabled]
    )

    for workload in enabled_workloads:
        if workload.ports:
            for port in workload.ports:
                wkld_status = "[red]✗ In use[/red]" if 'workloads' in conflicts and port in conflicts['workloads'] else "[green]✓ Available[/green]"
                table.add_row("Workload", str(port), wkld_status, workload.name)

    console.print(table)

    if available:
        console.print(f"\n[bold green]✓ All ports are available[/bold green]")
    else:
        console.print(f"\n[bold red]✗ Some ports are in use[/bold red]")
        console.print(f"\n[yellow]To find what's using a port:[/yellow]")
        console.print(f"[cyan]  • On macOS: sudo lsof -i :<port>[/cyan]")
        console.print(f"[cyan]  • On Linux: sudo netstat -tlnp | grep :<port>[/cyan]")
        sys.exit(1)




def helm_repo_add(
    config_file: ConfigArg = "loko.yaml",
    repos: Annotated[
        Optional[List[str]],
        typer.Option(
            "--helm-repo-name",
            help="Helm repository name (repeat with --helm-repo-url for multiple repos)"
        )
    ] = None,
    urls: Annotated[
        Optional[List[str]],
        typer.Option(
            "--helm-repo-url",
            help="Helm repository URL (must be paired with --helm-repo-name)"
        )
    ] = None,
) -> None:
    """
    Add one or more Helm repositories to the config file.

    Repositories can be added using paired --helm-repo-name and --helm-repo-url options.
    Multiple repositories can be added in a single command:

    Example:
      loko config helm-repo add \\
        --helm-repo-name repo1 --helm-repo-url https://repo1.example.com \\
        --helm-repo-name repo2 --helm-repo-url https://repo2.example.com
    """
    ensure_config_file(config_file)

    # Validate that we have both names and URLs
    if not repos or not urls:
        console.print("[red]Error: Both --helm-repo-name and --helm-repo-url must be provided[/red]")
        sys.exit(1)

    if len(repos) != len(urls):
        console.print("[red]Error: Number of --helm-repo-name must match number of --helm-repo-url[/red]")
        sys.exit(1)

    # Load config with comment preservation
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False

    try:
        with open(config_file, 'r') as f:
            data = yaml.load(f)

        if not data or 'environment' not in data:
            console.print("[red]Error: Invalid config file structure[/red]")
            sys.exit(1)

        # Ensure helm-repositories list exists
        if 'helm-repositories' not in data['environment']:
            data['environment']['helm-repositories'] = []

        helm_repos = data['environment']['helm-repositories']
        added_count = 0

        for name, url in zip(repos, urls):
            # Check if repo already exists
            existing = any(repo.get('name') == name for repo in helm_repos)

            if existing:
                console.print(f"[yellow]⚠️  Repository '{name}' already exists, skipping[/yellow]")
                continue

            # Ensure URL ends with trailing slash for consistency
            repo_url = url.rstrip('/') + '/'

            # Add new repo
            helm_repos.append({'name': name, 'url': repo_url})
            console.print(f"[green]✓ Added repository: {name} → {repo_url}[/green]")
            added_count += 1

        if added_count > 0:
            # Write updated config back
            with open(config_file, 'w') as f:
                yaml.dump(data, f)
            console.print(f"\n[bold green]✅ Added {added_count} repository(ies) to {config_file}[/bold green]")
        else:
            console.print("[yellow]No new repositories were added[/yellow]")

    except Exception as e:
        console.print(f"[bold red]Error adding Helm repositories: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def helm_repo_remove(
    config_file: ConfigArg = "loko.yaml",
    repos: Annotated[
        Optional[List[str]],
        typer.Option(
            "--helm-repo-name",
            help="Helm repository name to remove (can be repeated for multiple repos)"
        )
    ] = None,
) -> None:
    """
    Remove one or more Helm repositories from the config file.

    Multiple repositories can be removed in a single command:

    Example:
      loko config helm-repo remove --helm-repo-name repo1 --helm-repo-name repo2
    """
    ensure_config_file(config_file)

    if not repos:
        console.print("[red]Error: At least one --helm-repo-name must be provided[/red]")
        sys.exit(1)

    # Load config with comment preservation
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False

    try:
        with open(config_file, 'r') as f:
            data = yaml.load(f)

        if not data or 'environment' not in data:
            console.print("[red]Error: Invalid config file structure[/red]")
            sys.exit(1)

        # Ensure helm-repositories list exists
        if 'helm-repositories' not in data['environment']:
            console.print("[yellow]No Helm repositories found in config[/yellow]")
            return

        helm_repos = data['environment']['helm-repositories']
        removed_count = 0

        for repo_name in repos:
            # Find and remove the repository
            initial_length = len(helm_repos)
            helm_repos[:] = [repo for repo in helm_repos if repo.get('name') != repo_name]

            if len(helm_repos) < initial_length:
                console.print(f"[green]✓ Removed repository: {repo_name}[/green]")
                removed_count += 1
            else:
                console.print(f"[yellow]⚠️  Repository '{repo_name}' not found[/yellow]")

        if removed_count > 0:
            # Write updated config back
            with open(config_file, 'w') as f:
                yaml.dump(data, f)
            console.print(f"\n[bold green]✅ Removed {removed_count} repository(ies) from {config_file}[/bold green]")
        else:
            console.print("[yellow]No repositories were removed[/yellow]")

    except Exception as e:
        console.print(f"[bold red]Error removing Helm repositories: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
