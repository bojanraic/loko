# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Loko** is a Python CLI tool for managing local Kubernetes development environments using Kind. It automates cluster setup, DNS configuration, TLS certificates, local container registry, and service deployment via Helm.

**Key Dependencies:**
- `typer` - CLI framework
- `pydantic` - Configuration validation and parsing
- `ruamel.yaml` - YAML parsing with comment preservation (important for renovate comments)
- `jinja2` - Template rendering for configuration generation
- `rich` - Terminal output formatting

## Architecture

### Core Components

1. **CLI Layer** (`loko/cli/`):
   - Modular CLI architecture using Typer framework
   - Entry point: `loko/cli/__init__.py` with main `app` (Typer instance)
   - Subcommand groups: `config_app`, `service_app`, `secret_app` for grouped commands
   - **Command Organization** (`loko/cli/commands/`):
     - `lifecycle.py` - `init`, `create`, `destroy`, `recreate`, `clean` commands
     - `control.py` - `start`, `stop` commands
     - `status.py` - `status`, `validate` commands
     - `config.py` - `generate-config`, `config upgrade`, `config helm-repo-add`, `config helm-repo-remove` commands
     - `services.py` - `service list`, `service deploy`, `service undeploy` commands
     - `secrets.py` - `secret fetch`, `secret show` commands
     - `utility.py` - `version`, `check-prerequisites` commands
   - **CLI Type Definitions** (`loko/cli_types.py`):
     - Reusable `Annotated` type definitions for CLI arguments
     - Examples: `ConfigArg`, `NameArg`, `DomainArg`, `WorkersArg`, etc.
     - Ensures consistency across commands with shared argument definitions
   - **Runtime prerequisite checks** (`loko/validators.py`):
     - `ensure_docker_running()` - Ensures docker daemon is accessible
     - `ensure_config_file()` - Ensures config file exists
     - `ensure_ports_available()` - Validates DNS, LB, and service ports before cluster creation
     - Provides helpful error messages guiding users to solutions
   - **Help system**: Supports both `-h` and `--help` via `context_settings={"help_option_names": ["-h", "--help"]}`
   - **Shell Completion**: Uses Typer's built-in completion system (`add_completion=True`)
     - Auto-detects current shell (bash, zsh, fish, powershell)
     - Users run `loko --install-completion` to install completion
     - Users run `loko --show-completion` to view completion script

2. **Configuration** (`loko/config.py`):
   - Pydantic models defining the configuration schema
   - Key models: `RootConfig`, `EnvironmentConfig`, `NodesConfig`, `KubernetesConfig`, `ServicesConfig`, `HelmRepoConfig`
   - Uses field aliases (e.g., `api_port` → `api-port`) for YAML kebab-case naming
   - **Important**: Uses `allow_scheduling_on_control_plane`, `internal_components_on_control_plane` boolean flags for node scheduling control

3. **Configuration Generation** (`loko/generator.py`):
   - `ConfigGenerator` class: Renders Jinja2 templates to generate Kind cluster config, dnsmasq config, Helmfile, containerd config
   - Service preset loading from `service_presets.yaml`
   - Auto-generates random passwords for database services
   - Handles chart authentication configuration for MySQL, PostgreSQL, MongoDB, RabbitMQ, Valkey

4. **Command Execution** (`loko/runner.py`):
   - `CommandRunner` class: Orchestrates all external commands (kind, kubectl, mkcert, helm, etc.)
   - Manages cluster lifecycle: certificate setup, cluster creation, DNS setup, service deployment
   - **TCP Routes Deployment** (`deploy_tcp_routes()`): Applies Traefik `IngressRouteTCP` manifests for system services
     - Called after helmfile sync to ensure Traefik and service namespaces exist
     - Gracefully handles edge cases (missing file, empty routes)
   - Test app validation for registry and TLS
   - Service secret extraction from running Kubernetes pods

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
     - `yaml_walker.py` - Recursively walks YAML looking for Renovate comments
       - Handles complex structures (nested maps, lists)
       - Tracks processed comments to avoid duplicates
     - `parsers.py` - Parses Renovate-style comments
       - Extracts `datasource`, `depName`, `repositoryUrl` from comments
   - **Renovate Comments Format**:
     ```yaml
     # renovate: datasource=docker depName=kindest/node
     # renovate: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts
     ```
   - **Performance**: Both Docker and Helm version checks run in parallel, showing individual timing in output

6. **Utilities** (`loko/utils.py`):
   - Configuration loading and validation
   - YAML deep merge for combining configurations
   - DNS container name generation

### Templates Directory

- `loko.yaml.example` - Default configuration template with full structure
- `kind/` - Kind cluster configuration templates
- `dnsmasq/` - DNS configuration template
- `helmfile/` - Helmfile template for service deployment
- `containerd/` - Container runtime configuration
- `service_presets.yaml` - Port mappings and Helm value presets for common services
- `test-app/` - Kubernetes manifests for validation testing
- `traefik-tcp-routes.yaml.j2` - Traefik ingress template for TCP routing

## Common Development Commands

### Setup
```bash
uv sync          # Install dependencies
uv run loko --help
```

### Testing
```bash
# Check prerequisites
uv run loko check-prerequisites

# Generate a default config
uv run loko generate-config

# Run a single command
uv run loko init --config loko.yaml
uv run loko create --config loko.yaml
```

### Linting and Code Quality
```bash
# Format check (if configured with black/ruff)
uv run ruff check loko/
uv run ruff format loko/
```

