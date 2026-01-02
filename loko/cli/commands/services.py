"""Service commands: list, deploy, undeploy."""
import typer
from typing import Optional, List
from rich.console import Console
from rich.table import Table

from loko.validators import ensure_config_file, ensure_docker_running
from loko.runner import CommandRunner
from loko.cli_types import ConfigArg
from .lifecycle import get_config

console = Console()

app = typer.Typer(
    name="service",
    help="Manage cluster services (list, deploy, undeploy)",
    no_args_is_help=True,
)

@app.command(name="list")
def services_list(
    all_types: bool = typer.Option(True, "--all", help="Include all services (default)"),
    user_only: bool = typer.Option(False, "--user", help="Include only user services"),
    system_only: bool = typer.Option(False, "--system", help="Include only system services"),
    internal_only: bool = typer.Option(False, "--internal", help="Include only internal services"),
    config_file: ConfigArg = "loko.yaml"
) -> None:
    """
    List services and their status (defaults to all).
    """
    ensure_config_file(config_file)
    ensure_docker_running()
    
    config = get_config(config_file)
    runner = CommandRunner(config)
    
    status_list = runner.get_services_status()
    
    if not status_list:
        console.print("[yellow]No enabled services found or could not retrieve status.[/yellow]")
        return

    # Determine types to include
    # If all_types is True and no specific filter is set, show everything
    # If a specific filter is set, prioritize it
    has_specific_filter = user_only or system_only or internal_only
    
    include_user = user_only or (all_types and not has_specific_filter)
    include_system = system_only or (all_types and not has_specific_filter)
    include_internal = internal_only or (all_types and not has_specific_filter)

    filtered_status = [
        s for s in status_list 
        if (s['type'] == 'user' and include_user) or 
           (s['type'] == 'system' and include_system) or 
           (s['type'] == 'internal' and include_internal)
    ]

    if not filtered_status:
        console.print("[yellow]No services match the criteria.[/yellow]")
        return

    table = Table(title=f"Services Status for {config.environment.name}")
    table.add_column("Service", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Namespace", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Pods", style="blue")
    table.add_column("Chart", style="dim")
    
    for s in filtered_status:
        status_val = s['status']
        status_style = "green" if status_val in ['deployed', 'synced', 'ready'] else "yellow"
        if status_val == 'Not installed':
            status_style = "red"
            
        table.add_row(
            s['name'],
            s['type'],
            s['namespace'],
            f"[{status_style}]{status_val}[/{status_style}]",
            s['pods'],
            s['chart']
        )
    
    console.print(table)

@app.command(name="deploy")
def services_deploy(
    service_names: Optional[List[str]] = typer.Argument(None, help="Specific service(s) to deploy"),
    all_types: bool = typer.Option(False, "--all", help="Include all services (user, system, and internal)"),
    user_only: bool = typer.Option(False, "--user", help="Include only user services"),
    system_only: bool = typer.Option(False, "--system", help="Include only system services"),
    internal_only: bool = typer.Option(False, "--internal", help="Include only internal services"),
    config_file: ConfigArg = "loko.yaml"
) -> None:
    """
    Deploy specified services or filtered services (defaults to user and system).
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)
    runner = CommandRunner(config)

    to_deploy = service_names

    # Check if explicitly specified services are disabled
    if service_names:
        all_svcs = runner.get_all_services()
        svc_map = {s['name']: s for s in all_svcs}
        disabled_services = []

        for name in service_names:
            if name in svc_map and not svc_map[name]['enabled']:
                disabled_services.append(name)

        if disabled_services:
            console.print(f"[red]❌ Cannot deploy disabled services:[/red]")
            for svc in disabled_services:
                console.print(f"  • {svc}")
            console.print(f"\n[yellow]To deploy, enable these services in {config_file}[/yellow]")
            console.print(f"[dim]Set 'enabled: true' for each service in the configuration file.[/dim]")
            raise typer.Exit(1)

    if not to_deploy:
        # Determine types to include
        include_user = user_only or all_types or (not system_only and not internal_only)
        include_system = system_only or all_types or (not user_only and not internal_only)
        include_internal = internal_only or all_types
        
        all_svcs = runner.get_all_services()
        filtered = []
        for s in all_svcs:
            if not s['enabled']:
                continue
            if s['type'] == 'user' and include_user:
                filtered.append(s['name'])
            elif s['type'] == 'system' and include_system:
                filtered.append(s['name'])
            elif s['type'] == 'internal' and include_internal:
                filtered.append(s['name'])
        
        to_deploy = filtered

    if not to_deploy:
        console.print("[yellow]No services match the criteria for deployment.[/yellow]")
        return

    runner.deploy_services(to_deploy)
    runner.fetch_service_secrets(to_deploy)
    runner.configure_services(to_deploy)

@app.command(name="undeploy")
def services_undeploy(
    service_names: Optional[List[str]] = typer.Argument(None, help="Specific service(s) to undeploy"),
    all_types: bool = typer.Option(False, "--all", help="Include all services (user, system, and internal)"),
    user_only: bool = typer.Option(False, "--user", help="Include only user services"),
    system_only: bool = typer.Option(False, "--system", help="Include only system services"),
    internal_only: bool = typer.Option(False, "--internal", help="Include only internal services"),
    config_file: ConfigArg = "loko.yaml"
) -> None:
    """
    Undeploy specified services or filtered services (defaults to user and system).
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)
    runner = CommandRunner(config)

    to_undeploy = service_names

    if not to_undeploy:
        # Determine types to include
        include_user = user_only or all_types or (not system_only and not internal_only)
        include_system = system_only or all_types or (not user_only and not internal_only)
        include_internal = internal_only or all_types
        
        all_svcs = runner.get_all_services()
        filtered = []
        for s in all_svcs:
            if not s['enabled']:
                continue
            if s['type'] == 'user' and include_user:
                filtered.append(s['name'])
            elif s['type'] == 'system' and include_system:
                filtered.append(s['name'])
            elif s['type'] == 'internal' and include_internal:
                filtered.append(s['name'])
        
        to_undeploy = filtered

    if not to_undeploy:
        console.print("[yellow]No services match the criteria for undeployment.[/yellow]")
        return

    runner.destroy_services(to_undeploy)
