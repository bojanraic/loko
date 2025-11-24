import os
import sys
import shutil
import subprocess
import typer
import urllib.request
import re
from typing import Optional
from typing_extensions import Annotated
from rich.console import Console
from pathlib import Path
from importlib.metadata import metadata

from .config import RootConfig
from .utils import load_config, get_dns_container_name
from .generator import ConfigGenerator
from .runner import CommandRunner

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


app = typer.Typer(
    name="loko",
    help="Local Kubernetes Environment Manager - Create and manage local K8s clusters with Kind, DNS via dnsmasq, SSL certificates via mkcert, and service deployment via Helm/Helmfile. Perfect for local development without cloud dependencies.",
    add_completion=True,
    no_args_is_help=True,
)
config_app = typer.Typer(name="config", help="Manage configuration")
app.add_typer(config_app)

console = Console()

def _check_docker_running(runtime: str = "docker") -> bool:
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

def _check_config_file(config_path: str) -> bool:
    """Check if config file exists and is readable."""
    return os.path.exists(config_path) and os.path.isfile(config_path)

def _ensure_docker_running(runtime: str = "docker"):
    """Ensure docker daemon is running, exit with error if not."""
    if not _check_docker_running(runtime):
        console.print(f"[bold red]❌ {runtime.capitalize()} daemon is not running.[/bold red]")
        console.print(f"[yellow]Start it first, then try again.[/yellow]")
        sys.exit(1)

def _ensure_config_file(config_path: str):
    """Ensure config file exists, exit with error if not."""
    if not _check_config_file(config_path):
        console.print(f"[bold red]❌ Configuration file '{config_path}' not found.[/bold red]")
        console.print(f"[yellow]You can:[/yellow]")
        console.print(f"[cyan]  1. Specify an existing config file:[/cyan]")
        console.print(f"[cyan]     loko <command> --config <path>[/cyan]")
        console.print(f"[cyan]  2. Generate a new config file:[/cyan]")
        console.print(f"[cyan]     loko generate-config[/cyan]")
        sys.exit(1)

# Common config argument
ConfigArg = Annotated[
    str, 
    typer.Option(
        "--config", "-c", 
        help="Path to configuration file",
        show_default=True
    )
]

TemplatesDirArg = Annotated[
    Optional[Path],
    typer.Option(
        "--templates-dir", "-t",
        help="Path to custom templates directory",
        show_default=False
    )
]

from typing import List

# CLI Overrides
NameArg = Annotated[Optional[str], typer.Option("--name", help="Override environment name")]
DomainArg = Annotated[Optional[str], typer.Option("--domain", help="Override local domain")]
WorkersArg = Annotated[Optional[int], typer.Option("--workers", help="Override number of worker nodes")]
ControlPlanesArg = Annotated[Optional[int], typer.Option("--control-planes", help="Override number of control plane nodes")]
RuntimeArg = Annotated[Optional[str], typer.Option("--runtime", help="Override container runtime")]
LocalIPArg = Annotated[Optional[str], typer.Option("--local-ip", help="Override local IP address")]
K8sVersionArg = Annotated[Optional[str], typer.Option("--k8s-version", help="Override Kubernetes node image tag")]
LBPortsArg = Annotated[Optional[List[int]], typer.Option("--lb-port", help="Override load balancer ports")]
AppsSubdomainArg = Annotated[Optional[str], typer.Option("--apps-subdomain", help="Override apps subdomain")]
ServicePresetsArg = Annotated[Optional[bool], typer.Option("--service-presets/--no-service-presets", help="Enable/disable service presets")]
MetricsServerArg = Annotated[Optional[bool], typer.Option("--metrics-server/--no-metrics-server", help="Enable/disable metrics server")]
EnableServiceArg = Annotated[Optional[List[str]], typer.Option("--enable-service", help="Enable a system service")]
DisableServiceArg = Annotated[Optional[List[str]], typer.Option("--disable-service", help="Disable a system service")]
BaseDirArg = Annotated[Optional[str], typer.Option("--base-dir", help="Override base directory")]
ExpandVarsArg = Annotated[Optional[bool], typer.Option("--expand-vars/--no-expand-vars", help="Enable/disable environment variable expansion")]
K8sAPIPortArg = Annotated[Optional[int], typer.Option("--k8s-api-port", help="Override Kubernetes API port")]
ScheduleOnControlArg = Annotated[Optional[bool], typer.Option("--schedule-on-control/--no-schedule-on-control", help="Allow scheduling on control plane nodes")]
InternalOnControlArg = Annotated[Optional[bool], typer.Option("--internal-on-control/--no-internal-on-control", help="Force internal components on control plane")]
RegistryNameArg = Annotated[Optional[str], typer.Option("--registry-name", help="Override registry name")]
RegistryStorageArg = Annotated[Optional[str], typer.Option("--registry-storage", help="Override registry storage size")]
ServicesOnWorkersArg = Annotated[Optional[bool], typer.Option("--services-on-workers/--no-services-on-workers", help="Force services to run on workers only")]

