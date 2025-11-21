# Loko

[![PyPI version](https://badge.fury.io/py/loko.svg)](https://badge.fury.io/py/loko)
[![Python Versions](https://img.shields.io/pypi/pyversions/loko.svg)](https://pypi.org/project/loko/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python CLI utility to manage local Kubernetes environments with Kind, providing simplified configuration management, version upgrades, and extensive customization options.

## Features

- 🚀 **Easy Setup**: Initialize local Kubernetes clusters with a single command
- 🔄 **Smart Version Management**: Upgrade component versions using Renovate-style comments
- 💾 **Automatic Backups**: Config files are automatically backed up before upgrades
- 🎨 **Custom Templates**: Use your own Jinja2 templates for configuration generation
- ⚙️ **Extensive CLI Overrides**: Override any configuration value via command-line flags
- 📦 **Built-in Local Registry**: Local container registry with TLS support
- 🔒 **Automatic HTTPS**: Built-in certificate management with mkcert
- 🌐 **Local DNS**: Automatic DNS configuration for local development
- 📈 **Metrics & Monitoring**: Built-in metrics-server for resource monitoring and HPA support
- 📊 **Comprehensive Status**: Detailed view of cluster resources with `loko status`
- 🎯 **Advanced Node Scheduling**: Flexible node labeling and workload placement
- 🔧 **Service Presets**: Pre-configured settings for common services (MySQL, PostgreSQL, Valkey, etc.)
- 🛠️ **Helm-based Deployment**: Deploy services from public repositories (groundhog2k, etc.)
- 🗂️ **Centralized Helm Repos**: Define repositories once, reference everywhere
- 📋 **OCI Chart Validation**: Local registry testing with OCI artifact storage
- 🔑 **Secret Management**: Automatically fetch and save service credentials

## Prerequisites

- Python 3.9 or higher
- Docker or Podman
- [Kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [mkcert](https://github.com/FiloSottile/mkcert#installation) (for HTTPS certificates)
- [Helm](https://helm.sh/docs/intro/install/)
- [Helmfile](https://github.com/helmfile/helmfile#installation) (optional, for service deployment)
- (optional) nss (for macOS) or libnss3-tools (for Linux) - needed for Firefox to trust mkcert certificates

## Installation

### From PyPI (recommended)

```bash
pip install loko
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
   loko generate-config
   ```

3. Initialize your environment:
   ```bash
   loko init
   ```

4. Create the full environment:
   ```bash
   loko create
   ```

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

### Configuration & Secrets
- `loko generate-config` - Generate default loko.yaml
- `loko config upgrade` - Upgrade component versions using Renovate comments
- `loko secrets` - Fetch and display service credentials
- `loko config presets` - View available service presets (coming soon)

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

Loko uses Renovate-style comments in your configuration file to track and upgrade component versions. This approach allows you to:
- Keep component versions up-to-date
- Track version sources directly in your config
- Automatically query Docker Hub and Helm repositories for latest versions

### How It Works

Add Renovate comments above the version fields in your `loko.yaml`:

```yaml
kubernetes:
  image: kindest/node
  # renovate: datasource=docker depName=kindest/node
  tag: v1.34.0

internal-components:
  # renovate: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts
  - traefik: "37.3.0"

services:
  system:
    - name: mysql
      config:
        chart: groundhog2k/mysql
        # renovate: datasource=helm depName=mysql
        version: 3.0.7
```

### Supported Datasources

- **Docker Hub** (`datasource=docker`): Fetches latest tags from Docker Hub
- **Helm Repositories** (`datasource=helm`): Fetches latest chart versions from Helm repos

### Running Upgrades

```bash
loko config upgrade
```

This will:
1. 🔍 Scan your config for Renovate comments
2. 🌐 Query each datasource for the latest version
3. 💾 Create a backup (`loko-prev.yaml`)
4. ✅ Update versions in place
5. 📋 Show a summary of changes

Example output:
```
Upgrading component versions...

🔍 Checking kindest/node (docker)...
🔍 Checking traefik (helm)...
🔍 Checking mysql (helm)...

Updates found:
  kindest/node: v1.32.0 → v1.34.0
  traefik: 31.2.0 → 37.3.0
  mysql: 3.0.5 → 3.0.7

💾 Backup created: loko-prev.yaml
✅ Updated 3 version(s) in loko.yaml
```

### Restoring from Backup

If an upgrade causes issues, easily revert:

```bash
mv loko-prev.yaml loko.yaml
```

## Managing Service Credentials

Service credentials (database passwords, etc.) are automatically generated during deployment. To view them:

```bash
loko secrets
```

This fetches credentials from the cluster and displays them. Credentials are also saved to:
```
<base-dir>/<env-name>/service-secrets.txt
```

Example services with auto-generated credentials:
- MySQL (root password)
- PostgreSQL (postgres password)
- MongoDB (root password)
- RabbitMQ (admin password)
- Valkey (default password)

## Directory Structure

When you run `loko init` or `loko create`, a `.local` directory is created (configurable via `base-dir`).

```
.
├── loko.yaml                       # Main configuration file
├── .local/                            # Default directory for cluster data and configs
│   └── <env-name>/                    # Environment-specific directory (e.g. dev-me)
│       ├── certs/                     # TLS certificates and keys
│       │   ├── rootCA.pem             # Root CA certificate
│       │   ├── <domain>.pem           # Domain certificate
│       │   ├── <domain>-key.pem       # Domain private key
│       │   └── <domain>-combined.pem  # Combined cert and key
│       ├── config/                    # Generated configuration files
│       │   ├── cluster.yaml           # KinD cluster configuration
│       │   ├── containerd.yaml        # Container runtime config
│       │   ├── dnsmasq.conf           # Local DNS configuration
│       │   └── helmfile.yaml          # Helm releases definition
│       ├── logs/                      # Kubernetes node logs
│       ├── storage/                   # Persistent volume data
│       ├── kubeconfig                 # Cluster access configuration
│       └── service-secrets.txt        # Generated service credentials
```

> **Note**: The `.local` directory is git-ignored by default.

## Service Management

The environment manages development services (databases, message queues, etc.) through Helm deployments.

### Service Types and DNS Structure

1. **System Services** (`service.local.domain`):
   - Core infrastructure services (databases, message queues, etc.)
   - Direct DNS resolution (e.g., `mysql.dev.me`, `postgres.dev.me`)
   - No wildcard resolution for security

2. **Applications** (`${LOCAL_APPS_DOMAIN}`):
   - Custom applications and services
   - Either under `.apps` subdomain (`service.apps.local.domain`) or direct domain (`service.local.domain`)
   - Configurable via `use-apps-subdomain` setting

3. **Core Infrastructure**:
   - Registry service (e.g., `cr.dev.me`)

### Accessing Services

Once the environment is running, services are accessible through:

1. **Direct Port Access**:
   ```bash
   # Example for PostgreSQL
   psql -h localhost -p 5432 -U postgres
   ```

2. **Domain Names**:
   ```bash
   # Example for system service
   psql -h postgres.dev.me -U postgres
   ```

3. **Service Credentials**:
   - Passwords are automatically generated and stored in `<local-dir>/<env-name>/service-secrets.txt`
   - Or fetch them with: `loko secrets`

### Using the Local Container Registry

The environment includes a local container registry accessible at `<registry-name>.<local-domain>`.

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
nodes:
  labels:
    control-plane:
      tier: "infrastructure"
    worker:
      tier: "application"
```

### Scheduling Flags

- **`internal-components-on-control-plane`**: Forces infrastructure components (Traefik, registry) to run only on control-plane nodes.
- **`run-services-on-workers-only`**: Forces application services (databases, etc.) to run only on worker nodes.

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

## Configuration

The environment is configured through `loko.yaml`. You can generate a default one with `loko generate-config`.

### Schema Structure

```yaml
environment:
  # General settings
  name: string                    # Name of the environment
  base-dir: string                # Base directory for storage
  expand-env-vars: boolean        # Whether to expand OS and k8s-env variables

  # Centralized repository definitions
  helm-repositories: array        # List of Helm repositories

  # Provider configuration
  provider:
    name: string                  # Provider name (currently only "kind" supported)
    runtime: string               # Container runtime (docker or podman)

  # Kubernetes configuration
  kubernetes:
    api-port: integer             # API server port
    image: string                 # Node image
    tag: string                   # Node image tag

  # Node configuration
  nodes:
    servers: integer              # Number of control-plane nodes
    workers: integer              # Number of worker nodes
    allow-scheduling-on-control-plane: boolean
    internal-components-on-control-plane: boolean

  # Network configuration
  local-ip: string                # Local IP for DNS resolution
  local-domain: string            # Domain name
  local-lb-ports: array           # Load balancer ports
  use-apps-subdomain: boolean     # Use apps subdomain
  apps-subdomain: string          # Subdomain for apps

  # Registry configuration
  registry:
    name: string
    storage:
      size: string

  # Internal components
  internal-components: array      # List of internal components with versions

  # Service configuration
  use-service-presets: boolean    # Whether to use service presets
  run-services-on-workers-only: boolean
  enable-metrics-server: boolean
  services:
    system: array                 # List of system services to deploy
    user: array                   # List of user-defined services
```

### CLI Overrides

Loko provides extensive CLI options to override almost any configuration value during initialization:

```bash
loko init --name my-cluster --workers 3 --registry-storage 50Gi --no-schedule-on-control
```

See `loko init --help` for all available overrides.

## Troubleshooting

1. **DNS Resolution Issues**
   - Verify local DNS container is running: `loko status`
   - Check DNS configuration: `cat /etc/resolver/<your-domain>`

2. **Certificate Issues**
   - Regenerate certificates: `loko init` (will re-run certificate setup)
   - Verify cert location: `ls <local-dir>/<env-name>/certs/`

3. **Service Access Issues**
   - Validate environment: `loko validate`
   - Verify ingress: `kubectl get ingress -A`
   - Check credentials: `loko secrets`

4. **OCI Registry Issues**
   - Test registry connectivity: `docker pull cr.dev.me/test:latest`
   - Run validation: `loko validate`

5. **Version Upgrade Issues**
   - Restore from backup: `mv loko-prev.yaml loko.yaml`
   - Check Renovate comment syntax in config file

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
uv run loko --help
uv run loko init --help
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
