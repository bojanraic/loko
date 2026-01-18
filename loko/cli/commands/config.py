"""Config commands: generate, upgrade, validate, port-check, dns-check, helm-repo management."""
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, List
from typing_extensions import Annotated
import typer
from rich.console import Console
from rich.table import Table
from ruamel.yaml import YAML
from pydantic import ValidationError

from loko.validators import ensure_config_file, ensure_docker_running, check_ports_available
from loko.updates import upgrade_config
from loko.cli_types import ConfigArg
from loko.utils import load_config, get_dns_container_name
from loko.runner import CommandRunner
from .lifecycle import _detect_local_ip


console = Console()


def generate_config(
    output: Annotated[str, typer.Option("--output", "-o", help="Output file path")] = "loko.yaml",
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing file")] = False,
    minimal: Annotated[bool, typer.Option("--minimal", "-m", help="Generate minimal config without comments or disabled sections")] = False
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

    if minimal:
        _generate_minimal_config(template_path, output, detected_ip)
    else:
        _generate_full_config(template_path, output, detected_ip)

    config_type = "minimal " if minimal else ""
    console.print(f"[bold green]Generated {config_type}configuration at '{output}'[/bold green]")
    console.print(f"[cyan]Detected local IP: {detected_ip}[/cyan]")
    if not minimal:
        console.print("[dim]You can modify the local-ip setting in the config file if needed.[/dim]")
    else:
        console.print("[dim]Use 'loko config generate' without --minimal for full documentation.[/dim]")


def _generate_full_config(template_path: Path, output: str, detected_ip: str) -> None:
    """Generate full config with comments from template."""
    with open(template_path, 'r') as f:
        content = f.read()

    # Replace the hardcoded IP with detected IP
    content = re.sub(
        r'ip:\s+\d+\.\d+\.\d+\.\d+',
        f'ip: {detected_ip}',
        content
    )

    with open(output, 'w') as f:
        f.write(content)


def _generate_minimal_config(template_path: Path, output: str, detected_ip: str) -> None:
    """Generate minimal config without comments or disabled sections."""
    import yaml

    # Load template as YAML (standard yaml, no comment preservation)
    with open(template_path, 'r') as f:
        data = yaml.safe_load(f)

    env = data.get('environment', {})

    # Update detected IP
    if 'network' in env:
        env['network']['ip'] = detected_ip

    # Use shared compaction logic
    data = _compact_config_data(data)

    # Write minimal YAML
    with open(output, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _compact_config_data(data: dict) -> dict:
    """
    Compact a config data dict by removing comments and disabled sections.

    Args:
        data: The config data dict (from yaml.safe_load)

    Returns:
        The compacted config data dict
    """
    env = data.get('environment', {})

    # Filter mirroring sources - keep only enabled ones and strip 'enabled' field
    if 'registry' in env and 'mirroring' in env['registry']:
        mirroring = env['registry']['mirroring']
        if 'sources' in mirroring:
            enabled_sources = []
            for s in mirroring['sources']:
                if s.get('enabled', False):
                    # Keep only the name, strip enabled field
                    enabled_sources.append({'name': s['name']})
            mirroring['sources'] = enabled_sources

    # Collect used helm repo refs from enabled workloads
    used_repos = set()

    # Filter system workloads - keep only enabled ones
    # Note: 'enabled' field is required on Workload model, cannot be stripped
    if 'workloads' in env and 'system' in env['workloads']:
        enabled_system = []
        for w in env['workloads']['system']:
            if w.get('enabled', False):
                # Track used repo ref
                if 'config' in w and 'repo' in w['config'] and 'ref' in w['config']['repo']:
                    used_repos.add(w['config']['repo']['ref'])
                enabled_system.append(w)
        env['workloads']['system'] = enabled_system

    # Filter user workloads - keep only enabled ones
    if 'workloads' in env and 'user' in env['workloads']:
        enabled_user = []
        for w in env['workloads']['user']:
            if w.get('enabled', False):
                if 'config' in w and 'repo' in w['config'] and 'ref' in w['config']['repo']:
                    used_repos.add(w['config']['repo']['ref'])
                enabled_user.append(w)
        env['workloads']['user'] = enabled_user

    # Filter helm-repositories to only include used ones
    if 'workloads' in env and 'helm-repositories' in env['workloads']:
        env['workloads']['helm-repositories'] = [
            repo for repo in env['workloads']['helm-repositories']
            if repo.get('name') in used_repos
        ]

    # Remove node labels if present (usually just examples)
    if 'cluster' in env and 'nodes' in env['cluster']:
        nodes = env['cluster']['nodes']
        if 'labels' in nodes:
            del nodes['labels']

    # Note: metrics-server is required in schema (no default), so we keep it

    return data


def config_compact(
    config_file: ConfigArg = "loko.yaml",
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="Output file path (default: overwrite input)")] = None,
) -> None:
    """
    Compact an existing configuration file by removing comments and disabled sections.

    This strips comments, disabled workloads, disabled mirroring sources, unused helm
    repositories, and example node labels to produce a minimal, clean config.
    """
    import yaml

    ensure_config_file(config_file)

    # Determine output path
    output_path = output if output else config_file

    # Load config without comment preservation
    with open(config_file, 'r') as f:
        data = yaml.safe_load(f)

    if not data or 'environment' not in data:
        console.print("[red]Error: Invalid config file structure[/red]")
        sys.exit(1)

    # Compact the data
    data = _compact_config_data(data)

    # Write compacted YAML
    with open(output_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    if output:
        console.print(f"[bold green]Compacted configuration written to '{output_path}'[/bold green]")
    else:
        console.print(f"[bold green]Configuration '{config_file}' has been compacted[/bold green]")
    console.print("[dim]Comments and disabled sections have been removed.[/dim]")


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


def dns_check(
    config_file: ConfigArg = "loko.yaml",
) -> None:
    """
    Check DNS configuration and resolution status.

    Displays DNS configuration details, checks if the DNS container is running,
    verifies resolver file setup, and tests DNS resolution.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    try:
        config = load_config(config_file)
    except Exception as e:
        console.print(f"[bold red]✗ Error loading configuration: {e}[/bold red]")
        sys.exit(1)

    env = config.environment
    network = env.network
    runner = CommandRunner(config)
    os_name = platform.system()

    # Determine the app domain
    if network.subdomain.enabled:
        app_domain = f"{network.subdomain.value}.{network.domain}"
    else:
        app_domain = network.domain

    console.print("[bold blue]DNS Configuration Check[/bold blue]\n")

    # General DNS Details
    console.print("[bold]📋 DNS Configuration:[/bold]")
    console.print(f"├── Domain: [cyan]{network.domain}[/cyan]")
    console.print(f"├── Apps Domain: [cyan]{app_domain}[/cyan]")
    console.print(f"├── DNS Port: [cyan]{network.dns_port}[/cyan]")
    console.print(f"└── IP Address: [cyan]{network.ip}[/cyan]\n")

    all_checks_passed = True

    # Check DNS Container
    console.print("[bold]🐳 DNS Container Status:[/bold]")
    dns_container = get_dns_container_name(env.name)

    try:
        dns_status = runner.list_containers(
            name_filter=dns_container,
            format_expr="{{.Names}}\t{{.Status}}",
            check=False
        )

        if dns_status:
            name, status_str = dns_status[0].split('\t', 1)
            if 'Up' in status_str:
                console.print(f"├── Container: [green]✓[/green] {name}")
                console.print(f"└── Status: [green]{status_str}[/green]\n")
            else:
                console.print(f"├── Container: [yellow]⚠[/yellow] {name}")
                console.print(f"└── Status: [yellow]{status_str}[/yellow]\n")
                all_checks_passed = False
        else:
            console.print(f"└── [red]✗ DNS container '{dns_container}' not found[/red]\n")
            all_checks_passed = False
    except Exception as e:
        console.print(f"└── [red]✗ Error checking container: {e}[/red]\n")
        all_checks_passed = False

    # Check Resolver File
    console.print("[bold]📄 Resolver Configuration:[/bold]")
    resolver_ok = False

    if os_name == "Darwin":  # macOS
        resolver_file = f"/etc/resolver/{network.domain}"
        if os.path.exists(resolver_file):
            try:
                with open(resolver_file, 'r') as f:
                    content = f.read()
                console.print(f"├── File: [green]✓[/green] {resolver_file}")
                # Check content
                has_nameserver = f"nameserver {network.ip}" in content
                has_port = f"port {network.dns_port}" in content
                if has_nameserver and has_port:
                    console.print(f"├── Nameserver: [green]✓[/green] {network.ip}")
                    console.print(f"└── Port: [green]✓[/green] {network.dns_port}\n")
                    resolver_ok = True
                else:
                    if not has_nameserver:
                        console.print(f"├── [yellow]⚠ Nameserver mismatch (expected {network.ip})[/yellow]")
                    if not has_port:
                        console.print(f"├── [yellow]⚠ Port mismatch (expected {network.dns_port})[/yellow]")
                    console.print(f"└── [yellow]Content:[/yellow]\n{content}\n")
            except PermissionError:
                console.print(f"├── File: [green]✓[/green] {resolver_file}")
                console.print(f"└── [yellow]⚠ Cannot read file (permission denied)[/yellow]\n")
        else:
            console.print(f"└── [red]✗ Resolver file not found: {resolver_file}[/red]")
            console.print(f"    [dim]Run 'loko init' or 'loko create' to set up DNS[/dim]\n")
            all_checks_passed = False

    elif os_name == "Linux":
        resolved_file = f"/etc/systemd/resolved.conf.d/{network.domain}.conf"
        if os.path.exists(resolved_file):
            try:
                with open(resolved_file, 'r') as f:
                    content = f.read()
                console.print(f"├── File: [green]✓[/green] {resolved_file}")
                console.print(f"└── [dim]systemd-resolved configured[/dim]\n")
                resolver_ok = True
            except PermissionError:
                console.print(f"├── File: [green]✓[/green] {resolved_file}")
                console.print(f"└── [yellow]⚠ Cannot read file (permission denied)[/yellow]\n")
        else:
            console.print(f"└── [red]✗ Resolver config not found: {resolved_file}[/red]")
            console.print(f"    [dim]Run 'loko init' or 'loko create' to set up DNS[/dim]\n")
            all_checks_passed = False
    else:
        console.print(f"└── [yellow]⚠ Resolver check not supported on {os_name}[/yellow]\n")

    # Test DNS Resolution
    console.print("[bold]🔍 DNS Resolution Test:[/bold]")
    test_hostname = f"registry.{network.domain}"

    try:
        # Use dig or nslookup to test DNS resolution
        dns_port = network.dns_port
        dns_ip = network.ip

        # Try using dig first (more common on macOS)
        result = subprocess.run(
            ["dig", f"@{dns_ip}", "-p", str(dns_port), test_hostname, "+short"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0 and result.stdout.strip():
            resolved_ip = result.stdout.strip().split('\n')[0]
            console.print(f"├── Query: [cyan]{test_hostname}[/cyan]")
            console.print(f"├── Server: [cyan]{dns_ip}:{dns_port}[/cyan]")
            if resolved_ip == dns_ip:
                console.print(f"└── Result: [green]✓ {resolved_ip}[/green] (correct)\n")
            else:
                console.print(f"└── Result: [yellow]⚠ {resolved_ip}[/yellow] (expected {dns_ip})\n")
                all_checks_passed = False
        else:
            console.print(f"├── Query: [cyan]{test_hostname}[/cyan]")
            console.print(f"├── Server: [cyan]{dns_ip}:{dns_port}[/cyan]")
            console.print(f"└── [red]✗ No response from DNS server[/red]\n")
            if result.stderr:
                console.print(f"    [dim]{result.stderr.strip()}[/dim]\n")
            all_checks_passed = False

    except FileNotFoundError:
        # dig not found, try nslookup
        try:
            result = subprocess.run(
                ["nslookup", f"-port={dns_port}", test_hostname, dns_ip],
                capture_output=True,
                text=True,
                timeout=5
            )
            console.print(f"├── Query: [cyan]{test_hostname}[/cyan]")
            if result.returncode == 0 and dns_ip in result.stdout:
                console.print(f"└── Result: [green]✓ DNS resolution working[/green]\n")
            else:
                console.print(f"└── [red]✗ DNS resolution failed[/red]\n")
                all_checks_passed = False
        except FileNotFoundError:
            console.print(f"└── [yellow]⚠ Neither 'dig' nor 'nslookup' found - cannot test resolution[/yellow]\n")
    except subprocess.TimeoutExpired:
        console.print(f"├── Query: [cyan]{test_hostname}[/cyan]")
        console.print(f"└── [red]✗ DNS query timed out[/red]\n")
        all_checks_passed = False
    except Exception as e:
        console.print(f"└── [red]✗ Error testing DNS: {e}[/red]\n")
        all_checks_passed = False

    # Summary
    console.print("=" * 50)
    if all_checks_passed:
        console.print("[bold green]✓ DNS configuration is healthy[/bold green]")
    else:
        console.print("[bold yellow]⚠ Some DNS checks did not pass[/bold yellow]")
        console.print("\n[dim]Tips:[/dim]")
        console.print("[dim]  • Ensure the environment is created: loko create[/dim]")
        console.print("[dim]  • Check if DNS container is running: docker ps | grep dns[/dim]")
        console.print("[dim]  • Restart DNS: loko stop && loko start[/dim]")




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
