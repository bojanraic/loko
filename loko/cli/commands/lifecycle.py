"""Lifecycle commands: init, create, destroy, recreate, clean."""
import os
import re
import stat
import subprocess
import shutil
from typing import Optional, List
from rich.console import Console

from loko.config import RootConfig
from loko.utils import load_config, get_dns_container_name, print_environment_summary
from loko.generator import ConfigGenerator
from loko.runner import CommandRunner
from loko.validators import ensure_config_file, ensure_docker_running, ensure_base_dir_writable, ensure_single_server_cluster, ensure_ports_available


console = Console()


def _apply_config_overrides(config: RootConfig, **overrides) -> None:
    """Apply CLI overrides to configuration."""
    # Environment overrides
    if overrides.get('name'):
        config.environment.name = overrides['name']
    if overrides.get('domain'):
        config.environment.network.domain = overrides['domain']
    if overrides.get('local_ip'):
        config.environment.network.ip = overrides['local_ip']
    if overrides.get('apps_subdomain'):
        config.environment.network.subdomain.value = overrides['apps_subdomain']
    if overrides.get('base_dir'):
        config.environment.base_dir = overrides['base_dir']

    # Node overrides (now under cluster.nodes)
    if overrides.get('workers') is not None:
        config.environment.cluster.nodes.workers = overrides['workers']
    if overrides.get('control_planes') is not None:
        config.environment.cluster.nodes.servers = overrides['control_planes']
    if overrides.get('schedule_on_control') is not None:
        config.environment.cluster.nodes.scheduling.control_plane.allow_workloads = overrides['schedule_on_control']
    if overrides.get('internal_on_control') is not None:
        config.environment.cluster.nodes.scheduling.control_plane.isolate_internal_components = overrides['internal_on_control']

    # Provider overrides (now under cluster.provider)
    if overrides.get('runtime'):
        config.environment.cluster.provider.runtime = overrides['runtime']

    # Kubernetes overrides (now under cluster.kubernetes)
    if overrides.get('k8s_version'):
        config.environment.cluster.kubernetes.tag = overrides['k8s_version']
    if overrides.get('k8s_api_port') is not None:
        config.environment.cluster.kubernetes.api_port = overrides['k8s_api_port']

    # Registry overrides
    if overrides.get('registry_name'):
        config.environment.registry.name = overrides['registry_name']
    if overrides.get('registry_storage'):
        config.environment.registry.storage.size = overrides['registry_storage']

    # Load balancer overrides (now under network.lb_ports)
    if overrides.get('lb_ports'):
        config.environment.network.lb_ports = overrides['lb_ports']

    # Feature flags (now under workloads.use_presets and internal_components.metrics_server.enabled)
    if overrides.get('workload_presets') is not None:
        config.environment.workloads.use_presets = overrides['workload_presets']
    if overrides.get('metrics_server') is not None:
        config.environment.internal_components.metrics_server.enabled = overrides['metrics_server']
    if overrides.get('expand_vars') is not None:
        config.environment.expand_env_vars = overrides['expand_vars']
    if overrides.get('workloads_on_workers') is not None:
        config.environment.cluster.nodes.scheduling.workers.isolate_workloads = overrides['workloads_on_workers']


