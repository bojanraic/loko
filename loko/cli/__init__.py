import os
import sys
import shutil
import subprocess
import typer
import urllib.request
import re
from typing import Optional, List
from typing_extensions import Annotated
from pathlib import Path
from importlib.metadata import metadata

# Detect if running from source directory (editable install) vs installed package
def _is_running_from_source() -> bool:
    """Check if loko is running from source (editable install) or as installed package."""
    try:
        # Get the path to this file
        cli_path = Path(__file__).resolve()
        # Check if we're in a git repository (indicates source/editable install)
        git_dir = cli_path.parent.parent.parent / ".git"
        return git_dir.exists()
    except Exception:
        return False

# Use LOKO_DEV env var if set, otherwise auto-detect based on source vs installed
_RUNNING_FROM_SOURCE = _is_running_from_source()
_DEV_MODE = os.getenv("LOKO_DEV", "").lower() == "true" or _RUNNING_FROM_SOURCE

from rich.console import Console

from loko.config import RootConfig
from loko.utils import load_config, get_dns_container_name
from loko.generator import ConfigGenerator
from loko.runner import CommandRunner
from loko.validators import (
    check_docker_running,
    check_config_file,
    check_base_dir_writable,
    ensure_docker_running,
    ensure_config_file,
    ensure_base_dir_writable,
)
from loko.cli_types import (
    ConfigArg,
    TemplatesDirArg,
    NameArg,
    DomainArg,
    WorkersArg,
    ControlPlanesArg,
    RuntimeArg,
    LocalIPArg,
    K8sVersionArg,
    LBPortsArg,
    AppsSubdomainArg,
    ServicePresetsArg,
    MetricsServerArg,
    EnableServiceArg,
    DisableServiceArg,
    BaseDirArg,
    ExpandVarsArg,
    K8sAPIPortArg,
    ScheduleOnControlArg,
    InternalOnControlArg,
    RegistryNameArg,
    RegistryStorageArg,
    ServicesOnWorkersArg,
)
from loko.updates import upgrade_config
from .commands.lifecycle import (
    init as lifecycle_init,
    create as lifecycle_create,
    destroy as lifecycle_destroy,
    recreate as lifecycle_recreate,
    clean as lifecycle_clean,
)
from .commands.control import (
    start as control_start,
    stop as control_stop,
)
from .commands.status import (
    status as status_status,
    validate as status_validate,
)
from .commands.config import (
    generate_config as config_generate,
    config_upgrade as config_upgrade_cmd,
    secrets_fetch as config_secrets,
    helm_repo_add,
    helm_repo_remove,
)
from .commands.utility import (
    version as utility_version,
    check_prerequisites as utility_check_prerequisites,
)

def get_repository_url() -> str:
    """Get the repository URL from package metadata."""
    try:
        meta = metadata('loko')
        repo_url = meta.get('Home-page') or meta.get('Project-URL', '').split(',')[-1].strip()
        if repo_url:
            # Convert GitHub URL to raw content URL
            if 'github.com' in repo_url:
                repo_url = repo_url.rstrip('/')
                return f"{repo_url.replace('github.com', 'raw.githubusercontent.com')}/main/loko/templates/loko.yaml.example"
    except Exception:
        pass
    # Fallback to hardcoded URL
    return "https://raw.githubusercontent.com/bojanraic/loko/main/loko/templates/loko.yaml.example"


def version_callback(
    version: bool = typer.Option(None, "--version", "-v", help="Show version and exit"),
    help_opt: bool = typer.Option(None, "--help", "-h", help="Show this message and exit.")
):
    """Handle --version and --help options."""
    if help_opt:
        import click
        ctx = click.get_current_context()
        click.echo(ctx.get_help(), color=ctx.color)
        ctx.exit()
    if version:
        utility_version()
        raise typer.Exit()

