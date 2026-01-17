# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Loko** is a Python CLI tool for managing local Kubernetes development environments using Kind. It automates cluster setup, DNS configuration, TLS certificates, local container registry, and workload deployment via Helm.

**Key Dependencies:**
- `typer` - CLI framework
- `pydantic` - Configuration validation and parsing
- `ruamel.yaml` - YAML parsing with comment preservation (important for loko-updater comments)
- `jinja2` - Template rendering for configuration generation
- `rich` - Terminal output formatting

## Architecture

### Core Components

1. **CLI Layer** (`loko/cli/`):
   - Modular CLI architecture using Typer framework
   - Entry point: `loko/cli/__init__.py` with main `app` (Typer instance)
   - Subcommand groups: `config_app`, `workload_app`, `secret_app` for grouped commands
   - **Command Organization** (`loko/cli/commands/`):
     - `lifecycle.py` - `init`, `create`, `destroy`, `recreate`, `clean` commands
     - `control.py` - `start`, `stop` commands
     - `status.py` - `status`, `validate` commands
     - `config.py` - `config generate`, `config compact`, `config detect-ip`, `config validate`, `config port-check`, `config upgrade`, `config helm-repo-add`, `config helm-repo-remove` commands
     - `workloads.py` - `workload list`, `workload deploy`, `workload undeploy` commands
     - `secrets.py` - `secret fetch`, `secret show` commands
     - `registry.py` - `registry status`, `registry list-repos`, `registry show-repo`, `registry list-tags` commands
     - `utility.py` - `version`, `check-prerequisites` commands
     - `completion.py` - `completion` command (shell completion scripts)
   - **CLI Type Definitions** (`loko/cli_types.py`):
     - Reusable `Annotated` type definitions for CLI arguments
     - Examples: `ConfigArg`, `NameArg`, `DomainArg`, `WorkersArg`, etc.
     - Ensures consistency across commands with shared argument definitions
   - **Runtime prerequisite checks** (`loko/validators.py`):
     - `ensure_docker_running()` - Ensures docker daemon is accessible
     - `ensure_config_file()` - Ensures config file exists
     - `ensure_ports_available()` - Validates DNS, LB, and workload ports before cluster creation
     - Provides helpful error messages guiding users to solutions
   - **Help system**: Supports both `-h` and `--help` via `context_settings={"help_option_names": ["-h", "--help"]}`
   - **Shell Completion**: Custom `completion` subcommand (kubectl-style)
     - Supports bash, zsh, fish (no powershell - macOS/Linux only)
     - Users source the output: `source <(loko completion zsh)`
     - Implementation in `loko/cli/commands/completion.py`

2. **Configuration** (`loko/config.py`):
   - Pydantic models defining the configuration schema
   - **Key Models**:
     - `RootConfig` - Top-level config wrapper
     - `EnvironmentConfig` - Main environment configuration
     - `ClusterConfig` - Groups provider, kubernetes, and nodes config
     - `NetworkConfig` - Network settings (ip, domain, dns-port, subdomain, lb-ports)
     - `SubdomainConfig` - Subdomain settings (enabled, value)
     - `NodesConfig` - Node topology and scheduling
     - `SchedulingConfig` - Node scheduling with control_plane and workers sub-configs
     - `InternalComponentsConfig` - Dict-based internal component configs (traefik, zot, dnsmasq, metrics-server)
     - `WorkloadsConfig` - Workload definitions with helm-repositories
   - Uses field aliases (e.g., `api_port` → `api-port`) for YAML kebab-case naming
   - **Config Access Patterns**:
     - `config.environment.cluster.provider.runtime` - Container runtime
     - `config.environment.cluster.kubernetes.tag` - K8s version
     - `config.environment.cluster.nodes.scheduling.control_plane.allow_workloads` - Scheduling flags
     - `config.environment.network.domain` - Local domain
     - `config.environment.network.subdomain.enabled` - Subdomain toggle
     - `config.environment.internal_components.traefik.version` - Component versions
     - `config.environment.internal_components.metrics_server.enabled` - Optional component toggle

