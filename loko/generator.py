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

    def _process_services(self, services: List[Service], service_ports: Dict[str, int], 
                         service_values_presets: Dict[str, Any], k8s_env_vars: Dict[str, str], 
                         is_system: bool) -> List[Dict[str, Any]]:
        processed_services = []
        
        for service in services:
            if not service.enabled:
                continue

            service_dict = service.model_dump(by_alias=True)
            service_name = service.name
            
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
                        storage_config['persistence'] = {'enabled': True, 'size': service.storage['size']}
                    deep_merge(storage_config, base_values)
                
                chart_name = service.config.chart
                if chart_name:
                    auth_config = self._generate_chart_auth_config(service_name, chart_name)
                    if auth_config:
                        deep_merge(auth_config, base_values)

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
            'registry_version': get_internal_component('registry'),
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

        # Generate files
        files = {
            'cluster.yaml': 'kind/cluster.yaml.j2',
            'containerd/hosts.toml': 'containerd/hosts.toml.j2',
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
                
        return self.k8s_dir
