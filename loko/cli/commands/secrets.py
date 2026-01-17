"""Secret commands: fetch, show."""
import os
import typer
from rich.console import Console
from rich.panel import Panel

from loko.validators import ensure_config_file, ensure_docker_running
from loko.runner import CommandRunner
from loko.cli_types import ConfigArg
from .lifecycle import get_config

console = Console()

app = typer.Typer(
    name="secret",
    help="Manage workload secrets (fetch, show)",
    no_args_is_help=True,
)

@app.command(name="fetch")
def secrets_fetch(config_file: ConfigArg = "loko.yaml") -> None:
    """
    Fetch and save workload credentials to a file.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)
    runner = CommandRunner(config)

    runner.fetch_workload_secrets()

@app.command(name="show")
def secrets_show(config_file: ConfigArg = "loko.yaml") -> None:
    """
    Display workload credentials.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)
    runner = CommandRunner(config)

    secrets_path = runner.workload_secrets_path

    if not os.path.exists(secrets_path):
        console.print("[yellow]Secrets file not found. Fetching now...[/yellow]")
        runner.fetch_workload_secrets()

    if os.path.exists(secrets_path):
        with open(secrets_path, 'r') as f:
            content = f.read()

        console.print(Panel(content, title=f"Workload Secrets: {config.environment.name}", border_style="green"))
    else:
        console.print("[red]Could not retrieve secrets. Try deploying workloads first.[/red]")
