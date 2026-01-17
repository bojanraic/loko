"""Tests for config subcommands: validate, port-check, generate, compact."""
import pytest
import os
import yaml
from typer.testing import CliRunner
from loko.cli import app
from loko.cli.commands.config import _compact_config_data


runner = CliRunner()


class TestConfigValidate:
    """Tests for loko config validate command."""

    def test_config_validate_with_valid_config(self, mock_config_path):
        """Test config validate with a valid configuration file."""
        result = runner.invoke(app, ["config", "validate", "--config", mock_config_path])
        assert result.exit_code == 0
        assert "valid" in result.stdout.lower()
        assert "test-cluster" in result.stdout  # Environment name

    def test_config_validate_with_missing_config(self, temp_dir):
        """Test config validate with non-existent config file."""
        missing_path = os.path.join(temp_dir, "nonexistent.yaml")
        result = runner.invoke(app, ["config", "validate", "--config", missing_path])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_config_validate_with_invalid_yaml(self, temp_dir):
        """Test config validate with invalid YAML syntax."""
        invalid_path = os.path.join(temp_dir, "invalid.yaml")
        with open(invalid_path, "w") as f:
            f.write("invalid: yaml: content: [")
        result = runner.invoke(app, ["config", "validate", "--config", invalid_path])
        assert result.exit_code == 1

    def test_config_validate_with_invalid_schema(self, temp_dir):
        """Test config validate with invalid config schema."""
        invalid_path = os.path.join(temp_dir, "invalid_schema.yaml")
        # Missing required fields
        with open(invalid_path, "w") as f:
            yaml.dump({"environment": {"name": "test"}}, f)
        result = runner.invoke(app, ["config", "validate", "--config", invalid_path])
        assert result.exit_code == 1
        assert "invalid" in result.stdout.lower()

    def test_config_validate_shows_environment_info(self, mock_config_path):
        """Test config validate displays environment information."""
        result = runner.invoke(app, ["config", "validate", "--config", mock_config_path])
        assert result.exit_code == 0
        assert "Environment:" in result.stdout
        assert "Kubernetes:" in result.stdout
        assert "Domain:" in result.stdout


