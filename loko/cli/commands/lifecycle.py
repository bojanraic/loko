"""Lifecycle commands: init, create, destroy, recreate, clean."""
import os
import re
import subprocess
import shutil
from typing import Optional, List
from rich.console import Console

from loko.config import RootConfig
from loko.utils import load_config, get_dns_container_name, print_environment_summary
from loko.generator import ConfigGenerator
from loko.runner import CommandRunner
from loko.validators import ensure_config_file, ensure_docker_running, ensure_base_dir_writable, ensure_single_server_cluster


console = Console()


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
        raise FileNotFoundError(f"Configuration file '{config_path}' not found.")

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

    # Use either method if available
    if ip_via_route:
        return ip_via_route
    if ip_via_socket:
        return ip_via_socket

    # Fallback default
    return "192.168.1.1"


def init(
    config_file: str = "loko.yaml",
    templates_dir: Optional[str] = None,
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
    enable_service: Optional[List[str]] = None,
    disable_service: Optional[List[str]] = None,
    base_dir: Optional[str] = None,
    expand_vars: Optional[bool] = None,
    k8s_api_port: Optional[int] = None,
    schedule_on_control: Optional[bool] = None,
    internal_on_control: Optional[bool] = None,
    registry_name: Optional[str] = None,
    registry_storage: Optional[str] = None,
    services_on_workers: Optional[bool] = None,
) -> None:
    """
    Initialize the local environment (generate configs, setup certs, network).
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(
        config_file, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, service_presets,
        metrics_server, enable_service, disable_service,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, services_on_workers
    )

    # Validate cluster configuration
    ensure_single_server_cluster(config.environment.nodes.servers)

    console.print(f"[bold green]Initializing environment '{config.environment.name}'...[/bold green]")

    # Check that base directory is writable before proceeding
    ensure_base_dir_writable(config.environment.base_dir)

    # Generate configs
    generator = ConfigGenerator(config, config_file, templates_dir)
    generator.generate_configs()

    # Setup runtime
    runner = CommandRunner(config)
    runner.check_runtime()
    runner.setup_certificates()
    runner.ensure_network()


def create(
    config_file: str = "loko.yaml",
    templates_dir: Optional[str] = None,
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
    enable_service: Optional[List[str]] = None,
    disable_service: Optional[List[str]] = None,
    base_dir: Optional[str] = None,
    expand_vars: Optional[bool] = None,
    k8s_api_port: Optional[int] = None,
    schedule_on_control: Optional[bool] = None,
    internal_on_control: Optional[bool] = None,
    registry_name: Optional[str] = None,
    registry_storage: Optional[str] = None,
    services_on_workers: Optional[bool] = None,
) -> None:
    """
    Create the full environment.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    # Load config first to get environment name
    config = get_config(
        config_file, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, service_presets,
        metrics_server, enable_service, disable_service,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, services_on_workers
    )

    # Validate cluster configuration
    ensure_single_server_cluster(config.environment.nodes.servers)

    console.print(f"[bold green]Creating environment '{config.environment.name}'...[/bold green]")

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

    runner.setup_resolver_file()
    runner.create_cluster()
    runner.start_dnsmasq()
    runner.inject_dns_nameserver()
    runner.fetch_kubeconfig()
    runner.wait_for_cluster_ready()
    runner.set_control_plane_scheduling()
    runner.label_nodes()
    runner.list_nodes()
    runner.setup_wildcard_cert()
    runner.deploy_services()
    runner.fetch_service_secrets()

    # Print environment summary
    print_environment_summary(config)


def destroy(config_file: str = "loko.yaml") -> None:
    """
    Destroy the environment.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)
    console.print(f"[bold red]Destroying environment '{config.environment.name}'...[/bold red]")
    runner = CommandRunner(config)

    cluster_name = config.environment.name
    runtime = config.environment.provider.runtime

    # Delete cluster
    runner.delete_cluster()

    # Remove DNS container
    dns_container = get_dns_container_name(cluster_name)
    dns_containers = runner.list_containers(name_filter=dns_container, all_containers=True, quiet=True, check=False)
    if dns_containers:
        console.print(f"🔄 Removing DNS container '{dns_container}'...")
        runner.run_command([runtime, "rm", "-f", dns_container], check=False)
        console.print(f"✅ DNS container removed")
    else:
        console.print(f"ℹ️  DNS container '{dns_container}' does not exist")

    # Remove resolver file
    runner.remove_resolver_file()

    console.print(f"✅ Environment '{cluster_name}' destroyed")


def recreate(
    config_file: str = "loko.yaml",
    templates_dir: Optional[str] = None,
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
    enable_service: Optional[List[str]] = None,
    disable_service: Optional[List[str]] = None,
    base_dir: Optional[str] = None,
    expand_vars: Optional[bool] = None,
    k8s_api_port: Optional[int] = None,
    schedule_on_control: Optional[bool] = None,
    internal_on_control: Optional[bool] = None,
    registry_name: Optional[str] = None,
    registry_storage: Optional[str] = None,
    services_on_workers: Optional[bool] = None,
) -> None:
    """
    Recreate the environment (destroy + create).
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    # Load config to get environment name
    config = get_config(
        config_file, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, service_presets,
        metrics_server, enable_service, disable_service,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, services_on_workers
    )

    # Validate cluster configuration
    ensure_single_server_cluster(config.environment.nodes.servers)

    console.print(f"[bold blue]Recreating environment '{config.environment.name}'...[/bold blue]\n")

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


def clean(config_file: str = "loko.yaml") -> None:
    """
    Clean up the environment (destroy + remove artifacts).
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(config_file)

    console.print(f"[bold red]Cleaning environment '{config.environment.name}'...[/bold red]\n")

    # Destroy first
    destroy(config_file)

    console.print()

    # Remove generated directories
    k8s_dir = os.path.join(os.path.expandvars(config.environment.base_dir), config.environment.name)

    if os.path.exists(k8s_dir):
        console.print(f"[yellow]Removing directory: {k8s_dir}[/yellow]")
        shutil.rmtree(k8s_dir)
        console.print(f"[green]✅ Removed {k8s_dir}[/green]")

    console.print(f"\n[bold green]✅ Environment '{config.environment.name}' cleaned[/bold green]")
