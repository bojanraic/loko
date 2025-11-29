"""Control commands: start, stop."""
import sys
from rich.console import Console

from loko.validators import ensure_config_file, ensure_docker_running
from loko.runner import CommandRunner
from loko.cli_types import ConfigArg
from loko.utils import get_dns_container_name, print_environment_summary
from .lifecycle import get_config


console = Console()


def start(config_file: ConfigArg = "loko.yaml") -> None:
    """
    Start the environment.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)
    cluster_name = config.environment.name
    runtime = config.environment.provider.runtime
    runner = CommandRunner(config)

    # Check if cluster exists first
    if not runner.cluster_exists():
        console.print(f"[yellow]⚠️  Cluster '{cluster_name}' does not exist[/yellow]")
        console.print("Run [bold]loko create[/bold] first to create the environment")
        sys.exit(1)

    # Check what needs to be started
    containers = runner.list_containers(name_filter=cluster_name, all_containers=True, format_expr="{{.Names}}")

    dns_container = get_dns_container_name(cluster_name)
    cluster_containers = [c for c in containers if c != dns_container]

    existing_containers = runner.list_containers(name_filter=dns_container, all_containers=True, format_expr="{{.Names}}", check=False)
    dns_exists = dns_container in existing_containers

    if not cluster_containers and not dns_exists:
        console.print(f"[yellow]⚠️  No containers found for cluster '{cluster_name}'[/yellow]")
        console.print("Run [bold]loko create[/bold] first to create the environment")
        sys.exit(1)

    cluster_stopped = False
    for container in cluster_containers:
        running_containers = runner.list_containers(name_filter=container, status_filter="running", format_expr="{{.Names}}", check=False)
        if container not in running_containers:
            cluster_stopped = True
            break

    dns_stopped = False
    if dns_exists:
        running_containers = runner.list_containers(name_filter=dns_container, status_filter="running", format_expr="{{.Names}}", check=False)
        dns_stopped = dns_container not in running_containers

    # If everything is already running
    if not cluster_stopped and not dns_stopped:
        console.print(f"[green]ℹ️  Environment '{cluster_name}' is already running[/green]")
        return

    # Something needs starting
    console.print(f"[bold green]Starting environment '{cluster_name}'...[/bold green]")

    # Start cluster containers if needed
    if cluster_stopped and cluster_containers:
        try:
            console.print(f"[blue]Starting cluster containers...[/blue]")
            for container in cluster_containers:
                running_containers = runner.list_containers(name_filter=container, status_filter="running", format_expr="{{.Names}}", check=False)
                if container not in running_containers:
                    console.print(f"  ⏳ Starting {container}...")
                    runner.run_command([runtime, "start", container])
                    console.print(f"  ✅ Started {container}")
        except Exception as e:
            console.print(f"[bold red]Error starting cluster containers: {e}[/bold red]")
            sys.exit(1)
    else:
        console.print(f"[green]ℹ️  Cluster containers are already running[/green]")

    # Start DNS container if it exists and is stopped
    if dns_exists and dns_stopped:
        try:
            console.print(f"[blue]Starting DNS service...[/blue]")
            console.print(f"  ⏳ Starting {dns_container}...")
            runner.run_command([runtime, "start", dns_container])
            console.print(f"  ✅ Started {dns_container}")
        except Exception as e:
            console.print(f"[yellow]⚠️  Could not start DNS container: {e}[/yellow]")
        # Verify DNS container started
        running_containers = runner.list_containers(name_filter=dns_container, status_filter="running", format_expr="{{.Names}}", check=False)
        dns_running = dns_container in running_containers
        if dns_exists and not dns_running:
            console.print(f"[yellow]⚠️  DNS container '{dns_container}' failed to start[/yellow]")
        elif dns_exists:
            console.print(f"[bold green]✅ DNS container '{dns_container}' is running[/bold green]")
    elif dns_exists:
        console.print(f"[green]ℹ️  DNS container '{dns_container}' is already running[/green]")
    else:
        console.print(f"[yellow]ℹ️  DNS container '{dns_container}' does not exist[/yellow]")
        console.print(f"[dim]Tip: Run [bold]loko create[/bold] to recreate the full environment[/dim]")

    # Verify all containers are running
    all_running = True
    for container in cluster_containers:
        running_containers = runner.list_containers(name_filter=container, status_filter="running", format_expr="{{.Names}}", check=False)
        if container not in running_containers:
            all_running = False
            console.print(f"[yellow]⚠️  Container '{container}' failed to start[/yellow]")
    if all_running:
        console.print(f"[bold green]✅ All containers for '{cluster_name}' are running[/bold green]")
    else:
        console.print(f"[red]❌ Some containers failed to start for '{cluster_name}'[/red]")
    console.print(f"[bold green]✅ Environment '{cluster_name}' started[/bold green]")

    # Print environment summary
    print_environment_summary(config)


def stop(config_file: ConfigArg = "loko.yaml") -> None:
    """
    Stop the environment.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)
    cluster_name = config.environment.name
    runtime = config.environment.provider.runtime
    runner = CommandRunner(config)

    # Check what needs to be stopped before announcing
    cluster_exists = runner.cluster_exists()
    dns_container = get_dns_container_name(cluster_name)
    cluster_running = False
    dns_running = False

    if cluster_exists:
        containers = runner.list_containers(name_filter=cluster_name, all_containers=True, format_expr="{{.Names}}")
        cluster_containers = [c for c in containers if c != dns_container]
        for container in cluster_containers:
            running_containers = runner.list_containers(name_filter=container, status_filter="running", format_expr="{{.Names}}", check=False)
            if container in running_containers:
                cluster_running = True
                break

    running_containers = runner.list_containers(name_filter=dns_container, status_filter="running", format_expr="{{.Names}}", check=False)
    dns_running = dns_container in running_containers

    # If nothing is running, report and exit early
    if not cluster_running and not dns_running:
        console.print(f"[green]ℹ️  Environment '{cluster_name}' is already stopped[/green]")
        return

    # Something needs stopping
    console.print(f"[bold yellow]Stopping environment '{cluster_name}'...[/bold yellow]")

    # Stop cluster containers if running
    if cluster_running:
        try:
            containers = runner.list_containers(name_filter=cluster_name, all_containers=True, format_expr="{{.Names}}")
            cluster_containers = [c for c in containers if c != dns_container]
            console.print(f"[blue]Stopping cluster containers...[/blue]")
            for container in cluster_containers:
                running_containers = runner.list_containers(name_filter=container, status_filter="running", format_expr="{{.Names}}", check=False)
                if container in running_containers:
                    console.print(f"  ⏳ Stopping {container}...")
                    runner.run_command([runtime, "stop", container])
                    console.print(f"  ✅ Stopped {container}")
        except Exception as e:
            console.print(f"[bold red]Error stopping cluster containers: {e}[/bold red]")
    elif not cluster_exists:
        console.print(f"[yellow]ℹ️  Cluster '{cluster_name}' does not exist[/yellow]")
    else:
        console.print(f"[green]ℹ️  Cluster containers are already stopped[/green]")

    # Stop DNS container if running
    if dns_running:
        try:
            console.print(f"[blue]Stopping DNS service...[/blue]")
            console.print(f"  ⏳ Stopping {dns_container}...")
            runner.run_command([runtime, "stop", dns_container])
            console.print(f"  ✅ Stopped {dns_container}")
        except Exception as e:
            console.print(f"[yellow]⚠️  Could not stop DNS container: {e}[/yellow]")
    else:
        existing_containers = runner.list_containers(name_filter=dns_container, all_containers=True, format_expr="{{.Names}}", check=False)
        dns_exists = dns_container in existing_containers
        if dns_exists:
            console.print(f"[green]ℹ️  DNS container '{dns_container}' is already stopped[/green]")
        else:
            console.print(f"[yellow]ℹ️  DNS container '{dns_container}' does not exist[/yellow]")

    # Verify all containers are stopped
    all_stopped = True
    # Get list of containers for the cluster
    containers_check = runner.list_containers(name_filter=cluster_name, all_containers=True, format_expr="{{.Names}}")
    cluster_containers_check = [c for c in containers_check if c != dns_container]
    for container in cluster_containers_check:
        running_containers = runner.list_containers(name_filter=container, status_filter="running", format_expr="{{.Names}}", check=False)
        if container in running_containers:
            all_stopped = False
            console.print(f"[yellow]⚠️  Container '{container}' failed to stop[/yellow]")
    if all_stopped:
        console.print(f"[bold green]✅ All containers for '{cluster_name}' are stopped[/bold green]")
    else:
        console.print(f"[red]❌ Some containers failed to stop for '{cluster_name}'[/red]")
    console.print(f"[bold green]✅ Environment '{cluster_name}' stopped[/bold green]")
