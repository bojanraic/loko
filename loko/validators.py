"""Pre-flight validation checks for loko operations.

This module provides both check functions (return bool) and ensure functions
(exit on failure). Used by CLI commands to validate prerequisites before execution.

Check functions (return bool):
- check_docker_running(runtime) - Verify container runtime daemon is accessible
- check_config_file(config_path) - Verify config file exists and is readable
- check_base_dir_writable(base_dir) - Verify base directory is writable

Ensure functions (exit on failure with helpful error messages):
- ensure_docker_running(runtime) - Exit if Docker/container runtime not running
- ensure_config_file(config_path) - Exit if config file missing, suggest solutions
- ensure_base_dir_writable(base_dir) - Exit if base dir not writable, suggest fixes
- ensure_single_server_cluster(servers) - Exit if multi-server cluster configured (not yet supported)

Used by CLI commands in loko/cli/commands/:
- ensure_config_file() before commands that read config
- ensure_docker_running() before commands that use Docker (create, start, stop, etc.)
- ensure_base_dir_writable() before commands that write to base directory
- ensure_single_server_cluster() before commands that create/modify clusters

Example usage:
    @app.command()
    def create(config: ConfigArg = "loko.yaml"):
        ensure_config_file(config)
        ensure_docker_running()
        config = get_config(config)
        ensure_single_server_cluster(config.environment.nodes.servers)
        # ... rest of implementation
"""
import os
import sys
import subprocess
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
        console.print(f"[cyan]     loko generate-config[/cyan]")
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
        console.print(f"[cyan]  nodes:[/cyan]")
        console.print(f"[cyan]    servers: 1[/cyan]")
        sys.exit(1)