## Key Concepts

### Configuration Overrides
CLI arguments override config file values. The flow is:
1. Load `loko.yaml` (or specified config file)
2. Apply CLI overrides via `_apply_config_overrides()`
3. Update service enabled/disabled states via `_update_service_state()`
4. Pass final config to `CommandRunner`

### Service Management
- **System Services**: Pre-configured with presets (MySQL, PostgreSQL, MongoDB, etc.)
  - Defined in config under `services.system`
  - Use preset values from `service_presets.yaml` unless `use-service-presets: false`
  - Auto-generates passwords, stored in `<base-dir>/<env-name>/service-secrets.txt`

- **User Services**: Custom user-defined services
  - Defined in config under `services.user`
  - Full Helm chart configuration control

### Renovate Comment Handling
The `config upgrade` command uses Renovate-style comments to track component versions:
```yaml
kubernetes:
  image: kindest/node
  # renovate: datasource=docker depName=kindest/node
  tag: v1.34.0
```

**Important**: Uses `ruamel.yaml` to preserve comments while parsing/updating. The `_walk_yaml_for_renovate()` function handles complex YAML structures (nested maps, lists) and tracks processed comments to avoid duplicates.

### Environment Variables
- `expand-env-vars: true` in config enables shell variable expansion in paths (e.g., `$HOME`, `$PWD`)
- Used for `base-dir` path resolution

### Node Scheduling
- `allow-scheduling-on-control-plane`: Whether to schedule workloads on control plane nodes
- `internal-components-on-control-plane`: Forces infrastructure components (Traefik, registry) on control plane
- `run-services-on-workers-only`: Forces application services only on worker nodes

### Secrets Management
Loko uses a structured secrets file (`service-secrets.txt`) to manage service credentials:
- **Format**: Services separated by `---` delimiters for clean parsing
- **Operations**:
  - `fetch_service_secrets()` - Fetches passwords from deployed services, preserves non-password services
  - `remove_service_secrets()` - Removes secrets for undeployed services
  - `_parse_secrets_file()` - Parses structured format into service dictionary
  - `_write_secrets_file()` - Writes services with alphabetical sorting and clean delimiters
- **Deduplication**: Updates existing entries instead of appending, prevents duplicates
- **Preservation**: Non-password services (garage, custom services) are preserved during password fetches
- **Order**: `configure_services()` runs before `fetch_service_secrets()` to ensure all secrets are captured

### Runtime Prerequisite Checks and Error Handling
Commands verify prerequisites BEFORE executing and provide helpful, actionable error messages:
- **Missing Config File**: Guides user to either specify existing config with `--config` or generate new one with `generate-config`
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

### Local DNS and Certificates
- DNS runs in a separate container (dnsmasq) created via the container runtime
- Certificates generated via `mkcert` for local CA trust
- DNS resolver file configured at `/etc/resolver/<local-domain>` (macOS) or `/etc/resolv.conf` (Linux)

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
│   │   │   ├── services.py        # service list, deploy, undeploy
│   │   │   ├── secrets.py         # secret fetch, show
│   │   │   └── utility.py         # version, check-prerequisites
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
│   │   ├── yaml_walker.py         # Traverse YAML for Renovate comments
│   │   └── parsers.py             # Parse Renovate comment syntax
│   └── templates/                 # Configuration templates
│       ├── kind/
│       ├── dnsmasq/
│       ├── helmfile/
│       ├── containerd/
│       ├── test-app/
│       ├── loko.yaml.example
│       ├── service_presets.yaml
│       └── traefik-tcp-routes.yaml.j2
├── .mcp.json                       # MCP server configuration (git, docker, kubectl, context7, sequential-thinking)
├── pyproject.toml                  # Project metadata and dependencies
├── README.md                       # User documentation
├── CLAUDE.md                       # Architecture guidance for Claude Code
└── uv.lock                         # Dependency lock file
```

## Development Notes

### Adding New Commands
1. Add command function to `cli.py` decorated with `@app.command()` or `@config_app.command()`
2. Use Annotated types for CLI arguments with typer.Option
3. Extract common overrides pattern into `_apply_config_overrides()`

### Modifying Configuration Schema
1. Update Pydantic model in `config.py`
2. Update template example in `loko.yaml.example`
3. Update service preset file if applicable
4. Consider CLI overrides needed in `cli.py`

### Template Changes
- Templates use Jinja2 with custom `to_yaml` filter
- ConfigGenerator sets up environment with trim_blocks and lstrip_blocks
- Templates access config via `config.environment` (Pydantic object converted to context dict)

### Testing Service Deployment
The codebase relies on Kind + Helm + Helmfile for service deployment. Key interaction points:
- `runner.deploy_services()` calls helmfile
- Service secrets extracted via kubectl from deployed pods
- Uses Helm repositories defined in `helm-repositories` config list

## Important Files and Their Roles

- `pyproject.toml`: Entry point is `loko.cli:app`
- `loko/templates/loko.yaml.example`: Template all new configs should match
- `loko/templates/service_presets.yaml`: Defines port and values presets for system services
- `loko/utils.py`: Contains `load_config()` - critical for config initialization

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
   - Useful for: Checking cluster status, inspecting deployed services, viewing pods
   - Operations: Get clusters, inspect namespaces, view ingresses, check services

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
- **Kubernetes**: Query deployed services, check resource health, verify ingress config
- **Context7**: Fetch latest docs for dependencies when updating versions
- **Sequential-Thinking**: Plan complex features, review architecture decisions