def _apply_config_overrides(config: RootConfig, **overrides) -> None:
    """Apply CLI overrides to configuration."""
    # Environment overrides
    if overrides.get('name'):
        config.environment.name = overrides['name']
    if overrides.get('domain'):
        config.environment.local_domain = overrides['domain']
    if overrides.get('local_ip'):
        config.environment.local_ip = overrides['local_ip']
    if overrides.get('apps_subdomain'):
        config.environment.apps_subdomain = overrides['apps_subdomain']
    if overrides.get('base_dir'):
        config.environment.base_dir = overrides['base_dir']

    # Node overrides
    if overrides.get('workers') is not None:
        config.environment.nodes.workers = overrides['workers']
    if overrides.get('control_planes') is not None:
        config.environment.nodes.servers = overrides['control_planes']
    if overrides.get('schedule_on_control') is not None:
        config.environment.nodes.allow_scheduling_on_control_plane = overrides['schedule_on_control']
    if overrides.get('internal_on_control') is not None:
        config.environment.nodes.internal_components_on_control_plane = overrides['internal_on_control']

    # Provider overrides
    if overrides.get('runtime'):
        config.environment.provider.runtime = overrides['runtime']

    # Kubernetes overrides
    if overrides.get('k8s_version'):
        config.environment.kubernetes.tag = overrides['k8s_version']
    if overrides.get('k8s_api_port') is not None:
        config.environment.kubernetes.api_port = overrides['k8s_api_port']

    # Registry overrides
    if overrides.get('registry_name'):
        config.environment.registry.name = overrides['registry_name']
    if overrides.get('registry_storage'):
        config.environment.registry.storage["size"] = overrides['registry_storage']

    # Load balancer overrides
    if overrides.get('lb_ports'):
        config.environment.local_lb_ports = overrides['lb_ports']

    # Feature flags
    if overrides.get('service_presets') is not None:
        config.environment.use_service_presets = overrides['service_presets']
    if overrides.get('metrics_server') is not None:
        config.environment.enable_metrics_server = overrides['metrics_server']
    if overrides.get('expand_vars') is not None:
        config.environment.expand_env_vars = overrides['expand_vars']
    if overrides.get('services_on_workers') is not None:
        config.environment.run_services_on_workers_only = overrides['services_on_workers']

def _update_service_state(config: RootConfig, service_names: Optional[List[str]], enabled: bool) -> None:
    """Update enabled state for services."""
    if not service_names:
        return

    for svc_name in service_names:
        found = False
        if config.environment.services and config.environment.services.system:
            for svc in config.environment.services.system:
                if svc.name == svc_name:
                    svc.enabled = enabled
                    found = True
                    break
        if not found:
            console.print(f"[yellow]Warning: Service '{svc_name}' not found in system services.[/yellow]")

def get_config(
    config_path: str,
    name: Optional[str] = None,
    domain: Optional[str] = None,
    workers: Optional[int] = None,
    control_planes: Optional[int] = None,
    runtime: Optional[str] = None,
    local_ip: Optional[str] = None,
    k8s_version: Optional[str] = None,
    lb_ports: Optional[List[int]] = None,
    apps_subdomain: Optional[str] = None,
    service_presets: Optional[bool] = None,
    metrics_server: Optional[bool] = None,
    enable_services: Optional[List[str]] = None,
    disable_services: Optional[List[str]] = None,
    base_dir: Optional[str] = None,
    expand_vars: Optional[bool] = None,
    k8s_api_port: Optional[int] = None,
    schedule_on_control: Optional[bool] = None,
    internal_on_control: Optional[bool] = None,
    registry_name: Optional[str] = None,
    registry_storage: Optional[str] = None,
    services_on_workers: Optional[bool] = None,
) -> RootConfig:
    if not os.path.exists(config_path):
        console.print(f"[bold red]Configuration file '{config_path}' not found.[/bold red]")
        sys.exit(1)

    config = load_config(config_path)

    # Apply CLI overrides
    _apply_config_overrides(
        config,
        name=name,
        domain=domain,
        workers=workers,
        control_planes=control_planes,
        runtime=runtime,
        local_ip=local_ip,
        k8s_version=k8s_version,
        lb_ports=lb_ports,
        apps_subdomain=apps_subdomain,
        service_presets=service_presets,
        metrics_server=metrics_server,
        base_dir=base_dir,
        expand_vars=expand_vars,
        k8s_api_port=k8s_api_port,
        schedule_on_control=schedule_on_control,
        internal_on_control=internal_on_control,
        registry_name=registry_name,
        registry_storage=registry_storage,
        services_on_workers=services_on_workers,
    )

    # Update service states
    _update_service_state(config, enable_services, True)
    _update_service_state(config, disable_services, False)

    return config

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
    _ensure_config_file(config_file)
    _ensure_docker_running()

    console.print("[bold green]Initializing environment...[/bold green]")
    config = get_config(
        config_file, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, service_presets,
        metrics_server, enable_service, disable_service,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, services_on_workers
    )
    
    # Generate configs
    generator = ConfigGenerator(config, config_file, templates_dir)
    generator.generate_configs()
    
    # Setup runtime
    runner = CommandRunner(config)
    runner.check_runtime()
    runner.setup_certificates()
    runner.ensure_network()

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
    _ensure_config_file(config_file)
    _ensure_docker_running()

    console.print("[bold green]Creating environment...[/bold green]")

    # Run init first
    init(
        config_file, templates_dir, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, service_presets,
        metrics_server, enable_service, disable_service,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, services_on_workers
    )
    
    config = get_config(
        config_file, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, service_presets,
        metrics_server, enable_service, disable_service,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, services_on_workers
    )
    runner = CommandRunner(config)
    
    runner.start_dnsmasq()
    runner.setup_resolver_file()
    runner.create_cluster()
    runner.inject_dns_nameserver()
    runner.fetch_kubeconfig()
    runner.wait_for_cluster_ready()
    runner.set_control_plane_scheduling()
    runner.label_nodes()
    runner.list_nodes()
    runner.setup_wildcard_cert()
    runner.deploy_services()
    runner.fetch_service_secrets()