def _update_workload_state(config: RootConfig, workload_names: Optional[List[str]], enabled: bool) -> None:
    """Update enabled state for workloads."""
    if not workload_names:
        return

    for wkld_name in workload_names:
        found = False
        if config.environment.workloads and config.environment.workloads.system:
            for wkld in config.environment.workloads.system:
                if wkld.name == wkld_name:
                    wkld.enabled = enabled
                    found = True
                    break
        if not found:
            console.print(f"[yellow]Warning: Workload '{wkld_name}' not found in system workloads.[/yellow]")


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
    workload_presets: Optional[bool] = None,
    metrics_server: Optional[bool] = None,
    enable_workloads: Optional[List[str]] = None,
    disable_workloads: Optional[List[str]] = None,
    base_dir: Optional[str] = None,
    expand_vars: Optional[bool] = None,
    k8s_api_port: Optional[int] = None,
    schedule_on_control: Optional[bool] = None,
    internal_on_control: Optional[bool] = None,
    registry_name: Optional[str] = None,
    registry_storage: Optional[str] = None,
    workloads_on_workers: Optional[bool] = None,
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
        workload_presets=workload_presets,
        metrics_server=metrics_server,
        base_dir=base_dir,
        expand_vars=expand_vars,
        k8s_api_port=k8s_api_port,
        schedule_on_control=schedule_on_control,
        internal_on_control=internal_on_control,
        registry_name=registry_name,
        registry_storage=registry_storage,
        workloads_on_workers=workloads_on_workers,
    )

    # Update workload states
    _update_workload_state(config, enable_workloads, True)
    _update_workload_state(config, disable_workloads, False)

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
    workload_presets: Optional[bool] = None,
    metrics_server: Optional[bool] = None,
    enable_workload: Optional[List[str]] = None,
    disable_workload: Optional[List[str]] = None,
    base_dir: Optional[str] = None,
    expand_vars: Optional[bool] = None,
    k8s_api_port: Optional[int] = None,
    schedule_on_control: Optional[bool] = None,
    internal_on_control: Optional[bool] = None,
    registry_name: Optional[str] = None,
    registry_storage: Optional[str] = None,
    workloads_on_workers: Optional[bool] = None,
) -> None:
    """
    Initialize the local environment (generate configs, setup certs, network).
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    config = get_config(
        config_file, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, workload_presets,
        metrics_server, enable_workload, disable_workload,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, workloads_on_workers
    )

    # Validate cluster configuration
    ensure_single_server_cluster(config.environment.cluster.nodes.servers)

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
    workload_presets: Optional[bool] = None,
    metrics_server: Optional[bool] = None,
    enable_workload: Optional[List[str]] = None,
    disable_workload: Optional[List[str]] = None,
    base_dir: Optional[str] = None,
    expand_vars: Optional[bool] = None,
    k8s_api_port: Optional[int] = None,
    schedule_on_control: Optional[bool] = None,
    internal_on_control: Optional[bool] = None,
    registry_name: Optional[str] = None,
    registry_storage: Optional[str] = None,
    workloads_on_workers: Optional[bool] = None,
) -> None:
    """
    Create the full environment.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    # Load config first to get environment name
    config = get_config(
        config_file, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, workload_presets,
        metrics_server, enable_workload, disable_workload,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, workloads_on_workers
    )

    # Validate cluster configuration
    ensure_single_server_cluster(config.environment.cluster.nodes.servers)

    # Validate port availability before creating any resources
    ensure_ports_available(config)

    console.print(f"[bold green]Creating environment '{config.environment.name}'...[/bold green]")

    # Run init first
    init(
        config_file, templates_dir, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, workload_presets,
        metrics_server, enable_workload, disable_workload,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, workloads_on_workers
    )

    config = get_config(
        config_file, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, workload_presets,
        metrics_server, enable_workload, disable_workload,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, workloads_on_workers
    )
    runner = CommandRunner(config)

    runner.setup_resolver_file()
    runner.create_cluster()
    runner.start_dnsmasq()
    runner.inject_dns_nameserver()
    runner.wait_for_cluster_ready()
    runner.set_control_plane_scheduling()
    runner.label_nodes()
    runner.list_nodes()
    runner.setup_wildcard_cert()
    runner.deploy_workloads()
    runner.configure_workloads()
    runner.fetch_workload_secrets()

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
    runtime = config.environment.cluster.provider.runtime

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

    # Remove resolver file (handle gracefully if sudo fails)
    try:
        runner.remove_resolver_file()
    except Exception as e:
        console.print(f"[yellow]⚠️  Could not remove resolver file (may require sudo): {e}[/yellow]")

    # Remove environment directory
    env_dir = runner.k8s_dir
    if os.path.exists(env_dir):
        console.print(f"🔄 Removing environment directory '{env_dir}'...")
        try:
            # Try to remove normally first
            shutil.rmtree(env_dir)
            console.print(f"✅ Environment directory removed")
        except PermissionError:
            # If permission denied, try to change permissions and retry
            console.print(f"[yellow]⚠️  Permission denied, attempting to fix permissions...[/yellow]")
            try:
                # Change permissions recursively to make everything writable
                def make_writable(path):
                    """Make a path writable by adding write permissions."""
                    try:
                        os.chmod(path, stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
                    except (PermissionError, OSError):
                        pass  # If we can't change permissions, continue anyway

                # Walk the directory tree and make everything writable
                try:
                    for root, dirs, files in os.walk(env_dir, topdown=False):
                        for name in files:
                            make_writable(os.path.join(root, name))
                        for name in dirs:
                            make_writable(os.path.join(root, name))
                    make_writable(env_dir)
                except (PermissionError, OSError):
                    # If we can't even walk the directory, just try to remove it anyway
                    pass

                # Try removal again
                shutil.rmtree(env_dir)
                console.print(f"✅ Environment directory removed")
            except Exception as e:
                # If all else fails, warn the user but don't fail the command
                console.print(f"[yellow]⚠️  Could not fully remove environment directory '{env_dir}': {e}[/yellow]")
                console.print(f"[yellow]    You may need to manually remove it with: sudo rm -rf {env_dir}[/yellow]")
    else:
        console.print(f"ℹ️  Environment directory '{env_dir}' does not exist")

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
    workload_presets: Optional[bool] = None,
    metrics_server: Optional[bool] = None,
    enable_workload: Optional[List[str]] = None,
    disable_workload: Optional[List[str]] = None,
    base_dir: Optional[str] = None,
    expand_vars: Optional[bool] = None,
    k8s_api_port: Optional[int] = None,
    schedule_on_control: Optional[bool] = None,
    internal_on_control: Optional[bool] = None,
    registry_name: Optional[str] = None,
    registry_storage: Optional[str] = None,
    workloads_on_workers: Optional[bool] = None,
) -> None:
    """
    Recreate the environment (destroy + create).
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    # Load config to get environment name
    config = get_config(
        config_file, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, workload_presets,
        metrics_server, enable_workload, disable_workload,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, workloads_on_workers
    )

    # Validate cluster configuration
    ensure_single_server_cluster(config.environment.cluster.nodes.servers)

    console.print(f"[bold blue]Recreating environment '{config.environment.name}'...[/bold blue]\n")

    # Destroy first (this will free up ports)
    destroy(config_file)

    console.print()

    # Then create
    create(
        config_file, templates_dir, name, domain, workers, control_planes, runtime,
        local_ip, k8s_version, lb_ports, apps_subdomain, workload_presets,
        metrics_server, enable_workload, disable_workload,
        base_dir, expand_vars, k8s_api_port, schedule_on_control,
        internal_on_control, registry_name, registry_storage, workloads_on_workers
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
