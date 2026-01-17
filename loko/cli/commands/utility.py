"""Utility commands: version, check-prerequisites."""
import os
import shutil
import subprocess
import sys
from importlib.metadata import metadata

from rich.console import Console
from rich.prompt import Confirm


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


def _is_mise_available() -> tuple[bool, bool]:
    """
    Check if mise is installed and activated.

    Returns:
        Tuple of (is_installed, is_activated)
    """
    is_installed = shutil.which("mise") is not None
    if not is_installed:
        return False, False

    # Check if mise is activated in the current shell
    is_activated = bool(os.environ.get("MISE_SHELL") or os.environ.get("__MISE_WATCH"))
    return is_installed, is_activated


def _install_via_mise(tool: str) -> bool:
    """
    Install a tool via mise and activate it globally.

    Args:
        tool: Tool name to install (e.g., "kind", "helm")

    Returns:
        True if installation succeeded
    """
    try:
        # Use 'mise use -g' to install AND activate globally
        # 'mise install' only downloads but doesn't activate
        result = subprocess.run(
            ["mise", "use", "-g", f"{tool}@latest"],
            capture_output=True,
            text=True,
            timeout=120
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_prerequisites() -> None:
    """
    Check if all required tools are installed.
    """
    console.print("[bold blue]Checking prerequisites...[/bold blue]\n")

    # Tools that can be installed via mise
    mise_installable = {"kind", "helm", "kubectl", "mkcert", "helmfile"}

    tools = {
        "docker": {
            "cmd": ["docker", "--version"],
            "required": True,
            "description": "Docker (container runtime)",
            "install_url": "https://docs.docker.com/get-docker/",
        },
        "kind": {
            "cmd": ["kind", "version"],
            "required": True,
            "description": "Kind (Kubernetes in Docker)",
            "install_url": "https://kind.sigs.k8s.io/docs/user/quick-start/#installation",
        },
        "mkcert": {
            "cmd": ["mkcert", "-version"],
            "required": True,
            "description": "mkcert (local certificate authority)",
            "install_url": "https://github.com/FiloSottile/mkcert#installation",
        },
        "helmfile": {
            "cmd": ["helmfile", "--version"],
            "required": True,
            "description": "Helmfile (declarative Helm releases)",
            "install_url": "https://github.com/helmfile/helmfile#installation",
        },
        "helm": {
            "cmd": ["helm", "version", "--short"],
            "required": True,
            "description": "Helm (package manager for Kubernetes)",
            "install_url": "https://helm.sh/docs/intro/install/",
        },
        "kubectl": {
            "cmd": ["kubectl", "version", "--client"],
            "required": True,
            "description": "kubectl (Kubernetes CLI)",
            "install_url": "https://kubernetes.io/docs/tasks/tools/",
        },
        "mise": {
            "cmd": ["mise", "--version"],
            "required": False,
            "description": "Mise (tool version manager)",
            "install_url": "https://mise.jdx.dev/getting-started.html",
        },
    }

    # Check all tools
    results = {}
    for tool_name, tool_info in tools.items():
        try:
            result = subprocess.run(
                tool_info["cmd"],
                capture_output=True,
                text=True,
                timeout=5
            )
            results[tool_name] = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            results[tool_name] = False

    # Display results
    for tool_name, tool_info in tools.items():
        if results[tool_name]:
            if tool_info["required"]:
                console.print(f"✅ {tool_info['description']}: [green]installed[/green]")
            else:
                console.print(f"✅ {tool_info['description']}: [green]installed[/green] [dim](optional)[/dim]")
        else:
            if tool_info["required"]:
                console.print(f"❌ {tool_info['description']}: [red]not found[/red]")
                console.print(f"   Install: {tool_info['install_url']}")
            else:
                console.print(f"⚠️  {tool_info['description']}: [yellow]not found[/yellow] [dim](optional)[/dim]")

    # Check for missing tools that can be installed via mise
    missing_tools = [
        name for name, info in tools.items()
        if not results[name] and info["required"] and name in mise_installable
    ]

    # If tools are missing and mise is available, offer to install
    if missing_tools:
        mise_installed, mise_activated = _is_mise_available()

        if mise_installed and mise_activated:
            console.print()
            if Confirm.ask(
                f"[cyan]Install missing tools via mise?[/cyan] ({', '.join(missing_tools)})",
                default=True
            ):
                console.print()
                for tool in missing_tools:
                    console.print(f"Installing {tool}...", end=" ")
                    if _install_via_mise(tool):
                        console.print("[green]done[/green]")
                        results[tool] = True
                    else:
                        console.print("[red]failed[/red]")
        elif mise_installed and not mise_activated:
            console.print()
            console.print("[yellow]Tip: Mise is installed but not activated in your shell.[/yellow]")
            console.print("   Activate it to enable automatic tool installation:")
            shell = os.environ.get("SHELL", "")
            if "zsh" in shell:
                console.print("   [cyan]echo 'eval \"$(mise activate zsh)\"' >> ~/.zshrc && source ~/.zshrc[/cyan]")
            elif "fish" in shell:
                console.print("   [cyan]echo 'mise activate fish | source' >> ~/.config/fish/config.fish[/cyan]")
            else:
                console.print("   [cyan]echo 'eval \"$(mise activate bash)\"' >> ~/.bashrc && source ~/.bashrc[/cyan]")

    # Check if at least one container runtime is available
    if not results.get("docker", False):
        console.print("\n[bold red]Error: No container runtime found![/bold red]")
        console.print("Please install Docker:")
        console.print(f"  - Docker: {tools['docker']['install_url']}")

    # Summary
    console.print("\n[bold]Summary:[/bold]")
    required_tools = [name for name, info in tools.items() if info["required"]]
    all_required_installed = all(results.get(name, False) for name in required_tools)

    if all_required_installed:
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
