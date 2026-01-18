# LoKO - Local Kubernetes Oasis - simplified Kubernetes development environments

[![PyPI version](https://img.shields.io/pypi/v/loko-k8s.svg)](https://badge.fury.io/py/loko-k8s)
[![Python Versions](https://img.shields.io/pypi/pyversions/loko-k8s.svg)](https://pypi.org/project/loko-k8s/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<div align="center">
  <img src="https://raw.githubusercontent.com/bojanraic/loko/main/loko-logo.svg" alt="LoKO Logo" width="200" height="200">
</div>

A Python CLI utility to manage local Kubernetes environments with Kind, providing simplified configuration management, version upgrades, DNS, wildcard certificates, local container registry, and extensive customization options.

## Features

- **Easy Setup**: Initialize local Kubernetes clusters with a single command
- **Smart Version Management**: Upgrade component versions using loko-updater comments
- **Automatic Backups**: Config files are automatically backed up before upgrades
- **Custom Templates**: Use your own Jinja2 templates for configuration generation
- **Extensive CLI Overrides**: Override any configuration value via command-line flags
- **Built-in Local Registry**: Local container registry with TLS support
- **Automatic HTTPS**: Built-in certificate management with mkcert
- **Local DNS**: Automatic DNS configuration for local development
- **Metrics & Monitoring**: Built-in metrics-server for resource monitoring and HPA support
- **Comprehensive Status**: Detailed view of cluster resources with `loko status`
- **Granular Workload Management**: List, deploy, and undeploy individual workloads with `loko workload`
- **Advanced Node Scheduling**: Flexible node labeling and workload placement
- **Registry Mirroring**: Automatic caching/mirroring of external registries (Docker Hub, Quay, etc.)
- **Workload Presets**: Pre-configured settings for common workloads (MySQL, PostgreSQL, Valkey, etc.)
- **Helm-based Deployment**: Deploy workloads from public repositories (groundhog2k, etc.)
- **Centralized Helm Repos**: Define repositories once, reference everywhere
- **Automatic Secrets Management**: Automatically generate, fetch and save workload credentials with deduplication
- **Port Availability Checking**: Pre-flight validation ensures all required ports are available before cluster creation
- **Smart Error Handling**: Clear, actionable error messages guide you to solutions

## Breaking Changes in v0.1.0

> **Important for existing users**: The configuration schema has been restructured for better organization and clarity. If you have an existing `loko.yaml`, you'll need to regenerate it.

### Migration Steps

1. **Backup your existing config** (if you have customizations):
   ```bash
   cp loko.yaml loko.yaml.backup
   ```

2. **Regenerate the config**:
   ```bash
   loko config generate --force
   ```

3. **Re-apply your customizations** to the new config structure.

### Key Schema Changes

| Old Path | New Path |
|----------|----------|
| `local-ip` | `network.ip` |
| `local-domain` | `network.domain` |
| `local-dns-port` | `network.dns-port` |
| `local-lb-ports` | `network.lb-ports` |
| `use-apps-subdomain` | `network.subdomain.enabled` |
| `apps-subdomain` | `network.subdomain.value` |
| `provider` | `cluster.provider` |
| `kubernetes` | `cluster.kubernetes` |
| `nodes` | `cluster.nodes` |
| `nodes.allow-scheduling-on-control-plane` | `cluster.nodes.scheduling.control-plane.allow-workloads` |
| `nodes.internal-components-on-control-plane` | `cluster.nodes.scheduling.control-plane.isolate-internal-components` |
| `run-workloads-on-workers-only` | `cluster.nodes.scheduling.workers.isolate-workloads` |
| `internal-components` (list) | `internal-components` (dict with named components) |
| `helm-repositories` | `workloads.helm-repositories` |

## Prerequisites

- Python 3.9 or higher
- Docker
- [Kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [mkcert](https://github.com/FiloSottile/mkcert#installation) (for HTTPS certificates)
- [Helm](https://helm.sh/docs/intro/install/)
- [Helmfile](https://github.com/helmfile/helmfile#installation)
- (optional) nss (for macOS) or libnss3-tools (for Linux) - needed for Firefox to trust mkcert certificates

### Installing Prerequisites with Mise (Recommended)

[Mise](https://mise.jdx.dev/) is the recommended way to install and manage CLI tools. Clone the repo and run `mise install` from the project root to install all prerequisites:

```bash
git clone https://github.com/bojanraic/loko.git
cd loko
mise install  # Installs kind, helm, kubectl, mkcert, helmfile
```

## Installation

### From PyPI (recommended)

Using pip:
```bash
pip install loko-k8s
```

Using uv:
```bash
uv tool install loko-k8s
```

### From Source

```bash
git clone https://github.com/bojanraic/loko.git
cd loko
pip install -e .
```

### Using uv (for development)

```bash
git clone https://github.com/bojanraic/loko.git
cd loko
uv sync
uv run loko --help
```

## Quick Start

1. Check prerequisites:
   ```bash
   loko check-prerequisites
   ```

2. Generate a default configuration:
   ```bash
   loko config generate
   # Or use --minimal for a compact config without comments/disabled sections:
   # loko config generate --minimal
   ```

3. Initialize your environment:
   ```bash
   loko init
   ```

4. Create the full environment:
   ```bash
   loko create
   ```

## Demo

Watch Loko in action - see the complete workflow from installation to cluster validation:

[![asciicast](https://asciinema.org/a/BScbf8glbIWscjUo.svg)](https://asciinema.org/a/BScbf8glbIWscjUo)


**Demo highlights:**

- Installing loko
- Generating a default configuration with auto-detected IP
- Creating a local Kubernetes cluster with Kind
- Deploying workloads (Traefik, container registry, PostgreSQL) with Helm
- Validating the cluster setup
- Checking environment status
- Upgrading component versions
- Viewing workload secrets & connecting to PostgreSQL and test application
- Stopping and starting environment
- Installing shell completion (via `loko completion <shell>`)

## Commands

### Environment Lifecycle
- `loko init` - Initialize environment (generate configs, setup certs, network)
- `loko create` - Create full environment with complete workflow
- `loko start` - Start all cluster containers
- `loko stop` - Stop all cluster containers
- `loko destroy` - Destroy the environment
- `loko recreate` - Destroy and recreate the environment
- `loko clean` - Destroy environment and remove all artifacts

### Status & Validation
- `loko status` - Show comprehensive environment status
- `loko validate` - Validate the environment
- `loko check-prerequisites` - Check if required tools are installed
- `loko completion <shell>` - Generate shell completion script (bash, zsh, fish)

### Configuration & Secrets
- `loko config generate` - Generate default loko.yaml with auto-detected local IP (use `--minimal` for compact config without comments)
- `loko config compact` - Compact existing config by removing comments and disabled sections
- `loko config detect-ip` - Detect and display the local IP address
- `loko config validate` - Validate configuration file structure and values
- `loko config port-check` - Check availability of all configured ports
- `loko config dns-check` - Check DNS configuration and resolution status
- `loko config upgrade` - Upgrade component versions using loko-updater comments
- `loko config helm-repo-add` - Add Helm repositories to config
- `loko config helm-repo-remove` - Remove Helm repositories from config
- `loko workload list` - List workloads and their status (with filtering options)
- `loko workload deploy` - Deploy all or specific workloads
- `loko workload undeploy` - Undeploy all or specific workloads
- `loko secret fetch` - Fetch workload credentials from cluster
- `loko secret show` - Display saved workload credentials
- `loko registry status` - Show registry statistics and configuration
- `loko registry list-repos` - List all repositories in the registry
- `loko registry show-repo <name>` - Show details about a specific repository
- `loko registry list-tags <name>` - List all tags for a repository

## Checking Cluster Status

Use the `status` command to get a comprehensive overview of your local Kubernetes environment:

```bash
loko status
```

This will display:

- **Cluster Status**: Overall health of the Kubernetes cluster
- **Container Status**: Status of all related containers (nodes, DNS, etc.)
- **Node Status**: List of all nodes with their roles and status
- **DNS Status**: Status of the local DNS service

## Version Management & Upgrades

> **Migration Note:** If you're upgrading from an earlier version of Loko that used `# renovate:` comments, you'll need to update them to `# loko-updater:`. A simple find-and-replace in your `loko.yaml` will do:
> ```bash
> sed -i '' 's/# renovate:/# loko-updater:/g' loko.yaml  # macOS
> sed -i 's/# renovate:/# loko-updater:/g' loko.yaml     # Linux
> ```

Loko uses loko-updater comments in your configuration file to track and upgrade component versions. This approach allows you to:
- Keep component versions up-to-date
- Track version sources directly in your config
- Automatically query Docker Hub and Helm repositories for latest versions

### How It Works

Add loko-updater comments above the version fields in your `loko.yaml`:

```yaml
cluster:
  kubernetes:
    image: kindest/node
    # loko-updater: datasource=docker depName=kindest/node
    tag: v1.35.0

internal-components:
  traefik:
    # loko-updater: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts
    version: "38.0.2"

workloads:
  system:
    - name: mysql
      config:
        chart: groundhog2k/mysql
        # loko-updater: datasource=helm depName=mysql repositoryUrl=https://groundhog2k.github.io/helm-charts
        version: 3.0.8
```

### Supported Datasources

- **Docker Hub** (`datasource=docker`): Fetches latest tags from Docker Hub
- **Helm Repositories** (`datasource=helm`): Fetches latest chart versions from Helm repos

### Running Upgrades

```bash
loko config upgrade
```

This will:
1. Scan your config for loko-updater comments
2. Query each datasource for the latest version (in parallel)
3. Create a backup (`loko-prev.yaml`)
4. Update versions in place
5. Show a summary of changes

**Performance:** Helm repository checks are performed in parallel, significantly reducing upgrade time when checking multiple repositories.

Example output:
```
Upgrading component versions...

Updates found:
  kindest/node: v1.34.0 → v1.35.0
  traefik: 37.3.0 → 38.0.2
  mysql: 3.0.7 → 3.0.8

Backup created: loko-prev.yaml
Updated 3 version(s) in loko.yaml

Total fetch time: 8.18s (Helm ops: 8.18s)
```

### Restoring from Backup

If an upgrade causes issues, easily revert:

```bash
mv loko-prev.yaml loko.yaml
```

## Managing Helm Repositories

Loko provides commands to manage Helm repositories in your configuration file:

### Adding Repositories

```bash
# Add a single repository
loko config helm-repo-add \
  --helm-repo-name bitnami \
  --helm-repo-url https://charts.bitnami.com/bitnami

# Add multiple repositories at once
loko config helm-repo-add \
  --helm-repo-name bitnami --helm-repo-url https://charts.bitnami.com/bitnami \
  --helm-repo-name jetstack --helm-repo-url https://charts.jetstack.io
```

### Removing Repositories

```bash
# Remove a single repository
loko config helm-repo-remove --helm-repo-name bitnami

# Remove multiple repositories
loko config helm-repo-remove \
  --helm-repo-name bitnami \
  --helm-repo-name jetstack
```

### Using Added Repositories

Added repositories appear in your config and can be referenced:

```yaml
environment:
  workloads:
    helm-repositories:
      - name: bitnami
        url: https://charts.bitnami.com/bitnami/

    user:
      - name: my-app
        config:
          repo:
            ref: bitnami          # Reference the added repository
          chart: bitnami/nginx
          version: 1.0.0
```

## Managing Workload Credentials

Workload credentials (database passwords, etc.) are automatically generated during deployment:

```bash
# Fetch credentials from the cluster
loko secret fetch

# Display saved credentials
loko secret show
```

> **Tip**: `loko secret show` will automatically trigger a `fetch` if the secrets file doesn't exist yet.

Credentials are saved locally to:
```
<base-dir>/<env-name>/workload-secrets.txt
```

Example workloads with auto-generated credentials:
- MySQL (root password)
- PostgreSQL (postgres password)
- MongoDB (root password)
- RabbitMQ (admin password)
- Valkey (default password)

## Directory Structure

When you run `loko init` or `loko create`, a `.loko` directory is created (configurable via `base-dir`).

```
.
├── loko.yaml                       # Main configuration file
├── .loko/                          # Default directory for cluster data and configs
│   └── <env-name>/                 # Environment-specific directory (e.g. dev-me)
│       ├── certs/                  # TLS certificates and keys
│       │   ├── rootCA.pem          # Root CA certificate
│       │   ├── <domain>.pem        # Domain certificate
│       │   ├── <domain>-key.pem    # Domain private key
│       │   └── <domain>-combined.pem  # Combined cert and key
│       ├── config/                 # Generated configuration files
│       │   ├── cluster.yaml        # KinD cluster configuration
│       │   ├── containerd/         # Container runtime config (per registry)
│       │   │   ├── cr.dev.me/hosts.toml
│       │   │   └── docker.io/hosts.toml
│       │   ├── dnsmasq.conf        # Local DNS configuration
│       │   └── helmfile.yaml       # Helm releases definition
│       ├── logs/                   # Kubernetes node logs
│       ├── storage/                # Persistent volume data
│       ├── kubeconfig              # Cluster access configuration
│       └── workload-secrets.txt    # Generated workload credentials
```

> **Note**: The `.loko` directory is git-ignored by default.

## Workload Management

Loko permits granular control over your workloads through the `workload` command group.

### Listing Workloads

View all enabled workloads, their type, namespace, and current status:

```bash
loko workload list
```

Filter by type or status:
```bash
loko workload list --all       # All workloads including disabled
loko workload list --user      # Only enabled user workloads
loko workload list --system    # Only enabled system workloads
loko workload list --internal  # Only enabled internal components (Traefik, Registry, etc.)
loko workload list --disabled  # Only disabled workloads
loko workload list --system --disabled  # Disabled system workloads only
```

### Deploying and Undeploying

Deploy or undeploy specific workloads:

```bash
# Deploy all user and system workloads
loko workload deploy

# Deploy a specific workload
loko workload deploy mongodb

# Undeploy a specific workload
loko workload undeploy garage

# Include internal workloads
loko workload deploy --internal
```

The `deploy` and `undeploy` commands default to targeting **user** and **system** workloads. Use `--all` or specific type flags to include internal components.

> **Note**: Selective deployment uses `helmfile --selector` under the hood.

### Workload Types and DNS Structure

1. **System Workloads** (`workload.network.domain`):
   - Core infrastructure workloads (databases, message queues, etc.)
   - Direct DNS resolution (e.g., `mysql.dev.me`, `postgres.dev.me`)

2. **User Workloads** (`workload.network.subdomain.value.network.domain`):
   - Custom applications and workloads
   - Either under subdomain (`myapp.apps.dev.me`) or direct domain (`myapp.dev.me`)
   - Configurable via `network.subdomain.enabled` setting

3. **Internal Components**:
   - Registry (e.g., `cr.dev.me`)
   - Traefik ingress controller
   - DNS service (dnsmasq)
   - Metrics server (optional)

### Accessing Workloads

Once the environment is running, workloads are accessible through:

1. **Direct Port Access**:
   ```bash
   # Example for PostgreSQL
   psql -h localhost -p 5432 -U postgres
   ```

2. **Domain Names**:
   ```bash
   # Example for system workload
   psql -h postgres.dev.me -U postgres
   ```

3. **Workload Credentials**:
   - Passwords are automatically generated and stored in `<base-dir>/<env-name>/workload-secrets.txt`
   - Or fetch them with: `loko secret show`

### Using the Local Container Registry

The environment includes a local container registry accessible at `<registry.name>.<network.domain>`.

1. **Push Images**:
   ```bash
   docker tag myapp:latest cr.dev.me/myapp:latest
   docker push cr.dev.me/myapp:latest
   ```

2. **Use in Kubernetes**:
   ```yaml
   image: cr.dev.me/myapp:latest
   ```

## Node Scheduling and Workload Placement

The environment supports advanced node scheduling configurations to separate infrastructure and application workloads.

### Node Labels

Configure custom labels in `loko.yaml`:

```yaml
cluster:
  nodes:
    labels:
      control-plane:
        tier: "infrastructure"
      worker:
        tier: "application"
```

### Scheduling Configuration

Control workload placement with the scheduling section:

```yaml
cluster:
  nodes:
    scheduling:
      control-plane:
        allow-workloads: true              # Allow user/system workloads on control-plane
        isolate-internal-components: true  # Force Traefik/registry to control-plane only
      workers:
        isolate-workloads: true            # Force user/system workloads to workers only
```

## OCI Registry and Helm Chart Validation

Loko includes validation workflows for testing OCI registry functionality.

Run validation with:
```bash
loko validate
```

This runs a comprehensive check including:
1. Cluster status and node readiness
2. DNS service health
3. System pods status
4. Kubectl connectivity
5. **Registry & TLS Validation**: Builds a test image, pushes to local registry, deploys a test app, and verifies connectivity.

### Inspecting the Registry

Use the `registry` command group to inspect and manage the local container registry:

```bash
# Show registry statistics and configuration
loko registry status

# List all repositories (local and mirrored)
loko registry list-repos

# Show details about a specific repository
loko registry show-repo myapp
loko registry show-repo docker.io/library/nginx

# List all tags for a repository
loko registry list-tags myapp
```

When mirroring is enabled, images pulled through the cluster are cached in the local registry. Use `list-repos` to verify mirroring is working.

## Configuration

The environment is configured through `loko.yaml`. Generate a default one with `loko config generate`.

### Schema Structure

```yaml
environment:
  # General settings
  name: string                    # Name of the environment
  base-dir: string                # Base directory for storage
  expand-env-vars: boolean        # Whether to expand OS and loko variables

  # Cluster configuration
  cluster:
    provider:
      name: string                # Provider name (currently only "kind" supported)
      runtime: string             # Container runtime (docker or podman)

    kubernetes:
      api-port: integer           # API server port
      image: string               # Node image
      tag: string                 # Node image tag

    nodes:
      servers: integer            # Number of control-plane nodes
      workers: integer            # Number of worker nodes
      scheduling:
        control-plane:
          allow-workloads: boolean
          isolate-internal-components: boolean
        workers:
          isolate-workloads: boolean
      labels:                     # Optional custom node labels
        control-plane: {}
        worker: {}

  # Network configuration
  network:
    ip: string                    # Local IP for DNS resolution
    domain: string                # Domain name
    dns-port: integer             # DNS resolver port (default 53)
    subdomain:
      enabled: boolean            # Use subdomain for user apps
      value: string               # Subdomain value (e.g., "apps")
    lb-ports: array               # Load balancer ports [80, 443]

  # Registry configuration
  registry:
    name: string                  # Registry name (e.g., "cr")
    storage:
      size: string                # PVC size (e.g., "10Gi")
    mirroring:
      enabled: boolean
      sources: array              # List of mirror sources

  # Internal components (infrastructure)
  internal-components:
    traefik:
      version: string
    zot:
      version: string
    dnsmasq:
      version: string
    metrics-server:
      version: string
      enabled: boolean            # Only metrics-server is optional

  # Workload configuration
  workloads:
    use-presets: boolean          # Whether to use workload presets
    helm-repositories: array      # Centralized Helm repo definitions
    system: array                 # List of system workloads
    user: array                   # List of user-defined workloads
```

### CLI Overrides

Loko provides extensive CLI options to override almost any configuration value during initialization:

```bash
loko init --name my-cluster --workers 3 --registry-storage 50Gi --no-schedule-on-control
```

See `loko init --help` for all available overrides.

### Custom DNS Port

Loko runs a lightweight DNS container on your machine so that services such as `postgres.dev.me` resolve locally. By default it binds to the standard DNS port 53, but some hosts already listen on that port. If you need to avoid a conflict, set `network.dns-port` in `loko.yaml` (or pass `--dns-port` to `loko init`). Loko will start the DNS container on the specified port and automatically update the `/etc/resolver/<domain>` entry so lookups continue to work.

## Troubleshooting

1. **DNS Resolution Issues**
   - Run DNS diagnostics: `loko config dns-check`
   - Verify local DNS container is running: `loko status`
   - Check DNS configuration: `cat /etc/resolver/<your-domain>`

2. **Certificate Issues**
   - Regenerate certificates: `loko init` (will re-run certificate setup)
   - Verify cert location: `ls <base-dir>/<env-name>/certs/`

3. **Workload Access Issues**
   - Validate environment: `loko validate`
   - Verify ingress: `kubectl get ingress -A`
   - Check credentials: `loko secret show`

4. **OCI Registry Issues**
   - Test registry connectivity: `docker pull cr.dev.me/test:latest`
   - Run validation: `loko validate`

5. **Version Upgrade Issues**
   - Restore from backup: `mv loko-prev.yaml loko.yaml`
   - Check loko-updater comment syntax in config file

6. **Port Conflicts**
   - Check what's using a port: `sudo lsof -i :53` (macOS) or `sudo netstat -tlnp | grep :53` (Linux)
   - Change the DNS port in config: `network.dns-port: 5353`

## Development

### Setup

```bash
git clone https://github.com/bojanraic/loko.git
cd loko
uv sync
uv run loko --help
```

### Running Tests

```bash
# Run all unit tests
uv run pytest tests/ --ignore=tests/integration

# Run with verbose output
uv run pytest tests/ -v --ignore=tests/integration
```

### Code Quality

```bash
uv run ruff check loko/
uv run ruff format loko/
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
