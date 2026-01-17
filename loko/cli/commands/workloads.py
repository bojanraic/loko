"""Workload commands: list, deploy, undeploy."""
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
    name="workload",
    help="Manage cluster workloads (list, deploy, undeploy)",
    no_args_is_help=True,
)

@app.command(name="list")
def workloads_list(
    all_workloads: bool = typer.Option(False, "--all", "-a", help="Show all workloads including disabled"),
    internal_only: bool = typer.Option(False, "--internal", "-i", help="Show only enabled internal components (traefik, registry, metrics-server)"),
    system_only: bool = typer.Option(False, "--system", "-s", help="Show only enabled system workloads (postgres, mysql, etc.)"),
    user_only: bool = typer.Option(False, "--user", "-u", help="Show only enabled user-defined workloads"),
    enabled_only: bool = typer.Option(False, "--enabled", "-e", help="Show only enabled workloads"),
    disabled_only: bool = typer.Option(False, "--disabled", "-d", help="Show only disabled workloads"),
    config_file: ConfigArg = "loko.yaml"
) -> None:
    """
    List workloads and their status.

    By default shows all enabled workloads. Use filters to narrow down the list.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)
    runner = CommandRunner(config)

    # Determine what to include
    has_type_filter = internal_only or system_only or user_only
    has_status_filter = enabled_only or disabled_only

    # Type filters (which workload types to show)
    include_internal = internal_only or not has_type_filter
    include_system = system_only or not has_type_filter
    include_user = user_only or not has_type_filter

    # Status filters (enabled/disabled)
    # --all shows both enabled and disabled
    # --enabled shows only enabled
    # --disabled shows only disabled
    # default (no flag) shows only enabled
    if all_workloads:
        show_enabled = True
        show_disabled = True
    elif disabled_only:
        show_enabled = False
        show_disabled = True
    else:
        # Default or --enabled
        show_enabled = True
        show_disabled = False

    # Fetch workloads with disabled if needed
    status_list = runner.get_workloads_status(include_disabled=show_disabled)

    if not status_list:
        console.print("[yellow]No workloads found or could not retrieve status.[/yellow]")
        return

    # Group workloads by type and enabled status
    internal_enabled = [s for s in status_list if s['type'] == 'internal' and s.get('enabled', True)]
    system_enabled = [s for s in status_list if s['type'] == 'system' and s.get('enabled', True)]
    user_enabled = [s for s in status_list if s['type'] == 'user' and s.get('enabled', True)]
    disabled = [s for s in status_list if not s.get('enabled', True)]

    # Filter disabled by type if type filter is set
    if has_type_filter:
        disabled = [s for s in disabled
                    if (s['type'] == 'internal' and include_internal) or
                       (s['type'] == 'system' and include_system) or
                       (s['type'] == 'user' and include_user)]

    # Build table
    table = Table(title=f"Workloads Status for {config.environment.name}")
    table.add_column("Workload", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Namespace", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Pods", style="blue")
    table.add_column("Chart", style="dim")

    has_rows = False

    def add_rows(workloads: List[dict], add_section: bool = False):
        nonlocal has_rows
        if not workloads:
            return
        if add_section and has_rows:
            table.add_section()
        for s in workloads:
            status_val = s['status']
            if status_val in ['deployed', 'synced', 'ready']:
                status_style = "green"
            elif status_val == 'disabled':
                status_style = "dim"
            elif status_val == 'Not installed':
                status_style = "red"
            else:
                status_style = "yellow"
            table.add_row(s['name'], s['type'], s['namespace'],
                          f"[{status_style}]{status_val}[/{status_style}]", s['pods'], s['chart'])
        has_rows = True

    # Add enabled workloads by type
    if show_enabled:
        if include_internal:
            add_rows(internal_enabled)
        if include_system:
            add_rows(system_enabled, add_section=True)
        if include_user:
            add_rows(user_enabled, add_section=True)

    # Add disabled workloads
    if show_disabled and disabled:
        add_rows(disabled, add_section=True)

    if not has_rows:
        console.print("[yellow]No workloads match the criteria.[/yellow]")
        return

    console.print(table)

@app.command(name="deploy")
def workloads_deploy(
    workload_names: Optional[List[str]] = typer.Argument(None, help="Specific workload(s) to deploy"),
    all_types: bool = typer.Option(False, "--all", help="Include all workloads (user, system, and internal)"),
    user_only: bool = typer.Option(False, "--user", help="Include only user workloads"),
    system_only: bool = typer.Option(False, "--system", help="Include only system workloads"),
    internal_only: bool = typer.Option(False, "--internal", help="Include only internal workloads"),
    config_file: ConfigArg = "loko.yaml"
) -> None:
    """
    Deploy specified workloads or filtered workloads (defaults to user and system).
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)
    runner = CommandRunner(config)

    to_deploy = workload_names

    # Check if explicitly specified workloads are disabled
    if workload_names:
        all_wklds = runner.get_all_workloads()
        wkld_map = {w['name']: w for w in all_wklds}
        disabled_workloads = []

        for name in workload_names:
            if name in wkld_map and not wkld_map[name]['enabled']:
                disabled_workloads.append(name)

        if disabled_workloads:
            console.print(f"[red]Cannot deploy disabled workloads:[/red]")
            for wkld in disabled_workloads:
                console.print(f"  - {wkld}")
            console.print(f"\n[yellow]To deploy, enable these workloads in {config_file}[/yellow]")
            console.print(f"[dim]Set 'enabled: true' for each workload in the configuration file.[/dim]")
            raise typer.Exit(1)

    if not to_deploy:
        # Determine types to include
        include_user = user_only or all_types or (not system_only and not internal_only)
        include_system = system_only or all_types or (not user_only and not internal_only)
        include_internal = internal_only or all_types

        all_wklds = runner.get_all_workloads()
        filtered = []
        for w in all_wklds:
            if not w['enabled']:
                continue
            if w['type'] == 'user' and include_user:
                filtered.append(w['name'])
            elif w['type'] == 'system' and include_system:
                filtered.append(w['name'])
            elif w['type'] == 'internal' and include_internal:
                filtered.append(w['name'])

        to_deploy = filtered

    if not to_deploy:
        console.print("[yellow]No workloads match the criteria for deployment.[/yellow]")
        return

    runner.deploy_workloads(to_deploy)
    runner.fetch_workload_secrets(to_deploy)
    runner.configure_workloads(to_deploy)