app = typer.Typer(
    name="loko",
    help="Local Kubernetes Environment Manager - Create and manage local K8s clusters with Kind, DNS via dnsmasq, SSL certificates via mkcert, and service deployment via Helm/Helmfile. Perfect for local development without cloud dependencies.",
    add_completion=True,
    no_args_is_help=True,
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=_DEV_MODE,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.callback(invoke_without_command=True)(version_callback)
config_app = typer.Typer(
    name="config",
    help="Manage configuration",
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(config_app)

console = Console()

# Import lifecycle commands and utilities
from .commands.lifecycle import (
    _detect_local_ip,
    get_config,
)

@app.command()
def init(
    config_file: ConfigArg = "loko.yaml",
    templates_dir: TemplatesDirArg = None,
    name: NameArg = None,
    domain: DomainArg = None,
    workers: WorkersArg = None,
    control_planes: ControlPlanesArg = None,
    runtime: RuntimeArg = None,
    local_ip: LocalIPArg = None,
    k8s_version: K8sVersionArg = None,
    lb_ports: LBPortsArg = None,
    apps_subdomain: AppsSubdomainArg = None,
    service_presets: ServicePresetsArg = None,
    metrics_server: MetricsServerArg = None,
    enable_service: EnableServiceArg = None,
    disable_service: DisableServiceArg = None,
    base_dir: BaseDirArg = None,
    expand_vars: ExpandVarsArg = None,
    k8s_api_port: K8sAPIPortArg = None,
    schedule_on_control: ScheduleOnControlArg = None,
    internal_on_control: InternalOnControlArg = None,
    registry_name: RegistryNameArg = None,
    registry_storage: RegistryStorageArg = None,
    services_on_workers: ServicesOnWorkersArg = None,
):
    """
    Initialize the local environment (generate configs, setup certs, network).
    """
    lifecycle_init(
        config_file, templates_dir, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, service_presets,
        metrics_server, enable_service, disable_service,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, services_on_workers
    )

@app.command()
def create(
    config_file: ConfigArg = "loko.yaml",
    templates_dir: TemplatesDirArg = None,
    name: NameArg = None,
    domain: DomainArg = None,
    workers: WorkersArg = None,
    control_planes: ControlPlanesArg = None,
    runtime: RuntimeArg = None,
    local_ip: LocalIPArg = None,
    k8s_version: K8sVersionArg = None,
    lb_ports: LBPortsArg = None,
    apps_subdomain: AppsSubdomainArg = None,
    service_presets: ServicePresetsArg = None,
    metrics_server: MetricsServerArg = None,
    enable_service: EnableServiceArg = None,
    disable_service: DisableServiceArg = None,
    base_dir: BaseDirArg = None,
    expand_vars: ExpandVarsArg = None,
    k8s_api_port: K8sAPIPortArg = None,
    schedule_on_control: ScheduleOnControlArg = None,
    internal_on_control: InternalOnControlArg = None,
    registry_name: RegistryNameArg = None,
    registry_storage: RegistryStorageArg = None,
    services_on_workers: ServicesOnWorkersArg = None,
):
    """
    Create the full environment.
    """
    lifecycle_create(
        config_file, templates_dir, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, service_presets,
        metrics_server, enable_service, disable_service,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, services_on_workers
    )

@app.command()
def destroy(config_file: ConfigArg = "loko.yaml"):
    """
    Destroy the environment.
    """
    lifecycle_destroy(config_file)

@app.command()
def recreate(
    config_file: ConfigArg = "loko.yaml",
    templates_dir: TemplatesDirArg = None,
    name: NameArg = None,
    domain: DomainArg = None,
    workers: WorkersArg = None,
    control_planes: ControlPlanesArg = None,
    runtime: RuntimeArg = None,
    local_ip: LocalIPArg = None,
    k8s_version: K8sVersionArg = None,
    lb_ports: LBPortsArg = None,
    apps_subdomain: AppsSubdomainArg = None,
    service_presets: ServicePresetsArg = None,
    metrics_server: MetricsServerArg = None,
    enable_service: EnableServiceArg = None,
    disable_service: DisableServiceArg = None,
    base_dir: BaseDirArg = None,
    expand_vars: ExpandVarsArg = None,
    k8s_api_port: K8sAPIPortArg = None,
    schedule_on_control: ScheduleOnControlArg = None,
    internal_on_control: InternalOnControlArg = None,
    registry_name: RegistryNameArg = None,
    registry_storage: RegistryStorageArg = None,
    services_on_workers: ServicesOnWorkersArg = None,
):
    """
    Recreate the environment (destroy + create).
    """
    lifecycle_recreate(
        config_file, templates_dir, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, service_presets,
        metrics_server, enable_service, disable_service,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, services_on_workers
    )

@app.command()
def clean(config_file: ConfigArg = "loko.yaml"):
    """
    Clean up the environment (destroy + remove artifacts).
    """
    lifecycle_clean(config_file)



@app.command()
def start(config_file: ConfigArg = "loko.yaml"):
    """
    Start the environment.
    """
    control_start(config_file)

@app.command()
def stop(config_file: ConfigArg = "loko.yaml"):
    """
    Stop the environment.
    """
    control_stop(config_file)

@app.command()
def status(config_file: ConfigArg = "loko.yaml"):
    """
    Show environment status.
    """
    status_status(config_file)

@app.command()
def validate(config_file: ConfigArg = "loko.yaml"):
    """
    Validate the environment.
    """
    status_validate(config_file)

@app.command()
def secrets(config_file: ConfigArg = "loko.yaml"):
    """
    Fetch and save service credentials to a file.
    """
    config_secrets(config_file)

@app.command()
def version():
    """
    Print the current version of loko.
    """
    utility_version()

@app.command()
def help():
    """
    Show help message.
    """
    import click
    ctx = click.get_current_context().parent
    console.print(ctx.get_help())

@app.command(name="check-prerequisites")
def check_prerequisites():
    """
    Check if all required tools are installed.
    """
    utility_check_prerequisites()


@app.command(name="generate-config")
def generate_config(
    output: Annotated[str, typer.Option("--output", "-o", help="Output file path")] = "loko.yaml",
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing file")] = False
):
    """
    Generate a default configuration file with auto-detected local IP.
    """
    config_generate(output, force)


@config_app.command("upgrade")
def config_upgrade_command(
    config_file: ConfigArg = "loko.yaml",
):
    """
    Upgrade component versions in config file by checking renovate comments.

    This command reads renovate-style comments in the config file and queries
    the appropriate datasources (Docker Hub, Helm repositories) to find the
    latest versions of components.
    """
    config_upgrade_cmd(config_file)


@config_app.command(name="helm-repo-add")
def helm_repo_add_command(
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
):
    """
    Add one or more Helm repositories to the config file.

    Repositories can be added using paired --helm-repo-name and --helm-repo-url options.
    Multiple repositories can be added in a single command:

    Example:
      loko config helm-repo-add \\
        --helm-repo-name repo1 --helm-repo-url https://repo1.example.com \\
        --helm-repo-name repo2 --helm-repo-url https://repo2.example.com
    """
    helm_repo_add(config_file, repos, urls)


@config_app.command(name="helm-repo-remove")
def helm_repo_remove_command(
    config_file: ConfigArg = "loko.yaml",
    repos: Annotated[
        Optional[List[str]],
        typer.Option(
            "--helm-repo-name",
            help="Helm repository name to remove (can be repeated for multiple repos)"
        )
    ] = None,
):
    """
    Remove one or more Helm repositories from the config file.

    Multiple repositories can be removed in a single command:

    Example:
      loko config helm-repo-remove --helm-repo-name repo1 --helm-repo-name repo2
    """
    helm_repo_remove(config_file, repos)


if __name__ == "__main__":
    app()
