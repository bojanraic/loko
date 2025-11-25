"""CLI type definitions and annotations for loko commands.

This module defines reusable CLI argument types using Annotated types from
typing_extensions and Typer options. These definitions ensure consistency
across all commands and reduce code duplication.

Annotated types allow combining type information with metadata (via typer.Option).
This pattern provides:
- Type safety and IDE autocompletion
- Consistent help text and defaults across commands
- DRY principle (Don't Repeat Yourself)
- Easy updates to argument definitions (one place)

Example usage in a command:
    @app.command()
    def my_command(
        config: ConfigArg = "loko.yaml",
        workers: WorkersArg = None,
        domain: DomainArg = None
    ):
        \"\"\"Do something with loko.\"\"\"
        ...

This is much cleaner than repeating typer.Option definitions in each command.
"""
from typing import List, Optional
from pathlib import Path
from typing_extensions import Annotated
import typer

# Common config argument
ConfigArg = Annotated[
    str,
    typer.Option(
        "--config", "-c",
        help="Path to configuration file",
        show_default=True
    )
]

TemplatesDirArg = Annotated[
    Optional[Path],
    typer.Option(
        "--templates-dir", "-t",
        help="Path to custom templates directory",
        show_default=False
    )
]

# CLI Overrides
NameArg = Annotated[Optional[str], typer.Option("--name", help="Override environment name")]
DomainArg = Annotated[Optional[str], typer.Option("--domain", help="Override local domain")]
WorkersArg = Annotated[Optional[int], typer.Option("--workers", help="Override number of worker nodes")]
ControlPlanesArg = Annotated[Optional[int], typer.Option("--control-planes", help="Override number of control plane nodes")]
RuntimeArg = Annotated[Optional[str], typer.Option("--runtime", help="Override container runtime")]
LocalIPArg = Annotated[Optional[str], typer.Option("--local-ip", help="Override local IP address")]
K8sVersionArg = Annotated[Optional[str], typer.Option("--k8s-version", help="Override Kubernetes node image tag")]
LBPortsArg = Annotated[Optional[List[int]], typer.Option("--lb-port", help="Override load balancer ports")]
AppsSubdomainArg = Annotated[Optional[str], typer.Option("--apps-subdomain", help="Override apps subdomain")]
ServicePresetsArg = Annotated[Optional[bool], typer.Option("--service-presets/--no-service-presets", help="Enable/disable service presets")]
MetricsServerArg = Annotated[Optional[bool], typer.Option("--metrics-server/--no-metrics-server", help="Enable/disable metrics server")]
EnableServiceArg = Annotated[Optional[List[str]], typer.Option("--enable-service", help="Enable a system service")]
DisableServiceArg = Annotated[Optional[List[str]], typer.Option("--disable-service", help="Disable a system service")]
BaseDirArg = Annotated[Optional[str], typer.Option("--base-dir", help="Override base directory")]
ExpandVarsArg = Annotated[Optional[bool], typer.Option("--expand-vars/--no-expand-vars", help="Enable/disable environment variable expansion")]
K8sAPIPortArg = Annotated[Optional[int], typer.Option("--k8s-api-port", help="Override Kubernetes API port")]
ScheduleOnControlArg = Annotated[Optional[bool], typer.Option("--schedule-on-control/--no-schedule-on-control", help="Allow scheduling on control plane nodes")]
InternalOnControlArg = Annotated[Optional[bool], typer.Option("--internal-on-control/--no-internal-on-control", help="Force internal components on control plane")]
RegistryNameArg = Annotated[Optional[str], typer.Option("--registry-name", help="Override registry name")]
RegistryStorageArg = Annotated[Optional[str], typer.Option("--registry-storage", help="Override registry storage size")]
ServicesOnWorkersArg = Annotated[Optional[bool], typer.Option("--services-on-workers/--no-services-on-workers", help="Force services to run on workers only")]