@app.command()
def destroy(config_file: ConfigArg = "loko.yaml"):
    """
    Destroy the environment.
    """
    _ensure_config_file(config_file)
    _ensure_docker_running()

    console.print("[bold red]Destroying environment...[/bold red]")
    config = get_config(config_file)
    runner = CommandRunner(config)

    cluster_name = config.environment.name
    runtime = config.environment.provider.runtime

    # Delete cluster
    runner.run_command(["kind", "delete", "cluster", "--name", cluster_name])

    # Remove DNS container
    dns_container = get_dns_container_name(cluster_name)
    runner.run_command([runtime, "rm", "-f", dns_container], check=False)

    # Remove resolver file
    runner.remove_resolver_file()

    console.print(f"✅ Environment '{cluster_name}' destroyed")

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
    _ensure_config_file(config_file)
    _ensure_docker_running()

    console.print("[bold blue]Recreating environment...[/bold blue]\n")

    # Destroy first
    destroy(config_file)
    
    console.print()
    
    # Then create
    create(
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
    _ensure_config_file(config_file)
    _ensure_docker_running()

    console.print("[bold red]Cleaning environment...[/bold red]\n")

    config = get_config(config_file)
    
    # Destroy first
    destroy(config_file)
    
    console.print()
    
    # Remove generated directories
    import shutil
    k8s_dir = os.path.join(os.path.expandvars(config.environment.base_dir), config.environment.name)
    
    if os.path.exists(k8s_dir):
        console.print(f"[yellow]Removing directory: {k8s_dir}[/yellow]")
        shutil.rmtree(k8s_dir)
        console.print(f"[green]✅ Removed {k8s_dir}[/green]")
    
    console.print(f"\n[bold green]✅ Environment '{config.environment.name}' cleaned[/bold green]")



@app.command()
def start(config_file: ConfigArg = "loko.yaml"):
    """
    Start the environment.
    """
    _ensure_config_file(config_file)
    _ensure_docker_running()

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

@app.command()
def stop(config_file: ConfigArg = "loko.yaml"):
    """
    Stop the environment.
    """
    _ensure_config_file(config_file)
    _ensure_docker_running()

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

@app.command()
def status(config_file: ConfigArg = "loko.yaml"):
    """
    Show environment status.
    """
    _ensure_config_file(config_file)
    _ensure_docker_running()

    console.print("[bold blue]Environment Status[/bold blue]\n")
    config = get_config(config_file)
    runner = CommandRunner(config)
    
    cluster_name = config.environment.name
    runtime = config.environment.provider.runtime
    
    try:
        # Check if cluster exists
        result = runner.run_command(
            ["kind", "get", "clusters"],
            capture_output=True
        )
        clusters = result.stdout.strip().split('\n')
        
        if cluster_name not in clusters:
            console.print(f"[red]❌ Cluster '{cluster_name}' does not exist[/red]")
            console.print("Run 'loko create' to create the environment")
            sys.exit(1)
        
        # Resolve base_dir if it contains env vars
        base_dir_display = config.environment.base_dir
        if config.environment.expand_env_vars and '$' in config.environment.base_dir:
            # Get the config file's directory to resolve $PWD correctly
            config_dir = os.path.dirname(os.path.abspath(config_file))
            # Temporarily change to config dir to expand $PWD correctly
            original_cwd = os.getcwd()
            try:
                os.chdir(config_dir)
                base_dir_display = os.path.expandvars(config.environment.base_dir)
            finally:
                os.chdir(original_cwd)
        
        # Environment Configuration
        console.print("[bold]🌍 Environment Configuration:[/bold]")
        console.print(f"├── Name: {config.environment.name}")
        console.print(f"├── Base Directory: {base_dir_display}")
        console.print(f"├── Local Domain: {config.environment.local_domain}")
        console.print(f"├── Local IP: {config.environment.local_ip}")
        console.print(f"├── Container Runtime: {config.environment.provider.runtime}")
        console.print(f"├── Nodes:")
        console.print(f"│   ├── Control Plane: {config.environment.nodes.servers}")
        console.print(f"│   ├── Workers: {config.environment.nodes.workers}")
        console.print(f"│   ├── Allow Control Plane Scheduling: {config.environment.nodes.allow_scheduling_on_control_plane}")
        console.print(f"│   └── Run Services on Workers Only: {config.environment.run_services_on_workers_only}")
        console.print(f"└── Service Presets Enabled: {config.environment.use_service_presets}\n")
        
        # Enabled Services
        console.print("[bold]🔌 Enabled Services:[/bold]")
        sys_enabled = []
        user_enabled = []
        
        if config.environment.services and config.environment.services.system:
            for svc in config.environment.services.system:
                if svc.enabled:
                    ports = ', '.join(map(str, svc.ports)) if getattr(svc, 'ports', None) else 'none'
                    sys_enabled.append(f"{svc.name}: {ports}")
        
        if config.environment.services and config.environment.services.user:
            for svc in config.environment.services.user:
                if svc.enabled:
                    ns = getattr(svc, 'namespace', svc.name)
                    user_enabled.append(f"{svc.name} (namespace: {ns})")
        
        if sys_enabled:
            console.print("├── System Services (with presets):")
            for i, svc in enumerate(sys_enabled):
                console.print(f"│   ├── {svc}")
        else:
            console.print("├── System Services: None enabled")
        
        if user_enabled:
            console.print("├── User Services (custom configuration):")
            for i, svc in enumerate(user_enabled):
                console.print(f"│   ├── {svc}")
        else:
            console.print("├── User Services: None enabled")
        
        console.print(f"└── Registry: {config.environment.registry.name}.{config.environment.local_domain}\n")
        
        # Cluster Info
        console.print("[bold]🏢 Cluster Information:[/bold]")
        try:
            result = runner.run_command(
                ["kubectl", "cluster-info"],
                capture_output=True
            )
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    console.print(f"├── {line.strip()}")
        except:
            console.print("├── [yellow]kubectl not configured[/yellow]")
        console.print()
        
        # DNS Service
        console.print("[bold]🔍 DNS Service:[/bold]")
        dns_container = get_dns_container_name(cluster_name)
        dns_status = runner.list_containers(name_filter=dns_container, format_expr="{{.Names}}\t{{.Status}}", check=False)
        if dns_status:
            name, status = dns_status[0].split('\t', 1)
            console.print(f"├── Container: {name}")
            console.print(f"└── Status: {status}\n")
        else:
            console.print("└── [yellow]DNS container not running[/yellow]\n")

        # Container Status
        containers_status = runner.list_containers(name_filter=cluster_name, all_containers=True, format_expr="{{.Names}}\t{{.Status}}")

        if containers_status:
            console.print("[bold]📦 Container Status:[/bold]")
            for idx, line in enumerate(containers_status):
                if line.strip():
                    name, status = line.split('\t', 1)
                    prefix = "└──" if idx == len(containers_status) - 1 else "├──"
                    if 'Up' in status:
                        console.print(f"{prefix} [green]✅ {name}[/green]: {status}")
                    else:
                        console.print(f"{prefix} [yellow]⏸️  {name}[/yellow]: {status}")
            console.print()
        
        # Kubernetes Nodes
        try:
            result = runner.run_command(
                ["kubectl", "get", "nodes", "-o", "wide"],
                capture_output=True
            )
            console.print("[bold]☸️  Kubernetes Nodes:[/bold]")
            console.print(result.stdout)
        except:
            console.print("[bold]☸️  Kubernetes Nodes:[/bold]")
            console.print("[yellow]⚠️  Could not fetch node status (kubectl may not be configured)[/yellow]\n")
        
    except Exception as e:
        console.print(f"[bold red]Error checking status: {e}[/bold red]")
        sys.exit(1)

@app.command()
def validate(config_file: ConfigArg = "loko.yaml"):
    """
    Validate the environment.
    """
    _ensure_config_file(config_file)
    _ensure_docker_running()

    console.print("[bold green]Validating environment...[/bold green]\n")
    config = get_config(config_file)
    runner = CommandRunner(config)
    
    cluster_name = config.environment.name
    runtime = config.environment.provider.runtime
    
    validation_passed = True
    
    # 1. Check cluster exists and is running
    console.print("[bold]1. Checking cluster status...[/bold]")
    try:
        result = runner.run_command(
            ["kind", "get", "clusters"],
            capture_output=True
        )
        if cluster_name in result.stdout:
            console.print(f"  [green]✅ Cluster '{cluster_name}' exists[/green]")
        else:
            console.print(f"  [red]❌ Cluster '{cluster_name}' not found[/red]")
            validation_passed = False
    except Exception as e:
        console.print(f"  [red]❌ Error checking cluster: {e}[/red]")
        validation_passed = False
    
    # 2. Check all nodes are ready
    console.print("\n[bold]2. Checking node readiness...[/bold]")
    try:
        result = runner.run_command(
            ["kubectl", "get", "nodes", "-o", "jsonpath={.items[*].status.conditions[?(@.type=='Ready')].status}"],
            capture_output=True
        )
        statuses = result.stdout.strip().split()
        if statuses and all(s == "True" for s in statuses):
            console.print(f"  [green]✅ All {len(statuses)} node(s) are ready[/green]")
        else:
            console.print(f"  [red]❌ Some nodes are not ready[/red]")
            validation_passed = False
    except Exception as e:
        console.print(f"  [red]❌ Error checking nodes: {e}[/red]")
        validation_passed = False
    
    # 3. Check DNS container
    console.print("\n[bold]3. Checking DNS service...[/bold]")
    dns_container = get_dns_container_name(cluster_name)
    try:
        dns_running = runner.list_containers(name_filter=dns_container, status_filter="running", quiet=True, check=False)
        if dns_running:
            console.print(f"  [green]✅ DNS container is running[/green]")
        else:
            console.print(f"  [red]❌ DNS container is not running[/red]")
            validation_passed = False
    except Exception as e:
        console.print(f"  [red]❌ Error checking DNS: {e}[/red]")
        validation_passed = False
    
    # 4. Check system pods
    console.print("\n[bold]4. Checking system pods...[/bold]")
    try:
        result = runner.run_command(
            ["kubectl", "get", "pods", "-A", "-o", "jsonpath={.items[*].status.phase}"],
            capture_output=True
        )
        phases = result.stdout.strip().split()
        running_count = sum(1 for p in phases if p == "Running")
        total_count = len(phases)
        
        if total_count > 0:
            console.print(f"  [green]✅ {running_count}/{total_count} pods are running[/green]")
            if running_count < total_count:
                console.print(f"  [yellow]⚠️  Some pods are not in Running state[/yellow]")
        else:
            console.print(f"  [yellow]⚠️  No pods found[/yellow]")
    except Exception as e:
        console.print(f"  [yellow]⚠️  Error checking pods: {e}[/yellow]")
    
    # 5. Check kubectl connectivity
    console.print("\n[bold]5. Checking kubectl connectivity...[/bold]")
    try:
        result = runner.run_command(
            ["kubectl", "cluster-info"],
            capture_output=True
        )
        if "Kubernetes control plane" in result.stdout:
            console.print(f"  [green]✅ kubectl can connect to cluster[/green]")
        else:
            console.print(f"  [red]❌ kubectl connectivity issue[/red]")
            validation_passed = False
    except Exception as e:
        console.print(f"  [red]❌ Error checking kubectl: {e}[/red]")
        validation_passed = False
    
    # 6. Test app validation (registry + TLS)
    console.print("\n[bold]6. Testing registry and TLS (deploy test app)...[/bold]")
    try:
        image_tag, registry_host = runner.build_and_push_test_image()
        test_host = runner.deploy_test_app(image_tag, registry_host)
        
        if runner.validate_test_app(test_host):
            console.print(f"  [green]✅ Registry and TLS validation passed[/green]")
        else:
            console.print(f"  [red]❌ Registry or TLS validation failed[/red]")
            validation_passed = False
            
    except Exception as e:
        console.print(f"  [red]❌ Error with test app: {e}[/red]")
        validation_passed = False
    finally:
        # # Always cleanup
        # try:
        #     runner.cleanup_test_app()
        # except:
        #     pass
        # Skipping cleanup as per user request
        pass
    
    # Summary
    console.print("\n" + "="*50)
    if validation_passed:
        console.print("[bold green]✅ Validation PASSED - Environment is healthy![/bold green]")
    else:
        console.print("[bold red]❌ Validation FAILED - Some checks did not pass[/bold red]")
        sys.exit(1)


@app.command()
def secrets(config_file: ConfigArg = "loko.yaml"):
    """
    Fetch and save service credentials to a file.
    """
    _ensure_config_file(config_file)
    _ensure_docker_running()

    console.print("[bold blue]Fetching service credentials...[/bold blue]\n")
    config = get_config(config_file)
    runner = CommandRunner(config)

    try:
        runner.fetch_service_secrets()
    except Exception as e:
        console.print(f"[bold red]Error fetching secrets: {e}[/bold red]")
        sys.exit(1)

@app.command()
def version():
    """
    Print the current version of loko.
    """
    try:
        meta = metadata('loko-k8s')
        ver = meta.get('Version')
        console.print(ver)
    except Exception:
        console.print("version not found")
        sys.exit(1)

@app.command(name="check-prerequisites")
def check_prerequisites():
    """
    Check if all required tools are installed.
    """
    console.print("[bold blue]Checking prerequisites...[/bold blue]\n")
    
    tools = {
        "docker": {
            "cmd": ["docker", "--version"],
            "required": True,
            "description": "Docker (container runtime)",
            "install_url": "https://docs.docker.com/get-docker/"
        },
        "kind": {
            "cmd": ["kind", "version"],
            "required": True,
            "description": "Kind (Kubernetes in Docker)",
            "install_url": "https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
        },
        "mkcert": {
            "cmd": ["mkcert", "-version"],
            "required": True,
            "description": "mkcert (local certificate authority)",
            "install_url": "https://github.com/FiloSottile/mkcert#installation"
        },
        "helmfile": {
            "cmd": ["helmfile", "--version"],
            "required": False,
            "description": "Helmfile (declarative Helm releases)",
            "install_url": "https://github.com/helmfile/helmfile#installation"
        },
        "helm": {
            "cmd": ["helm", "version", "--short"],
            "required": True,
            "description": "Helm (package manager for Kubernetes)",
            "install_url": "https://helm.sh/docs/intro/install/"
        },
        "kubectl": {
            "cmd": ["kubectl", "version", "--client"],
            "required": False,
            "description": "kubectl (Kubernetes CLI)",
            "install_url": "https://kubernetes.io/docs/tasks/tools/"
        }
    }
    
    results = {}
    runtime_found = False
    
    for tool_name, tool_info in tools.items():
        try:
            result = subprocess.run(
                tool_info["cmd"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                results[tool_name] = True
                console.print(f"✅ {tool_info['description']}: [green]installed[/green]")
                if tool_name in ["docker", "podman"]:
                    runtime_found = True
            else:
                results[tool_name] = False
                if tool_info["required"]:
                    console.print(f"❌ {tool_info['description']}: [red]not found[/red]")
                    console.print(f"   Install: {tool_info['install_url']}")
                else:
                    console.print(f"⚠️  {tool_info['description']}: [yellow]not found (optional)[/yellow]")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            results[tool_name] = False
            if tool_info["required"]:
                console.print(f"❌ {tool_info['description']}: [red]not found[/red]")
                console.print(f"   Install: {tool_info['install_url']}")
            else:
                console.print(f"⚠️  {tool_info['description']}: [yellow]not found (optional)[/yellow]")
    
    # Check if at least one container runtime is available
    if not runtime_found:
        console.print("\n[bold red]Error: No container runtime found![/bold red]")
        console.print("Please install either Docker or Podman:")
        console.print(f"  - Docker: {tools['docker']['install_url']}")
        console.print(f"  - Podman: {tools['podman']['install_url']}")
    
    # Summary
    console.print("\n[bold]Summary:[/bold]")
    required_tools = [name for name, info in tools.items() if info["required"]]
    required_installed = sum(1 for name in required_tools if results.get(name, False))

    if runtime_found and required_installed >= len([t for t in required_tools if t not in ["docker", "podman"]]) + 1:
        console.print("[bold green]✅ All required tools are installed![/bold green]")

        # Additional note about NSS/libnss for certificate trust
        console.print("\n[bold]Additional Requirements:[/bold]")
        console.print("📝 [yellow]NSS/libnss[/yellow] - Required for trusting self-signed certificates in browsers")
        console.print("   mkcert uses NSS to install certificates in Firefox and other browsers")
        console.print("   Install via package manager:")
        console.print("     • Ubuntu/Debian: [cyan]sudo apt install libnss3-tools[/cyan]")
        console.print("     • Fedora/RHEL: [cyan]sudo dnf install nss-tools[/cyan]")
        console.print("     • Arch: [cyan]sudo pacman -S nss[/cyan]")
        console.print("     • macOS: NSS is included with Firefox")
        console.print("   Without NSS, mkcert will only work for system-wide cert stores (Chrome, curl)")

        return 0
    else:
        console.print("[bold red]❌ Some required tools are missing.[/bold red]")
        console.print("Please install the missing tools before using loko.")
        sys.exit(1)


@app.command(name="generate-config")
def generate_config(
    output: Annotated[str, typer.Option("--output", "-o", help="Output file path")] = "loko.yaml",
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing file")] = False
):
    """
    Generate a default configuration file with auto-detected local IP.
    """
    template_path = Path(__file__).parent / "templates" / "loko.yaml.example"

    if not template_path.exists():
        console.print("[bold red]Error: Default configuration template not found.[/bold red]")
        sys.exit(1)

    if os.path.exists(output) and not force:
        if not typer.confirm(f"File '{output}' already exists. Overwrite?"):
            console.print("[yellow]Operation cancelled.[/yellow]")
            sys.exit(0)

    # Auto-detect local IP
    detected_ip = _detect_local_ip()

    # Read template and replace IP
    with open(template_path, 'r') as f:
        content = f.read()

    # Replace the hardcoded IP with detected IP
    content = re.sub(
        r'local-ip:\s+\d+\.\d+\.\d+\.\d+',
        f'local-ip: {detected_ip}',
        content
    )

    # Write to output file
    with open(output, 'w') as f:
        f.write(content)

    console.print(f"[bold green]Generated configuration at '{output}'[/bold green]")
    console.print(f"[cyan]Detected local IP: {detected_ip}[/cyan]")
    console.print("[dim]You can modify the local-ip setting in the config file if needed.[/dim]")


def _get_ip_via_default_route() -> Optional[str]:
    """
    Get local IP by finding the interface with the default route.
    Works on both Linux and macOS.
    """
    import platform

    try:
        system = platform.system()

        if system == "Linux":
            # Use ip route to find default interface
            result = subprocess.run(
                ["ip", "route", "get", "1.1.1.1"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Parse output like: "1.1.1.1 via 192.168.1.1 dev eth0 src 192.168.1.100"
                match = re.search(r'src\s+(\d+\.\d+\.\d+\.\d+)', result.stdout)
                if match:
                    return match.group(1)

        elif system == "Darwin":  # macOS
            # Use route get to find the IP used for routing
            result = subprocess.run(
                ["route", "-n", "get", "1.1.1.1"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Parse output for "interface:" and then get IP from that interface
                match = re.search(r'interface:\s+(\S+)', result.stdout)
                if match:
                    interface = match.group(1)
                    # Get IP from the interface using ifconfig
                    ifconfig_result = subprocess.run(
                        ["ifconfig", interface],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if ifconfig_result.returncode == 0:
                        # Look for inet address
                        ip_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', ifconfig_result.stdout)
                        if ip_match:
                            return ip_match.group(1)

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass

    return None


def _get_ip_via_socket() -> Optional[str]:
    """
    Get local IP by opening a UDP socket to a public DNS server.
    No data is actually sent.
    """
    import socket

    try:
        # Create a UDP socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to Google's public DNS (no data sent with UDP)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        pass

    return None


def _detect_local_ip() -> str:
    """
    Detect local IP address using multiple methods.
    Prefers default route method, uses socket method as fallback.
    Returns a sensible default if both fail.
    """
    ip_via_route = _get_ip_via_default_route()
    ip_via_socket = _get_ip_via_socket()

    # If both methods agree, use that IP
    if ip_via_route and ip_via_socket and ip_via_route == ip_via_socket:
        return ip_via_route

    # Prefer default route method
    if ip_via_route:
        return ip_via_route

    # Fall back to socket method
    if ip_via_socket:
        return ip_via_socket

    # Last resort: return a common default
    console.print("[yellow]Warning: Could not auto-detect local IP. Using default 192.168.1.100[/yellow]")
    return "192.168.1.100"


def _parse_renovate_comment(comment: str) -> Optional[dict]:
    """
    Parse a renovate comment and extract datasource, depName, and repositoryUrl.

    Example:
        # renovate: datasource=docker depName=kindest/node
        # renovate: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts
    """
    if 'renovate:' not in comment:
        return None

    result = {}

    # Extract datasource
    datasource_match = re.search(r'datasource=(\w+)', comment)
    if datasource_match:
        result['datasource'] = datasource_match.group(1)

    # Extract depName
    depname_match = re.search(r'depName=([\w\-/\.]+)', comment)
    if depname_match:
        result['depName'] = depname_match.group(1)

    # Extract repositoryUrl (optional)
    repo_match = re.search(r'repositoryUrl=(https?://[^\s]+)', comment)
    if repo_match:
        result['repositoryUrl'] = repo_match.group(1)

    return result if 'datasource' in result and 'depName' in result else None


def _fetch_latest_docker_version(dep_name: str) -> Optional[str]:
    """
    Fetch the latest version of a Docker image from Docker Hub or registry.
    """
    try:
        # Handle official images (no slash) vs user/org images
        if '/' not in dep_name:
            # Official Docker library images
            url = f"https://registry.hub.docker.com/v2/repositories/library/{dep_name}/tags?page_size=100"
        else:
            # User or organization images
            url = f"https://registry.hub.docker.com/v2/repositories/{dep_name}/tags?page_size=100"

        import json
        # Add User-Agent header to avoid 403 errors
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'loko/0.1.0 (https://github.com/bojanraic/loko)',
                'Accept': 'application/json'
            }
        )

        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())

        # Filter out non-version tags and sort
        tags = []
        for tag_info in data.get('results', []):
            tag = tag_info.get('name', '')
            # Skip tags like 'latest', 'nightly', 'dev', etc.
            if tag and not any(skip in tag.lower() for skip in ['latest', 'nightly', 'dev', 'rc', 'beta', 'alpha']):
                # Prefer semantic versions (e.g., v1.31.2, 1.31.2)
                if re.match(r'^v?\d+', tag):
                    tags.append(tag)

        # Return the first tag (most recent)
        return tags[0] if tags else None

    except Exception as e:
        console.print(f"[yellow]Warning: Could not fetch Docker version for {dep_name}: {e}[/yellow]")
        return None


def _fetch_latest_helm_version(dep_name: str, repository_url: Optional[str] = None) -> Optional[str]:
    """
    Fetch the latest version of a Helm chart from a Helm repository.
    """
    try:
        # Default Helm chart repositories
        default_repos = {
            'app-template': 'https://bjw-s-labs.github.io/helm-charts',
            'traefik': 'https://traefik.github.io/charts',
            'metrics-server': 'https://kubernetes-sigs.github.io/metrics-server',
            'mysql': 'https://groundhog2k.github.io/helm-charts',
            'postgres': 'https://groundhog2k.github.io/helm-charts',
            'mongodb': 'https://groundhog2k.github.io/helm-charts',
            'rabbitmq': 'https://groundhog2k.github.io/helm-charts',
            'valkey': 'https://groundhog2k.github.io/helm-charts',
            'http-webhook': 'https://charts.securecodebox.io',
        }

        # Use provided repository URL or fall back to defaults
        repo_url = repository_url or default_repos.get(dep_name)

        if not repo_url:
            console.print(f"[yellow]Warning: No repository URL found for {dep_name}[/yellow]")
            return None

        # Fetch index.yaml from Helm repository
        index_url = f"{repo_url.rstrip('/')}/index.yaml"

        import yaml
        import time

        # Add User-Agent header and small delay to avoid rate limiting
        req = urllib.request.Request(
            index_url,
            headers={
                'User-Agent': 'loko/0.1.0 (https://github.com/bojanraic/loko)',
                'Accept': 'application/x-yaml, text/yaml, */*'
            }
        )

        # Small delay to avoid rate limiting
        time.sleep(0.5)

        with urllib.request.urlopen(req) as response:
            index_data = yaml.safe_load(response.read())

        # Get chart entries
        entries = index_data.get('entries', {})
        chart_versions = entries.get(dep_name, [])

        if not chart_versions:
            console.print(f"[yellow]Warning: No versions found for chart {dep_name}[/yellow]")
            return None

        # Charts are usually sorted by version in descending order
        # Get the latest non-prerelease version
        for version_info in chart_versions:
            version = version_info.get('version', '')
            # Skip pre-release versions
            if version and not any(pre in version.lower() for pre in ['-rc', '-beta', '-alpha', '-dev']):
                return version

        # If no stable version found, return the first one
        return chart_versions[0].get('version') if chart_versions else None

    except Exception as e:
        console.print(f"[yellow]Warning: Could not fetch Helm version for {dep_name}: {e}[/yellow]")
        return None


def _fetch_latest_version(renovate_info: dict) -> Optional[str]:
    """
    Fetch the latest version based on renovate datasource type.
    """
    datasource = renovate_info.get('datasource')
    dep_name = renovate_info.get('depName')

    if datasource == 'docker':
        return _fetch_latest_docker_version(dep_name)
    elif datasource == 'helm':
        return _fetch_latest_helm_version(dep_name, renovate_info.get('repositoryUrl'))
    else:
        console.print(f"[yellow]Warning: Unsupported datasource type: {datasource}[/yellow]")
        return None


def _walk_yaml_for_renovate(data, updates, path="", processed_comments=None):
    """
    Recursively walk YAML structure looking for renovate comments.
    Only processes each comment once and associates it with the correct value.
    """
    from ruamel.yaml.comments import CommentedMap, CommentedSeq

    if processed_comments is None:
        processed_comments = set()

    if isinstance(data, CommentedMap):
        keys = list(data.keys())
        for i, key in enumerate(keys):
            value = data[key]
            current_path = f"{path}.{key}" if path else str(key)

            # Only check for renovate comments on scalar values (not nested structures)
            if not isinstance(value, (CommentedMap, CommentedSeq)):
                renovate_info = None

                # Check if the PREVIOUS key has a comment in position [2] (after that key)
                # That comment should apply to THIS (current) key
                if i > 0 and hasattr(data, 'ca') and data.ca.items:
                    prev_key = keys[i - 1]
                    prev_comment_token = data.ca.items.get(prev_key)
                    # Position [2] is "after" - contains comments after the previous key's value
                    if prev_comment_token and len(prev_comment_token) > 2 and prev_comment_token[2]:
                        comment_obj = prev_comment_token[2]
                        if comment_obj and hasattr(comment_obj, 'value'):
                            comment_text = comment_obj.value
                            comment_id = (id(data), prev_key, 'after_to', key)
                            if comment_id not in processed_comments:
                                parsed = _parse_renovate_comment(comment_text)
                                if parsed:
                                    renovate_info = parsed
                                    processed_comments.add(comment_id)

                if renovate_info:
                    updates.append((current_path, key, renovate_info, value, data))

            # Recurse into nested structures
            if isinstance(value, (CommentedMap, CommentedSeq)):
                _walk_yaml_for_renovate(value, updates, current_path, processed_comments)

    elif isinstance(data, CommentedSeq):
        for idx, item in enumerate(data):
            current_path = f"{path}[{idx}]"

            # For list items that are dicts with single key-value (like "- traefik: 37.3.0")
            if isinstance(item, CommentedMap) and len(item) == 1:
                item_key = list(item.keys())[0]
                item_value = item[item_key]

                renovate_info = None

                # For the first item, check the sequence's comment
                if idx == 0 and hasattr(data, 'ca') and hasattr(data.ca, 'comment'):
                    if data.ca.comment and len(data.ca.comment) > 1 and data.ca.comment[1]:
                        comment_list = data.ca.comment[1]
                        for comment_obj in (comment_list if isinstance(comment_list, list) else [comment_list]):
                            if comment_obj and hasattr(comment_obj, 'value'):
                                comment_text = comment_obj.value
                                comment_id = (id(data), 'seq_comment', idx)
                                if comment_id not in processed_comments:
                                    parsed = _parse_renovate_comment(comment_text)
                                    if parsed:
                                        renovate_info = parsed
                                        processed_comments.add(comment_id)
                                        break

                # For subsequent items, check the previous item's key comment (position [2])
                if not renovate_info and idx > 0:
                    prev_item = data[idx - 1]
                    if isinstance(prev_item, CommentedMap) and len(prev_item) == 1:
                        prev_key = list(prev_item.keys())[0]
                        if hasattr(prev_item, 'ca') and prev_item.ca.items:
                            comment_token = prev_item.ca.items.get(prev_key)
                            if comment_token and len(comment_token) > 2 and comment_token[2]:
                                comment_obj = comment_token[2]
                                if comment_obj and hasattr(comment_obj, 'value'):
                                    comment_text = comment_obj.value
                                    comment_id = (id(prev_item), prev_key, 'after')
                                    if comment_id not in processed_comments:
                                        parsed = _parse_renovate_comment(comment_text)
                                        if parsed:
                                            renovate_info = parsed
                                            processed_comments.add(comment_id)

                if renovate_info:
                    updates.append((current_path, item_key, renovate_info, item_value, item))

            # Recurse into more complex nested structures
            elif isinstance(item, (CommentedMap, CommentedSeq)):
                _walk_yaml_for_renovate(item, updates, current_path, processed_comments)



@config_app.command("upgrade")
def config_upgrade(
    config_file: ConfigArg = "loko.yaml",
):
    """
    Upgrade component versions in config file by checking renovate comments.

    This command reads renovate-style comments in the config file and queries
    the appropriate datasources (Docker Hub, Helm repositories) to find the
    latest versions of components.
    """
    _ensure_config_file(config_file)

    console.print("[bold blue]Upgrading component versions...[/bold blue]\n")

    try:
        from ruamel.yaml import YAML

        # Load YAML with comment preservation
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.default_flow_style = False

        with open(config_file, 'r') as f:
            data = yaml.load(f)

        # Find all renovate comments and their associated values
        updates_to_check = []
        _walk_yaml_for_renovate(data, updates_to_check)

        # Check each one for updates
        updates_made = []
        for path, key, renovate_info, current_value, parent in updates_to_check:
            console.print(f"🔍 Checking {renovate_info['depName']} ({renovate_info['datasource']})...")

            # Fetch latest version
            latest_version = _fetch_latest_version(renovate_info)

            if latest_version and str(current_value) != latest_version:
                # Update the value in the YAML structure
                parent[key] = latest_version
                updates_made.append(f"  {renovate_info['depName']}: {current_value} → {latest_version}")

        if updates_made:
            console.print("\n[bold green]Updates found:[/bold green]")
            for update in updates_made:
                console.print(update)

            # Create backup before writing changes
            backup_file = config_file.rsplit('.', 1)[0] + '-prev.' + config_file.rsplit('.', 1)[1]
            shutil.copy(config_file, backup_file)
            console.print(f"\n💾 Backup created: {backup_file}")

            # Write updated config back
            with open(config_file, 'w') as f:
                yaml.dump(data, f)

            console.print(f"✅ Updated {len(updates_made)} version(s) in {config_file}")
        else:
            console.print("[green]✅ All versions are up to date[/green]")

    except Exception as e:
        console.print(f"[red]Error upgrading config: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    app()
