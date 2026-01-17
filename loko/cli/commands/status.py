"""Status commands: status, validate."""
import os
import sys
from rich.console import Console
from rich.table import Table

from loko.utils import PASSWORD_PROTECTED_WORKLOADS, get_dns_container_name
from loko.validators import ensure_config_file, ensure_docker_running
from loko.runner import CommandRunner
from loko.cli_types import ConfigArg
from .lifecycle import get_config


console = Console()


def status(config_file: ConfigArg = "loko.yaml") -> None:
    """
    Show environment status.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    console.print("[bold blue]Environment Status[/bold blue]\n")
    config = get_config(config_file)
    runner = CommandRunner(config)

    cluster_name = config.environment.name
    runtime = config.environment.cluster.provider.runtime

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
        env = config.environment
        network = env.network
        cluster = env.cluster
        nodes = cluster.nodes
        scheduling = nodes.scheduling

        console.print("[bold]🌍 Environment Configuration:[/bold]")
        console.print(f"├── Name: {env.name}")
        console.print(f"├── Base Directory: {base_dir_display}")
        console.print(f"├── Domain: {network.domain}")
        console.print(f"├── IP: {network.ip}")
        console.print(f"├── Container Runtime: {cluster.provider.runtime}")
        console.print(f"├── Nodes:")
        console.print(f"│   ├── Control Plane: {nodes.servers}")
        console.print(f"│   ├── Workers: {nodes.workers}")
        console.print(f"│   ├── Allow Control Plane Workloads: {scheduling.control_plane.allow_workloads}")
        console.print(f"│   └── Isolate Workloads on Workers: {scheduling.workers.isolate_workloads}")
        console.print(f"└── Workload Presets Enabled: {env.workloads.use_presets}\n")

        # Enabled Workloads
        console.print("[bold]🔌 Enabled Workloads:[/bold]")
        sys_enabled = []
        user_enabled = []

        if env.workloads and env.workloads.system:
            for wkld in env.workloads.system:
                if wkld.enabled:
                    ports = ', '.join(map(str, wkld.ports)) if getattr(wkld, 'ports', None) else 'none'
                    sys_enabled.append(f"{wkld.name}: {ports}")

        if env.workloads and env.workloads.user:
            for wkld in env.workloads.user:
                if wkld.enabled:
                    ns = getattr(wkld, 'namespace', wkld.name)
                    user_enabled.append(f"{wkld.name} (namespace: {ns})")

        if sys_enabled:
            console.print("├── System Workloads (with presets):")
            for i, wkld in enumerate(sys_enabled):
                console.print(f"│   ├── {wkld}")
        else:
            console.print("├── System Workloads: None enabled")

        if user_enabled:
            console.print("├── User Workloads (custom configuration):")
            for i, wkld in enumerate(user_enabled):
                console.print(f"│   ├── {wkld}")
        else:
            console.print("├── User Workloads: None enabled")

        console.print(f"└── Registry: {env.registry.name}.{network.domain}\n")

        # Cluster Info
        console.print("[bold]🏢 Cluster Information:[/bold]")
        result = runner.run_command(
            ["kubectl", "cluster-info"],
            capture_output=True,
            check=False
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    console.print(f"├── {line.strip()}")
        else:
            console.print("├── [yellow]Cluster not accessible (stopped or kubectl not configured)[/yellow]")
        console.print()

        # DNS Service
        console.print("[bold]🔍 DNS Service:[/bold]")
        dns_container = get_dns_container_name(cluster_name)
        dns_status = runner.list_containers(name_filter=dns_container, format_expr="{{.Names}}\t{{.Status}}", check=False)
        resolver_port = network.dns_port
        if dns_status:
            name, status_str = dns_status[0].split('\t', 1)
            console.print(f"├── Container: {name}")
            console.print(f"├── Status: {status_str}")
            console.print(f"└── Port: {resolver_port}\n")
        else:
            console.print(f"├── [yellow]DNS container not running[/yellow]")
            console.print(f"└── Port: {resolver_port}\n")

        # Container Status
        containers_status = runner.list_containers(name_filter=cluster_name, all_containers=True, format_expr="{{.Names}}\t{{.Status}}")

        if containers_status:
            console.print("[bold]📦 Container Status:[/bold]")
            for idx, line in enumerate(containers_status):
                if line.strip():
                    name, status_str = line.split('\t', 1)
                    prefix = "└──" if idx == len(containers_status) - 1 else "├──"
                    if 'Up' in status_str:
                        console.print(f"{prefix} [green]✅ {name}[/green]: {status_str}")
                    else:
                        console.print(f"{prefix} [yellow]⏸️  {name}[/yellow]: {status_str}")
            console.print()

        # Kubernetes Nodes
        console.print("[bold]☸️  Kubernetes Nodes:[/bold]")
        result = runner.run_command(
            ["kubectl", "get", "nodes", "-o", "wide"],
            capture_output=True,
            check=False
        )
        if result.returncode == 0:
            console.print(result.stdout)
        else:
            console.print("[yellow]⚠️  Could not fetch node status (cluster stopped or kubectl not configured)[/yellow]\n")

        # Quick Reference - Service Access Info
        console.print("[bold]🔗 Quick Reference - Service Access:[/bold]")

        # Determine the app domain
        if network.subdomain.enabled:
            app_domain = f"{network.subdomain.value}.{network.domain}"
        else:
            app_domain = network.domain

        # Workload DNS Names
        enabled_workloads = [wkld for wkld in env.workloads.system if wkld.enabled]
        if enabled_workloads:
            table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 2))
            table.add_column("Workload", style="cyan")
            table.add_column("DNS Name", style="yellow")
            table.add_column("Ports", style="green")

            for wkld in enabled_workloads:
                dns_name = f"{wkld.name}.{network.domain}"
                ports = ", ".join(str(p) for p in wkld.ports) if wkld.ports else "N/A"
                table.add_row(wkld.name, dns_name, ports)

            console.print(table)

        password_workloads_enabled = {
            wkld.name
            for wkld in (env.workloads.system + env.workloads.user)
            if wkld.enabled and wkld.name in PASSWORD_PROTECTED_WORKLOADS
        }

        if password_workloads_enabled:
            secrets_file = os.path.join(os.path.expandvars(env.base_dir), env.name, 'workload-secrets.txt')
            console.print(f"├── Workload Credentials: [yellow]{secrets_file}[/yellow]")

        # App deployment info
        kube_context = f"kind-{env.name}"
        registry_host = f"{env.registry.name}.{network.domain}"
        app_domain_display = f"https://<app-name>.{app_domain}"

        console.print(f"├── Kubeconfig Context: [yellow]{kube_context}[/yellow]")
        console.print(f"├── Registry: [yellow]{registry_host}[/yellow]")
        console.print(f"└── Apps Domain: [yellow]{app_domain_display}[/yellow]")
        console.print()

    except Exception as e:
        console.print(f"[bold red]Error checking status: {e}[/bold red]")
        sys.exit(1)


def validate(config_file: ConfigArg = "loko.yaml") -> None:
    """
    Validate the environment.
    """
    ensure_config_file(config_file)
    ensure_docker_running()

    console.print("[bold green]Validating environment...[/bold green]\n")
    config = get_config(config_file)
    runner = CommandRunner(config)

    cluster_name = config.environment.name
    runtime = config.environment.cluster.provider.runtime

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
        pass

    # Summary
    console.print("\n" + "="*50)
    if validation_passed:
        console.print("[bold green]✅ Validation PASSED - Environment is healthy![/bold green]")
    else:
        console.print("[bold red]❌ Validation FAILED - Some checks did not pass[/bold red]")
        sys.exit(1)