3. **Configuration Generation** (`loko/generator.py`):
   - `ConfigGenerator` class: Renders Jinja2 templates to generate Kind cluster config, dnsmasq config, Helmfile, containerd config
   - **`prepare_context()`**: Maps Pydantic models to template context dict
     - Provides template aliases for backwards compatibility (e.g., `services` → `system_workloads`)
     - Exposes scheduling config as nested dict for template access
   - Workload preset loading from `workload_presets.yaml`
   - Auto-generates random passwords for database workloads
   - Handles chart authentication configuration for MySQL, PostgreSQL, MongoDB, RabbitMQ, Valkey

4. **Command Execution** (`loko/runner.py`):
   - `CommandRunner` class: Orchestrates all external commands (kind, kubectl, mkcert, helm, etc.)
   - Manages cluster lifecycle: certificate setup, cluster creation, DNS setup, workload deployment
   - **Field Access**: Uses new paths like `self.env.cluster.provider.runtime`, `self.env.network.domain`
   - **TCP Routes Deployment** (`deploy_tcp_routes()`): Applies Traefik `IngressRouteTCP` manifests for system workloads
     - Called after helmfile sync to ensure Traefik and workload namespaces exist
     - Gracefully handles edge cases (missing file, empty routes)
   - Test app validation for registry and TLS
   - Workload secret extraction from running Kubernetes pods

5. **Version Management** (`loko/updates/`):
   - **Parallel Version Checking**: Fetches Docker and Helm chart versions concurrently for 1.85x speedup
   - **Modules**:
     - `fetchers.py` - Fetches latest versions from Docker Hub and Helm repositories
       - `fetch_latest_docker_version()` - Validates semantic versions using `packaging.version`
       - `fetch_latest_helm_version()` - Fetches and parses Helm index.yaml, filters stable releases only
       - Both return timing information for performance tracking
     - `upgrader.py` - Orchestrates the upgrade process with parallel ThreadPoolExecutor
       - Loads YAML preserving comments (uses `ruamel.yaml`)
       - Creates backup before writing changes
       - Displays timing metrics for Docker and Helm operations separately
     - `yaml_walker.py` - Recursively walks YAML looking for loko-updater comments
       - Handles complex structures (nested maps, lists, dict-based internal-components)
       - Checks both position [2] (after previous key) and dict's ca.comment (start of dict)
       - Tracks processed comments to avoid duplicates
     - `parsers.py` - Parses loko-updater comments
       - Extracts `datasource`, `depName`, `repositoryUrl` from comments
   - **Loko-Updater Comments Format**:
     ```yaml
     # loko-updater: datasource=docker depName=kindest/node
     # loko-updater: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts
     ```
   - **Performance**: Both Docker and Helm version checks run in parallel, showing individual timing in output

6. **Utilities** (`loko/utils.py`):
   - Configuration loading and validation
   - YAML deep merge for combining configurations
   - DNS container name generation
   - Environment summary printing with new config paths

### Templates Directory

- `loko.yaml.example` - Default configuration template with full structure
- `kind/` - Kind cluster configuration templates
- `dnsmasq/` - DNS configuration template
- `helmfile/` - Helmfile template for workload deployment
- `containerd/` - Container runtime configuration
- `workload_presets.yaml` - Port mappings and Helm value presets for common workloads
- `test-app/` - Kubernetes manifests for validation testing
- `traefik-tcp-routes.yaml.j2` - Traefik ingress template for TCP routing

## Configuration Schema (v0.1.0)

The config schema is organized into logical sections:

