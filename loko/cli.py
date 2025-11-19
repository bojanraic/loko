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
from .utils import load_config
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
    help="Local Kubernetes Environment Manager",
    add_completion=True,
    no_args_is_help=True,
)
config_app = typer.Typer(name="config", help="Manage configuration")
app.add_typer(config_app)

console = Console()

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
    
    # Apply overrides
    if name:
        config.environment.name = name
    if domain:
        config.environment.local_domain = domain
    if workers is not None:
        config.environment.nodes.workers = workers
    if control_planes is not None:
        config.environment.nodes.servers = control_planes
    if runtime:
        config.environment.provider.runtime = runtime
    if local_ip:
        config.environment.local_ip = local_ip
    if k8s_version:
        config.environment.kubernetes.tag = k8s_version
    if lb_ports:
        config.environment.local_lb_ports = lb_ports
    if apps_subdomain:
        config.environment.apps_subdomain = apps_subdomain
    if service_presets is not None:
        config.environment.use_service_presets = service_presets
    if metrics_server is not None:
        config.environment.enable_metrics_server = metrics_server
    if base_dir:
        config.environment.base_dir = base_dir
    if expand_vars is not None:
        config.environment.expand_env_vars = expand_vars
    if k8s_api_port is not None:
        config.environment.kubernetes.api_port = k8s_api_port
    if schedule_on_control is not None:
        config.environment.nodes.allow_scheduling_on_control_plane = schedule_on_control
    if internal_on_control is not None:
        config.environment.nodes.internal_components_on_control_plane = internal_on_control
    if registry_name:
        config.environment.registry.name = registry_name
    if registry_storage:
        config.environment.registry.storage["size"] = registry_storage
    if services_on_workers is not None:
        config.environment.run_services_on_workers_only = services_on_workers
        
    if enable_services:
        for svc_name in enable_services:
            found = False
            if config.environment.services and config.environment.services.system:
                for svc in config.environment.services.system:
                    if svc.name == svc_name:
                        svc.enabled = True
                        found = True
                        break
            if not found:
                console.print(f"[yellow]Warning: Service '{svc_name}' not found in system services.[/yellow]")

    if disable_services:
        for svc_name in disable_services:
            found = False
            if config.environment.services and config.environment.services.system:
                for svc in config.environment.services.system:
                    if svc.name == svc_name:
                        svc.enabled = False
                        found = True
                        break
            if not found:
                console.print(f"[yellow]Warning: Service '{svc_name}' not found in system services.[/yellow]")
        
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
    console.print("[bold red]Destroying environment...[/bold red]")
    config = get_config(config_file)
    runner = CommandRunner(config)
    
    # Delete cluster
    runner.run_command(["kind", "delete", "cluster", "--name", config.environment.name])
    
    # Remove containers
    for container in ["loko-dns"]:
        runner.run_command([config.environment.provider.runtime, "rm", "-f", container], check=False)
        
    # Remove resolver file
    runner.remove_resolver_file()
        
    console.print(f"✅ Environment '{config.environment.name}' destroyed")

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
    console.print("[bold green]Starting environment...[/bold green]")
    config = get_config(config_file)
    runner = CommandRunner(config)
    
    cluster_name = config.environment.name
    runtime = config.environment.provider.runtime
    
    # Get all cluster-related containers
    try:
        result = runner.run_command(
            [runtime, "ps", "-a", "--filter", f"name={cluster_name}", "--format", "{{.Names}}"],
            capture_output=True
        )
        containers = [c.strip() for c in result.stdout.strip().split('\n') if c.strip()]
        
        if not containers:
            console.print(f"[yellow]No containers found for cluster '{cluster_name}'[/yellow]")
            console.print("Run 'loko create' first to create the environment")
            sys.exit(1)
        
        # Check if all are already running
        all_running = True
        for container in containers:
            result = runner.run_command(
                [runtime, "ps", "--filter", f"name={container}", "--filter", "status=running", "-q"],
                capture_output=True
            )
            if not result.stdout.strip():
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
    console.print("[bold yellow]Stopping environment...[/bold yellow]")
    config = get_config(config_file)
    runner = CommandRunner(config)
    
    cluster_name = config.environment.name
    runtime = config.environment.provider.runtime
    
    # Get all cluster-related containers
    try:
        result = runner.run_command(
            [runtime, "ps", "-a", "--filter", f"name={cluster_name}", "--format", "{{.Names}}"],
            capture_output=True
        )
        containers = [c.strip() for c in result.stdout.strip().split('\n') if c.strip()]
        
        if not containers:
            console.print(f"[yellow]No containers found for cluster '{cluster_name}'[/yellow]")
            return
        
        # Check if all are already stopped
        all_stopped = True
        for container in containers:
            result = runner.run_command(
                [runtime, "ps", "--filter", f"name={container}", "--filter", "status=running", "-q"],
                capture_output=True
            )
            if result.stdout.strip():
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
        dns_container = "loko-dns"
        result = runner.run_command(
            [runtime, "ps", "--filter", f"name={dns_container}", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, check=False
        )
        if result.stdout.strip():
            name, status = result.stdout.strip().split('\t', 1)
            console.print(f"├── Container: {name}")
            console.print(f"└── Status: {status}\n")
        else:
            console.print("└── [yellow]DNS container not running[/yellow]\n")
        
        # Container Status
        result = runner.run_command(
            [runtime, "ps", "-a", "--filter", f"name={cluster_name}", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True
        )
        
        if result.stdout.strip():
            console.print("[bold]📦 Container Status:[/bold]")
            lines = result.stdout.strip().split('\n')
            for idx, line in enumerate(lines):
                if line.strip():
                    name, status = line.split('\t', 1)
                    prefix = "└──" if idx == len(lines) - 1 else "├──"
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
    dns_container = "loko-dns"
    try:
        result = runner.run_command(
            [runtime, "ps", "--filter", f"name={dns_container}", "--filter", "status=running", "-q"],
            capture_output=True
        )
        if result.stdout.strip():
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
    Generate a default configuration file.
    """
    template_path = Path(__file__).parent / "templates" / "loko.yaml.example"
    
    if not template_path.exists():
        console.print("[bold red]Error: Default configuration template not found.[/bold red]")
        sys.exit(1)
        
    if os.path.exists(output) and not force:
        if not typer.confirm(f"File '{output}' already exists. Overwrite?"):
            console.print("[yellow]Operation cancelled.[/yellow]")
            sys.exit(0)
        
    shutil.copy(template_path, output)
    console.print(f"[bold green]Generated default configuration at '{output}'[/bold green]")

@config_app.command("upgrade")
def config_upgrade(
    config_file: ConfigArg = "k8s-env.yaml",
    upstream_url: Annotated[Optional[str], typer.Option(help="URL to fetch upstream versions from")] = None
):
    """
    Upgrade component versions in config file from upstream.
    """
    console.print("[bold blue]Upgrading component versions...[/bold blue]\n")
    
    if not os.path.exists(config_file):
        console.print(f"[red]Error: Config file '{config_file}' not found[/red]")
        sys.exit(1)
    
    # Determine upstream URL
    if upstream_url is None:
        upstream_url = f"{get_repository_url()}/loko/templates/versions.yaml"
    
    console.print(f"📥 Fetching versions from: {upstream_url}")
    
    try:
        # Fetch upstream versions
        import urllib.request
        with urllib.request.urlopen(upstream_url) as response:
            upstream_versions = yaml.safe_load(response.read())
        
        console.print("✅ Fetched upstream versions\n")
        
        # Load current config
        with open(config_file, 'r') as f:
            config_data = yaml.safe_load(f)
        
        updates = []
        
        # Update Kubernetes version
        if 'environment' in config_data and 'kubernetes' in config_data['environment']:
            old_version = config_data['environment']['kubernetes'].get('version', 'unknown')
            new_version = upstream_versions['kubernetes']['version']
            if old_version != new_version:
                config_data['environment']['kubernetes']['version'] = new_version
                updates.append(f"  kubernetes: {old_version} → {new_version}")
        
        # Update internal components (chart_version only)
        if 'environment' in config_data and 'internal_components' in config_data['environment']:
            for component_name, component_data in config_data['environment']['internal_components'].items():
                if component_name in upstream_versions['internal_components']:
                    upstream = upstream_versions['internal_components'][component_name]
                    
                    # Update chart_version
                    old_chart = component_data.get('chart_version', 'unknown')
                    new_chart = upstream['chart_version']
                    if old_chart != new_chart:
                        component_data['chart_version'] = new_chart
                        updates.append(f"  {component_name} (chart): {old_chart} → {new_chart}")
        
        # Update system services (chart_version only)
        if 'environment' in config_data and 'services' in config_data['environment'] and 'system' in config_data['environment']['services']:
            for service in config_data['environment']['services']['system']:
                service_name = service.get('name')
                if service_name in upstream_versions['system_services']:
                    upstream = upstream_versions['system_services'][service_name]
                    
                    # Update chart_version
                    old_chart = service.get('chart_version', 'unknown')
                    new_chart = upstream['chart_version']
                    if old_chart != new_chart:
                        service['chart_version'] = new_chart
                        updates.append(f"  {service_name} (chart): {old_chart} → {new_chart}")
        
        # Update registry (chart_version only)
        if 'environment' in config_data and 'registry' in config_data['environment']:
            if 'registry' in upstream_versions:
                upstream = upstream_versions['registry']
                
                old_chart = config_data['environment']['registry'].get('chart_version', 'unknown')
                new_chart = upstream['chart_version']
                if old_chart != new_chart:
                    config_data['environment']['registry']['chart_version'] = new_chart
                    updates.append(f"  registry (chart): {old_chart} → {new_chart}")
        
        if updates:
            console.print("[bold green]Updates found:[/bold green]")
            for update in updates:
                console.print(update)
            
            # Write updated config
            with open(config_file, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
            
            console.print(f"\n✅ Updated {len(updates)} version(s) in {config_file}")
        else:
            console.print("[green]✅ All versions are up to date[/green]")
        
    except Exception as e:
        console.print(f"[red]Error upgrading config: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    app()
