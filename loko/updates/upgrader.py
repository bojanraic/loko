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
from .fetchers import fetch_latest_version, fetch_latest_helm_versions_batch

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
            # Group updates by datasource
            docker_updates = []
            helm_updates_by_repo = {}  # repo_url -> list of (path, key, renovate_info, current_value, parent)

            for item in updates_to_check:
                path, key, renovate_info, current_value, parent = item
                if renovate_info.get('datasource') == 'helm':
                    repo_url = renovate_info.get('repositoryUrl')
                    if repo_url:
                        if repo_url not in helm_updates_by_repo:
                            helm_updates_by_repo[repo_url] = []
                        helm_updates_by_repo[repo_url].append(item)
                    else:
                        # Fallback to individual fetch if no repo URL (it will use default logic in fetcher)
                        docker_updates.append(item) # Treat as generic individual task
                else:
                    docker_updates.append(item)

            future_to_info = {}
            
            # Use a Rich status spinner that updates for each component
            with console.status("", spinner="dots") as status:
                # Submit Docker/Individual tasks
                for path, key, renovate_info, current_value, parent in docker_updates:
                    future = executor.submit(fetch_latest_version, renovate_info)
                    future_to_info[future] = (path, key, renovate_info, current_value, parent, 'single')
                    status.update(f"Checking {renovate_info['depName']} ({renovate_info['datasource']})…")

                # Submit Batch Helm tasks
                for repo_url, items in helm_updates_by_repo.items():
                    dep_names = [item[2]['depName'] for item in items]
                    future = executor.submit(fetch_latest_helm_versions_batch, repo_url, dep_names)
                    # Store the list of items associated with this future
                    future_to_info[future] = (repo_url, items, 'batch')
                    status.update(f"Checking {len(items)} charts from {repo_url}…")

                # Process results as they complete
                for future in as_completed(future_to_info):
                    info = future_to_info[future]
                    task_type = info[-1]

                    if task_type == 'single':
                        path, key, renovate_info, current_value, parent, _ = info
                        status.update(f"Checking {renovate_info['depName']} ({renovate_info['datasource']})…")
                        try:
                            latest_version, fetch_time = future.result()
                            
                            if renovate_info['datasource'] == 'helm':
                                helm_timing = max(helm_timing, fetch_time)
                            elif renovate_info['datasource'] == 'docker':
                                docker_timing = max(docker_timing, fetch_time)

                            if latest_version and str(current_value) != latest_version:
                                parent[key] = latest_version
                                updates_made.append(f"  {renovate_info['depName']}: {current_value} → {latest_version}")
                        except Exception as e:
                            console.print(f"[yellow]Error fetching version for {renovate_info['depName']}: {e}[/yellow]")
                    
                    elif task_type == 'batch':
                        repo_url, items, _ = info
                        dep_names = [item[2]['depName'] for item in items]
                        status.update(f"Checking {', '.join(dep_names)} (helm)…")
                        try:
                            results = future.result() # dict[dep_name] -> (version, time)
                            
                            # All items in this batch share the same fetch time (roughly)
                            # We can take the max time from the batch results for helm_timing
                            batch_max_time = 0.0

                            for path, key, renovate_info, current_value, parent in items:
                                dep_name = renovate_info['depName']
                                if dep_name in results:
                                    latest_version, fetch_time = results[dep_name]
                                    batch_max_time = max(batch_max_time, fetch_time)
                                    
                                    if latest_version and str(current_value) != latest_version:
                                        parent[key] = latest_version
                                        updates_made.append(f"  {dep_name}: {current_value} → {latest_version}")
                            
                            helm_timing = max(helm_timing, batch_max_time)

                        except Exception as e:
                            console.print(f"[yellow]Error fetching batch versions from {repo_url}: {e}[/yellow]")

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