```yaml
environment:
  name: string
  base-dir: string
  expand-env-vars: boolean

  cluster:                          # Cluster configuration
    provider:
      name: string                  # "kind"
      runtime: string               # "docker" or "podman"
    kubernetes:
      api-port: integer
      image: string
      tag: string
    nodes:
      servers: integer
      workers: integer
      scheduling:
        control-plane:
          allow-workloads: boolean
          isolate-internal-components: boolean
        workers:
          isolate-workloads: boolean
      labels: {}

  network:                          # Network configuration
    ip: string
    domain: string
    dns-port: integer
    subdomain:
      enabled: boolean
      value: string
    lb-ports: [integer]

  internal-components:              # Dict-based (not list)
    traefik:
      version: string
    zot:
      version: string
    dnsmasq:
      version: string
    metrics-server:
      version: string
      enabled: boolean              # Only metrics-server is optional

  registry:
    name: string
    storage:
      size: string
    mirroring:
      enabled: boolean
      sources: []

  workloads:
    use-presets: boolean
    helm-repositories: []           # Moved under workloads
    system: []
    user: []
```

## Common Development Commands

### Setup
```bash
uv sync          # Install dependencies
uv run loko --help
```

### Testing
```bash
# Run unit tests
uv run pytest tests/ --ignore=tests/integration

# Run specific test file
uv run pytest tests/test_config.py -v

# Run with coverage
uv run pytest tests/ --cov=loko --ignore=tests/integration
```

### Linting and Code Quality
```bash
uv run ruff check loko/
uv run ruff format loko/
```

## Key Concepts

### Configuration Overrides
CLI arguments override config file values. The flow is:
1. Load `loko.yaml` (or specified config file)
2. Apply CLI overrides via `_apply_config_overrides()`
3. Update workload enabled/disabled states via `_update_workload_state()`
4. Pass final config to `CommandRunner`

### Workload Management
- **System Workloads**: Pre-configured with presets (MySQL, PostgreSQL, MongoDB, etc.)
  - Defined in config under `workloads.system`
  - Use preset values from `workload_presets.yaml` unless `use-presets: false`
  - Auto-generates passwords, stored in `<base-dir>/<env-name>/workload-secrets.txt`

- **User Workloads**: Custom user-defined workloads
  - Defined in config under `workloads.user`
  - Full Helm chart configuration control

