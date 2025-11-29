from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field

class ProviderConfig(BaseModel):
    name: str
    runtime: str

class KubernetesConfig(BaseModel):
    api_port: int = Field(alias="api-port")
    image: str
    tag: str

class NodeLabels(BaseModel):
    control_plane: Dict[str, str] = Field(default_factory=dict, alias="control-plane")
    worker: Dict[str, str] = Field(default_factory=dict)
    individual: Optional[Dict[str, Dict[str, str]]] = None

class NodesConfig(BaseModel):
    servers: int
    workers: int
    allow_scheduling_on_control_plane: bool = Field(alias="allow-scheduling-on-control-plane")
    internal_components_on_control_plane: bool = Field(alias="internal-components-on-control-plane")
    labels: Optional[NodeLabels] = None

class RegistryConfig(BaseModel):
    name: str
    storage: Dict[str, str]

class HelmRepoConfig(BaseModel):
    name: str
    url: str

class ServiceRepoConfig(BaseModel):
    ref: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None

class ServiceConfig(BaseModel):
    repo: ServiceRepoConfig
    chart: str
    version: str
    values: Optional[Dict[str, Any]] = None

class Service(BaseModel):
    name: str
    enabled: bool
    namespace: Optional[str] = None
    ports: Optional[List[int]] = None
    storage: Optional[Dict[str, str]] = None
    config: ServiceConfig

class ServicesConfig(BaseModel):
    system: List[Service] = Field(default_factory=list)
    user: List[Service] = Field(default_factory=list)

class EnvironmentConfig(BaseModel):
    name: str
    base_dir: str = Field(alias="base-dir")
    expand_env_vars: bool = Field(default=True, alias="expand-env-vars")
    provider: ProviderConfig
    kubernetes: KubernetesConfig
    nodes: NodesConfig
    local_dns_port: int = Field(default=53, alias="local-dns-port")
    local_ip: str = Field(alias="local-ip")
    local_domain: str = Field(alias="local-domain")
    use_apps_subdomain: bool = Field(default=True, alias="use-apps-subdomain")
    apps_subdomain: str = Field(default="apps", alias="apps-subdomain")
    local_lb_ports: List[int] = Field(alias="local-lb-ports")
    registry: RegistryConfig
    internal_components: List[Dict[str, str]] = Field(alias="internal-components")
    use_service_presets: bool = Field(default=True, alias="use-service-presets")
    run_services_on_workers_only: bool = Field(default=False, alias="run-services-on-workers-only")
    enable_metrics_server: bool = Field(default=True, alias="enable-metrics-server")
    helm_repositories: List[HelmRepoConfig] = Field(default_factory=list, alias="helm-repositories")
    services: ServicesConfig

class RootConfig(BaseModel):
    environment: EnvironmentConfig
