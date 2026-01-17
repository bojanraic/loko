from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


# =============================================================================
# Cluster Configuration Models
# =============================================================================

class ProviderConfig(BaseModel):
    name: str
    runtime: str


class KubernetesConfig(BaseModel):
    api_port: int = Field(alias="api-port")
    image: str
    tag: str


class ControlPlaneSchedulingConfig(BaseModel):
    allow_workloads: bool = Field(default=True, alias="allow-workloads")
    isolate_internal_components: bool = Field(default=True, alias="isolate-internal-components")


class WorkersSchedulingConfig(BaseModel):
    isolate_workloads: bool = Field(default=True, alias="isolate-workloads")


class SchedulingConfig(BaseModel):
    control_plane: ControlPlaneSchedulingConfig = Field(
        default_factory=ControlPlaneSchedulingConfig,
        alias="control-plane"
    )
    workers: WorkersSchedulingConfig = Field(default_factory=WorkersSchedulingConfig)


class NodeLabels(BaseModel):
    control_plane: Dict[str, str] = Field(default_factory=dict, alias="control-plane")
    worker: Dict[str, str] = Field(default_factory=dict)
    individual: Optional[Dict[str, Dict[str, str]]] = None


class NodesConfig(BaseModel):
    servers: int
    workers: int
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig)
    labels: Optional[NodeLabels] = None


class ClusterConfig(BaseModel):
    provider: ProviderConfig
    kubernetes: KubernetesConfig
    nodes: NodesConfig


# =============================================================================
# Network Configuration Models
# =============================================================================

class SubdomainConfig(BaseModel):
    enabled: bool = True
    value: str = "apps"


class NetworkConfig(BaseModel):
    ip: str
    domain: str
    dns_port: int = Field(default=53, alias="dns-port")
    subdomain: SubdomainConfig = Field(default_factory=SubdomainConfig)
    lb_ports: List[int] = Field(alias="lb-ports")


# =============================================================================
# Registry Configuration Models
# =============================================================================

class RegistryMirrorSource(BaseModel):
    """Individual mirror source configuration"""
    name: str  # e.g., 'docker_hub', 'quay', 'ghcr', 'k8s_registry', 'mcr'
    enabled: bool = True


class RegistryMirroringConfig(BaseModel):
    enabled: bool = True
    sources: List[RegistryMirrorSource] = Field(default_factory=lambda: [
        RegistryMirrorSource(name='docker_hub', enabled=True),
        RegistryMirrorSource(name='quay', enabled=True),
        RegistryMirrorSource(name='ghcr', enabled=True),
        RegistryMirrorSource(name='k8s_registry', enabled=True),
        RegistryMirrorSource(name='mcr', enabled=True),
    ])


class RegistryStorageConfig(BaseModel):
    size: str


class RegistryConfig(BaseModel):
    name: str
    storage: RegistryStorageConfig
    mirroring: RegistryMirroringConfig = Field(default_factory=RegistryMirroringConfig)


# =============================================================================
# Internal Components Configuration Models
# =============================================================================

class InternalComponentConfig(BaseModel):
    """Base config for internal components"""
    version: str


class MetricsServerConfig(InternalComponentConfig):
    """Metrics server is the only optional internal component"""
    enabled: bool = False


class InternalComponentsConfig(BaseModel):
    traefik: InternalComponentConfig
    zot: InternalComponentConfig
    dnsmasq: InternalComponentConfig
    metrics_server: MetricsServerConfig = Field(alias="metrics-server")


# =============================================================================
# Workload Configuration Models
# =============================================================================

class HelmRepoConfig(BaseModel):
    name: str
    url: str


class WorkloadRepoConfig(BaseModel):
    ref: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    type: Literal["helm", "git"] = "helm"


class WorkloadHelmConfig(BaseModel):
    repo: Optional[WorkloadRepoConfig] = None
    chart: str
    version: str
    values: Optional[Dict[str, Any]] = None


class Workload(BaseModel):
    name: str
    enabled: bool
    namespace: Optional[str] = None
    ports: Optional[List[int]] = None
    storage: Optional[RegistryStorageConfig] = None
    config: WorkloadHelmConfig


class WorkloadsConfig(BaseModel):
    use_presets: bool = Field(default=True, alias="use-presets")
    helm_repositories: List[HelmRepoConfig] = Field(default_factory=list, alias="helm-repositories")
    system: List[Workload] = Field(default_factory=list)
    user: List[Workload] = Field(default_factory=list)


# =============================================================================
# Root Configuration Models
# =============================================================================

class EnvironmentConfig(BaseModel):
    name: str
    base_dir: str = Field(alias="base-dir")
    expand_env_vars: bool = Field(default=True, alias="expand-env-vars")
    cluster: ClusterConfig
    network: NetworkConfig
    registry: RegistryConfig
    internal_components: InternalComponentsConfig = Field(alias="internal-components")
    workloads: WorkloadsConfig


class RootConfig(BaseModel):
    environment: EnvironmentConfig
