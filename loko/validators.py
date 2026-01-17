"""Pre-flight validation checks for loko operations.

This module provides both check functions (return bool) and ensure functions
(exit on failure). Used by CLI commands to validate prerequisites before execution.

Check functions (return bool):
- check_docker_running(runtime) - Verify container runtime daemon is accessible
- check_config_file(config_path) - Verify config file exists and is readable
- check_base_dir_writable(base_dir) - Verify base directory is writable
- check_ports_available(config) - Verify all required ports are available

Ensure functions (exit on failure with helpful error messages):
- ensure_docker_running(runtime) - Exit if Docker/container runtime not running
- ensure_config_file(config_path) - Exit if config file missing, suggest solutions
- ensure_base_dir_writable(base_dir) - Exit if base dir not writable, suggest fixes
- ensure_single_server_cluster(servers) - Exit if multi-server cluster configured (not yet supported)
- ensure_ports_available(config) - Exit if any required ports are in use

Used by CLI commands in loko/cli/commands/:
- ensure_config_file() before commands that read config
- ensure_docker_running() before commands that use Docker (create, start, stop, etc.)
- ensure_base_dir_writable() before commands that write to base directory
- ensure_single_server_cluster() before commands that create/modify clusters
- ensure_ports_available() before cluster creation to check DNS, LB, and workload ports

Example usage:
    @app.command()
    def create(config: ConfigArg = "loko.yaml"):
        ensure_config_file(config)
        ensure_docker_running()
        config = get_config(config)
        ensure_single_server_cluster(config.environment.cluster.nodes.servers)
        ensure_ports_available(config)
        # ... rest of implementation
"""
import os
import sys
import subprocess
import socket
from typing import Tuple, List, Dict
from rich.console import Console

console = Console()


