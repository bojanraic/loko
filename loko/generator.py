import os
import yaml
import jinja2
import secrets
import string
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from .config import RootConfig, Workload
from .utils import deep_merge

CACERT_FILE = "/etc/ssl/certs/mkcert-ca.pem"

# Mirror source definitions: name -> (hostname, upstream_hostname, prefix)
MIRROR_SOURCES = {
    'docker_hub': ('docker.io', 'registry-1.docker.io', '/dockerhub'),
    'quay': ('quay.io', 'quay.io', '/quay'),
    'ghcr': ('ghcr.io', 'ghcr.io', '/ghcr'),
    'k8s_registry': [
        ('k8s.gcr.io', 'k8s.gcr.io', '/k8s'),
        ('registry.k8s.io', 'registry.k8s.io', '/k8s'),
    ],
    'mcr': ('mcr.microsoft.com', 'mcr.microsoft.com', '/mcr'),
}

def load_presets(templates_dir: Optional[Path] = None) -> tuple[Dict[str, int], Dict[str, Any]]:
    template_dir = templates_dir if templates_dir else Path(__file__).parent / "templates"
    preset_file = template_dir / 'workload_presets.yaml'

    if not preset_file.exists():
        return {}, {}

    with open(preset_file) as f:
        presets = yaml.safe_load(f) or {}

    return (
        presets.get('workload_ports', {}),
        presets.get('workload_values_presets', {})
    )

