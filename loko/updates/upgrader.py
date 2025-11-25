"""Configuration upgrade functionality.

This module orchestrates the version upgrade process for loko configurations.
It parses Renovate-style comments in YAML files to identify components that
need version checking, fetches the latest versions in parallel, and updates
the configuration while preserving YAML formatting and comments.

Key features:
- Parallel fetching of Docker and Helm versions (1.85x faster)
- Preserves YAML comments and formatting using ruamel.yaml
- Automatic backup creation before modifications
- Separate timing metrics for Docker and Helm operations
- Graceful error handling with helpful messages

Typical workflow:
1. Load config file with comment preservation
2. Walk YAML structure to find Renovate comments
3. Submit all version checks to ThreadPoolExecutor (max_workers=5)
4. Process results as they complete
5. Create backup and write updated config
6. Display summary with timing information
"""
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from ruamel.yaml import YAML
from .yaml_walker import walk_yaml_for_renovate
from .fetchers import fetch_latest_version

console = Console()


def upgrade_config(config_file: str) -> None:
    """
    Upgrade component versions in config file by checking renovate comments.

    This function reads renovate-style comments in the config file and queries
    the appropriate datasources (Docker Hub, Helm repositories) to find the
    latest versions of components.
    """
    console.print("[bold blue]Upgrading component versions...[/bold blue]\n")

    try:
        # Load YAML with comment preservation
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.default_flow_style = False

        with open(config_file, 'r') as f:
            data = yaml.load(f)

        # Find all renovate comments and their associated values
        updates_to_check = []
        walk_yaml_for_renovate(data, updates_to_check)

        if not updates_to_check:
            console.print("[green]✅ No components to check[/green]")
            return

        # Fetch versions in parallel
        updates_made = []
        helm_timing = 0.0
        docker_timing = 0.0
        total_fetch_time = time.time()

        with ThreadPoolExecutor(max_workers=5) as executor:
            # Submit all fetch tasks
            future_to_info = {}
            for path, key, renovate_info, current_value, parent in updates_to_check:
                future = executor.submit(fetch_latest_version, renovate_info)
                future_to_info[future] = (path, key, renovate_info, current_value, parent)
                console.print(f"🔍 Checking {renovate_info['depName']} ({renovate_info['datasource']})...")

            # Process results as they complete
            for future in as_completed(future_to_info):
                path, key, renovate_info, current_value, parent = future_to_info[future]
                try:
                    latest_version, fetch_time = future.result()

                    # Track timing by datasource
                    if renovate_info['datasource'] == 'helm':
                        helm_timing += fetch_time
                    elif renovate_info['datasource'] == 'docker':
                        docker_timing += fetch_time

                    if latest_version and str(current_value) != latest_version:
                        # Update the value in the YAML structure
                        parent[key] = latest_version
                        updates_made.append(f"  {renovate_info['depName']}: {current_value} → {latest_version}")
                except Exception as e:
                    console.print(f"[yellow]Error fetching version for {renovate_info['depName']}: {e}[/yellow]")

        total_fetch_time = time.time() - total_fetch_time

        if updates_made:
            console.print("\n[bold green]Updates found:[/bold green]")
            for update in updates_made:
                console.print(update)

            # Create backup before writing changes
            backup_file = config_file.rsplit('.', 1)[0] + '-prev.' + config_file.rsplit('.', 1)[1]
            shutil.copy(config_file, backup_file)
            console.print(f"\n💾 Backup created: {backup_file}")

            # Write updated config back
            with open(config_file, 'w') as f:
                yaml.dump(data, f)

            console.print(f"✅ Updated {len(updates_made)} version(s) in {config_file}")
        else:
            console.print("[green]✅ All versions are up to date[/green]")

        # Print timing information
        timing_msg = f"\n[dim]⏱️  Total fetch time: {total_fetch_time:.2f}s"
        if docker_timing > 0:
            timing_msg += f" (Docker: {docker_timing:.2f}s"
            if helm_timing > 0:
                timing_msg += f", Helm: {helm_timing:.2f}s"
            timing_msg += ")"
        elif helm_timing > 0:
            timing_msg += f" (Helm: {helm_timing:.2f}s)"
        timing_msg += "[/dim]"
        console.print(timing_msg)

    except Exception as e:
        console.print(f"[red]Error upgrading config: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
