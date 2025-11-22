import subprocess
import shutil
import os
import time
from datetime import datetime
from typing import List, Optional
from rich.console import Console
from .config import RootConfig
from .utils import get_dns_container_name

console = Console()

class CommandRunner:
    def __init__(self, config: RootConfig):
        self.config = config
        self.env = config.environment
        self.runtime = self.env.provider.runtime
        self.k8s_dir = os.path.join(os.path.expandvars(self.env.base_dir), self.env.name)

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
        
        cert_file = os.path.join(cert_dir, f"{self.env.local_domain}.pem")
        key_file = os.path.join(cert_dir, f"{self.env.local_domain}-key.pem")
        combined_file = os.path.join(cert_dir, f"{self.env.local_domain}-combined.pem")
        
        if not os.path.exists(cert_file):
            console.print("  🔐 Generating certificates using mkcert...")
            domains = [f"*.{self.env.local_domain}", self.env.local_domain]
            if self.env.use_apps_subdomain:
                domains.append(f"*.{self.env.apps_subdomain}.{self.env.local_domain}")
                
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

    def create_cluster(self):
        """Create Kind cluster."""
        console.print(f"🔄 Creating cluster '{self.env.name}'...")
        
        # Check if cluster exists
        clusters = subprocess.check_output(["kind", "get", "clusters"], text=True).splitlines()
        if self.env.name in clusters:
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

    def deploy_services(self):
        """Deploy services using helmfile."""
        console.print("🔄 Deploying services...")
        helmfile_config = os.path.join(self.k8s_dir, "config", "helmfile.yaml")

        # Prepare environment variables for helmfile
        env = os.environ.copy()

        # Add variables that might be used in helmfile values
        apps_subdomain = self.env.apps_subdomain
        local_apps_domain = f"{apps_subdomain}.{self.env.local_domain}" if self.env.use_apps_subdomain else self.env.local_domain

        env.update({
            'ENV_NAME': self.env.name,
            'LOCAL_DOMAIN': self.env.local_domain,
            'LOCAL_IP': self.env.local_ip,
            'REGISTRY_NAME': self.env.registry.name,
            'REGISTRY_HOST': f"{self.env.registry.name}.{self.env.local_domain}",
            'APPS_SUBDOMAIN': apps_subdomain,
            'USE_APPS_SUBDOMAIN': str(self.env.use_apps_subdomain).lower(),
            'LOCAL_APPS_DOMAIN': local_apps_domain,
        })

        # Add and update helm repositories first to ensure we have the latest chart versions
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

        # Update all helm repositories to fetch latest chart indexes
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
            "sync"
        ]
        
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
        
        console.print("✅ Services deployed")

    def start_dnsmasq(self):
        """Start dnsmasq container."""
        console.print("🔄 Starting DNS service...")
        container_name = get_dns_container_name(self.env.name)

        # Check if running and remove if exists to ensure config update
        if self.list_containers(name_filter=container_name, quiet=True, check=False):
            self.run_command([self.runtime, "rm", "-f", container_name], check=False, capture_output=True)

        config_path = os.path.join(self.k8s_dir, "config", "dnsmasq.conf")
        cmd = [
            self.runtime, "run", "-d",
            "--name", container_name,
            "--network", "kind",
            "--restart", "unless-stopped",
            "-p", "53:53/udp",
            "-p", "53:53/tcp",
            "-v", f"{config_path}:/etc/dnsmasq.conf:ro",
            "dockurr/dnsmasq:2.91" # Hardcoded for now, should come from config
        ]
        self.run_command(cmd)
        console.print("✅ DNS service started")

    def setup_resolver_file(self):
        """Setup /etc/resolver file for DNS resolution (macOS/Linux)."""
        console.print(f"🔧 Setting up DNS resolver for {self.env.local_domain}...")
        
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
        resolver_dir = "/etc/resolver"
        resolver_file = f"{resolver_dir}/{self.env.local_domain}"
        
        try:
            # Create resolver directory if it doesn't exist
            if not os.path.exists(resolver_dir):
                console.print(f"  📁 Creating {resolver_dir}...")
                self.run_command(['sudo', 'mkdir', '-p', resolver_dir])
            
            # Create resolver content
            resolver_content = f"nameserver {self.env.local_ip}\n"
            
            # Write to temp file first
            temp_file = f'/tmp/resolver_file_{self.env.local_domain}'
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
            console.print(f"[yellow]   nameserver {self.env.local_ip}[/yellow]")
    
    def _setup_resolver_file_linux(self):
        """Setup resolver file for Linux (systemd-resolved)."""
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
                resolved_conf = f"""[Resolve]
DNS={self.env.local_ip}
Domains=~{self.env.local_domain}
"""
                temp_file = f'/tmp/resolved_{self.env.local_domain}.conf'
                with open(temp_file, 'w') as f:
                    f.write(resolved_conf)
                
                # Move to systemd-resolved directory
                resolved_file = f"/etc/systemd/resolved.conf.d/{self.env.local_domain}.conf"
                self.run_command(['sudo', 'mkdir', '-p', '/etc/systemd/resolved.conf.d'])
                self.run_command(['sudo', 'mv', temp_file, resolved_file])
                self.run_command(['sudo', 'systemctl', 'restart', 'systemd-resolved'])
                
                console.print(f"✅ systemd-resolved configured for {self.env.local_domain}")
            else:
                console.print("[yellow]⚠️  systemd-resolved not enabled, skipping DNS setup[/yellow]")
                
        except Exception as e:
            console.print(f"[yellow]⚠️  Could not setup Linux resolver: {e}[/yellow]")

    def remove_resolver_file(self):
        """Remove /etc/resolver file for DNS resolution (macOS/Linux)."""
        console.print(f"🔄 Removing DNS resolver for {self.env.local_domain}...")
        
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
        resolver_file = f"/etc/resolver/{self.env.local_domain}"
        
        try:
            if os.path.exists(resolver_file):
                console.print(f"  🗑️  Removing {resolver_file}...")
                self.run_command(['sudo', 'rm', '-f', resolver_file])
                console.print(f"✅ Resolver file removed")
            else:
                console.print(f"  ℹ️  Resolver file {resolver_file} does not exist")
        except Exception as e:
            console.print(f"[yellow]⚠️  Could not remove resolver file: {e}[/yellow]")
    
    def _remove_resolver_file_linux(self):
        """Remove resolver file for Linux (systemd-resolved)."""
        try:
            # Check if systemd-resolved is enabled
            result = self.run_command(
                ['systemctl', 'is-enabled', 'systemd-resolved'],
                capture_output=True,
                check=False
            )
            
            if result.returncode == 0:
                resolved_file = f"/etc/systemd/resolved.conf.d/{self.env.local_domain}.conf"
                
                if os.path.exists(resolved_file):
                    console.print(f"  🗑️  Removing {resolved_file}...")
                    self.run_command(['sudo', 'rm', '-f', resolved_file])
                    self.run_command(['sudo', 'systemctl', 'restart', 'systemd-resolved'])
                    console.print(f"✅ systemd-resolved configuration removed")
                else:
                    console.print(f"  ℹ️  Resolver config {resolved_file} does not exist")
            else:
                console.print("  ℹ️  systemd-resolved not enabled, skipping")
                
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
                
                # Append our DNS as secondary nameserver (after Docker's DNS)
                # This preserves Docker's internal DNS (127.0.0.11) for node-to-node resolution
                # while adding our DNS for external *.dev.me domains
                inject_cmd = f"if ! grep -q '^nameserver {dns_ip}$' /etc/resolv.conf; then echo 'nameserver {dns_ip}' >> /etc/resolv.conf; fi"
                
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
        
        try:
            expected_context = f"kind-{self.env.name}"
            
            # Explicitly export kubeconfig to ensure context exists
            # This merges into default ~/.kube/config
            self.run_command(
                ["kind", "export", "kubeconfig", "--name", self.env.name],
                capture_output=True
            )
            
            # Switch to the kind context
            self.run_command(
                ["kubectl", "config", "use-context", expected_context],
                capture_output=True,
                check=False
            )
            
            # Verify it worked
            result = self.run_command(
                ["kubectl", "config", "current-context"],
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
        
        while time.time() - start_time < timeout:
            try:
                result = self.run_command(
                ["kubectl", "--context", f"kind-{self.env.name}", "get", "nodes", "-o", "jsonpath={.items[*].status.conditions[?(@.type=='Ready')].status}"],
                capture_output=True,
                check=False
            )
                
                # Check if all nodes are Ready
                statuses = result.stdout.strip().split()
                if statuses and all(s == "True" for s in statuses):
                    console.print("✅ Cluster is ready")
                    return
                    
            except Exception:
                pass
            
            time.sleep(5)
        
        console.print("[yellow]⚠️  Cluster readiness check timed out[/yellow]")

    def list_nodes(self):
        """List cluster nodes."""
        console.print("📋 Cluster nodes:")
        
        try:
            result = self.run_command(
                ["kubectl", "get", "nodes", "-o", "wide"],
                capture_output=True
            )
            console.print(result.stdout)
        except Exception as e:
            console.print(f"[yellow]⚠️  Could not list nodes: {e}[/yellow]")

    def set_control_plane_scheduling(self):
        """Configure control plane node scheduling based on config."""
        console.print("🔄 Configuring control plane scheduling...")
        
        try:
            if self.env.nodes.allow_scheduling_on_control_plane:
                # Remove NoSchedule taint from control plane nodes
                result = self.run_command(
                    ["kubectl", "taint", "nodes", "--all", "node-role.kubernetes.io/control-plane-"],
                    capture_output=True,
                    check=False
                )
                if result.returncode == 0:
                    console.print("✅ Control plane nodes can schedule workloads")
                else:
                    console.print("[yellow]⚠️  Control plane already configured or no taint found[/yellow]")
            else:
                console.print("ℹ️  Control plane scheduling disabled (default)")
                
        except Exception as e:
            console.print(f"[yellow]⚠️  Could not configure control plane scheduling: {e}[/yellow]")

    def label_nodes(self):
        """Label worker nodes."""
        console.print("🔄 Labeling worker nodes...")
        
        try:
            # Get worker nodes (nodes without control-plane role)
            result = self.run_command(
                ["kubectl", "get", "nodes", "-l", "!node-role.kubernetes.io/control-plane", "-o", "name"],
                capture_output=True,
                check=False
            )
            
            worker_nodes = [n.strip() for n in result.stdout.strip().split('\n') if n.strip()]
            
            if not worker_nodes:
                console.print("[yellow]ℹ️  No worker nodes found to label[/yellow]")
                return
            
            for node in worker_nodes:
                self.run_command(
                    ["kubectl", "label", node, "node-role.kubernetes.io/worker=true", "--overwrite"],
                    capture_output=True,
                    check=False
                )
            
            console.print(f"✅ Labeled {len(worker_nodes)} worker node(s)")
            
        except Exception as e:
            console.print(f"[yellow]⚠️  Could not label nodes: {e}[/yellow]")

    def setup_wildcard_cert(self):
        """Setup wildcard certificate as Kubernetes secret."""
        console.print("🔄 Setting up wildcard certificate...")
        
        try:
            cert_dir = os.path.join(self.k8s_dir, "certs")
            cert_file = os.path.join(cert_dir, f"{self.env.local_domain}.pem")
            key_file = os.path.join(cert_dir, f"{self.env.local_domain}-key.pem")
            
            if not os.path.exists(cert_file) or not os.path.exists(key_file):
                console.print("[yellow]⚠️  Certificate files not found, skipping[/yellow]")
                return
            
            # Ensure traefik namespace exists
            self.run_command(["kubectl", "create", "namespace", "traefik"], capture_output=True, check=False)

            # Create tls secret in traefik namespace (where Traefik expects it)
            # Name must be wildcard-tls as per helmfile config
            secret_name = "wildcard-tls"
            namespace = "traefik"
            
            # Check if secret exists
            check = self.run_command(
                ["kubectl", "get", "secret", secret_name, "-n", namespace],
                capture_output=True,
                check=False
            )
            
            if check.returncode == 0:
                console.print(f"ℹ️  Secret '{secret_name}' already exists in '{namespace}'")
                return

            # Create the secret
            result = self.run_command([
                "kubectl", "create", "secret", "tls", secret_name,
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

    def fetch_service_secrets(self):
        """Fetch and extract service credentials to a file."""
        console.print("🔄 Fetching service credentials...")

        try:
            # Service configurations mapping service name to username and Helm value path
            service_configs = {
                'mysql': ('root', 'settings.rootPassword.value'),
                'postgres': ('postgres', 'settings.superuserPassword.value'),
                'mongodb': ('root', 'settings.rootPassword'),
                'rabbitmq': ('admin', 'authentication.password.value'),
                'valkey': ('default', 'settings.password'),  # valkey might not have auth by default
            }

            output_file = os.path.join(self.k8s_dir, 'service-secrets.txt')
            found_any = False

            # Clear/create the output file
            with open(output_file, 'w') as f:
                f.write(f"# Service Credentials for {self.env.name}\n")
                f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            console.print("  🔍 Extracting passwords from Helm release values...")

            # Get all helm releases
            result = self.run_command(
                ["helm", "list", "--all-namespaces", "-o", "json"],
                capture_output=True,
                check=False
            )

            if result.returncode != 0 or not result.stdout.strip():
                console.print("  ℹ️  No Helm releases found. Deploy services first.")
                return

            import json
            releases = json.loads(result.stdout)

            if not releases:
                console.print("  ℹ️  No Helm releases found. Deploy services first.")
                return

            # Process each configured service
            for service_name, (username, value_path) in service_configs.items():
                # Find if this service is deployed
                release_info = next((r for r in releases if r['name'] == service_name), None)

                if release_info:
                    namespace = release_info['namespace']
                    console.print(f"  📦 Found deployed service: {service_name} in namespace: {namespace}")

                    # Get Helm values
                    values_result = self.run_command(
                        ["helm", "get", "values", service_name, "-n", namespace, "-o", "json"],
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
                                # Write to file
                                with open(output_file, 'a') as f:
                                    f.write(f"Service: {service_name}\n")
                                    f.write(f"Namespace: {namespace}\n")
                                    f.write(f"Username: {username}\n")
                                    f.write(f"Password: {password}\n")
                                    f.write(f"\n")

                                console.print(f"    ✅ Retrieved password for {service_name}")
                                found_any = True
                            else:
                                console.print(f"    ⚠️  Password not found at path '{value_path}' for {service_name}")
                        except json.JSONDecodeError:
                            console.print(f"    ⚠️  Could not parse Helm values for {service_name}")
                    else:
                        console.print(f"    ⚠️  Could not retrieve Helm values for {service_name}")

            if found_any:
                console.print("")
                console.print("🔑 Service credentials extracted successfully")
                console.print(f"📝 Secrets saved to: [bold]{output_file}[/bold]")
            else:
                console.print("  ⚠️  No service credentials found. Services may not be deployed yet or passwords may not be in Helm values.")

        except Exception as e:
            console.print(f"[yellow]⚠️  Could not fetch service secrets: {e}[/yellow]")

    def build_and_push_test_image(self):
        """Build and push test image to local registry."""
        console.print("🔄 Building test image...")
        
        import hashlib
        import time
        
        # Generate image tag based on timestamp
        image_tag = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        registry_host = f"{self.env.registry.name}.{self.env.local_domain}"
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
        if self.env.use_apps_subdomain:
            test_host = f"loko-test.{self.env.apps_subdomain}.{self.env.local_domain}"
        else:
            test_host = f"loko-test.{self.env.local_domain}"
        
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
            self.run_command(["kubectl", "apply", "-f", temp_manifest])
            
            # Wait for pod to be ready
            console.print("  ⏳ Waiting for pod to be ready...")
            self.run_command([
                "kubectl", "wait", "--for=condition=ready",
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
                "kubectl", "delete", "namespace", "loko-test", "--ignore-not-found=true"
            ], capture_output=True, check=False)
            
            console.print("  ✅ Test app cleaned up")
            
        except Exception as e:
            console.print(f"  [yellow]⚠️  Error during cleanup: {e}[/yellow]")