class ConfigGenerator:
    def __init__(self, config: RootConfig, config_path: str, templates_dir: Optional[Path] = None):
        self.config = config
        self.config_path = config_path
        self.env = self.config.environment
        self.base_dir = os.path.expandvars(self.env.base_dir) if self.env.expand_env_vars else self.env.base_dir
        self.k8s_dir = os.path.join(self.base_dir, self.env.name)
        self.template_dir = templates_dir if templates_dir else Path(__file__).parent / "templates"
        self.jinja_env = self._setup_jinja_env()

    def _setup_jinja_env(self) -> jinja2.Environment:
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self.template_dir),
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True
        )

        def to_yaml_filter(value):
            return yaml.dump(value, default_flow_style=False)

        env.filters['to_yaml'] = to_yaml_filter
        return env

    def generate_random_password(self, length: int = 16) -> str:
        """Generate a secure random password."""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def get_presets(self) -> tuple[Dict[str, int], Dict[str, Any]]:
        return load_presets(self.template_dir)

    def _generate_chart_auth_config(self, workload_name: str, chart_name: str) -> Dict[str, Any]:
        auth_configs = {
            'mysql': {
                'settings': {
                    'rootPassword': {
                        'value': self.generate_random_password()
                    }
                }
            },
            'postgres': {
                'settings': {
                    'superuserPassword': {
                        'value': self.generate_random_password()
                    }
                }
            },
            'mongodb': {
                'settings': {
                    'rootUsername': 'root',
                    'rootPassword': self.generate_random_password()
                }
            },
            'rabbitmq': {
                'authentication': {
                    'user': {
                        'value': 'admin'
                    },
                    'password': {
                        'value': self.generate_random_password()
                    },
                    'erlangCookie': {
                        'value': self.generate_random_password(32)
                    }
                }
            },
            'valkey': {
                'useDeploymentWhenNonHA': False
            }
        }

        chart_basename = chart_name.split('/')[-1] if '/' in chart_name else chart_name
        return auth_configs.get(chart_basename, {})

    def _expand_vars(self, value: Any, env_vars: Dict[str, str]) -> Any:
        """Recursively expand variables in value."""
        if isinstance(value, str):
            for key, val in env_vars.items():
                value = value.replace(f"${{{key}}}", val).replace(f"${key}", val)
            return value
        elif isinstance(value, dict):
            return {k: self._expand_vars(v, env_vars) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._expand_vars(v, env_vars) for v in value]
        return value

    def _manage_git_chart(self, workload_name: str, repo_url: str, chart_path: str, version: str) -> str:
        """
        Clone a git repo to a temp directory and copy the chart to the cluster config directory.
        Returns the absolute path to the local chart directory.
        """
        import tempfile
        import shutil

        target_dir = os.path.join(self.k8s_dir, "charts", workload_name)

        # Always clean up existing directory to ensure fresh copy
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)

        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                # Clone specific version/tag/branch
                subprocess.check_call(
                    ['git', 'clone', '--depth', '1', '--branch', version, repo_url, tmp_dir],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except subprocess.CalledProcessError:
                # If branch fails (e.g. might be a commit hash or tag that doesn't work with --branch),
                # try full clone and checkout. Or just fail for now.
                # Fallback to cloning without branch and checking out
                 subprocess.check_call(
                    ['git', 'clone', repo_url, tmp_dir],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                 subprocess.check_call(
                    ['git', 'checkout', version],
                    cwd=tmp_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            src_chart_path = os.path.join(tmp_dir, chart_path)
            if not os.path.exists(src_chart_path):
                raise ValueError(f"Chart path '{chart_path}' not found in repo '{repo_url}'")

            # Copy to target directory
            shutil.copytree(src_chart_path, target_dir)

        return target_dir

    def _process_workloads(self, workloads: List[Workload], workload_ports: Dict[str, int],
                           workload_values_presets: Dict[str, Any], k8s_env_vars: Dict[str, str],
                           is_system: bool) -> List[Dict[str, Any]]:
        processed_workloads = []

        for workload in workloads:
            if not workload.enabled:
                continue

            workload_dict = workload.model_dump(by_alias=True)
            workload_name = workload.name

            # Handle Git-based charts
            if workload.config.repo and workload.config.repo.type == 'git':
                if not workload.config.repo.url:
                    raise ValueError(f"Git repo URL required for workload '{workload_name}'")

                local_chart_path = self._manage_git_chart(
                    workload_name=workload_name,
                    repo_url=workload.config.repo.url,
                    chart_path=workload.config.chart,
                    version=workload.config.version
                )
                # Update chart to point to the local absolute path
                workload_dict['config']['chart'] = local_chart_path
                # We don't need repo ref for local charts in helmfile

            base_values = {}

            if is_system and self.env.workloads.use_presets and workload_name in workload_values_presets:
                base_values = workload_values_presets[workload_name].copy()
                base_values.update({
                    'fullNameOverride': workload_name,
                    'nameOverride': workload_name
                })

                if workload.storage and workload.storage.size:
                    storage_size = workload.storage.size
                    storage_config = {}
                    if 'storage' in workload_values_presets[workload_name]:
                        storage_config['storage'] = {'requestedSize': storage_size}
                    elif 'primary' in workload_values_presets[workload_name]:
                        storage_config['primary'] = {'persistence': {'enabled': True, 'size': storage_size}}
                    elif 'persistence' in workload_values_presets[workload_name]:
                        # Check for sub-keys like 'data' used in Garage
                        preset_persistence = workload_values_presets[workload_name]['persistence']
                        if isinstance(preset_persistence, dict) and 'data' in preset_persistence:
                            storage_config['persistence'] = {'data': {'size': storage_size}}
                        else:
                            storage_config['persistence'] = {'enabled': True, 'size': storage_size}
                    deep_merge(storage_config, base_values)

                chart_name = workload.config.chart
                if chart_name:
                    auth_config = self._generate_chart_auth_config(workload_name, chart_name)
                    if auth_config:
                        deep_merge(auth_config, base_values)

                # Expand variables in base_values (from presets)
                base_values = self._expand_vars(base_values, k8s_env_vars)

            custom_values = workload.config.values or {}
            if custom_values:
                # Expand variables in custom values
                custom_values = self._expand_vars(custom_values, k8s_env_vars)
                base_values.update(custom_values)

            workload_dict['base_values'] = base_values
            workload_dict['workload_type'] = 'system' if is_system else 'user'

            if is_system and workload_name in workload_ports:
                workload_dict['default_port'] = workload_ports[workload_name]

            processed_workloads.append(workload_dict)

        return processed_workloads

    def _collect_helm_repositories(self, workloads: List[Dict[str, Any]]) -> Dict[str, str]:
        repositories = {repo.name: repo.url for repo in self.env.workloads.helm_repositories}

        # Also collect inline repos from workloads if any (though our model enforces structure)
        # In our Pydantic model, repo is a WorkloadRepoConfig, which might have name/url or ref

        for workload in workloads:
            # Access config from the dict structure since workloads here are dicts dump from loaded model
            # But 'config' key exists and 'repo' might be a dict
            # Warning: 'workloads' passed here is List[Dict], so we access as dict
            if 'config' in workload and 'repo' in workload['config']:
                repo = workload['config']['repo']
                if repo and repo.get('type') == 'git':
                    continue
                if repo and repo.get('name') and repo.get('url'):
                    repositories[repo['name']] = repo['url']

        return repositories

    def _prepare_registry_context(self) -> Dict[str, Any]:
        """Prepare registry context with mirroring sources as a dict for template access."""
        registry = self.env.registry
        mirroring = registry.mirroring

        # Build a dict mapping source name -> enabled status for easy template access
        # e.g., registry.mirroring.docker_hub -> True/False
        sources_dict = {}
        for source in mirroring.sources:
            sources_dict[source.name] = source.enabled

        return {
            'name': registry.name,
            'storage': {'size': registry.storage.size},
            'mirroring': {
                'enabled': mirroring.enabled,
                'sources': [{'name': s.name, 'enabled': s.enabled} for s in mirroring.sources],
                # Add individual source flags for template compatibility
                **sources_dict,
            },
        }

    def prepare_context(self) -> Dict[str, Any]:
        workload_ports, workload_values_presets = self.get_presets()

        # Network settings
        subdomain_value = self.env.network.subdomain.value
        subdomain_enabled = self.env.network.subdomain.enabled
        local_domain = self.env.network.domain
        local_ip = self.env.network.ip
        local_apps_domain = f"{subdomain_value}.{local_domain}" if subdomain_enabled else local_domain

        k8s_env_vars = {
            'ENV_NAME': self.env.name,
            'LOCAL_DOMAIN': local_domain,
            'LOCAL_IP': local_ip,
            'REGISTRY_NAME': self.env.registry.name,
            'REGISTRY_HOST': f"{self.env.registry.name}.{local_domain}",
            'APPS_SUBDOMAIN': subdomain_value,
            'USE_APPS_SUBDOMAIN': str(subdomain_enabled).lower(),
            'LOCAL_APPS_DOMAIN': local_apps_domain,
        }

        processed_system_workloads = self._process_workloads(
            self.env.workloads.system, workload_ports, workload_values_presets, k8s_env_vars, True
        )
        processed_user_workloads = self._process_workloads(
            self.env.workloads.user, workload_ports, workload_values_presets, k8s_env_vars, False
        )

        all_workloads = processed_system_workloads + processed_user_workloads
        helm_repositories = self._collect_helm_repositories(all_workloads)

        # Internal components - now a dict with named attributes
        internal_components = self.env.internal_components

        # Cluster settings
        cluster = self.env.cluster
        kubernetes = cluster.kubernetes
        nodes = cluster.nodes
        provider = cluster.provider
        scheduling = nodes.scheduling

        context = {
            # Environment
            'env_name': self.env.name,

            # Network
            'local_ip': local_ip,
            'local_domain': local_domain,
            'subdomain_value': subdomain_value,
            'subdomain_enabled': subdomain_enabled,
            'dns_port': self.env.network.dns_port,
            'lb_ports': self.env.network.lb_ports,

            # Template aliases (dnsmasq compatibility)
            'use_apps_subdomain': subdomain_enabled,
            'apps_subdomain': subdomain_value,
            'ingress_ports': self.env.network.lb_ports,

            # Cluster
            'runtime': provider.runtime,
            'provider': provider.model_dump(by_alias=True, exclude_none=True),
            'kubernetes': kubernetes.model_dump(by_alias=True, exclude_none=True),
            'api_port': kubernetes.api_port,
            'kubernetes_full_image': f"{kubernetes.image}:{kubernetes.tag}" if kubernetes.tag else kubernetes.image,
            'nodes': nodes.model_dump(by_alias=True, exclude_none=True),

            # Scheduling
            'scheduling': {
                'control_plane': {
                    'allow_workloads': scheduling.control_plane.allow_workloads,
                    'isolate_internal_components': scheduling.control_plane.isolate_internal_components,
                },
                'workers': {
                    'isolate_workloads': scheduling.workers.isolate_workloads,
                }
            },

            # Registry - build a structure compatible with templates
            'registry': self._prepare_registry_context(),
            'registry_name': self.env.registry.name,

            # Internal components
            'internal_components': {
                'traefik': {'version': internal_components.traefik.version},
                'zot': {'version': internal_components.zot.version},
                'dnsmasq': {'version': internal_components.dnsmasq.version},
                'metrics_server': {
                    'version': internal_components.metrics_server.version,
                    'enabled': internal_components.metrics_server.enabled,
                },
            },
            'traefik_version': internal_components.traefik.version,
            'zot_version': internal_components.zot.version,
            'dnsmasq_version': internal_components.dnsmasq.version,
            'metrics_server_version': internal_components.metrics_server.version,
            'deploy_metrics_server': internal_components.metrics_server.enabled,

            # Workloads
            'workloads': all_workloads,
            'system_workloads': processed_system_workloads,
            'user_workloads': processed_user_workloads,
            'helm_repositories': helm_repositories,
            'workload_ports': workload_ports,
            'workload_values_presets': workload_values_presets,
            'use_workload_presets': self.env.workloads.use_presets,

            # Template aliases (cluster.yaml.j2, dnsmasq compatibility)
            'services': processed_system_workloads,
            'system_services': processed_system_workloads,
            'run_workloads_on_workers_only': scheduling.workers.isolate_workloads,

            # Paths and certificates
            'cacert_file': CACERT_FILE,
            'k8s_dir': self.k8s_dir,
            'root_ca_path': os.path.abspath(f"{self.k8s_dir}/certs/rootCA.pem"),
            'mounts': [
                {'local_path': 'logs', 'node_path': '/var/log'},
                {'local_path': 'storage', 'node_path': '/var/local-path-provisioner'}
            ],

            # Internal domain settings
            'internal_domain': 'kind.internal',
            'internal_host': 'localhost.kind.internal',
        }

        # Ensure absolute paths for mounts
        for mount in context['mounts']:
            mount['hostPath'] = os.path.abspath(f"{self.k8s_dir}/{mount['local_path']}")

        return context

    def generate_configs(self):
        context = self.prepare_context()

        # Create directories
        os.makedirs(f"{self.k8s_dir}/config", exist_ok=True)
        os.makedirs(f"{self.k8s_dir}/config/containerd", exist_ok=True)
        os.makedirs(f"{self.k8s_dir}/certs", exist_ok=True)
        os.makedirs(f"{self.k8s_dir}/logs", exist_ok=True)
        os.makedirs(f"{self.k8s_dir}/storage", exist_ok=True)

        # Generate non-containerd files
        files = {
            'cluster.yaml': 'kind/cluster.yaml.j2',
            'dnsmasq.conf': 'dnsmasq/config.conf.j2',
            'helmfile.yaml': 'helmfile/helmfile.yaml.j2',
            'traefik-tcp-routes.yaml': 'traefik-tcp-routes.yaml.j2'
        }

        has_tcp_routes = any(
            workload.get('ports')
            for workload in context['system_workloads']
            if workload.get('ports')
        )

        for filename, template_name in files.items():
            if filename == 'traefik-tcp-routes.yaml' and not has_tcp_routes:
                tcp_path = f"{self.k8s_dir}/config/{filename}"
                if os.path.exists(tcp_path):
                    os.remove(tcp_path)
                continue

            template = self.jinja_env.get_template(template_name)
            content = template.render(**context)
            output_path = f"{self.k8s_dir}/config/{filename}"
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w') as f:
                f.write(content)

        # Generate containerd hosts.toml files
        containerd_template = self.jinja_env.get_template('containerd/hosts.toml.j2')
        registry_host = f"{self.env.registry.name}.{self.env.network.domain}"

        # Local registry config
        local_reg_ctx = context.copy()
        local_reg_ctx.update({
            'hostname': registry_host,
            'upstream_hostname': registry_host,
            'registry_host': registry_host,
            'is_local_registry': True,
            'mirror_prefix': ''
        })
        self._write_containerd_config(registry_host, containerd_template.render(**local_reg_ctx))

        # Mirroring configs
        if self.env.registry.mirroring.enabled:
            mirrors = []
            # Iterate through enabled mirror sources
            for source in self.env.registry.mirroring.sources:
                if source.enabled and source.name in MIRROR_SOURCES:
                    source_def = MIRROR_SOURCES[source.name]
                    # Handle sources with single or multiple mirrors (k8s_registry has two)
                    if isinstance(source_def, list):
                        mirrors.extend(source_def)
                    else:
                        mirrors.append(source_def)

            for hostname, upstream, prefix in mirrors:
                mirror_ctx = context.copy()
                mirror_ctx.update({
                    'hostname': hostname,
                    'upstream_hostname': upstream,
                    'registry_host': registry_host,
                    'is_local_registry': False,
                    'mirror_prefix': prefix
                })
                self._write_containerd_config(hostname, containerd_template.render(**mirror_ctx))

        return self.k8s_dir

    def _write_containerd_config(self, hostname: str, content: str):
        output_path = f"{self.k8s_dir}/config/containerd/{hostname}/hosts.toml"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(content)
