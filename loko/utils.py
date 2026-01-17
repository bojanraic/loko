import os
import yaml
from typing import Any, Dict
from pathlib import Path
import socket
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from .config import RootConfig

console = Console()

PASSWORD_PROTECTED_WORKLOADS = {
    "mysql",
    "postgres",
    "mongodb",
    "rabbitmq",
    "valkey",
    "garage"
}

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

def get_dns_container_name(environment_name: str) -> str:
    """Get DNS container name for the given environment."""
    return f"{environment_name}-dns"

def is_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def print_environment_summary(config: RootConfig):
    """Print a summary of the environment after creation/start."""
    env = config.environment
    network = env.network

    # Determine the app domain
    if network.subdomain.enabled:
        app_domain = f"{network.subdomain.value}.{network.domain}"
    else:
        app_domain = network.domain

    # Build the summary
    console.print("\n" + "="*60)
    console.print(Panel.fit(
        f"[bold green]Environment '{env.name}' is ready![/bold green]",
        border_style="green"
    ))

    # Environment info
    console.print(f"\n[bold cyan]Environment Information:[/bold cyan]")
    console.print(f"  Name:              [yellow]{env.name}[/yellow]")
    console.print(f"  Kubeconfig:        [yellow]kind-{env.name}[/yellow]")
    console.print(f"  Domain:            [yellow]{network.domain}[/yellow]")
    console.print(f"  Apps Domain:       [yellow]{app_domain}[/yellow]")

    # Enabled workloads
    enabled_workloads = [wkld for wkld in env.workloads.system if wkld.enabled]
    if enabled_workloads:
        console.print(f"\n[bold cyan]Enabled System Workloads:[/bold cyan]")

        # Create table for workloads
        table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 2))
        table.add_column("Workload", style="cyan")
        table.add_column("DNS Name", style="yellow")
        table.add_column("Ports", style="green")

        for wkld in enabled_workloads:
            dns_name = f"{wkld.name}.{network.domain}"
            ports = ", ".join(str(p) for p in wkld.ports) if wkld.ports else "N/A"
            table.add_row(wkld.name, dns_name, ports)

        console.print(table)
    else:
        console.print(f"\n[dim]No system workloads enabled[/dim]")

    password_workloads_enabled = {
        wkld.name
        for wkld in (env.workloads.system + env.workloads.user)
        if wkld.enabled and wkld.name in PASSWORD_PROTECTED_WORKLOADS
    }

    if password_workloads_enabled:
        secrets_file = os.path.join(os.path.expandvars(env.base_dir), env.name, 'workload-secrets.txt')
        console.print(f"\n[bold cyan]Workload Credentials:[/bold cyan]")
        console.print(f"  Location: [yellow]{secrets_file}[/yellow]")

    # App deployment info
    console.print(f"\n[bold cyan]Deploying Applications:[/bold cyan]")
    console.print(f"  Apps with a valid ingress will be accessible at: [yellow]https://<app-name>.{app_domain}[/yellow]")
    console.print(f"  Example: [dim]https://myapp.{app_domain}[/dim]")

    # Registry info
    console.print(f"\n[bold cyan]Container Registry:[/bold cyan]")
    console.print(f"  URL: [yellow]{env.registry.name}.{network.domain}[/yellow]")

    console.print("\n" + "="*60 + "\n")