@app.command(name="undeploy")
def workloads_undeploy(
    workload_names: Optional[List[str]] = typer.Argument(None, help="Specific workload(s) to undeploy"),
    all_types: bool = typer.Option(False, "--all", help="Include all workloads (user, system, and internal)"),
    user_only: bool = typer.Option(False, "--user", help="Include only user workloads"),
    system_only: bool = typer.Option(False, "--system", help="Include only system workloads"),
    internal_only: bool = typer.Option(False, "--internal", help="Include only internal workloads"),
    config_file: ConfigArg = "loko.yaml"
) -> None:
    """
    Undeploy specified workloads or filtered workloads (defaults to user and system).
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)
    runner = CommandRunner(config)

    to_undeploy = workload_names

    if not to_undeploy:
        # Determine types to include
        include_user = user_only or all_types or (not system_only and not internal_only)
        include_system = system_only or all_types or (not user_only and not internal_only)
        include_internal = internal_only or all_types

        all_wklds = runner.get_all_workloads()
        filtered = []
        for w in all_wklds:
            if not w['enabled']:
                continue
            if w['type'] == 'user' and include_user:
                filtered.append(w['name'])
            elif w['type'] == 'system' and include_system:
                filtered.append(w['name'])
            elif w['type'] == 'internal' and include_internal:
                filtered.append(w['name'])

        to_undeploy = filtered

    if not to_undeploy:
        console.print("[yellow]No workloads match the criteria for undeployment.[/yellow]")
        return

    runner.destroy_workloads(to_undeploy)
