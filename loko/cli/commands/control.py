"""Control commands: start, stop."""
import sys
from rich.console import Console

from loko.validators import ensure_config_file, ensure_docker_running
from loko.runner import CommandRunner
from loko.cli_types import ConfigArg
from .lifecycle import get_config


console = Console()


def start(config_file: ConfigArg = "loko.yaml") -> None:
    """
    Start the environment.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    console.print("[bold green]Starting environment...[/bold green]")
    config = get_config(config_file)
    runner = CommandRunner(config)

    cluster_name = config.environment.name
    runtime = config.environment.provider.runtime

    # Get all cluster-related containers
    try:
        containers = runner.list_containers(name_filter=cluster_name, all_containers=True, format_expr="{{.Names}}")

        if not containers:
            console.print(f"[yellow]No containers found for cluster '{cluster_name}'[/yellow]")
            console.print("Run 'loko create' first to create the environment")
            sys.exit(1)

        # Check if all are already running
        all_running = True
        for container in containers:
            running = runner.list_containers(name_filter=container, status_filter="running", quiet=True, check=False)
            if not running:
                all_running = False
                break

        if all_running:
            console.print(f"[green]✅ Cluster '{cluster_name}' is already running[/green]")
            return

        # Start containers
        console.print(f"[blue]Starting all '{cluster_name}'-related containers...[/blue]")
        for container in containers:
            console.print(f"  ⏳ Starting {container}...")
            runner.run_command([runtime, "start", container])
            console.print(f"  ✅ Started {container}")

        console.print(f"[bold green]✅ Started cluster '{cluster_name}'[/bold green]")

    except Exception as e:
        console.print(f"[bold red]Error starting environment: {e}[/bold red]")
        sys.exit(1)


def stop(config_file: ConfigArg = "loko.yaml") -> None:
    """
    Stop the environment.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    console.print("[bold yellow]Stopping environment...[/bold yellow]")
    config = get_config(config_file)
    runner = CommandRunner(config)

    cluster_name = config.environment.name
    runtime = config.environment.provider.runtime

    # Get all cluster-related containers
    try:
        containers = runner.list_containers(name_filter=cluster_name, all_containers=True, format_expr="{{.Names}}")

        if not containers:
            console.print(f"[yellow]No containers found for cluster '{cluster_name}'[/yellow]")
            return

        # Check if all are already stopped
        all_stopped = True
        for container in containers:
            running = runner.list_containers(name_filter=container, status_filter="running", quiet=True, check=False)
            if running:
                all_stopped = False
                break

        if all_stopped:
            console.print(f"[green]ℹ️  Cluster '{cluster_name}' is already stopped[/green]")
            return

        # Stop containers
        console.print(f"[blue]Stopping all '{cluster_name}'-related containers...[/blue]")
        for container in containers:
            console.print(f"  ⏳ Stopping {container}...")
            runner.run_command([runtime, "stop", container])
            console.print(f"  ✅ Stopped {container}")

        console.print(f"[bold yellow]✅ Stopped cluster '{cluster_name}'[/bold yellow]")

    except Exception as e:
        console.print(f"[bold red]Error stopping environment: {e}[/bold red]")
        sys.exit(1)
