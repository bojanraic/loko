import subprocess
import shutil
import os
import time
from datetime import datetime
from typing import List, Optional
from rich.console import Console
from .config import RootConfig
from .utils import PASSWORD_PROTECTED_WORKLOADS, get_dns_container_name, is_port_in_use

console = Console()

class CommandRunner:
    def __init__(self, config: RootConfig):
        self.config = config
        self.env = config.environment
        self.runtime = self.env.cluster.provider.runtime
        self.k8s_dir = os.path.join(os.path.expandvars(self.env.base_dir), self.env.name)
        self.kubeconfig = os.path.join(self.k8s_dir, "kubeconfig")

    @property
    def workload_secrets_path(self) -> str:
        """Return the path to the workload secrets file."""
        return os.path.join(self.k8s_dir, 'workload-secrets.txt')

    def run_command(self, command: List[str], check: bool = True, capture_output: bool = False) -> subprocess.CompletedProcess:
        """Run a shell command."""
        try:
            result = subprocess.run(
                command,
                check=check,
                capture_output=capture_output,
                text=True
            )
            return result
        except subprocess.CalledProcessError as e:
            if check:
                console.print(f"[bold red]Error running command: {' '.join(command)}[/bold red]")
                if e.stderr:
                    console.print(f"[red]{e.stderr}[/red]")
                raise
            return e

    def list_containers(self, name_filter: Optional[str] = None, all_containers: bool = False,
                       quiet: bool = False, status_filter: Optional[str] = None,
                       format_expr: Optional[str] = None, check: bool = True) -> List[str]:
        """List containers with optional filters. Returns list of container IDs or names."""
        cmd = [self.runtime, "ps"]
        if all_containers:
            cmd.append("-a")
        if quiet:
            cmd.append("-q")
        if name_filter:
            cmd.extend(["--filter", f"name={name_filter}"])
        if status_filter:
            cmd.extend(["--filter", f"status={status_filter}"])
        if format_expr:
            cmd.extend(["--format", format_expr])

        result = self.run_command(cmd, capture_output=True, check=check)
        return [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]

    def check_runtime(self):
        """Check if container runtime is running."""
        console.print(f"🔍 Checking if {self.runtime} is running...")
        if not shutil.which(self.runtime):
            raise RuntimeError(f"{self.runtime} not found in PATH")

        try:
            self.run_command([self.runtime, "info"], capture_output=True)
            console.print(f"✅ {self.runtime} is running")
        except subprocess.CalledProcessError:
            raise RuntimeError(f"{self.runtime} is not running")

    def setup_certificates(self):
        """Setup mkcert certificates."""
        console.print("🔄 Setting up certificates...")
        cert_dir = os.path.join(self.k8s_dir, "certs")
        os.makedirs(cert_dir, exist_ok=True)

        local_domain = self.env.network.domain
        cert_file = os.path.join(cert_dir, f"{local_domain}.pem")
        key_file = os.path.join(cert_dir, f"{local_domain}-key.pem")
        combined_file = os.path.join(cert_dir, f"{local_domain}-combined.pem")

        if not os.path.exists(cert_file):
            console.print("  🔐 Generating certificates using mkcert...")
            domains = [f"*.{local_domain}", local_domain]
            if self.env.network.subdomain.enabled:
                domains.append(f"*.{self.env.network.subdomain.value}.{local_domain}")

            # Add Garage-specific wildcard domains if Garage is enabled
            garage_enabled = False
            if self.env.workloads.system:
                garage_enabled = any(wkld.name == "garage" and wkld.enabled for wkld in self.env.workloads.system)

            if garage_enabled:
                domains.append(f"*.garage.{local_domain}")
                domains.append(f"*.s3.{local_domain}")

            cmd = ["mkcert", "-cert-file", cert_file, "-key-file", key_file] + domains
            self.run_command(cmd)

        # Copy root CA
        caroot = subprocess.check_output(["mkcert", "-CAROOT"], text=True).strip()
        shutil.copy(os.path.join(caroot, "rootCA.pem"), os.path.join(cert_dir, "rootCA.pem"))
        shutil.copy(os.path.join(caroot, "rootCA-key.pem"), os.path.join(cert_dir, "rootCA-key.pem"))
        os.chmod(os.path.join(cert_dir, "rootCA-key.pem"), 0o600)

        # Create combined file
        with open(combined_file, 'wb') as wfd:
            for f in [cert_file, key_file]:
                with open(f, 'rb') as fd:
                    shutil.copyfileobj(fd, wfd)

        console.print("✅ Certificates setup complete")

    def ensure_network(self):
        """Ensure container network exists."""
        network_name = "kind" # Default kind network
        console.print(f"🔄 Checking for '{network_name}' network...")

        try:
            output = self.run_command([self.runtime, "network", "ls", "--format", "{{.Name}}"], capture_output=True).stdout
            if network_name not in output.splitlines():
                console.print(f"  🔄 Creating '{network_name}' network...")
                self.run_command([self.runtime, "network", "create", network_name])
                console.print(f"  ✅ '{network_name}' network created")
            else:
                console.print(f"ℹ️ '{network_name}' network already exists")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not check/create network: {e}[/yellow]")

    def cluster_exists(self) -> bool:
        """Check if Kind cluster exists."""
        try:
            result = self.run_command(["kind", "get", "clusters"], capture_output=True, check=False)
            if result.returncode == 0:
                clusters = result.stdout.strip().splitlines()
                return self.env.name in clusters
            return False
        except Exception:
            return False

    def _apply_node_labels(self):
        """Apply node labels after cluster creation (KIND overrides kubeadm labels)."""
        console.print("🔄 Applying node labels...")

        nodes = self.env.cluster.nodes

        # Build label map for control plane nodes
        for i in range(nodes.servers):
            # KIND naming: control-plane, control-plane2, control-plane3, ... (first has no number, rest start at 2)
            node_name = f"{self.env.name}-control-plane" if i == 0 else f"{self.env.name}-control-plane{i+1}"

            # Base labels that should always be present
            labels = {
                "ingress-ready": "true",
                "node-role": "control-plane",
            }

            # Add user-defined labels from config
            if nodes.labels:
                # Check for individual node labels first
                individual_key = f"control-plane-{i}"
                if nodes.labels.individual and individual_key in nodes.labels.individual:
                    labels.update(nodes.labels.individual[individual_key])
                # Otherwise use global control-plane labels
                elif nodes.labels.control_plane:
                    labels.update(nodes.labels.control_plane)

            # Apply labels
            for key, value in labels.items():
                label_str = f"{key}={value}"
                try:
                    self.run_command(["kubectl", "--kubeconfig", self.kubeconfig, "label", "node", node_name, label_str, "--overwrite"], capture_output=True)
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not apply label {label_str} to {node_name}: {e}[/yellow]")

        # Build label map for worker nodes
        for i in range(nodes.workers):
            # KIND naming: worker, worker2, worker3, ... (first has no number, rest start at 2)
            node_name = f"{self.env.name}-worker" if i == 0 else f"{self.env.name}-worker{i+1}"

            labels = {
                "node-role": "worker",
            }

            # Add user-defined labels from config
            if nodes.labels:
                # Check for individual node labels first
                individual_key = f"worker-{i}"
                if nodes.labels.individual and individual_key in nodes.labels.individual:
                    labels.update(nodes.labels.individual[individual_key])
                # Otherwise use global worker labels
                elif nodes.labels.worker:
                    labels.update(nodes.labels.worker)

            # Apply labels
            for key, value in labels.items():
                label_str = f"{key}={value}"
                try:
                    self.run_command(["kubectl", "--kubeconfig", self.kubeconfig, "label", "node", node_name, label_str, "--overwrite"], capture_output=True)
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not apply label {label_str} to {node_name}: {e}[/yellow]")

        console.print("✅ Node labels applied")

    def create_cluster(self):
        """Create Kind cluster."""
        console.print(f"🔄 Creating cluster '{self.env.name}'...")

        # Check if cluster exists
        if self.cluster_exists():
            console.print(f"ℹ️ Cluster '{self.env.name}' already exists")
            return

        config_file = os.path.join(self.k8s_dir, "config", "cluster.yaml")
        cmd = ["kind", "create", "cluster", "--name", self.env.name, "--config", config_file]

        try:
            subprocess.run(cmd, check=True, text=True, capture_output=False)
        except subprocess.CalledProcessError as e:
            console.print(f"[bold red]Error creating cluster: {e}[/bold red]")
            raise
        console.print(f"✅ Cluster '{self.env.name}' created")

        # Fetch kubeconfig immediately after creation so we can use kubectl
        self.fetch_kubeconfig()

        # Apply node labels post-creation (KIND overrides kubeadm labels)
        self._apply_node_labels()

    def delete_cluster(self):
        """Delete Kind cluster."""
        if not self.cluster_exists():
            console.print(f"ℹ️  Cluster '{self.env.name}' does not exist")
            return

        console.print(f"🔄 Deleting cluster '{self.env.name}'...")
        self.run_command(["kind", "delete", "cluster", "--name", self.env.name])
        console.print(f"✅ Cluster '{self.env.name}' deleted")

    def deploy_workloads(self, workload_names: Optional[List[str]] = None):
        """Deploy workloads using helmfile."""
        if workload_names:
            console.print(f"🔄 Deploying workloads: {', '.join(workload_names)}...")
        else:
            console.print("🔄 Deploying all workloads...")

        helmfile_config = os.path.join(self.k8s_dir, "config", "helmfile.yaml")

        # Prepare environment variables for helmfile
        env = os.environ.copy()

        # Add variables that might be used in helmfile values
        network = self.env.network
        subdomain_value = network.subdomain.value
        local_domain = network.domain
        local_apps_domain = f"{subdomain_value}.{local_domain}" if network.subdomain.enabled else local_domain

        env.update({
            'ENV_NAME': self.env.name,
            'LOCAL_DOMAIN': local_domain,
            'LOCAL_IP': network.ip,
            'REGISTRY_NAME': self.env.registry.name,
            'REGISTRY_HOST': f"{self.env.registry.name}.{local_domain}",
            'APPS_SUBDOMAIN': subdomain_value,
            'USE_APPS_SUBDOMAIN': str(network.subdomain.enabled).lower(),
            'LOCAL_APPS_DOMAIN': local_apps_domain,
        })

        # Add and update helm repositories first
        console.print("🔄 Adding helm repositories...")
        repos_cmd = [
            "helmfile",
            "--kube-context", f"kind-{self.env.name}",
            "--file", helmfile_config,
            "repos"
        ]

        try:
            subprocess.run(
                repos_cmd,
                check=True,
                capture_output=True,
                text=True,
                env=env
            )
        except subprocess.CalledProcessError as e:
            console.print(f"[yellow]⚠️  Warning: Could not add repositories: {e.stderr}[/yellow]")

        # Update all helm repositories
        console.print("🔄 Updating helm repository indexes...")
        update_cmd = ["helm", "repo", "update"]

        try:
            subprocess.run(
                update_cmd,
                check=True,
                capture_output=True,
                text=True,
                env=env
            )
        except subprocess.CalledProcessError as e:
            console.print(f"[yellow]⚠️  Warning: Could not update repository indexes: {e.stderr}[/yellow]")

        # Use sync instead of apply to avoid helm-diff issues
        cmd = [
            "helmfile",
            "--kube-context", f"kind-{self.env.name}",
            "--file", helmfile_config,
        ]

        if workload_names:
            for name in workload_names:
                cmd.extend(["--selector", f"name={name}"])

        cmd.append("sync")

        # Run with updated environment
        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=False, # Let it print to stdout
                text=True,
                env=env
            )
        except subprocess.CalledProcessError as e:
            console.print(f"[bold red]Error running helmfile: {e}[/bold red]")
            raise

        if workload_names:
            console.print(f"✅ Workloads deployed: {', '.join(workload_names)}")
        else:
            console.print("✅ Workloads deployed")

        # Deploy TCP routes for system workloads
        self.deploy_tcp_routes(workload_names)

    def destroy_workloads(self, workload_names: Optional[List[str]] = None):
        """Destroy workloads using helmfile."""
        if workload_names:
            console.print(f"🔄 Undeploying workloads: {', '.join(workload_names)}...")
        else:
            console.print("🔄 Undeploying all workloads...")

        helmfile_config = os.path.join(self.k8s_dir, "config", "helmfile.yaml")

        # Prepare environment variables for helmfile
        env = os.environ.copy()
        network = self.env.network
        subdomain_value = network.subdomain.value
        local_domain = network.domain
        local_apps_domain = f"{subdomain_value}.{local_domain}" if network.subdomain.enabled else local_domain

        env.update({
            'ENV_NAME': self.env.name,
            'LOCAL_DOMAIN': local_domain,
            'LOCAL_IP': network.ip,
            'REGISTRY_NAME': self.env.registry.name,
            'REGISTRY_HOST': f"{self.env.registry.name}.{local_domain}",
            'APPS_SUBDOMAIN': subdomain_value,
            'USE_APPS_SUBDOMAIN': str(network.subdomain.enabled).lower(),
            'LOCAL_APPS_DOMAIN': local_apps_domain,
        })

        cmd = [
            "helmfile",
            "--kube-context", f"kind-{self.env.name}",
            "--file", helmfile_config,
        ]

        if workload_names:
            for name in workload_names:
                cmd.extend(["--selector", f"name={name}"])

        cmd.append("destroy")

        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=False,
                text=True,
                env=env
            )
        except subprocess.CalledProcessError as e:
            console.print(f"[bold red]Error running helmfile destroy: {e}[/bold red]")
            raise

        # Remove secrets for undeployed workloads
        if workload_names:
            self.remove_workload_secrets(workload_names)
            console.print(f"✅ Workloads undeployed: {', '.join(workload_names)}")
        else:
            # If destroying all workloads, we could remove the entire secrets file
            # but let's be conservative and only remove when specific workloads are given
            console.print("✅ Workloads undeployed")

    def get_all_workloads(self) -> List[dict]:
        """Get all enabled workloads (system and user)."""
        all_workloads = []

        # Add internal components (traefik, metrics-server, registry)
        all_workloads.append({"name": "traefik", "type": "internal", "enabled": True})
        if self.env.internal_components.metrics_server.enabled:
            all_workloads.append({"name": "metrics-server", "type": "internal", "enabled": True})
        all_workloads.append({"name": "registry", "type": "internal", "enabled": True})

        # Add system workloads
        if self.env.workloads.system:
            for wkld in self.env.workloads.system:
                all_workloads.append({
                    "name": wkld.name,
                    "type": "system",
                    "enabled": wkld.enabled,
                    "namespace": wkld.namespace or wkld.name
                })

        # Add user workloads
        if self.env.workloads.user:
            for wkld in self.env.workloads.user:
                all_workloads.append({
                    "name": wkld.name,
                    "type": "user",
                    "enabled": wkld.enabled,
                    "namespace": wkld.namespace or wkld.name
                })

        return all_workloads

    def get_workloads_status(self, include_disabled: bool = False) -> List[dict]:
        """Get status of workloads.

        Args:
            include_disabled: If True, include disabled workloads in the result.
        """
        workloads = self.get_all_workloads()
        target_workloads = workloads if include_disabled else [w for w in workloads if w['enabled']]

        try:
            # Get helm releases status
            result = self.run_command(
                ["helm", "--kubeconfig", self.kubeconfig, "list", "--all-namespaces", "-o", "json"],
                capture_output=True,
                check=False
            )

            import json
            releases = []
            if result.returncode == 0 and result.stdout.strip():
                releases = json.loads(result.stdout)

            # Get pods status
            pods_result = self.run_command(
                ["kubectl", "--kubeconfig", self.kubeconfig, "get", "pods", "-A", "-o", "json"],
                capture_output=True,
                check=False
            )

            pods = []
            if pods_result.returncode == 0 and pods_result.stdout.strip():
                pods_data = json.loads(pods_result.stdout)
                pods = pods_data.get('items', [])

            status_list = []
            for wkld in target_workloads:
                # Find release info
                release = next((r for r in releases if r['name'] == wkld['name']), None)

                # Find pod info (rough check by label or name)
                namespace = wkld.get('namespace', wkld['name'])
                if wkld['name'] == 'metrics-server':
                    namespace = 'kube-system'

                wkld_pods = [p for p in pods if p['metadata']['namespace'] == namespace]

                pod_status = "Unknown"
                if wkld_pods:
                    ready_pods = sum(1 for p in wkld_pods if all(c.get('ready', False) for c in p.get('status', {}).get('containerStatuses', [])))
                    total_pods = len(wkld_pods)
                    pod_status = f"{ready_pods:>3}/{total_pods:<3} Ready"
                elif release:
                    pod_status = "No pods"

                # Determine status
                if not wkld['enabled']:
                    status = "disabled"
                    pod_status = "-"
                elif release:
                    status = release['status']
                else:
                    status = "Not installed"

                status_list.append({
                    "name": wkld['name'],
                    "type": wkld['type'],
                    "namespace": namespace,
                    "enabled": wkld['enabled'],
                    "installed": release is not None,
                    "status": status,
                    "pods": pod_status,
                    "chart": release['chart'] if release else "-",
                    "version": release['app_version'] if release else "-"
                })

            return status_list

        except Exception as e:
            console.print(f"[yellow]⚠️  Could not get workloads status: {e}[/yellow]")
            return []

    def deploy_tcp_routes(self, workload_names: Optional[List[str]] = None):
        """Deploy Traefik TCP routes for system workloads."""
        tcp_routes_file = os.path.join(self.k8s_dir, "config", "traefik-tcp-routes.yaml")
        if not os.path.exists(tcp_routes_file):
            return
        # If specific workloads are provided, check if any of them are system workloads with ports
        # This prevents triggering TCP route deployment for unrelated user workloads
        if workload_names:
            system_workload_names = {wkld.name for wkld in self.env.workloads.system if wkld.enabled and wkld.ports}
            if not any(name in system_workload_names for name in workload_names):
                return

        # Check if there's content to apply (file might be empty if no services have ports)
        with open(tcp_routes_file, 'r') as f:
            lines = [line for line in f if line.strip()]

        has_manifest_content = any(
            not line.lstrip().startswith('#') and line.strip() != '---'
            for line in lines
        )

        if not has_manifest_content:
            return

        console.print("🔄 Deploying Traefik TCP routes...")

        try:
            result = self.run_command([
                "kubectl", "--kubeconfig", self.kubeconfig,
                "apply", "-f", tcp_routes_file
            ], capture_output=True)

            console.print("✅ TCP routes deployed")

        except subprocess.CalledProcessError as e:
            console.print(f"[yellow]⚠️  Warning: Could not deploy TCP routes: {e.stderr}[/yellow]")

    def start_dnsmasq(self):
        """Start dnsmasq container."""
        console.print("🔄 Starting DNS service...")
        container_name = get_dns_container_name(self.env.name)

        # Check if running and remove if exists to ensure config update
        if self.list_containers(name_filter=container_name, quiet=True, check=False):
            self.run_command([self.runtime, "rm", "-f", container_name], check=False, capture_output=True)

        config_path = os.path.join(self.k8s_dir, "config", "dnsmasq.conf")

        # Use alternate DNS port in CI environments where port 53 may be in use
        is_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"
        # Prioritize CI env var, then config, then default 53
        dns_port = "5353" if is_ci else str(self.env.network.dns_port)

        if is_ci:
            console.print(f"[yellow]ℹ️  CI environment detected, overriding DNS port to {dns_port}[/yellow]")
        elif self.env.network.dns_port != 53:
            console.print(f"ℹ️  Using configured custom DNS port: {dns_port}")

        # Remove any existing container with the same name
        existing = self.list_containers(name_filter=container_name, all_containers=True, quiet=True, check=False)
        if existing:
            console.print(f"  🔄 Removing existing DNS container...")
            self.run_command([self.runtime, "rm", "-f", container_name], check=False)

        # Check if port is available
        if is_port_in_use(int(dns_port)):
            raise RuntimeError(f"Port {dns_port} is already in use. Please stop the service using it (e.g. systemd-resolved) or check for other running containers.")

        cmd = [
            self.runtime, "run", "-d",
            "--name", container_name,
            "--network", "kind",
            "--restart", "unless-stopped",
            "-p", f"{dns_port}:53/udp",
            "-p", f"{dns_port}:53/tcp",
            "-v", f"{config_path}:/etc/dnsmasq.conf:ro",
            f"dockurr/dnsmasq:{self._get_dnsmasq_version()}"
        ]
        self.run_command(cmd)
        console.print("✅ DNS service started")

    def _get_dnsmasq_version(self) -> str:
        """Get dnsmasq version from config."""
        return self.env.internal_components.dnsmasq.version

    def setup_resolver_file(self):
        """Setup /etc/resolver file for DNS resolution (macOS/Linux)."""
        local_domain = self.env.network.domain
        console.print(f"🔧 Setting up DNS resolver for {local_domain}...")

        import platform
        os_name = platform.system()

        if os_name == "Darwin":  # macOS
            self._setup_resolver_file_mac()
        elif os_name == "Linux":
            self._setup_resolver_file_linux()
        else:
            console.print(f"[yellow]⚠️  Resolver file setup not implemented for {os_name}[/yellow]")

    def _setup_resolver_file_mac(self):
        """Setup resolver file for macOS."""
        local_domain = self.env.network.domain
        local_ip = self.env.network.ip
        dns_port = self.env.network.dns_port

        resolver_dir = "/etc/resolver"
        resolver_file = f"{resolver_dir}/{local_domain}"

        try:
            # Create resolver directory if it doesn't exist
            if not os.path.exists(resolver_dir):
                console.print(f"  📁 Creating {resolver_dir}...")
                self.run_command(['sudo', 'mkdir', '-p', resolver_dir])

            # Create resolver content
            resolver_content = f"nameserver {local_ip}\nport {dns_port}\n"

            # Write to temp file first
            temp_file = f'/tmp/resolver_file_{local_domain}'
            with open(temp_file, 'w') as f:
                f.write(resolver_content)

            # Move to /etc/resolver with sudo
            console.print(f"  📝 Creating resolver file {resolver_file}...")
            self.run_command(['sudo', 'mv', temp_file, resolver_file])
            self.run_command(['sudo', 'chown', 'root:wheel', resolver_file])
            self.run_command(['sudo', 'chmod', '644', resolver_file])

            console.print(f"✅ Resolver file created at {resolver_file}")

        except Exception as e:
            console.print(f"[yellow]⚠️  Could not setup resolver file: {e}[/yellow]")
            console.print(f"[yellow]   You may need to manually create {resolver_file} with content:[/yellow]")
            console.print(f"[yellow]   nameserver {local_ip}[/yellow]")

    def _setup_resolver_file_linux(self):
        """Setup resolver file for Linux (systemd-resolved)."""
        local_domain = self.env.network.domain
        local_ip = self.env.network.ip
        dns_port = self.env.network.dns_port

        try:
            # Check if systemd-resolved is enabled
            result = self.run_command(
                ['systemctl', 'is-enabled', 'systemd-resolved'],
                capture_output=True,
                check=False
            )

            if result.returncode == 0:
                console.print("  🔧 Configuring systemd-resolved...")

                # Create resolved config
                # systemd-resolved supports port in DNS=IP:PORT format
                dns_entry = f"{local_ip}:{dns_port}" if dns_port != 53 else local_ip
                resolved_conf = f"""[Resolve]
DNS={dns_entry}
Domains=~{local_domain}
"""
                temp_file = f'/tmp/resolved_{local_domain}.conf'
                with open(temp_file, 'w') as f:
                    f.write(resolved_conf)

                # Move to systemd-resolved directory
                resolved_file = f"/etc/systemd/resolved.conf.d/{local_domain}.conf"
                self.run_command(['sudo', 'mkdir', '-p', '/etc/systemd/resolved.conf.d'])
                self.run_command(['sudo', 'mv', temp_file, resolved_file])
                self.run_command(['sudo', 'systemctl', 'restart', 'systemd-resolved'])

                console.print(f"✅ systemd-resolved configured for {local_domain}")
            else:
                console.print("[yellow]⚠️  systemd-resolved not enabled, skipping DNS setup[/yellow]")

        except Exception as e:
            console.print(f"[yellow]⚠️  Could not setup Linux resolver: {e}[/yellow]")

    def remove_resolver_file(self):
        """Remove /etc/resolver file for DNS resolution (macOS/Linux)."""
        import platform
        os_name = platform.system()

        if os_name == "Darwin":  # macOS
            self._remove_resolver_file_mac()
        elif os_name == "Linux":
            self._remove_resolver_file_linux()
        else:
            console.print(f"[yellow]⚠️  Resolver file removal not implemented for {os_name}[/yellow]")

    def _remove_resolver_file_mac(self):
        """Remove resolver file for macOS."""
        local_domain = self.env.network.domain
        resolver_file = f"/etc/resolver/{local_domain}"

        try:
            if os.path.exists(resolver_file):
                console.print(f"🔄 Removing DNS resolver for {local_domain}...")
                console.print(f"  🗑️  Removing {resolver_file}...")
                self.run_command(['sudo', 'rm', '-f', resolver_file])
                console.print(f"✅ Resolver file removed")
            else:
                console.print(f"ℹ️  DNS resolver file for {local_domain} does not exist")
        except Exception as e:
            console.print(f"[yellow]⚠️  Could not remove resolver file: {e}[/yellow]")

    def _remove_resolver_file_linux(self):
        """Remove resolver file for Linux (systemd-resolved)."""
        local_domain = self.env.network.domain

        try:
            # Check if systemd-resolved is enabled
            result = self.run_command(
                ['systemctl', 'is-enabled', 'systemd-resolved'],
                capture_output=True,
                check=False
            )

            if result.returncode == 0:
                resolved_file = f"/etc/systemd/resolved.conf.d/{local_domain}.conf"

                if os.path.exists(resolved_file):
                    console.print(f"🔄 Removing DNS resolver for {local_domain}...")
                    console.print(f"  🗑️  Removing {resolved_file}...")
                    self.run_command(['sudo', 'rm', '-f', resolved_file])
                    self.run_command(['sudo', 'systemctl', 'restart', 'systemd-resolved'])
                    console.print(f"✅ systemd-resolved configuration removed")
                else:
                    console.print(f"ℹ️  DNS resolver config for {local_domain} does not exist")
            else:
                console.print("ℹ️  systemd-resolved not enabled, skipping DNS resolver removal")

        except Exception as e:
            console.print(f"[yellow]⚠️  Could not remove Linux resolver: {e}[/yellow]")

    def inject_dns_nameserver(self):
        """Inject DNS container IP into cluster nodes' resolv.conf."""
        console.print("🔄 Injecting DNS nameserver into cluster nodes...")

        dns_container = get_dns_container_name(self.env.name)

        # Get DNS container IP
        try:
            result = self.run_command(
                [self.runtime, "inspect", dns_container, "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"],
                capture_output=True
            )
            dns_ip = result.stdout.strip()

            if not dns_ip:
                console.print("[yellow]⚠️  Could not get DNS container IP, skipping DNS injection[/yellow]")
                return

            console.print(f"  📍 DNS container IP: {dns_ip}")

        except Exception as e:
            console.print(f"[yellow]⚠️  Could not get DNS container IP: {e}[/yellow]")
            return

        # Get all cluster node containers
        try:
            node_ids = self.list_containers(name_filter=self.env.name, quiet=True)

            # Filter out DNS container
            dns_ids = self.list_containers(name_filter=dns_container, quiet=True)
            dns_id = dns_ids[0] if dns_ids else None

            # Remove DNS container from node list
            if dns_id:
                node_ids = [n for n in node_ids if n != dns_id]

            if not node_ids:
                console.print("[yellow]⚠️  No cluster nodes found[/yellow]")
                return

            console.print(f"  🔍 Found {len(node_ids)} node(s) to update")

            # Inject DNS into each node
            for node_id in node_ids:
                node_name = self.run_command(
                    [self.runtime, "inspect", node_id, "--format", "{{.Name}}"],
                    capture_output=True
                ).stdout.strip().lstrip('/')

                console.print(f"  📝 Updating DNS for node: {node_name}")

                # Prepend our DNS as primary nameserver (before Docker's DNS)
                # This ensures our custom DNS resolver is tried first for *.dev.me domains
                # Docker's DNS (172.19.0.1) will still be available as fallback
                # Note: Using temp file approach because /etc/resolv.conf is bind-mounted by Docker
                # Check if our DNS is NOT the first nameserver (not just if it exists anywhere)
                # Using || logic because sh shell in Kind nodes doesn't support 'if !' syntax
                inject_cmd = (
                    f"head -n 1 /etc/resolv.conf | grep -q '^nameserver {dns_ip}$' || ("
                    f"cat /etc/resolv.conf > /tmp/resolv.conf.bak && "
                    f"echo 'nameserver {dns_ip}' > /tmp/resolv.conf.new && "
                    f"grep -v '^nameserver {dns_ip}' /tmp/resolv.conf.bak >> /tmp/resolv.conf.new && "
                    f"cat /tmp/resolv.conf.new > /etc/resolv.conf"
                    f")"
                )

                result = self.run_command(
                    [self.runtime, "exec", node_id, "/bin/sh", "-c", inject_cmd],
                    capture_output=True,
                    check=False
                )

                if result.returncode != 0:
                    console.print(f"    [yellow]⚠️  Warning: DNS injection may have failed: {result.stderr}[/yellow]")
                else:
                    # Verify the injection worked
                    verify_result = self.run_command(
                        [self.runtime, "exec", node_id, "/bin/sh", "-c", f"grep '^nameserver {dns_ip}$' /etc/resolv.conf"],
                        capture_output=True,
                        check=False
                    )
                    if verify_result.returncode == 0:
                        console.print(f"    ✅ DNS nameserver {dns_ip} verified in resolv.conf")
                    else:
                        console.print(f"    [yellow]⚠️  DNS nameserver not found in resolv.conf after injection[/yellow]")

            console.print("✅ DNS nameserver injection complete")

        except Exception as e:
            console.print(f"[yellow]⚠️  Error during DNS injection: {e}[/yellow]")

    def fetch_kubeconfig(self):
        """Fetch kubeconfig from kind cluster."""
        console.print("🔄 Fetching kubeconfig...")

        # Ensure the directory for kubeconfig exists
        os.makedirs(os.path.dirname(self.kubeconfig), exist_ok=True)

        try:
            expected_context = f"kind-{self.env.name}"

            # Explicitly export kubeconfig to ensure context exists
            # This merges into default ~/.kube/config AND saves to local file
            self.run_command(
                ["kind", "export", "kubeconfig", "--name", self.env.name, "--kubeconfig", self.kubeconfig],
                capture_output=True
            )

            # Also export to default to be safe for other tools
            self.run_command(
                ["kind", "export", "kubeconfig", "--name", self.env.name],
                capture_output=True
            )

            # Switch to the kind context in the local kubeconfig
            self.run_command(
                ["kubectl", "--kubeconfig", self.kubeconfig, "config", "use-context", expected_context],
                capture_output=True,
                check=False
            )

            # Verify it worked
            result = self.run_command(
                ["kubectl", "--kubeconfig", self.kubeconfig, "config", "current-context"],
                capture_output=True,
                check=False
            )

            if expected_context in result.stdout:
                console.print(f"✅ Kubeconfig ready (context: {expected_context})")
            else:
                console.print(f"[yellow]⚠️  Current context: {result.stdout.strip()}[/yellow]")

        except Exception as e:
            console.print(f"[yellow]⚠️  Could not verify kubeconfig: {e}[/yellow]")

    def wait_for_cluster_ready(self, timeout: int = 120):
        """Wait for cluster to be ready."""
        console.print("🔄 Waiting for cluster to be ready...")

        import time
        start_time = time.time()
        last_error = None
        attempt = 0

        while time.time() - start_time < timeout:
            attempt += 1
            elapsed = int(time.time() - start_time)

            try:
                result = self.run_command(
                    ["kubectl", "--kubeconfig", self.kubeconfig, "get", "nodes", "-o", "jsonpath={.items[*].status.conditions[?(@.type=='Ready')].status}"],
                    capture_output=True,
                    check=False
                )

                # Check if all nodes are Ready
                statuses = result.stdout.strip().split()
                if statuses and all(s == "True" for s in statuses):
                    console.print("✅ Cluster is ready")
                    return
                elif result.returncode != 0 and result.stdout:
                    # API is responding but nodes aren't ready
                    console.print(f"  ⏳ Nodes not ready yet ({elapsed}s)... statuses: {statuses if statuses else 'none'}")

            except Exception as e:
                last_error = str(e)
                if attempt % 3 == 0:  # Log every 3rd attempt (every ~15 seconds)
                    console.print(f"  ⏳ Waiting for API server ({elapsed}s)...")

            time.sleep(5)

        if last_error:
            console.print(f"[yellow]⚠️  Cluster readiness check timed out (last error: {last_error})[/yellow]")
        else:
            console.print(f"[yellow]⚠️  Cluster readiness check timed out after {timeout}s[/yellow]")

    def list_nodes(self):
        """List cluster nodes."""
        console.print("📋 Cluster nodes:")

        try:
            result = self.run_command(
                ["kubectl", "--kubeconfig", self.kubeconfig, "get", "nodes", "-o", "wide"],
                capture_output=True
            )
            console.print(result.stdout)
        except Exception as e:
            console.print(f"[yellow]⚠️  Could not list nodes: {e}[/yellow]")

    def set_control_plane_scheduling(self):
        """Configure control plane node scheduling based on config."""
        console.print("🔄 Configuring control plane scheduling...")

        try:
            if self.env.cluster.nodes.scheduling.control_plane.allow_workloads:
                # Remove NoSchedule taint from control plane nodes
                result = self.run_command(
                    ["kubectl", "--kubeconfig", self.kubeconfig, "taint", "nodes", "--all", "node-role.kubernetes.io/control-plane-"],
                    capture_output=True,
                    check=False
                )
                if result.returncode == 0:
                    console.print("✅ Control plane nodes can schedule workloads")
                else:
                    console.print("ℹ️  Control plane already configured or no taint found")
            else:
                console.print("ℹ️  Control plane scheduling disabled (default)")

        except Exception as e:
            console.print(f"[yellow]⚠️  Could not configure control plane scheduling: {e}[/yellow]")

    def label_nodes(self):
        """Label worker nodes."""
        if self.env.cluster.nodes.workers <= 0:
            return

        console.print("🔄 Labeling worker nodes...")

        try:
            # Get worker nodes (nodes without control-plane role)
            result = self.run_command(
                ["kubectl", "--kubeconfig", self.kubeconfig, "get", "nodes", "-l", "!node-role.kubernetes.io/control-plane", "-o", "name"],
                capture_output=True,
                check=False
            )

            worker_nodes = [n.strip() for n in result.stdout.strip().split('\n') if n.strip()]

            if not worker_nodes:
                console.print("[yellow]ℹ️  No worker nodes found to label[/yellow]")
                return

            for node in worker_nodes:
                self.run_command(
                    ["kubectl", "--kubeconfig", self.kubeconfig, "label", node, "node-role.kubernetes.io/worker=true", "--overwrite"],
                    capture_output=True,
                    check=False
                )

            console.print(f"✅ Labeled {len(worker_nodes)} worker node(s)")

        except Exception as e:
            console.print(f"[yellow]⚠️  Could not label nodes: {e}[/yellow]")

    def setup_wildcard_cert(self):
        """Setup wildcard certificate as Kubernetes secret."""
        console.print("🔄 Setting up wildcard certificate...")

        local_domain = self.env.network.domain

        try:
            cert_dir = os.path.join(self.k8s_dir, "certs")
            cert_file = os.path.join(cert_dir, f"{local_domain}.pem")
            key_file = os.path.join(cert_dir, f"{local_domain}-key.pem")

            if not os.path.exists(cert_file) or not os.path.exists(key_file):
                console.print("[yellow]⚠️  Certificate files not found, skipping[/yellow]")
                return

            # Ensure traefik namespace exists
            self.run_command(["kubectl", "--kubeconfig", self.kubeconfig, "create", "namespace", "traefik"], capture_output=True, check=False)

            # Create tls secret in traefik namespace (where Traefik expects it)
            # Name must be wildcard-tls as per helmfile config
            secret_name = "wildcard-tls"
            namespace = "traefik"

            # Check if secret exists
            check = self.run_command(
                ["kubectl", "--kubeconfig", self.kubeconfig, "get", "secret", secret_name, "-n", namespace],
                capture_output=True,
                check=False
            )

            if check.returncode == 0:
                console.print(f"ℹ️  Secret '{secret_name}' already exists in '{namespace}'")
                return

            # Create the secret
            result = self.run_command([
                "kubectl", "--kubeconfig", self.kubeconfig, "create", "secret", "tls", secret_name,
                f"--cert={cert_file}",
                f"--key={key_file}",
                f"--namespace={namespace}"
            ], capture_output=True, check=False)

            if result.returncode == 0:
                console.print(f"✅ Wildcard certificate secret '{secret_name}' created in '{namespace}'")
            else:
                console.print(f"[red]❌ Failed to create secret: {result.stderr}[/red]")

        except Exception as e:
            console.print(f"[yellow]⚠️  Could not setup wildcard certificate: {e}[/yellow]")

    def _parse_secrets_file(self) -> dict:
        """Parse the secrets file into a dictionary of workload entries."""
        secrets_file = self.workload_secrets_path
        if not os.path.exists(secrets_file):
            return {}

        with open(secrets_file, 'r') as f:
            content = f.read()

        # Remove header (lines starting with #)
        lines = content.split('\n')
        content_without_header = []
        for line in lines:
            if line.strip() and not line.strip().startswith('#'):
                content_without_header.append(line)
            elif not line.strip().startswith('#'):
                # Keep blank lines that aren't part of header
                content_without_header.append(line)

        content = '\n'.join(content_without_header)

        # Split by delimiter
        sections = content.split('\n' + '=' * 50 + '\n')
        workloads = {}

        for section in sections:
            section = section.strip()
            if not section:
                continue

            # Extract workload name from the section
            lines = section.split('\n')
            workload_name = None
            for line in lines:
                line_stripped = line.strip()
                if line_stripped.startswith('Workload:'):
                    workload_name = line_stripped.split(':', 1)[1].strip()
                    break

            if workload_name:
                workloads[workload_name] = section

        return workloads

    def _write_secrets_file(self, workloads: dict):
        """Write workloads dictionary back to secrets file with clean structure."""
        secrets_file = self.workload_secrets_path

        with open(secrets_file, 'w') as f:
            f.write(f"# Workload Credentials for {self.env.name}\n")
            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"\n")

            # Sort workloads alphabetically for consistent output
            for i, workload_name in enumerate(sorted(workloads.keys())):
                f.write(workloads[workload_name])
                # Add delimiter between workloads, but not after the last one
                if i < len(workloads) - 1:
                    f.write(f"\n\n{'=' * 50}\n\n")
                else:
                    f.write(f"\n")

    def remove_workload_secrets(self, workload_names: List[str]):
        """Remove secrets for specified workloads from the secrets file."""
        if not workload_names:
            return

        workloads = self._parse_secrets_file()
        removed_any = False

        for workload_name in workload_names:
            if workload_name in workloads:
                del workloads[workload_name]
                removed_any = True

        if removed_any:
            if workloads:
                self._write_secrets_file(workloads)
            else:
                # If no workloads left, remove the file
                if os.path.exists(self.workload_secrets_path):
                    os.remove(self.workload_secrets_path)

    def fetch_workload_secrets(self, workload_names: Optional[List[str]] = None):
        """Fetch and extract workload credentials to a file."""
        workload_configs = {
            'mysql': ('root', 'settings.rootPassword.value'),
            'postgres': ('postgres', 'settings.superuserPassword.value'),
            'mongodb': ('root', 'settings.rootPassword'),
            'rabbitmq': ('admin', 'authentication.password.value'),
            'valkey': ('default', 'settings.password'),  # valkey might not have auth by default
        }

        all_workloads = list(self.env.workloads.system) + list(self.env.workloads.user)
        # Filter enabled workloads, and if workload_names is provided, further filter by those
        enabled_workload_names = {
            wkld.name for wkld in all_workloads if getattr(wkld, "enabled", False)
        }

        target_workloads = enabled_workload_names
        if workload_names:
            target_workloads = enabled_workload_names.intersection(set(workload_names))

        password_workloads = target_workloads.intersection(PASSWORD_PROTECTED_WORKLOADS)

        if not password_workloads:
            return

        console.print("🔄 Fetching workload credentials...")

        try:
            # Load existing secrets - preserve ALL workloads, not just password ones
            workloads_dict = self._parse_secrets_file()
            found_any = False
            modified = False  # Track if we actually updated anything

            console.print("  🔍 Extracting passwords from Helm release values...")

            # Get all helm releases
            result = self.run_command(
                ["helm", "--kubeconfig", self.kubeconfig, "list", "--all-namespaces", "-o", "json"],
                capture_output=True,
                check=False
            )

            if result.returncode != 0 or not result.stdout.strip():
                console.print("  ℹ️  No Helm releases found. Deploy workloads first.")
                return

            import json
            releases = json.loads(result.stdout)

            if not releases:
                console.print("  ℹ️  No Helm releases found. Deploy workloads first.")
                return

            # Process each configured workload
            for workload_name, (username, value_path) in workload_configs.items():
                if workload_name not in password_workloads:
                    continue

                # Find if this workload is deployed
                release_info = next((r for r in releases if r['name'] == workload_name), None)

                if release_info:
                    namespace = release_info['namespace']
                    console.print(f"  📦 Found deployed workload: {workload_name} in namespace: {namespace}")

                    # Get Helm values
                    values_result = self.run_command(
                        ["helm", "--kubeconfig", self.kubeconfig, "get", "values", workload_name, "-n", namespace, "-o", "json"],
                        capture_output=True,
                        check=False
                    )

                    if values_result.returncode == 0 and values_result.stdout.strip():
                        try:
                            values = json.loads(values_result.stdout)

                            # Navigate the nested path to get password
                            password = values
                            for key in value_path.split('.'):
                                if isinstance(password, dict) and key in password:
                                    password = password[key]
                                else:
                                    password = None
                                    break

                            if password and password != "null":
                                # Build workload entry
                                entry = f"Workload: {workload_name}\n"
                                entry += f"Namespace: {namespace}\n"
                                entry += f"Username: {username}\n"
                                entry += f"Password: {password}"

                                # Add or update in workloads dictionary
                                workloads_dict[workload_name] = entry
                                modified = True

                                console.print(f"    ✅ Retrieved password for {workload_name}")
                                found_any = True
                            else:
                                console.print(f"    ⚠️  Password not found at path '{value_path}' for {workload_name}")
                        except json.JSONDecodeError:
                            console.print(f"    ⚠️  Could not parse Helm values for {workload_name}")
                    else:
                        console.print(f"    ⚠️  Could not retrieve Helm values for {workload_name}")

            # Write updated secrets back to file only if we modified something
            # This preserves other workloads (like garage) that weren't fetched
            if modified and workloads_dict:
                self._write_secrets_file(workloads_dict)

            if found_any:
                console.print("")
                console.print(f"🔑 Workload credentials extracted successfully. Credentials saved at {self.workload_secrets_path}. Use [cyan]loko secret show[/cyan] to display them.")
            else:
                console.print("  ⚠️  No workload credentials found. Workloads may not be deployed yet or passwords may not be in Helm values.")

        except Exception as e:
            console.print(f"  [yellow]⚠️  Error fetching secrets: {e}[/yellow]")

    def build_and_push_test_image(self):
        """Build and push test image to local registry."""
        console.print("🔄 Building test image...")

        import hashlib
        import time

        # Generate image tag based on timestamp
        image_tag = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        registry_host = f"{self.env.registry.name}.{self.env.network.domain}"
        image_name = f"{registry_host}/loko-test:{image_tag}"

        dockerfile_dir = os.path.join(os.path.dirname(__file__), "templates", "test-app")

        try:
            # Build image
            self.run_command([
                self.runtime, "build", dockerfile_dir,
                "-t", image_name,
                "-t", f"{registry_host}/loko-test:latest"
            ], capture_output=True)

            console.print(f"  ✅ Built image: {image_name}")

            # Push to registry
            console.print("🔄 Pushing image to local registry...")
            self.run_command([
                self.runtime, "push", image_name
            ], capture_output=True)

            self.run_command([
                self.runtime, "push", f"{registry_host}/loko-test:latest"
            ], capture_output=True)

            console.print(f"  ✅ Pushed image to registry")

            return image_tag, registry_host

        except Exception as e:
            console.print(f"[red]❌ Error building/pushing image: {e}[/red]")
            raise

    def deploy_test_app(self, image_tag, registry_host):
        """Deploy test application with ingress and TLS."""
        console.print("🔄 Deploying test application...")

        from jinja2 import Template

        # Generate test hostname
        local_domain = self.env.network.domain
        if self.env.network.subdomain.enabled:
            test_host = f"loko-test.{self.env.network.subdomain.value}.{local_domain}"
        else:
            test_host = f"loko-test.{local_domain}"

        # Load and render manifest template
        template_path = os.path.join(os.path.dirname(__file__), "templates", "test-app", "manifest.yaml.j2")

        with open(template_path, 'r') as f:
            template = Template(f.read())

        manifest = template.render(
            registry_host=registry_host,
            image_tag=image_tag,
            test_host=test_host
        )

        # Write to temp file and apply
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(manifest)
            temp_manifest = f.name

        try:
            self.run_command(["kubectl", "--kubeconfig", self.kubeconfig, "apply", "-f", temp_manifest])

            # Wait for pod to be ready
            console.print("  ⏳ Waiting for pod to be ready...")
            self.run_command([
                "kubectl", "--kubeconfig", self.kubeconfig, "wait", "--for=condition=ready",
                "pod", "-l", "app=loko-test",
                "-n", "loko-test",
                "--timeout=60s"
            ])

            console.print(f"  ✅ Test app deployed at https://{test_host}")

            return test_host

        finally:
            os.unlink(temp_manifest)

    def validate_test_app(self, test_host):
        """Validate test app is accessible via HTTPS."""
        console.print("🔄 Validating test app (registry + TLS)...")

        import time
        time.sleep(5)  # Give ingress a moment to configure

        try:
            # Curl the HTTPS endpoint
            result = self.run_command([
                "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                f"https://{test_host}/"
            ], capture_output=True, check=False)

            status_code = result.stdout.strip()

            if status_code == "200":
                console.print(f"  [green]✅ Test app accessible via HTTPS (status: {status_code})[/green]")
                console.print(f"  [green]✅ Registry pull successful[/green]")
                console.print(f"  [green]✅ TLS certificate working[/green]")
                return True
            else:
                console.print(f"  [red]❌ Test app returned status: {status_code}[/red]")
                return False

        except Exception as e:
            console.print(f"  [red]❌ Error validating test app: {e}[/red]")
            return False

    def cleanup_test_app(self):
        """Remove test application and namespace."""
        console.print("🔄 Cleaning up test application...")

        try:
            self.run_command([
                "kubectl", "--kubeconfig", self.kubeconfig, "delete", "namespace", "loko-test", "--ignore-not-found=true"
            ], capture_output=True, check=False)

            console.print("  ✅ Test app cleaned up")

        except Exception as e:
            console.print(f"  [yellow]⚠️  Error during cleanup: {e}[/yellow]")

    def configure_workloads(self, workload_names: Optional[List[str]] = None):
        """Perform post-deployment configuration for workloads."""
        # Check if garage workload is enabled and (if selective) included in deployment
        garage_enabled = False
        if self.env.workloads.system:
            # If workload_names is provided, only configure if garage is in it
            # Otherwise (none or empty), configure if it's enabled in config
            if workload_names:
                garage_enabled = "garage" in workload_names
            else:
                garage_enabled = any(wkld.name == "garage" and wkld.enabled for wkld in self.env.workloads.system)

        if garage_enabled:
            self._configure_garage()

    def _configure_garage(self):
        """Configure Garage layout and create initial resources."""
        console.print("🔄 Configuring Garage S3...")

        local_domain = self.env.network.domain
        namespace = "common-services"
        pod_name = "garage-0"

        # Wait for pod to be ready explicitly (extra safety)
        console.print(f"  ⏳ Waiting for {pod_name} to be ready...")
        try:
             self.run_command([
                "kubectl", "--kubeconfig", self.kubeconfig, "wait", "--for=condition=ready",
                "pod", pod_name, "-n", namespace,
                "--timeout=120s"
            ], capture_output=True)
        except subprocess.CalledProcessError:
            console.print(f"  ⚠️  {pod_name} not ready, skipping configuration")
            return

        try:
            # 1. Layout Assign
            console.print("  🔧 Configuring layout...")

            # Get Node ID
            node_id_res = self.run_command([
                "kubectl", "--kubeconfig", self.kubeconfig, "exec", "-n", namespace, pod_name, "--",
                "/garage", "node", "id", "-q"
            ], capture_output=True)
            node_id = node_id_res.stdout.strip()

            if not node_id:
                 console.print("    ⚠️  Could not retrieve Node ID, failing over to pod name")
                 node_id = pod_name

            # Assign using Node ID
            self.run_command([
                "kubectl", "--kubeconfig", self.kubeconfig, "exec", "-n", namespace, pod_name, "--",
                "/garage", "layout", "assign", "-z", "dc1", "-c", "1G", node_id
            ], check=False, capture_output=True)

            # 2. Layout Apply
            apply_res = self.run_command([
                "kubectl", "--kubeconfig", self.kubeconfig, "exec", "-n", namespace, pod_name, "--",
                "/garage", "layout", "apply", "--version", "1"
            ], check=False, capture_output=True)

            if apply_res.returncode == 0:
                console.print("    ✅ Layout applied")
            elif "No changes to apply" in apply_res.stdout or "No changes to apply" in apply_res.stderr:
                console.print("    ℹ️  Layout already configured")
            else:
                console.print(f"    ⚠️  Layout apply failed: {apply_res.stderr}")

            # 3. Create Key
            key_name = f"{self.env.name}-key"
            console.print(f"  🔑 Creating API key '{key_name}'...")

            # Check if key exists
            list_keys = self.run_command([
                 "kubectl", "--kubeconfig", self.kubeconfig, "exec", "-n", namespace, pod_name, "--",
                "/garage", "key", "list"
            ], capture_output=True)

            key_id = None
            secret_key = None

            if key_name in list_keys.stdout:
                console.print(f"    ℹ️  Key '{key_name}' already exists")
                # Try to get key info if possible, but secret is usually hidden
                # For now, we only save if we created it
            else:
                create_key = self.run_command([
                    "kubectl", "--kubeconfig", self.kubeconfig, "exec", "-n", namespace, pod_name, "--",
                    "/garage", "key", "create", key_name
                ], capture_output=True)

                # Parse output
                for line in create_key.stdout.splitlines():
                    if "Key ID" in line:
                         key_id = line.split(":")[-1].strip()
                    if "Secret key" in line:
                         secret_key = line.split(":")[-1].strip()

                if key_id and secret_key:
                    console.print(f"    ✅ Key created: {key_id}")
                    self._save_garage_secrets(key_id, secret_key)
                else:
                     console.print("    ⚠️  Failed to parse key creation output")

            # 4. Create Bucket
            bucket_name = f"{self.env.name}-bucket"
            console.print(f"  🪣 Creating bucket '{bucket_name}'...")

            # Create bucket (idempotent-ish, will fail if exists but that's fine)
            self.run_command([
                "kubectl", "--kubeconfig", self.kubeconfig, "exec", "-n", namespace, pod_name, "--",
                "/garage", "bucket", "create", bucket_name
            ], check=False, capture_output=True)

            # Enable website access for the bucket
            self.run_command([
                "kubectl", "--kubeconfig", self.kubeconfig, "exec", "-n", namespace, pod_name, "--",
                "/garage", "bucket", "website", bucket_name, "--allow"
            ], check=False, capture_output=True)

            # Allow anonymous read access for web serving
            # The --owner flag allows unauthenticated reads
            self.run_command([
                "kubectl", "--kubeconfig", self.kubeconfig, "exec", "-n", namespace, pod_name, "--",
                "/garage", "bucket", "allow", bucket_name, "--read", "--owner"
            ], check=False, capture_output=True)

            # 5. Allow Access
            if key_name:
                console.print(f"  🔓 Allowing access for key '{key_name}' to bucket '{bucket_name}'...")
                self.run_command([
                    "kubectl", "--kubeconfig", self.kubeconfig, "exec", "-n", namespace, pod_name, "--",
                    "/garage", "bucket", "allow", bucket_name, "--read", "--write", "--key", key_name
                ], check=False, capture_output=True)

            console.print("✅ Garage configured")

        except Exception as e:
             console.print(f"[yellow]⚠️  Error configuring Garage: {e}[/yellow]")

    def _save_garage_secrets(self, key_id, secret_key):
        """Add or update Garage secrets in the secrets file."""
        # Load existing secrets
        workloads_dict = self._parse_secrets_file()

        local_domain = self.env.network.domain
        ca_bundle_path = os.path.join(self.k8s_dir, 'certs', 'rootCA.pem')

        # Build garage entry
        entry = f"Workload: garage\n"
        entry += f"Access Key: {key_id}\n"
        entry += f"Secret Key: {secret_key}\n"
        entry += f"Endpoint: https://s3.{local_domain}\n"
        entry += f"Bucket: {self.env.name}-bucket\n"
        entry += f"\n"
        entry += f"AWS CLI Profile Configuration:\n"
        entry += f"Add the following to ~/.aws/credentials:\n"
        entry += f"\n"
        entry += f"[garage-{self.env.name}]\n"
        entry += f"aws_access_key_id = {key_id}\n"
        entry += f"aws_secret_access_key = {secret_key}\n"
        entry += f"\n"
        entry += f"Add the following to ~/.aws/config:\n"
        entry += f"\n"
        entry += f"[profile garage-{self.env.name}]\n"
        entry += f"region = garage\n"
        entry += f"output = json\n"
        entry += f"services = s3-garage-{self.env.name}\n"
        entry += f"ca_bundle = {ca_bundle_path}\n"
        entry += f"\n"
        entry += f"[services s3-garage-{self.env.name}]\n"
        entry += f"s3 =\n"
        entry += f"  endpoint_url = https://s3.{local_domain}\n"
        entry += f"\n"
        entry += f"Usage example:\n"
        entry += f"aws s3 ls --profile garage-{self.env.name}\n"

        # Add or update garage entry
        workloads_dict['garage'] = entry

        # Write back to file
        self._write_secrets_file(workloads_dict)