### Loko-Updater Comment Handling
The `config upgrade` command uses loko-updater comments to track component versions:
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
```

**Important**: Uses `ruamel.yaml` to preserve comments while parsing/updating. The `walk_yaml_for_updater()` function handles:
- Comments after previous key (position [2])
- Comments at start of dict (for internal-components structure)
- Tracks processed comments to avoid duplicates

### Environment Variables
- `expand-env-vars: true` in config enables shell variable expansion in paths (e.g., `$HOME`, `$PWD`)
- Used for `base-dir` path resolution
- Loko variables available in helm values: `${ENV_NAME}`, `${LOCAL_DOMAIN}`, `${LOCAL_IP}`, etc.

### Node Scheduling
Scheduling is configured under `cluster.nodes.scheduling`:
- `control-plane.allow-workloads`: Whether to schedule user/system workloads on control plane nodes
- `control-plane.isolate-internal-components`: Forces Traefik/registry/metrics-server to control plane
- `workers.isolate-workloads`: Forces user/system workloads only on worker nodes

### Secrets Management
Loko uses a structured secrets file (`workload-secrets.txt`) to manage workload credentials:
- **Format**: Workloads separated by `---` delimiters for clean parsing
- **Operations**:
  - `fetch_workload_secrets()` - Fetches passwords from deployed workloads, preserves non-password workloads
  - `remove_workload_secrets()` - Removes secrets for undeployed workloads
  - `_parse_secrets_file()` - Parses structured format into workload dictionary
  - `_write_secrets_file()` - Writes workloads with alphabetical sorting and clean delimiters
- **Deduplication**: Updates existing entries instead of appending, prevents duplicates
- **Preservation**: Non-password workloads (garage, custom workloads) are preserved during password fetches
- **Order**: `configure_workloads()` runs before `fetch_workload_secrets()` to ensure all secrets are captured

### Runtime Prerequisite Checks and Error Handling
Commands verify prerequisites BEFORE executing and provide helpful, actionable error messages:
- **Missing Config File**: Guides user to either specify existing config with `--config` or generate new one with `config generate`
- **Docker Not Running**: Clear message to start docker daemon before attempting command
- **Check Order**: Config file check runs first, then docker check (fail-fast approach)
- **Apply to**: All commands that need config: `init`, `create`, `destroy`, `recreate`, `clean`, `start`, `stop`, `status`, `validate`, `secret`, `config upgrade`

## Important Patterns and Details

### Configuration Validation
- Pydantic validates all config on load via `load_config()` in utils
- Invalid configs fail fast with clear error messages
- Field aliases map kebab-case YAML to snake_case Python (critical for compatibility)

### YAML Comment Preservation
When modifying `config upgrade` or parsing logic:
- Use `ruamel.yaml` (not standard `yaml`) to preserve formatting and comments
- CommentedMap and CommentedSeq track comments via `.ca` attribute
- Comment positions: position [0]=before, [1]=first, [2]=after a key
- For dict-based internal-components, also check `data.ca.comment` for comments at start of dict

### Local DNS and Certificates
- DNS runs in a separate container (dnsmasq) created via the container runtime
- Certificates generated via `mkcert` for local CA trust
- DNS resolver file configured at `/etc/resolver/<domain>` (macOS) or `/etc/resolv.conf` (Linux)

### Test App Validation
The `validate` command includes registry + TLS validation:
1. Builds a test image
2. Pushes to local registry
3. Deploys test app to cluster
4. Validates connectivity via HTTPS

## Directory Structure

```
loko/
├── loko/
│   ├── __init__.py
│   ├── cli/                        # Modular CLI system
│   │   ├── __init__.py            # Main app definition and root commands
│   │   ├── commands/              # Command implementations
│   │   │   ├── lifecycle.py       # init, create, destroy, recreate, clean
│   │   │   ├── control.py         # start, stop
│   │   │   ├── status.py          # status, validate
│   │   │   ├── config.py          # config-related commands
│   │   │   ├── workloads.py       # workload list, deploy, undeploy
│   │   │   ├── secrets.py         # secret fetch, show
│   │   │   ├── registry.py        # registry status, list-repos, show-repo, list-tags
│   │   │   ├── utility.py         # version, check-prerequisites
│   │   │   └── completion.py      # shell completion generation (bash, zsh, fish)
│   ├── cli_types.py               # Reusable CLI type definitions (Annotated types)
│   ├── validators.py              # Validation functions (ensure_docker_running, ensure_config_file)
│   ├── config.py                  # Pydantic configuration models
│   ├── generator.py               # Jinja2 template rendering
│   ├── runner.py                  # Command execution orchestration
│   ├── utils.py                   # Utility functions
│   ├── updates/                   # Version management system
│   │   ├── __init__.py
│   │   ├── fetchers.py            # Fetch versions from Docker Hub and Helm repos
│   │   ├── upgrader.py            # Orchestrate parallel version upgrades
│   │   ├── yaml_walker.py         # Traverse YAML for loko-updater comments
│   │   └── parsers.py             # Parse loko-updater comment syntax
│   └── templates/                 # Configuration templates
│       ├── kind/
│       ├── dnsmasq/
│       ├── helmfile/
│       ├── containerd/
│       ├── test-app/
│       ├── loko.yaml.example
│       ├── workload_presets.yaml
│       └── traefik-tcp-routes.yaml.j2
├── tests/                          # Test suite
│   ├── conftest.py                # Pytest fixtures
│   ├── test_config.py             # Config model tests
│   ├── test_generator.py          # Generator tests
│   ├── test_runner.py             # Runner tests
│   ├── test_validators.py         # Validator tests
│   ├── test_upgrader.py           # Version upgrade tests
│   ├── test_yaml_walker.py        # YAML walker tests
│   └── integration/               # Integration tests (require cluster)
├── .mcp.json                       # MCP server configuration
├── pyproject.toml                  # Project metadata and dependencies
├── README.md                       # User documentation
├── CLAUDE.md                       # Architecture guidance for Claude Code
└── uv.lock                         # Dependency lock file
```

## Development Notes

### Adding New Commands
1. Add command function to appropriate file in `loko/cli/commands/`
2. Register with `@app.command()` or appropriate subcommand group
3. Use Annotated types from `cli_types.py` for CLI arguments
4. Add validation calls (ensure_config_file, ensure_docker_running, etc.)

### Modifying Configuration Schema
1. Update Pydantic models in `config.py`
2. Update template example in `loko.yaml.example`
3. Update `prepare_context()` in `generator.py` to map new fields
4. Update field access in `runner.py` and CLI commands
5. Update workload preset file if applicable
6. Update tests with new config structure
7. Update CLAUDE.md and README.md documentation

### Template Changes
- Templates use Jinja2 with custom `to_yaml` filter
- ConfigGenerator sets up environment with trim_blocks and lstrip_blocks
- Templates access config via context dict from `prepare_context()`
- Template aliases maintained for backwards compatibility

### Testing Workload Deployment
The codebase relies on Kind + Helm + Helmfile for workload deployment. Key interaction points:
- `runner.deploy_workloads()` calls helmfile
- Workload secrets extracted via kubectl from deployed pods
- Uses Helm repositories defined in `workloads.helm-repositories` config list

## Important Files and Their Roles

- `pyproject.toml`: Entry point is `loko.cli:app`
- `loko/templates/loko.yaml.example`: Template all new configs should match
- `loko/templates/workload_presets.yaml`: Defines port and values presets for system workloads
- `loko/utils.py`: Contains `load_config()` - critical for config initialization
- `loko/config.py`: All Pydantic models - source of truth for config schema

## MCP Servers Configuration

MCPs (Model Context Protocol servers) enhance Claude Code's capabilities when working with Loko. Configuration is managed via `.mcp.json` in the project root.

### Configured MCPs

**File: `.mcp.json`**

```json
{
  "mcpServers": {
    "git": {
      "command": "git"
    },
    "docker": {
      "command": "docker"
    },
    "kubernetes": {
      "command": "kubectl"
    },
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"]
    },
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/sequential-thinking"]
    }
  }
}
```

### MCP Server Descriptions

1. **Git MCP** (`git`)
   - Repository operations: status, diffs, commits, history
   - Essential for: Understanding changes, reviewing code, version control
   - Usage patterns: `git status`, `git diff`, `git log --oneline`

2. **Docker MCP** (`docker`)
   - Docker operations: inspect containers, check daemon status
   - Useful for: Verifying docker is running, inspecting Kind cluster nodes
   - Operations: List containers, inspect networks, check image status

3. **Kubernetes MCP** (`kubernetes`)
   - kubectl operations: query clusters, inspect resources
   - Useful for: Checking cluster status, inspecting deployed workloads, viewing pods
   - Operations: Get clusters, inspect namespaces, view ingresses, check workloads

4. **Context7 MCP** (`context7`)
   - Fetches up-to-date library documentation from official sources (PyPI, npm, GitHub, etc.)
   - Useful for: Getting current API references, version-specific documentation
   - Usage: Add `use context7` to your prompt to fetch current docs

5. **Sequential-Thinking MCP** (`sequential-thinking`)
   - Enables step-by-step reasoning for complex problems
   - Useful for: Planning architecture, debugging complex issues, design reviews
   - Usage: Use for multi-step problem analysis and design decisions

### Common MCP Usage Patterns for Loko

- **Git**: Review changes, understand commit history, check status
- **Docker**: Verify daemon running, inspect Kind cluster state
- **Kubernetes**: Query deployed workloads, check resource health, verify ingress config
- **Context7**: Fetch latest docs for dependencies when updating versions
- **Sequential-Thinking**: Plan complex features, review architecture decisions
