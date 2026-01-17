"""Shell completion command."""
import sys
from enum import Enum

import typer
from click.shell_completion import get_completion_class
from rich.console import Console

console = Console()


class Shell(str, Enum):
    """Supported shells for completion."""
    bash = "bash"
    zsh = "zsh"
    fish = "fish"


def completion(shell: Shell) -> None:
    """
    Generate shell completion script.

    Output completion script for the specified shell. The script should be
    sourced in your shell configuration file.

    Usage:
        # For bash (~/.bashrc)
        source <(loko completion bash)

        # For zsh (~/.zshrc)
        source <(loko completion zsh)

        # For fish (~/.config/fish/config.fish)
        loko completion fish | source
    """
    # Get Click's completion class for the shell
    comp_cls = get_completion_class(shell.value)
    if comp_cls is None:
        console.print(f"[red]Unsupported shell: {shell.value}[/red]", file=sys.stderr)
        raise typer.Exit(1)

    # We need a Click command to generate the script
    # Import here to avoid circular imports
    from loko.cli import app
    cmd = typer.main.get_command(app)

    # Create completion instance and output the source script
    comp = comp_cls(cmd, {}, "loko", "_LOKO_COMPLETE")
    print(comp.source())
