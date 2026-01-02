import os
import yaml
import jinja2
import secrets
import string
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from .config import RootConfig, Service
from .utils import deep_merge

CACERT_FILE = "/etc/ssl/certs/mkcert-ca.pem"

def load_presets(templates_dir: Optional[Path] = None) -> tuple[Dict[str, int], Dict[str, Any]]:
    template_dir = templates_dir if templates_dir else Path(__file__).parent / "templates"
    preset_file = template_dir / 'service_presets.yaml'
    
    if not preset_file.exists():
        return {}, {}
        
    with open(preset_file) as f:
        presets = yaml.safe_load(f) or {}
        
    return (
        presets.get('service_ports', {}),
        presets.get('service_values_presets', {})
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

    def _generate_chart_auth_config(self, service_name: str, chart_name: str) -> Dict[str, Any]:
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

    def _manage_git_chart(self, service_name: str, repo_url: str, chart_path: str, version: str) -> str:
        """
        Clone a git repo to a temp directory and copy the chart to the cluster config directory.
        Returns the absolute path to the local chart directory.
        """
        import tempfile
        import shutil
        
        target_dir = os.path.join(self.k8s_dir, "charts", service_name)
        
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

    def _process_services(self, services: List[Service], service_ports: Dict[str, int], 
                         service_values_presets: Dict[str, Any], k8s_env_vars: Dict[str, str], 
                         is_system: bool) -> List[Dict[str, Any]]:
        processed_services = []
        
        for service in services:
            if not service.enabled:
                continue

            service_dict = service.model_dump(by_alias=True)
            service_name = service.name
            
            # Handle Git-based charts
            if service.config.repo and service.config.repo.type == 'git':
                if not service.config.repo.url:
                    raise ValueError(f"Git repo URL required for service '{service_name}'")
                    
                local_chart_path = self._manage_git_chart(
                    service_name=service_name,
                    repo_url=service.config.repo.url,
                    chart_path=service.config.chart,
                    version=service.config.version
                )
                # Update chart to point to the local absolute path
                service_dict['config']['chart'] = local_chart_path
                # We don't need repo ref for local charts in helmfile
                
            base_values = {}
            
            if is_system and self.env.use_service_presets and service_name in service_values_presets:
                base_values = service_values_presets[service_name].copy()
                base_values.update({
                    'fullNameOverride': service_name,
                    'nameOverride': service_name
                })
                
                if service.storage and 'size' in service.storage:
                    storage_config = {}
                    if 'storage' in service_values_presets[service_name]:
                        storage_config['storage'] = {'requestedSize': service.storage['size']}
                    elif 'primary' in service_values_presets[service_name]:
                        storage_config['primary'] = {'persistence': {'enabled': True, 'size': service.storage['size']}}
                    elif 'persistence' in service_values_presets[service_name]:
                        # Check for sub-keys like 'data' used in Garage
                        preset_persistence = service_values_presets[service_name]['persistence']
                        if isinstance(preset_persistence, dict) and 'data' in preset_persistence:
                            storage_config['persistence'] = {'data': {'size': service.storage['size']}}
                        else:
                            storage_config['persistence'] = {'enabled': True, 'size': service.storage['size']}
                    deep_merge(storage_config, base_values)
                
                chart_name = service.config.chart
                if chart_name:
                    auth_config = self._generate_chart_auth_config(service_name, chart_name)
                    if auth_config:
                        deep_merge(auth_config, base_values)
                
                # Expand variables in base_values (from presets)
                base_values = self._expand_vars(base_values, k8s_env_vars)

            custom_values = service.config.values or {}
            if custom_values:
                # Expand variables in custom values
                custom_values = self._expand_vars(custom_values, k8s_env_vars)
                base_values.update(custom_values)
            
            service_dict['base_values'] = base_values
            service_dict['service_type'] = 'system' if is_system else 'user'
            
            if is_system and service_name in service_ports:
                service_dict['default_port'] = service_ports[service_name]
            
            processed_services.append(service_dict)
            
        return processed_services

    def _collect_helm_repositories(self, services: List[Dict[str, Any]]) -> Dict[str, str]:
        repositories = {repo.name: repo.url for repo in self.env.helm_repositories}
        
        # Also collect inline repos from services if any (though our model enforces structure)
        # In our Pydantic model, repo is a ServiceRepoConfig, which might have name/url or ref
        
        for service in services:
             # Access config from the dict structure since services here are dicts dump from loaded model
             # But 'config' key exists and 'repo' might be a dict
             # Warning: 'services' passed here is List[Dict], so we access as dict
             if 'config' in service and 'repo' in service['config']:
                 repo = service['config']['repo']
                 if repo and repo.get('type') == 'git':
                     continue
                 if repo and repo.get('name') and repo.get('url'):
                     repositories[repo['name']] = repo['url']
        
        return repositories

    def prepare_context(self) -> Dict[str, Any]:
        service_ports, service_values_presets = self.get_presets()
        
        apps_subdomain = self.env.apps_subdomain
        local_apps_domain = f"{apps_subdomain}.{self.env.local_domain}" if self.env.use_apps_subdomain else self.env.local_domain
        
        k8s_env_vars = {
            'ENV_NAME': self.env.name,
            'LOCAL_DOMAIN': self.env.local_domain,
            'LOCAL_IP': self.env.local_ip,
            'REGISTRY_NAME': self.env.registry.name,
            'REGISTRY_HOST': f"{self.env.registry.name}.{self.env.local_domain}",
            'APPS_SUBDOMAIN': apps_subdomain,
            'USE_APPS_SUBDOMAIN': str(self.env.use_apps_subdomain).lower(),
            'LOCAL_APPS_DOMAIN': local_apps_domain,
        }
        
        processed_system_services = self._process_services(
            self.env.services.system, service_ports, service_values_presets, k8s_env_vars, True
        )
        processed_user_services = self._process_services(
            self.env.services.user, service_ports, service_values_presets, k8s_env_vars, False
        )
        
        all_services = processed_system_services + processed_user_services
        helm_repositories = self._collect_helm_repositories(all_services)
        
        def get_internal_component(key):
            for comp in self.env.internal_components:
                if key in comp:
                    return comp[key]
            return None

        context = {
            'env_name': self.env.name,
            'local_ip': self.env.local_ip,
            'local_domain': self.env.local_domain,
            'apps_subdomain': apps_subdomain,
            'use_apps_subdomain': self.env.use_apps_subdomain,
            'kubernetes': self.env.kubernetes.model_dump(by_alias=True, exclude_none=True),
            'api_port': self.env.kubernetes.api_port,
            'nodes': self.env.nodes.model_dump(by_alias=True, exclude_none=True),
            'runtime': self.env.provider.runtime,
            'ingress_ports': self.env.local_lb_ports,
            'services': all_services,
            'system_services': processed_system_services,
            'user_services': processed_user_services,
            'helm_repositories': helm_repositories,
            'registry': self.env.registry.model_dump(by_alias=True, exclude_none=True),
            'registry_name': self.env.registry.name,
            'zot_version': get_internal_component('zot'),
            'app_template_version': get_internal_component('app-template'),
            'traefik_version': get_internal_component('traefik'),
            'metrics_server_version': get_internal_component('metrics-server'),
            'dnsmasq_version': get_internal_component('dnsmasq'),
            'service_ports': service_ports,
            'service_values_presets': service_values_presets,
            'use_service_presets': self.env.use_service_presets,
            'run_services_on_workers_only': self.env.run_services_on_workers_only,
            'deploy_metrics_server': self.env.enable_metrics_server,
            'cacert_file': CACERT_FILE,
            'k8s_dir': self.k8s_dir,
            'mounts': [
                {'local_path': 'logs', 'node_path': '/var/log'},
                {'local_path': 'storage', 'node_path': '/var/local-path-provisioner'}
            ],
            'internal_domain': 'kind.internal',
            'internal_host': 'localhost.kind.internal',
            'provider': self.env.provider.model_dump(by_alias=True, exclude_none=True),
            'allow_control_plane_scheduling': self.env.nodes.allow_scheduling_on_control_plane,
            'internal_components_on_control_plane': self.env.nodes.internal_components_on_control_plane,
            'root_ca_path': os.path.abspath(f"{self.k8s_dir}/certs/rootCA.pem"),
            'dns_port': self.env.local_dns_port,
            'kubernetes_full_image': f"{self.env.kubernetes.image}:{self.env.kubernetes.tag}" if self.env.kubernetes.tag else self.env.kubernetes.image
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
            service.get('ports')
            for service in context['system_services']
            if service.get('ports')
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
        registry_host = f"{self.env.registry.name}.{self.env.local_domain}"
        
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
            if self.env.registry.mirroring.docker_hub:
                mirrors.append(('docker.io', 'registry-1.docker.io', '/dockerhub'))
            if self.env.registry.mirroring.quay:
                mirrors.append(('quay.io', 'quay.io', '/quay'))
            if self.env.registry.mirroring.ghcr:
                mirrors.append(('ghcr.io', 'ghcr.io', '/ghcr'))
            if self.env.registry.mirroring.k8s_registry:
                mirrors.append(('k8s.gcr.io', 'k8s.gcr.io', '/k8s'))
                mirrors.append(('registry.k8s.io', 'registry.k8s.io', '/k8s'))
            if self.env.registry.mirroring.mcr:
                mirrors.append(('mcr.microsoft.com', 'mcr.microsoft.com', '/mcr'))

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
