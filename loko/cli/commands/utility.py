"""Utility commands: version, check-prerequisites."""
import subprocess
import sys
from importlib.metadata import metadata
from rich.console import Console


console = Console()


def version() -> None:
    """
    Print the current version of loko.
    """
    try:
        meta = metadata('loko-k8s')
        ver = meta.get('Version')
        console.print(ver)
    except Exception:
        console.print("version not found")
        sys.exit(1)


def check_prerequisites() -> None:
    """
    Check if all required tools are installed.
    """
    console.print("[bold blue]Checking prerequisites...[/bold blue]\n")

    tools = {
        "docker": {
            "cmd": ["docker", "--version"],
            "required": True,
            "description": "Docker (container runtime)",
            "install_url": "https://docs.docker.com/get-docker/"
        },
        "kind": {
            "cmd": ["kind", "version"],
            "required": True,
            "description": "Kind (Kubernetes in Docker)",
            "install_url": "https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
        },
        "mkcert": {
            "cmd": ["mkcert", "-version"],
            "required": True,
            "description": "mkcert (local certificate authority)",
            "install_url": "https://github.com/FiloSottile/mkcert#installation"
        },
        "helmfile": {
            "cmd": ["helmfile", "--version"],
            "required": False,
            "description": "Helmfile (declarative Helm releases)",
            "install_url": "https://github.com/helmfile/helmfile#installation"
        },
        "helm": {
            "cmd": ["helm", "version", "--short"],
            "required": True,
            "description": "Helm (package manager for Kubernetes)",
            "install_url": "https://helm.sh/docs/intro/install/"
        },
        "kubectl": {
            "cmd": ["kubectl", "version", "--client"],
            "required": False,
            "description": "kubectl (Kubernetes CLI)",
            "install_url": "https://kubernetes.io/docs/tasks/tools/"
        }
    }

    results = {}
    runtime_found = False

    for tool_name, tool_info in tools.items():
        try:
            result = subprocess.run(
                tool_info["cmd"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                results[tool_name] = True
                console.print(f"✅ {tool_info['description']}: [green]installed[/green]")
                if tool_name in ["docker", "podman"]:
                    runtime_found = True
            else:
                results[tool_name] = False
                if tool_info["required"]:
                    console.print(f"❌ {tool_info['description']}: [red]not found[/red]")
                    console.print(f"   Install: {tool_info['install_url']}")
                else:
                    console.print(f"⚠️  {tool_info['description']}: [yellow]not found (optional)[/yellow]")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            results[tool_name] = False
            if tool_info["required"]:
                console.print(f"❌ {tool_info['description']}: [red]not found[/red]")
                console.print(f"   Install: {tool_info['install_url']}")
            else:
                console.print(f"⚠️  {tool_info['description']}: [yellow]not found (optional)[/yellow]")

    # Check if at least one container runtime is available
    if not runtime_found:
        console.print("\n[bold red]Error: No container runtime found![/bold red]")
        console.print("Please install either Docker or Podman:")
        console.print(f"  - Docker: {tools['docker']['install_url']}")
        console.print(f"  - Podman: {tools['podman']['install_url']}")

    # Summary
    console.print("\n[bold]Summary:[/bold]")
    required_tools = [name for name, info in tools.items() if info["required"]]
    required_installed = sum(1 for name in required_tools if results.get(name, False))

    if runtime_found and required_installed >= len([t for t in required_tools if t not in ["docker", "podman"]]) + 1:
        console.print("[bold green]✅ All required tools are installed![/bold green]")

        # Additional note about NSS/libnss for certificate trust
        console.print("\n[bold]Additional Requirements:[/bold]")
        console.print("📝 [yellow]NSS/libnss[/yellow] - Required for trusting self-signed certificates in browsers")
        console.print("   mkcert uses NSS to install certificates in Firefox and other browsers")
        console.print("   Install via package manager:")
        console.print("     • Ubuntu/Debian: [cyan]sudo apt install libnss3-tools[/cyan]")
        console.print("     • Fedora/RHEL: [cyan]sudo dnf install nss-tools[/cyan]")
        console.print("     • Arch: [cyan]sudo pacman -S nss[/cyan]")
        console.print("     • macOS: NSS is included with Firefox")
        console.print("   Without NSS, mkcert will only work for system-wide cert stores (Chrome, curl)")

        return
    else:
        console.print("[bold red]❌ Some required tools are missing.[/bold red]")
        console.print("Please install the missing tools before using loko.")
        sys.exit(1)
