"""Utility commands: version, check-prerequisites."""
import shutil
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


def _install_via_mise(tool_name: str, mise_tool: str) -> bool:
    """
    Attempt to install a tool using mise.

    Args:
        tool_name: Human-readable tool name for display
        mise_tool: Mise tool identifier (e.g., "kind", "helm")

    Returns:
        True if installation succeeded, False otherwise
    """
    console.print(f"   [cyan]Installing {tool_name} via mise...[/cyan]")
    try:
        result = subprocess.run(
            ["mise", "install", mise_tool],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            console.print(f"   [green]✅ {tool_name} installed successfully[/green]")
            return True
        else:
            console.print(f"   [red]Failed to install {tool_name}: {result.stderr}[/red]")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        console.print(f"   [red]Failed to install {tool_name}: {e}[/red]")
        return False


def check_prerequisites(install: bool = False) -> None:
    """
    Check if all required tools are installed.

    Args:
        install: If True, attempt to install missing tools via mise
    """
    console.print("[bold blue]Checking prerequisites...[/bold blue]\n")

    # Check if mise is available when install flag is used
    mise_available = False
    if install:
        mise_available = shutil.which("mise") is not None
        if not mise_available:
            console.print("[yellow]⚠️  Mise not found. Install mise first to use --install flag:[/yellow]")
            console.print("   https://mise.jdx.dev/getting-started.html")
            console.print()

    tools = {
        "docker": {
            "cmd": ["docker", "--version"],
            "required": True,
            "description": "Docker (container runtime)",
            "install_url": "https://docs.docker.com/get-docker/",
            "mise_tool": None  # Docker requires system install
        },
        "kind": {
            "cmd": ["kind", "version"],
            "required": True,
            "description": "Kind (Kubernetes in Docker)",
            "install_url": "https://kind.sigs.k8s.io/docs/user/quick-start/#installation",
            "mise_tool": "kind"
        },
        "mkcert": {
            "cmd": ["mkcert", "-version"],
            "required": True,
            "description": "mkcert (local certificate authority)",
            "install_url": "https://github.com/FiloSottile/mkcert#installation",
            "mise_tool": "mkcert"
        },
        "helmfile": {
            "cmd": ["helmfile", "--version"],
            "required": False,
            "description": "Helmfile (declarative Helm releases)",
            "install_url": "https://github.com/helmfile/helmfile#installation",
            "mise_tool": "helmfile"
        },
        "helm": {
            "cmd": ["helm", "version", "--short"],
            "required": True,
            "description": "Helm (package manager for Kubernetes)",
            "install_url": "https://helm.sh/docs/intro/install/",
            "mise_tool": "helm"
        },
        "kubectl": {
            "cmd": ["kubectl", "version", "--client"],
            "required": False,
            "description": "kubectl (Kubernetes CLI)",
            "install_url": "https://kubernetes.io/docs/tasks/tools/",
            "mise_tool": "kubectl"
        }
    }

    results = {}
    runtime_found = False

    for tool_name, tool_info in tools.items():
        tool_found = False
        try:
            result = subprocess.run(
                tool_info["cmd"],
                capture_output=True,
                text=True,
                timeout=5
            )
            tool_found = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            tool_found = False

        if tool_found:
            results[tool_name] = True
            console.print(f"✅ {tool_info['description']}: [green]installed[/green]")
            if tool_name in ["docker", "podman"]:
                runtime_found = True
        else:
            # Tool not found - try to install if --install flag is set
            installed = False
            if install and mise_available and tool_info.get("mise_tool"):
                installed = _install_via_mise(tool_info['description'], tool_info['mise_tool'])

            if installed:
                results[tool_name] = True
                if tool_name in ["docker", "podman"]:
                    runtime_found = True
            else:
                results[tool_name] = False
                if tool_info["required"]:
                    console.print(f"❌ {tool_info['description']}: [red]not found[/red]")
                    if not install:
                        console.print(f"   Install: {tool_info['install_url']}")
                        if tool_info.get("mise_tool"):
                            console.print(f"   Or run: [cyan]loko check-prerequisites --install[/cyan]")
                else:
                    console.print(f"⚠️  {tool_info['description']}: [yellow]not found (optional)[/yellow]")

    # Check if at least one container runtime is available
    if not runtime_found:
        console.print("\n[bold red]Error: No container runtime found![/bold red]")
        console.print("Please install Docker:")
        console.print(f"  - Docker: {tools['docker']['install_url']}")

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