def check_docker_running(runtime: str = "docker") -> bool:
    """Check if docker/container runtime daemon is actually running."""
    try:
        result = subprocess.run(
            [runtime, "info"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_config_file(config_path: str) -> bool:
    """Check if config file exists and is readable."""
    return os.path.exists(config_path) and os.path.isfile(config_path)


def check_base_dir_writable(base_dir: str) -> bool:
    """Check if base directory is writable."""
    try:
        expanded_dir = os.path.expandvars(base_dir)
        # Try to write a test file
        test_file = os.path.join(expanded_dir, ".loko_write_test")
        os.makedirs(expanded_dir, exist_ok=True)
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        return True
    except (OSError, IOError):
        return False


def ensure_docker_running(runtime: str = "docker"):
    """Ensure docker daemon is running, exit with error if not."""
    if not check_docker_running(runtime):
        console.print(f"[bold red]❌ {runtime.capitalize()} daemon is not running.[/bold red]")
        console.print(f"[yellow]Start it first, then try again.[/yellow]")
        sys.exit(1)


def ensure_config_file(config_path: str):
    """Ensure config file exists, exit with error if not."""
    if not check_config_file(config_path):
        console.print(f"[bold red]❌ Configuration file '{config_path}' not found.[/bold red]")
        console.print(f"[yellow]You can:[/yellow]")
        console.print(f"[cyan]  1. Specify an existing config file:[/cyan]")
        console.print(f"[cyan]     loko <command> --config <path>[/cyan]")
        console.print(f"[cyan]  2. Generate a new config file:[/cyan]")
        console.print(f"[cyan]     loko config generate[/cyan]")
        sys.exit(1)


def ensure_base_dir_writable(base_dir: str):
    """Ensure base directory is writable, exit with error if not."""
    if not check_base_dir_writable(base_dir):
        expanded_dir = os.path.expandvars(base_dir)
        console.print(f"[bold red]❌ Base directory is not writable: {expanded_dir}[/bold red]")
        console.print(f"[yellow]Please ensure:[/yellow]")
        console.print(f"[cyan]  • The directory exists[/cyan]")
        console.print(f"[cyan]  • You have write permissions[/cyan]")
        console.print(f"[cyan]  • The filesystem is not read-only[/cyan]")
        console.print(f"\n[yellow]You can override the base directory with:[/yellow]")
        console.print(f"[cyan]  loko <command> --base-dir /path/to/writable/directory[/cyan]")
        sys.exit(1)


def ensure_single_server_cluster(servers: int):
    """Ensure cluster has only 1 control plane server (multi-server not yet supported)."""
    if servers > 1:
        console.print(f"[bold red]❌ Multi-control-plane clusters are not supported yet.[/bold red]")
        console.print(f"[yellow]You specified {servers} control plane servers, but only 1 is currently supported.[/yellow]")
        console.print(f"\n[yellow]Please update your configuration:[/yellow]")
        console.print(f"[cyan]  cluster:[/cyan]")
        console.print(f"[cyan]    nodes:[/cyan]")
        console.print(f"[cyan]      servers: 1[/cyan]")
        sys.exit(1)


def check_ports_available(config) -> Tuple[bool, Dict[str, List[int]]]:
    """Check if all required ports (DNS, LB, and workload ports) are available.

    Returns:
        Tuple of (all_available, conflicts) where conflicts is a dict mapping
        port categories to lists of unavailable ports.
    """
    from .config import RootConfig

    if not isinstance(config, RootConfig):
        return True, {}

    env = config.environment
    conflicts: Dict[str, List[int]] = {}

    # Check DNS port (now under network.dns_port)
    dns_port = env.network.dns_port
    if _is_port_in_use(dns_port):
        conflicts.setdefault('dns', []).append(dns_port)

    # Check load balancer ports (now under network.lb_ports)
    for port in env.network.lb_ports:
        if _is_port_in_use(port):
            conflicts.setdefault('load_balancer', []).append(port)

    # Check enabled workload ports
    enabled_workloads = (
        [wkld for wkld in env.workloads.system if wkld.enabled] +
        [wkld for wkld in env.workloads.user if wkld.enabled]
    )

    for workload in enabled_workloads:
        if workload.ports:
            for port in workload.ports:
                if _is_port_in_use(port):
                    conflicts.setdefault('workloads', []).append(port)

    return len(conflicts) == 0, conflicts


def _is_port_in_use(port: int) -> bool:
    """Check if a port is in use by attempting to bind to it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def ensure_ports_available(config):
    """Ensure all required ports are available, exit with error if not."""
    from .config import RootConfig

    if not isinstance(config, RootConfig):
        return

    available, conflicts = check_ports_available(config)

    if not available:
        console.print(f"[bold red]❌ Required ports are already in use[/bold red]")
        console.print(f"\n[yellow]The following ports must be available before cluster creation:[/yellow]\n")

        if 'dns' in conflicts:
            console.print(f"[bold cyan]DNS Port:[/bold cyan]")
            for port in conflicts['dns']:
                console.print(f"  • Port {port} (DNS service)")
            console.print(f"[dim]  Common culprits: systemd-resolved, dnsmasq, other DNS servers[/dim]\n")

        if 'load_balancer' in conflicts:
            console.print(f"[bold cyan]Load Balancer Ports:[/bold cyan]")
            for port in conflicts['load_balancer']:
                console.print(f"  • Port {port}")
            console.print(f"[dim]  These ports are used for ingress traffic routing[/dim]\n")

        if 'workloads' in conflicts:
            console.print(f"[bold cyan]Workload Ports:[/bold cyan]")
            for port in conflicts['workloads']:
                console.print(f"  • Port {port}")
            console.print(f"[dim]  These ports are mapped to enabled workloads[/dim]\n")

        console.print(f"[yellow]Solutions:[/yellow]")
        console.print(f"[cyan]  1. Stop the processes using these ports[/cyan]")
        console.print(f"[cyan]  2. Disable the conflicting workloads in your loko.yaml config[/cyan]")
        console.print(f"[cyan]  3. Change port mappings in your loko.yaml config[/cyan]")
        console.print(f"\n[yellow]To find what's using a port:[/yellow]")
        console.print(f"[cyan]  • On macOS: sudo lsof -i :<port>[/cyan]")
        console.print(f"[cyan]  • On Linux: sudo netstat -tlnp | grep :<port>[/cyan]")

        sys.exit(1)