class TestConfigPortCheck:
    """Tests for loko config port-check command."""

    def test_config_port_check_with_valid_config(self, mock_config_path):
        """Test config port-check with a valid configuration file."""
        result = runner.invoke(app, ["config", "port-check", "--config", mock_config_path])
        # Exit code depends on whether ports are available
        assert result.exit_code in [0, 1]
        # Should display a table with port information
        assert "Port" in result.stdout
        assert "Status" in result.stdout

    def test_config_port_check_with_missing_config(self, temp_dir):
        """Test config port-check with non-existent config file."""
        missing_path = os.path.join(temp_dir, "nonexistent.yaml")
        result = runner.invoke(app, ["config", "port-check", "--config", missing_path])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_config_port_check_shows_dns_port(self, mock_config_path):
        """Test config port-check shows DNS port."""
        result = runner.invoke(app, ["config", "port-check", "--config", mock_config_path])
        assert "DNS" in result.stdout
        assert "dnsmasq" in result.stdout

    def test_config_port_check_shows_lb_ports(self, mock_config_path):
        """Test config port-check shows load balancer ports."""
        result = runner.invoke(app, ["config", "port-check", "--config", mock_config_path])
        assert "Load Balancer" in result.stdout
        assert "traefik" in result.stdout

    def test_config_port_check_shows_workload_ports(self, temp_dir):
        """Test config port-check shows workload ports when configured."""
        config_path = os.path.join(temp_dir, "config_with_workloads.yaml")
        config_data = {
            "environment": {
                "name": "test-cluster",
                "base-dir": "/tmp/loko",
                "cluster": {
                    "provider": {"name": "kind", "runtime": "docker"},
                    "kubernetes": {"api-port": 6443, "image": "kindest/node", "tag": "v1.27.3"},
                    "nodes": {
                        "servers": 1,
                        "workers": 1,
                        "scheduling": {
                            "control-plane": {"allow-workloads": True, "isolate-internal-components": True},
                            "workers": {"isolate-workloads": False}
                        }
                    }
                },
                "network": {
                    "ip": "127.0.0.1",
                    "domain": "loko.local",
                    "dns-port": 53,
                    "subdomain": {"enabled": False, "value": "apps"},
                    "lb-ports": [80, 443]
                },
                "internal-components": {
                    "traefik": {"version": "37.3.0"},
                    "zot": {"version": "0.1.66"},
                    "dnsmasq": {"version": "2.90"},
                    "metrics-server": {"version": "3.13.0", "enabled": False}
                },
                "registry": {"name": "registry", "storage": {"size": "10Gi"}},
                "workloads": {
                    "system": [
                        {
                            "name": "postgres",
                            "enabled": True,
                            "ports": [5432],
                            "config": {
                                "chart": "groundhog2k/postgres",
                                "version": "1.0.0"
                            }
                        }
                    ],
                    "user": []
                }
            }
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        result = runner.invoke(app, ["config", "port-check", "--config", config_path])
        assert "Workload" in result.stdout
        assert "postgres" in result.stdout
        assert "5432" in result.stdout


class TestConfigGenerate:
    """Tests for loko config generate command."""

    def test_config_generate_creates_file(self, temp_dir):
        """Test config generate creates a config file."""
        output_path = os.path.join(temp_dir, "generated.yaml")
        result = runner.invoke(app, ["config", "generate", "--output", output_path])
        assert result.exit_code == 0
        assert os.path.exists(output_path)
        assert "Generated" in result.stdout

    def test_config_generate_valid_yaml(self, temp_dir):
        """Test config generate creates valid YAML."""
        output_path = os.path.join(temp_dir, "generated.yaml")
        runner.invoke(app, ["config", "generate", "--output", output_path])

        with open(output_path, "r") as f:
            config = yaml.safe_load(f)

        assert "environment" in config
        assert "name" in config["environment"]
        assert "cluster" in config["environment"]
        assert "network" in config["environment"]

    def test_config_generate_refuses_overwrite(self, temp_dir):
        """Test config generate refuses to overwrite without --force."""
        output_path = os.path.join(temp_dir, "existing.yaml")
        # Create existing file
        with open(output_path, "w") as f:
            f.write("existing: content")

        result = runner.invoke(app, ["config", "generate", "--output", output_path], input="n\n")
        assert result.exit_code == 0  # Cancelled gracefully
        # File should still have original content
        with open(output_path, "r") as f:
            assert "existing: content" in f.read()

    def test_config_generate_force_overwrite(self, temp_dir):
        """Test config generate with --force overwrites existing file."""
        output_path = os.path.join(temp_dir, "existing.yaml")
        # Create existing file
        with open(output_path, "w") as f:
            f.write("existing: content")

        result = runner.invoke(app, ["config", "generate", "--output", output_path, "--force"])
        assert result.exit_code == 0

        with open(output_path, "r") as f:
            content = f.read()
        assert "environment" in content  # New content
        assert "existing: content" not in content

    def test_config_generate_detects_local_ip(self, temp_dir):
        """Test config generate auto-detects local IP."""
        output_path = os.path.join(temp_dir, "generated.yaml")
        result = runner.invoke(app, ["config", "generate", "--output", output_path])
        assert result.exit_code == 0
        assert "Detected local IP" in result.stdout


class TestConfigDetectIp:
    """Tests for loko config detect-ip command."""

    def test_config_detect_ip_shows_ip(self):
        """Test config detect-ip displays detected IP."""
        result = runner.invoke(app, ["config", "detect-ip"])
        assert result.exit_code == 0
        assert "Detected local IP:" in result.stdout
        # Should show an IP address pattern
        import re
        assert re.search(r'\d+\.\d+\.\d+\.\d+', result.stdout)

    def test_config_detect_ip_shows_manual_update_note(self):
        """Test config detect-ip shows note about manual update."""
        result = runner.invoke(app, ["config", "detect-ip"])
        assert result.exit_code == 0
        assert "update" in result.stdout.lower()
        assert "config" in result.stdout.lower()


class TestConfigCompact:
    """Tests for loko config compact command."""

    def test_config_compact_removes_disabled_workloads(self, temp_dir):
        """Test config compact removes disabled workloads."""
        config_data = {
            "environment": {
                "name": "test",
                "base-dir": "/tmp/loko",
                "cluster": {
                    "provider": {"name": "kind", "runtime": "docker"},
                    "kubernetes": {"api-port": 6443, "image": "kindest/node", "tag": "v1.27.3"},
                    "nodes": {
                        "servers": 1, "workers": 1,
                        "scheduling": {
                            "control-plane": {"allow-workloads": True, "isolate-internal-components": True},
                            "workers": {"isolate-workloads": False}
                        }
                    }
                },
                "network": {
                    "ip": "127.0.0.1", "domain": "test.local", "dns-port": 53,
                    "subdomain": {"enabled": False, "value": "apps"}, "lb-ports": [80, 443]
                },
                "internal-components": {
                    "traefik": {"version": "38.0.0"},
                    "zot": {"version": "0.1.95"},
                    "dnsmasq": {"version": "2.91"},
                    "metrics-server": {"version": "3.13.0", "enabled": False}
                },
                "registry": {"name": "cr", "storage": {"size": "10Gi"}},
                "workloads": {
                    "helm-repositories": [
                        {"name": "groundhog2k", "url": "https://groundhog2k.github.io/helm-charts/"},
                        {"name": "unused", "url": "https://unused.example.com/"}
                    ],
                    "system": [
                        {"name": "postgres", "enabled": True, "ports": [5432],
                         "config": {"repo": {"ref": "groundhog2k"}, "chart": "groundhog2k/postgres", "version": "1.0.0"}},
                        {"name": "mysql", "enabled": False, "ports": [3306],
                         "config": {"chart": "groundhog2k/mysql", "version": "1.0.0"}}
                    ],
                    "user": [
                        {"name": "myapp", "enabled": False, "config": {"chart": "myrepo/myapp", "version": "1.0.0"}}
                    ]
                }
            }
        }

        input_path = os.path.join(temp_dir, "input.yaml")
        output_path = os.path.join(temp_dir, "output.yaml")
        with open(input_path, "w") as f:
            yaml.dump(config_data, f)

        result = runner.invoke(app, ["config", "compact", "--config", input_path, "-o", output_path])
        assert result.exit_code == 0

        with open(output_path, "r") as f:
            compacted = yaml.safe_load(f)

        # Check disabled workloads are removed
        system_workloads = compacted["environment"]["workloads"]["system"]
        assert len(system_workloads) == 1
        assert system_workloads[0]["name"] == "postgres"

        # Check user workloads are empty
        user_workloads = compacted["environment"]["workloads"]["user"]
        assert len(user_workloads) == 0

    def test_config_compact_removes_unused_helm_repos(self, temp_dir):
        """Test config compact removes unused helm repositories."""
        config_data = {
            "environment": {
                "name": "test",
                "base-dir": "/tmp/loko",
                "cluster": {
                    "provider": {"name": "kind", "runtime": "docker"},
                    "kubernetes": {"api-port": 6443, "image": "kindest/node", "tag": "v1.27.3"},
                    "nodes": {
                        "servers": 1, "workers": 1,
                        "scheduling": {
                            "control-plane": {"allow-workloads": True, "isolate-internal-components": True},
                            "workers": {"isolate-workloads": False}
                        }
                    }
                },
                "network": {
                    "ip": "127.0.0.1", "domain": "test.local", "dns-port": 53,
                    "subdomain": {"enabled": False, "value": "apps"}, "lb-ports": [80, 443]
                },
                "internal-components": {
                    "traefik": {"version": "38.0.0"},
                    "zot": {"version": "0.1.95"},
                    "dnsmasq": {"version": "2.91"},
                    "metrics-server": {"version": "3.13.0", "enabled": False}
                },
                "registry": {"name": "cr", "storage": {"size": "10Gi"}},
                "workloads": {
                    "helm-repositories": [
                        {"name": "groundhog2k", "url": "https://groundhog2k.github.io/helm-charts/"},
                        {"name": "unused", "url": "https://unused.example.com/"}
                    ],
                    "system": [
                        {"name": "postgres", "enabled": True, "ports": [5432],
                         "config": {"repo": {"ref": "groundhog2k"}, "chart": "groundhog2k/postgres", "version": "1.0.0"}}
                    ],
                    "user": []
                }
            }
        }

        input_path = os.path.join(temp_dir, "input.yaml")
        output_path = os.path.join(temp_dir, "output.yaml")
        with open(input_path, "w") as f:
            yaml.dump(config_data, f)

        result = runner.invoke(app, ["config", "compact", "--config", input_path, "-o", output_path])
        assert result.exit_code == 0

        with open(output_path, "r") as f:
            compacted = yaml.safe_load(f)

        # Check unused helm repos are removed
        helm_repos = compacted["environment"]["workloads"]["helm-repositories"]
        assert len(helm_repos) == 1
        assert helm_repos[0]["name"] == "groundhog2k"

    def test_config_compact_removes_disabled_mirroring_sources(self, temp_dir):
        """Test config compact removes disabled mirroring sources."""
        config_data = {
            "environment": {
                "name": "test",
                "base-dir": "/tmp/loko",
                "cluster": {
                    "provider": {"name": "kind", "runtime": "docker"},
                    "kubernetes": {"api-port": 6443, "image": "kindest/node", "tag": "v1.27.3"},
                    "nodes": {
                        "servers": 1, "workers": 1,
                        "scheduling": {
                            "control-plane": {"allow-workloads": True, "isolate-internal-components": True},
                            "workers": {"isolate-workloads": False}
                        }
                    }
                },
                "network": {
                    "ip": "127.0.0.1", "domain": "test.local", "dns-port": 53,
                    "subdomain": {"enabled": False, "value": "apps"}, "lb-ports": [80, 443]
                },
                "internal-components": {
                    "traefik": {"version": "38.0.0"},
                    "zot": {"version": "0.1.95"},
                    "dnsmasq": {"version": "2.91"},
                    "metrics-server": {"version": "3.13.0", "enabled": False}
                },
                "registry": {
                    "name": "cr",
                    "storage": {"size": "10Gi"},
                    "mirroring": {
                        "enabled": True,
                        "sources": [
                            {"name": "docker_hub", "enabled": True},
                            {"name": "quay", "enabled": False},
                            {"name": "ghcr", "enabled": True}
                        ]
                    }
                },
                "workloads": {"system": [], "user": []}
            }
        }

        input_path = os.path.join(temp_dir, "input.yaml")
        output_path = os.path.join(temp_dir, "output.yaml")
        with open(input_path, "w") as f:
            yaml.dump(config_data, f)

        result = runner.invoke(app, ["config", "compact", "--config", input_path, "-o", output_path])
        assert result.exit_code == 0

        with open(output_path, "r") as f:
            compacted = yaml.safe_load(f)

        # Check disabled sources are removed and enabled field is stripped
        sources = compacted["environment"]["registry"]["mirroring"]["sources"]
        assert len(sources) == 2
        assert sources[0] == {"name": "docker_hub"}
        assert sources[1] == {"name": "ghcr"}

    def test_config_compact_removes_node_labels(self, temp_dir):
        """Test config compact removes node labels."""
        config_data = {
            "environment": {
                "name": "test",
                "base-dir": "/tmp/loko",
                "cluster": {
                    "provider": {"name": "kind", "runtime": "docker"},
                    "kubernetes": {"api-port": 6443, "image": "kindest/node", "tag": "v1.27.3"},
                    "nodes": {
                        "servers": 1, "workers": 1,
                        "scheduling": {
                            "control-plane": {"allow-workloads": True, "isolate-internal-components": True},
                            "workers": {"isolate-workloads": False}
                        },
                        "labels": {
                            "control-plane": {"tier": "control"},
                            "worker": {"tier": "compute"}
                        }
                    }
                },
                "network": {
                    "ip": "127.0.0.1", "domain": "test.local", "dns-port": 53,
                    "subdomain": {"enabled": False, "value": "apps"}, "lb-ports": [80, 443]
                },
                "internal-components": {
                    "traefik": {"version": "38.0.0"},
                    "zot": {"version": "0.1.95"},
                    "dnsmasq": {"version": "2.91"},
                    "metrics-server": {"version": "3.13.0", "enabled": False}
                },
                "registry": {"name": "cr", "storage": {"size": "10Gi"}},
                "workloads": {"system": [], "user": []}
            }
        }

        input_path = os.path.join(temp_dir, "input.yaml")
        output_path = os.path.join(temp_dir, "output.yaml")
        with open(input_path, "w") as f:
            yaml.dump(config_data, f)

        result = runner.invoke(app, ["config", "compact", "--config", input_path, "-o", output_path])
        assert result.exit_code == 0

        with open(output_path, "r") as f:
            compacted = yaml.safe_load(f)

        # Check labels are removed
        assert "labels" not in compacted["environment"]["cluster"]["nodes"]

    def test_config_compact_overwrites_in_place(self, temp_dir):
        """Test config compact overwrites input file when no output specified."""
        config_data = {
            "environment": {
                "name": "test",
                "base-dir": "/tmp/loko",
                "cluster": {
                    "provider": {"name": "kind", "runtime": "docker"},
                    "kubernetes": {"api-port": 6443, "image": "kindest/node", "tag": "v1.27.3"},
                    "nodes": {
                        "servers": 1, "workers": 1,
                        "scheduling": {
                            "control-plane": {"allow-workloads": True, "isolate-internal-components": True},
                            "workers": {"isolate-workloads": False}
                        }
                    }
                },
                "network": {
                    "ip": "127.0.0.1", "domain": "test.local", "dns-port": 53,
                    "subdomain": {"enabled": False, "value": "apps"}, "lb-ports": [80, 443]
                },
                "internal-components": {
                    "traefik": {"version": "38.0.0"},
                    "zot": {"version": "0.1.95"},
                    "dnsmasq": {"version": "2.91"},
                    "metrics-server": {"version": "3.13.0", "enabled": False}
                },
                "registry": {"name": "cr", "storage": {"size": "10Gi"}},
                "workloads": {
                    "system": [
                        {"name": "disabled", "enabled": False, "config": {"chart": "test/test", "version": "1.0.0"}}
                    ],
                    "user": []
                }
            }
        }

        input_path = os.path.join(temp_dir, "input.yaml")
        with open(input_path, "w") as f:
            yaml.dump(config_data, f)

        result = runner.invoke(app, ["config", "compact", "--config", input_path])
        assert result.exit_code == 0
        assert "compacted" in result.stdout.lower()

        with open(input_path, "r") as f:
            compacted = yaml.safe_load(f)

        # Check disabled workload is removed
        assert len(compacted["environment"]["workloads"]["system"]) == 0

    def test_config_compact_with_missing_config(self, temp_dir):
        """Test config compact with non-existent config file."""
        missing_path = os.path.join(temp_dir, "nonexistent.yaml")
        result = runner.invoke(app, ["config", "compact", "--config", missing_path])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()


class TestCompactConfigData:
    """Tests for the _compact_config_data helper function."""

    def test_compact_preserves_enabled_workloads(self):
        """Test _compact_config_data preserves enabled workloads."""
        data = {
            "environment": {
                "workloads": {
                    "system": [
                        {"name": "enabled1", "enabled": True, "config": {"chart": "test", "version": "1.0"}},
                        {"name": "disabled1", "enabled": False, "config": {"chart": "test", "version": "1.0"}},
                        {"name": "enabled2", "enabled": True, "config": {"chart": "test", "version": "1.0"}}
                    ],
                    "user": []
                }
            }
        }
        result = _compact_config_data(data)
        system = result["environment"]["workloads"]["system"]
        assert len(system) == 2
        assert all(w["enabled"] for w in system)

    def test_compact_handles_empty_workloads(self):
        """Test _compact_config_data handles empty workloads lists."""
        data = {
            "environment": {
                "workloads": {
                    "system": [],
                    "user": []
                }
            }
        }
        result = _compact_config_data(data)
        assert result["environment"]["workloads"]["system"] == []
        assert result["environment"]["workloads"]["user"] == []

    def test_compact_handles_missing_sections(self):
        """Test _compact_config_data handles missing optional sections."""
        data = {"environment": {}}
        result = _compact_config_data(data)
        assert result == {"environment": {}}
